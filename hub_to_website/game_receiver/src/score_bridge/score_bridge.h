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
 *        hub's nRF9151, which uploads it to the HTTPS API.
 *
 * The BLE central (@ref ble_central) recognizes a "SCORE:<game>:<points>"
 * notification from the game console and calls score_bridge_send(). This
 * module owns uart21 (the dedicated link to the nRF9151, separate from the
 * console) and emits one newline-terminated line the nRF9151 turns into an
 * HTTPS request:
 *
 *     <game>|{"score":<points>}\n
 *
 * The nRF9151 splits on the first '|': the left side becomes the game segment
 * in `/api/scores/<game>` and the right side becomes the JSON request body.
 *
 * The module also owns uart30 (VCOM1), the game-control link to the PC: it
 * reads score lines from it and, via score_bridge_write_game(), emits the
 * relayed controller commands on it.
 */
#ifndef __SCORE_BRIDGE_H__
#define __SCORE_BRIDGE_H__

#include <stddef.h>
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
 * @brief Forward a highscore to the nRF9151 for HTTPS upload.
 *
 * @param game   Game name, e.g. "snake_voice" or "minesweeper". Used in the
 *               `/api/scores/<game>` path.
 * @param points The score value.
 */
void score_bridge_send(const char *game, uint32_t points);

/**
 * @brief Write raw bytes to the game-control link (VCOM1, uart30).
 *
 * Used by the BLE central to emit relayed controller commands to the PC on
 * VCOM1, keeping the console (VCOM0) reserved for debug logging.
 *
 * @param buf Bytes to write.
 * @param len Number of bytes.
 */
void score_bridge_write_game(const char *buf, size_t len);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __SCORE_BRIDGE_H__ */

/**
 * @}
 */
