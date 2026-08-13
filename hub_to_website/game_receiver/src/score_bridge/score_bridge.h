/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/**
 * @defgroup score_bridge Highscore UART bridge to the nRF9151
 * @{
 * @ingroup game_receiver
 *
 * @brief Forwards a finished game's highscore out a dedicated UART to the
 *        hub's nRF9151, which publishes it over MQTT.
 *
 * The BLE central (@ref ble_central) recognizes a "SCORE:<game>:<points>"
 * notification from the game console and calls score_bridge_send(). This
 * module owns uart30 (separate from the console UART) and emits one
 * newline-terminated line the nRF9151 turns into an MQTT publish:
 *
 *     <game>|{"session_id":"<game>-<seq>","score":<points>}\n
 *
 * The nRF9151 splits on the first '|': the left side becomes the topic
 * (games/<game>/score) and the right side is the JSON payload the backend
 * (camera_to_website/backend/mqtt_listener.py) already expects.
 */
#ifndef __SCORE_BRIDGE_H__
#define __SCORE_BRIDGE_H__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * @brief Initialize the dedicated UART link to the nRF9151.
 *
 * @return 0 on success, negative errno on failure.
 */
int score_bridge_init(void);

/**
 * @brief Forward a highscore to the nRF9151 for MQTT publishing.
 *
 * @param game   Game name, e.g. "snake" or "minesweeper". Used as the MQTT
 *               topic segment (games/<game>/score).
 * @param points The score value.
 */
void score_bridge_send(const char *game, uint32_t points);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __SCORE_BRIDGE_H__ */

/**
 * @}
 */
