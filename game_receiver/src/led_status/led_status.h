/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

/**
 * @defgroup led_status Peer status LEDs
 * @{
 * @ingroup game_receiver
 *
 * @brief One LED per peripheral the receiver expects, showing whether its link
 *        is up.
 *
 * Slow blink means "not connected, still being scanned for"; solid on means
 * connected. The mapping is positional and matches the peer table in
 * ble_central.c:
 *
 *   led0  peer 0  "Game Controller"
 *   led1  peer 1  "Axon_Sensor"
 *
 * So at boot both blink, one goes solid as its board is found, and once both are
 * solid the receiver has stopped scanning. A board dropping out puts its LED
 * back to blinking without touching the other.
 */
#ifndef __LED_STATUS_H__
#define __LED_STATUS_H__

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/** Number of peers with a status LED. Must match the peer table's size. */
#define LED_STATUS_COUNT 2

/**
 * @brief Configure the status LEDs and start the "searching" blink.
 *
 * @return 0 on success, negative errno if an LED is unavailable.
 */
int led_status_init(void);

/**
 * @brief Report a peer's link state.
 *
 * @param idx       Peer index, matching the peer table (< @ref LED_STATUS_COUNT).
 * @param connected true for solid on, false to go back to blinking.
 */
void led_status_set_connected(size_t idx, bool connected);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __LED_STATUS_H__ */

/**
 * @}
 */
