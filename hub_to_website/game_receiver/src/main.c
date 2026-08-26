/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 *
 * @brief Game receiver entry point.
 *
 * Bridges the game_controller's BLE commands onto this board's game-control
 * link (VCOM1, uart30): connects as a NUS central and relays every received
 * token as a "Command: <token>" line, keeping the console (VCOM0) for debug
 * logging.
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "ble/ble_central.h"
#include "led_status/led_status.h"
#include "score_bridge/score_bridge.h"
#include "test_button/test_button.h"

LOG_MODULE_REGISTER(main);

int main(void)
{
	int err;

	/* Before the BLE central, so the LED is already blinking by the time
	 * scanning starts and the board never looks dead at boot.
	 *
	 * A failure here is not fatal: relaying commands is this board's job, and
	 * losing the indicator is no reason to stop doing it. led_status_*() calls
	 * from the BLE callbacks become no-ops.
	 */
	err = led_status_init();
	if (err) {
		LOG_WRN("Status LED init failed (err %d); continuing without LEDs", err);
	}

	err = score_bridge_init();
	if (err) {
		LOG_ERR("Score bridge init failed (err %d)", err);
		return err;
	}



	/* TEMPORARY: sw0 sends a test score until the game console can. */
	err = test_button_init();
	if (err) {
		LOG_ERR("Test button init failed (err %d)", err);
		return err;
	}

	err = ble_central_init();
	if (err) {
		LOG_ERR("BLE central init failed (err %d)", err);
		return err;
	}

	return 0;
}
