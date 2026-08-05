/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 *
 * @brief Game controller entry point.
 *
 * Brings up the inference engines and the buttons, then hands control to the
 * engine controller. Each engine owns its own model and acquisition path; one
 * runs at a time.
 *
 * A short click picks a game *and* the engine that will drive it, and tells the
 * host which game to open (relayed to the host's menu as a MENU: token):
 *
 *   btn0  Snake, driven by voice           KWS       -> MENU:SNAKE
 *   btn1  Snake, driven by swipe gestures  Gesture   -> MENU:SNAKE
 *   btn2  Minesweeper, driven by voice     KWS_MINE  -> MENU:MINESWEEPER
 *
 * Snake deliberately sits on two buttons: the host does not care which engine
 * feeds it, since both emit the same UP/DOWN/LEFT/RIGHT commands, so picking
 * the engine is entirely this side's business.
 *
 * A long click on any button sends MENU:BACK, which the host reads as "leave
 * this screen" (Main Menu on the game-over screen). The active engine is left
 * alone, since the next game choice sets it anyway.
 *
 * The quiz is played with the finger_digits controller, not this application,
 * so no button here selects it -- the host menu still accepts MENU:QUIZ from
 * that board.
 */

#include <zephyr/logging/log.h>

#include "ble/ble_nus.h"
#include "hw_modules/button.h"
#include "engine/engine.h"
#include "engine/engine_controller.h"

LOG_MODULE_REGISTER(main);

/**
 * @brief Switch to @p engine_name, then ask the host to open @p menu_token.
 *
 * Nothing is sent if the engine is unavailable (e.g. the gesture engine on a
 * board with no IMU wired up), so the host never opens a game that has no
 * working input source; the currently active engine keeps running.
 */
static void start_game(const char *engine_name, const char *menu_token)
{
	int err = engine_request_select(engine_name);

	if (err) {
		LOG_WRN("Cannot start game on engine '%s' (err %d)", engine_name, err);
		return;
	}

	(void)ble_nus_send_raw(menu_token);
}

static void on_button_click(uint8_t button_id, button_click_t click)
{
	if (click == BUTTON_CLICK_LONG) {
		/* Back out of the host's current screen; engine unchanged. */
		(void)ble_nus_send_raw("MENU:BACK\r\n");
		return;
	}

	switch (button_id) {
	case 0:
		start_game(ENGINE_NAME_KWS, "MENU:SNAKE\r\n");
		break;
	case 1:
		start_game(ENGINE_NAME_GESTURE, "MENU:SNAKE\r\n");
		break;
	case 2:
		start_game(ENGINE_NAME_KWS_MINE, "MENU:MINESWEEPER\r\n");
		break;
	default:
		LOG_WRN("Ukjent knapp: %u", button_id);
		break;
	}
}
int main(void)
{
	int err;

	err = engine_controller_init();
	if (err) {
		LOG_ERR("Engine controller init failed (err %d)", err);
		return err;
	}

	err = button_init();
	if (err) {
		LOG_ERR("Button init failed (err %d)", err);
		return err;
	}
	button_reg_click_handler(on_button_click);

	err = ble_nus_init();
	if (err) {
		LOG_ERR("BLE NUS init failed (err %d)", err);
		return err;
	}

	/* 	Runs the active engine and switches between them on request
		Function is a while loop. */
	engine_controller_run();

	return 0;
}
