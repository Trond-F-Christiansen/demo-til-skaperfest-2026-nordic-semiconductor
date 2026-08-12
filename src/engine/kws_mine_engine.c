/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 *
 * @brief Minesweeper KWS inference engine: keyword spotting over the DMIC.
 */

#include <errno.h>
#include <stddef.h>

#include <zephyr/audio/dmic.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>

#include "ble/ble_nus.h"
#include "engine.h"
#include "kws/dmic.h"
#include "kws/kws_mine.h"

LOG_MODULE_REGISTER(kws_mine_engine);

#define DMIC_READ_TIMEOUT 100

static const struct device *const dmic_dev = DEVICE_DT_GET(DT_NODELABEL(dmic_dev));

static int kws_mine_engine_init(void)
{
	int err = kws_mine_init();

	if (err) {
		LOG_ERR("Minesweeper KWS init failed (err %d)", err);
		return err;
	}
	return 0;
}

static int kws_mine_engine_enter(void)
{
	int err = dmic_init();

	if (err) {
		LOG_ERR("DMIC configure failed (err %d)", err);
		return err;
	}

	kws_mine_reset();

	err = dmic_trigger(dmic_dev, DMIC_TRIGGER_START);
	if (err < 0) {
		LOG_ERR("Failed to start DMIC (err %d)", err);
		return err;
	}

	return 0;
}

/* Bound on how long to wait for the asynchronous stop to complete. */
#define DMIC_STOP_SETTLE_MS 100
#define DMIC_STOP_POLL_MS   5

static void kws_mine_engine_exit(void)
{
	int err = dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP);

	if (err < 0) {
		LOG_ERR("Failed to stop DMIC (err %d)", err);
	}

	void *buffer;
	size_t size;

	for (int waited = 0; waited <= DMIC_STOP_SETTLE_MS; waited += DMIC_STOP_POLL_MS) {
		while (dmic_read(dmic_dev, 0, &buffer, &size, 0) == 0) {
			free_dmic_buffer(buffer);
		}

		err = dmic_deinit();
		if (err != -EBUSY) {
			break;
		}

		k_msleep(DMIC_STOP_POLL_MS);
	}

	if (err) {
		LOG_ERR("Failed to deinit DMIC (err %d)", err);
	}
}

static void kws_mine_engine_run(atomic_t *stop)
{
	void *audio_buffer;
	size_t audio_buffer_size;
	struct kws_mine_prediction prediction;
	int err;

	while (!atomic_get(stop)) {
		err = dmic_read(dmic_dev, 0, &audio_buffer, &audio_buffer_size,
				DMIC_READ_TIMEOUT);
		if (err < 0) {
			LOG_ERR("Failed to read from DMIC (err %d)", err);
			return;
		}

		/* kws_mine_process takes ownership of audio_buffer and frees it. */
		err = kws_mine_process(audio_buffer, DMIC_SAMPLES_IN_BLOCK, &prediction);
		if (err == -EBUSY) {
			continue;
		} else if (err) {
			LOG_ERR("Minesweeper keyword spotting failed (err %d)", err);
			return;
		}

		if (prediction.valid && prediction.token != NULL) {
			printk("Keyword spotted: %s", prediction.token);
			(void)ble_nus_send_raw(prediction.token);
		}
	}
}

const engine_t kws_mine_engine = {
	.name = ENGINE_NAME_KWS_MINE,
	.init = kws_mine_engine_init,
	.enter = kws_mine_engine_enter,
	.exit = kws_mine_engine_exit,
	.run = kws_mine_engine_run,
};