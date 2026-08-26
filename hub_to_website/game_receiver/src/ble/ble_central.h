/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/**
 * @defgroup ble_central Bluetooth NUS central interface
 * @{
 * @ingroup game_receiver
 *
 * @brief Connects to the game_controller peripheral and relays its Nordic UART
 *        Service (NUS) notifications onto the game-control link (VCOM1, uart30).
 *
 * Scans for the peripheral by advertised name -- "Game Controller" -- connects,
 * discovers its NUS instance and subscribes to notifications.
 *
 * Each received token (e.g. "UP\r\n") is forwarded as a "Command: <token>" line
 * on VCOM1, where a PC-side script picks it up. Debug logging stays on the
 * console (VCOM0).
 */
#ifndef __BLE_CENTRAL_H__
#define __BLE_CENTRAL_H__

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * @brief Initialize the BLE stack, the NUS client and start scanning for a
 *        game_controller peripheral.
 *
 * @return 0 on success, negative errno on failure.
 */
int ble_central_init(void);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __BLE_CENTRAL_H__ */

/**
 * @}
 */
