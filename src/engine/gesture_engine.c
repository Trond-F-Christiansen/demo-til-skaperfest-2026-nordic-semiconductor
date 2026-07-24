/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 *
 * @brief Gesture inference engine: gesture recognition over the IMU.
 *
 * The IMU is brought up once in init() and left sampling for the lifetime of
 * the application; in other engines its data-ready signals are simply ignored.
 */

#include <errno.h>
#include <math.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>

#include "ble/ble_nus.h"
#include "engine.h"
#include "gesture/gesture.h"
#include "gesture/imu/imu.h"

LOG_MODULE_REGISTER(gesture_engine);

/* IMU sample rate; the imu module fires its data-ready callback at this rate. */
#define IMU_DATA_RATE_HZ 100

/* Re-check the stop flag at least this often while waiting for IMU data. */
#define IMU_SEM_TIMEOUT_MS 100

/*
 * Motion gating: the Axon runtime's input window is a continuous
 * hop-based sliding buffer (window_size/window_hop) with no public reset --
 * only nrf_dsp_window_sliding_init() (called once at model init) and
 * nrf_dsp_window_sliding_feed() are exposed. Pausing feed and resuming at
 * the next onset does NOT give a fresh window: the buffer still holds the
 * tail of whatever was fed last (e.g. the previous gesture), so the next
 * completed window is a mix of stale + new samples. (Confirmed on-device:
 * every capture after the first fired after exactly one hop period instead
 * of a full window, and was misclassified as IDLE almost every time.)
 *
 * So: feed every sample continuously, same as before, keeping the window
 * always naturally fresh. Motion gating instead decides which resulting
 * prediction to act on -- discard everything while idle or cooling down,
 * accept only the first prediction that completes while armed. That still
 * gives one clean, motion-aligned prediction per gesture instead of a flood
 * of overlapping ones; it just doesn't save the inference cycles idle would
 * otherwise skip, since the runtime doesn't support "emptying" the window.
 *
 * Onset/offset detection reuses the same signal as the offline labeling
 * tool (burst_detection.py): smoothed gyro-magnitude energy above an
 * adaptively tracked idle baseline, self-calibrating to the live sensor's
 * idle noise floor. MOTION_ONSET_K/MOTION_OFFSET_K are the knobs to retune
 * on real hardware if onset detection is too eager or too sluggish.
 */
#define MOTION_BASELINE_ALPHA   0.02f /* idle baseline/deviation EMA weight per sample */
#define MOTION_ONSET_K          4.0f  /* onset when magnitude > baseline + K * deviation */
#define MOTION_OFFSET_K         1.5f  /* offset when magnitude < baseline + K * deviation */
#define MOTION_ONSET_CONFIRM_N  3     /* consecutive above-threshold samples to confirm onset */
#define MOTION_OFFSET_CONFIRM_N 10    /* consecutive below-threshold samples to confirm offset */

enum motion_state {
	MOTION_STATE_IDLE,     /* watching for onset; completed windows are discarded */
	MOTION_STATE_ARMED,    /* onset confirmed; the next completed window is accepted */
	MOTION_STATE_COOLDOWN, /* prediction accepted; watching for offset before re-arming */
};

static struct {
	enum motion_state state;
	float baseline;
	float deviation;
	bool baseline_init;
	int confirm_count;
} motion = {
	.state = MOTION_STATE_IDLE,
};

static void motion_engine_reset(void)
{
	motion.state = MOTION_STATE_IDLE;
	motion.baseline_init = false;
	motion.confirm_count = 0;
}

static float gyro_magnitude(const imu_data_t *imu_data)
{
	const float gx = imu_data->gyro[0].phys;
	const float gy = imu_data->gyro[1].phys;
	const float gz = imu_data->gyro[2].phys;

	return sqrtf(gx * gx + gy * gy + gz * gz);
}

/* Updates onset/offset tracking from the latest sample. Does not gate
 * feeding -- see the block comment above. */
static void motion_track(float magnitude)
{
	switch (motion.state) {
	case MOTION_STATE_IDLE:
		if (!motion.baseline_init) {
			motion.baseline = magnitude;
			motion.deviation = 0.0f;
			motion.baseline_init = true;
		} else {
			motion.baseline += MOTION_BASELINE_ALPHA * (magnitude - motion.baseline);
			motion.deviation += MOTION_BASELINE_ALPHA *
					     (fabsf(magnitude - motion.baseline) - motion.deviation);
		}

		const float onset_threshold = motion.baseline + MOTION_ONSET_K * motion.deviation;

		if (magnitude <= onset_threshold) {
			motion.confirm_count = 0;
			return;
		}

		if (++motion.confirm_count < MOTION_ONSET_CONFIRM_N) {
			return;
		}

		LOG_DBG("Motion onset (mag %.1f, baseline %.1f)", (double)magnitude,
			(double)motion.baseline);
		motion.confirm_count = 0;
		motion.state = MOTION_STATE_ARMED;
		return;

	case MOTION_STATE_ARMED:
		/* Nothing to track; waiting for the next completed window. */
		return;

	case MOTION_STATE_COOLDOWN: {
		const float offset_threshold = motion.baseline + MOTION_OFFSET_K * motion.deviation;

		if (magnitude >= offset_threshold) {
			motion.confirm_count = 0;
			return;
		}

		if (++motion.confirm_count < MOTION_OFFSET_CONFIRM_N) {
			return;
		}

		LOG_DBG("Motion settled, re-armed");
		motion.confirm_count = 0;
		motion.state = MOTION_STATE_IDLE;
		return;
	}
	}
}

/* Signalled from the imu module's data-ready callback (timer context). */
K_SEM_DEFINE(imu_data_ready_sem, 0, 1);

/* IMU configuration the gesture model was trained with. */
static const imu_config_t imu_cfg = {
	.accel_fs_g = IMU_ACCEL_SCALE_4G,
	.gyro_fs_dps = IMU_GYRO_SCALE_1000DPS,
	.data_rate_hz = IMU_DATA_RATE_HZ,
};

/* Runs in timer context: only signal, never touch the SPI bus from here. */
static void on_imu_data_ready(void)
{
	k_sem_give(&imu_data_ready_sem);
}

static int gesture_engine_init(void)
{
	int err = gesture_init();

	if (err) {
		LOG_ERR("Gesture init failed (err %d)", err);
		return err;
	}

	status_t status = imu_init(&imu_cfg, on_imu_data_ready);

	if (status != STATUS_SUCCESS) {
		LOG_ERR("IMU init failed (status %d)", status);
		return -EIO;
	}

	return 0;
}

static int gesture_engine_enter(void)
{
	gesture_reset();
	motion_engine_reset();
	/* Drop stale data-ready signals so the input window refills cleanly. */
	k_sem_reset(&imu_data_ready_sem);
	return 0;
}

static void gesture_engine_exit(void)
{
	/* IMU is left running; nothing to tear down. */
}

static void gesture_engine_run(atomic_t *stop)
{
	imu_data_t imu_data;
	struct gesture_prediction prediction;
	int err;

	while (!atomic_get(stop)) {
		if (k_sem_take(&imu_data_ready_sem, K_MSEC(IMU_SEM_TIMEOUT_MS)) != 0) {
			/* Timeout: loop to re-check the stop flag. */
			continue;
		}

		if (imu_read(&imu_data) != STATUS_SUCCESS) {
			LOG_ERR("IMU read failed");
			continue;
		}

		motion_track(gyro_magnitude(&imu_data));

		const float features[GESTURE_NUM_FEATURES] = {
			imu_data.accel[0].phys * 1000.0f,
			imu_data.accel[1].phys * 1000.0f,
			imu_data.accel[2].phys * 1000.0f,
			imu_data.gyro[0].phys * 1000.0f,
			imu_data.gyro[1].phys * 1000.0f,
			imu_data.gyro[2].phys * 1000.0f,
		};

		err = gesture_process(features, GESTURE_NUM_FEATURES, &prediction);
		if (err == -EBUSY) {
			/* Input window not full yet; keep feeding. */
			continue;
		}

		/* Only the first window that completes while armed gets
		 * acted on; everything else (idle, or still cooling down) is
		 * discarded even though the model still runs on it. */
		const bool accept = (motion.state == MOTION_STATE_ARMED);

		if (accept) {
			motion.state = MOTION_STATE_COOLDOWN;
		}

		if (err) {
			LOG_ERR("Gesture inference failed (err %d)", err);
			continue;
		}

		if (accept && prediction.valid) {
			LOG_INF("Gesture: %s (class %u, prob %.2f)", prediction.name,
				prediction.target, (double)prediction.probability);

			if (prediction.command != GAME_CMD_NONE) {
				(void)ble_nus_send_command(prediction.command);
			}
		}
	}
}

const engine_t gesture_engine = {
	.name = "Gesture",
	.init = gesture_engine_init,
	.enter = gesture_engine_enter,
	.exit = gesture_engine_exit,
	.run = gesture_engine_run,
};
