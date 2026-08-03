/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef __KWS_MINE_H__
#define __KWS_MINE_H__

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/** @brief Prediction from the Minesweeper keyword spotting model. */
struct kws_mine_prediction {
	/** Prediction valid flag. */
	bool valid;
	/** Predicted class index. */
	uint16_t class;
	/** Uppercase token to send over BLE (ends in "\r\n"), or NULL. */
	const char *token;
	/** Average probability of multiple predictions. */
	float avg_probability;
};

/** @brief Initialize the Minesweeper KWS model. @return 0 on success. */
int kws_mine_init(void);

/** @brief Process one audio block. Takes ownership of @p audio_buffer.
 *  @retval 0 success  @retval -EBUSY needs more data  @retval -EPERM error.
 */
int kws_mine_process(uint8_t *const audio_buffer, const uint16_t num_samples,
		     struct kws_mine_prediction *const prediction);

/** @brief Reset model state. */
void kws_mine_reset(void);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __KWS_MINE_H__ */