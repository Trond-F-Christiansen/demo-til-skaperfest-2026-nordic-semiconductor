/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <stddef.h>
#include <stdint.h>

#include <zephyr/logging/log.h>
#include <nrf_edgeai/nrf_edgeai.h>
#include <nrf_edgeai/rt/nrf_edgeai_runtime_aux.h>

#include "dmic.h"
#include "kws_mine.h"
#include "Minesweeper_94292_kws_generated/nrf_edgeai_user_model.h"

LOG_MODULE_REGISTER(kws_mine);

/* Equal to 150 ms of audio. */
#define SKIP_DETECTIONS_COUNT 5

/* Class order MUST match the model output index order documented in
 * Minesweeper_94292_kws_generated/nrf_edgeai_user_model_labels.h:
 * OTHER, SILENCE, five, flag, four, no, one, open, reset, seven, six,
 * three, two, zero
 */
enum mine_class {
	MINE_OTHER,
	MINE_SILENCE,
	MINE_FIVE,
	MINE_FLAG,
	MINE_FOUR,
	MINE_NO,
	MINE_ONE,
	MINE_OPEN,
	MINE_RESET,
	MINE_SEVEN,
	MINE_SIX,
	MINE_THREE,
	MINE_TWO,
	MINE_ZERO,
	MINE_COUNT
};

struct mine_detection_ctx {
	const char *name;    /* for logging */
	const char *token;   /* uppercase token sent over BLE, or NULL */
	const float threshold;
	const uint8_t num_in_row;
};

/* OTHER/SILENCE have no token and are treated as "quiet" (reset the counter).
 * The rest map to the uppercase tokens the Minesweeper Python expects.
 */
static const struct mine_detection_ctx mine_ctxs[] = {
	[MINE_OTHER]   = {.name = "OTHER",   .token = NULL,        .threshold = 0.99f, .num_in_row = 22},
	[MINE_SILENCE] = {.name = "SILENCE", .token = NULL,        .threshold = 0.99f, .num_in_row = 22},
	[MINE_FIVE]    = {.name = "five",    .token = "FIVE\r\n",  .threshold = 0.3f,  .num_in_row = 5},
	[MINE_FLAG]    = {.name = "flag",    .token = "FLAG\r\n",  .threshold = 0.3f,  .num_in_row = 5},
	[MINE_FOUR]    = {.name = "four",    .token = "FOUR\r\n",  .threshold = 0.3f,  .num_in_row = 5},
	[MINE_NO]      = {.name = "no",      .token = "NO\r\n",    .threshold = 0.3f,  .num_in_row = 5},
	[MINE_ONE]     = {.name = "one",     .token = "ONE\r\n",   .threshold = 0.3f,  .num_in_row = 5},
	[MINE_OPEN]    = {.name = "open",    .token = "OPEN\r\n",  .threshold = 0.2f,  .num_in_row = 4},
	[MINE_RESET]   = {.name = "reset",   .token = "RESET\r\n", .threshold = 0.3f,  .num_in_row = 5},
	[MINE_SEVEN]   = {.name = "seven",   .token = "SEVEN\r\n", .threshold = 0.3f,  .num_in_row = 5},
	[MINE_SIX]     = {.name = "six",     .token = "SIX\r\n",   .threshold = 0.3f,  .num_in_row = 5},
	[MINE_THREE]   = {.name = "three",   .token = "THREE\r\n", .threshold = 0.2f,  .num_in_row = 4},
	[MINE_TWO]     = {.name = "two",     .token = "TWO\r\n",   .threshold = 0.3f,  .num_in_row = 5},
	[MINE_ZERO]    = {.name = "zero",    .token = "ZERO\r\n",  .threshold = 0.3f,  .num_in_row = 5},
};

BUILD_ASSERT(MINE_COUNT == ARRAY_SIZE(mine_ctxs),
	     "Mismatch between mine_class and mine_ctxs size");

static nrf_edgeai_t *mine_model;

int kws_mine_init(void)
{
	mine_model = nrf_edgeai_user_model_94292();
	__ASSERT_NO_MSG(mine_model);
	__ASSERT_NO_MSG(nrf_edgeai_model_outputs_num(mine_model) == MINE_COUNT);
	__ASSERT_NO_MSG(nrf_edgeai_input_window_size(mine_model) == DMIC_SAMPLES_IN_BLOCK);

	nrf_edgeai_err_t err = nrf_edgeai_init(mine_model);

	if (err) {
		LOG_ERR("Minesweeper model init failed (err %d)", err);
		return -ENOENT;
	}

	return 0;
}

static void kws_mine_postprocess(struct kws_mine_prediction *const prediction)
{
	prediction->valid = false;
	prediction->token = NULL;

	const float alpha = CONFIG_KWS_EMA_ALPHA / 1000.0f;
	static enum mine_class last_class;
	static int count;
	static bool armed = true;
	static float probability_ema;

	const uint16_t predicted_class = mine_model->decoded_output.classif.predicted_class;

	__ASSERT_NO_MSG(predicted_class < MINE_COUNT);

	const flt32_t class_probability =
		mine_model->decoded_output.classif.probabilities.p_f32[predicted_class];
	const struct mine_detection_ctx *class_ctx = &mine_ctxs[predicted_class];

	if (predicted_class == MINE_OTHER || predicted_class == MINE_SILENCE) {
		LOG_DBG("class: %s, prob: %f", class_ctx->name, (double)class_probability);
		count = 0;
		probability_ema = 0.0f;
		armed = true;
		return;
	}

	if (predicted_class != last_class) {
		last_class = predicted_class;
		count = 0;
		probability_ema = 0.0f;
		armed = true;
	}

	count++;
	probability_ema = alpha * class_probability + (1 - alpha) * probability_ema;

	LOG_DBG("class: %s, count %d, prob: %f, ema %f", class_ctx->name, count,
		(double)class_probability, (double)probability_ema);

	if (armed && count >= class_ctx->num_in_row && probability_ema >= class_ctx->threshold) {
		prediction->valid = true;
		prediction->class = predicted_class;
		prediction->avg_probability = probability_ema;
		prediction->token = class_ctx->token;

		armed = false;
		count = -SKIP_DETECTIONS_COUNT;
		probability_ema = 0.0f;
	}
}

int kws_mine_process(uint8_t *const audio_buffer, const uint16_t num_samples,
		     struct kws_mine_prediction *const prediction)
{
	__ASSERT_NO_MSG(audio_buffer);
	__ASSERT_NO_MSG(num_samples == nrf_edgeai_input_window_size(mine_model));
	__ASSERT_NO_MSG(prediction);

	nrf_edgeai_err_t err;

	err = nrf_edgeai_feed_inputs(mine_model, audio_buffer, num_samples);
	free_dmic_buffer(audio_buffer);

	if (err == NRF_EDGEAI_ERR_INPROGRESS) {
		return -EBUSY;
	} else if (err) {
		LOG_ERR("Failed to feed inputs (err %d)", err);
		return -EPERM;
	}

	err = nrf_edgeai_run_inference(mine_model);
	if (err == NRF_EDGEAI_ERR_INPROGRESS) {
		return -EBUSY;
	} else if (err) {
		LOG_ERR("Failed to run inference (err %d)", err);
		return -EPERM;
	}

	kws_mine_postprocess(prediction);

	return 0;
}

void kws_mine_reset(void)
{
	nrf_edgeai_model_axon_init_persistent_vars(mine_model);
}