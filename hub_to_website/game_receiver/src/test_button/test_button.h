/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/**
 * @defgroup test_button Temporary test-score button
 * @{
 * @ingroup game_receiver
 *
 * @brief TEMPORARY bring-up helper: sends a fake highscore through the real
 *        uart21 -> nRF9151 path when button sw0 is pressed.
 *
 * This lets the full hub -> nRF9151 -> MQTT -> website chain be tested before
 * the game console can send real "SCORE:..." notifications over BLE. Remove
 * this module (and its call in main.c) once real scores arrive over BLE.
 */
#ifndef __TEST_BUTTON_H__
#define __TEST_BUTTON_H__

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * @brief Configure sw0 to send a test score on press.
 *
 * @return 0 on success, negative errno on failure.
 */
int test_button_init(void);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __TEST_BUTTON_H__ */

/**
 * @}
 */
