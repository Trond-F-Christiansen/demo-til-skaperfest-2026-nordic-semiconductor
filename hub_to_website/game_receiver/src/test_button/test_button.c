/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 *
 * TEMPORARY bring-up helper - see test_button.h. Remove once the game console
 * sends real scores over BLE.
 */

#include "test_button.h"

#include "score_bridge/score_bridge.h"

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(test_button, LOG_LEVEL_INF);

#define BUTTON_DEBOUNCE_MS 200
#define TEST_GAME          "snake_voice"
#define TEST_SCORE         20

static const struct gpio_dt_spec btn = GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios);
static struct gpio_callback btn_cb;

/* score_bridge_send() writes to the UART, so run it in a workqueue thread
 * rather than in the button's interrupt context.
 */
static void send_work_fn(struct k_work *work)
{
	ARG_UNUSED(work);

	LOG_INF("sw0 pressed: sending test score %s:%d", TEST_GAME, TEST_SCORE);
	score_bridge_send(TEST_GAME, TEST_SCORE);
}

static K_WORK_DEFINE(send_work, send_work_fn);

/* Ignore presses closer than BUTTON_DEBOUNCE_MS apart; a physical switch can
 * bounce and otherwise register several presses.
 */
static bool debounce_ok(uint32_t *last)
{
	uint32_t now = k_uptime_get_32();

	if (now - *last < BUTTON_DEBOUNCE_MS) {
		return false;
	}
	*last = now;
	return true;
}

static void btn_pressed(const struct device *port, struct gpio_callback *cb, uint32_t pins)
{
	static uint32_t last;

	ARG_UNUSED(port);
	ARG_UNUSED(cb);
	ARG_UNUSED(pins);

	if (!debounce_ok(&last)) {
		return;
	}

	k_work_submit(&send_work);
}

int test_button_init(void)
{
	int err;

	if (!gpio_is_ready_dt(&btn)) {
		LOG_ERR("sw0 GPIO not ready");
		return -ENODEV;
	}

	err = gpio_pin_configure_dt(&btn, GPIO_INPUT);
	if (err) {
		LOG_ERR("Failed to configure sw0 (err %d)", err);
		return err;
	}

	err = gpio_pin_interrupt_configure_dt(&btn, GPIO_INT_EDGE_TO_ACTIVE);
	if (err) {
		LOG_ERR("Failed to configure sw0 interrupt (err %d)", err);
		return err;
	}

	gpio_init_callback(&btn_cb, btn_pressed, BIT(btn.pin));
	err = gpio_add_callback(btn.port, &btn_cb);
	if (err) {
		LOG_ERR("Failed to add sw0 callback (err %d)", err);
		return err;
	}

	LOG_INF("Test-score button ready: press sw0 to send %s:%d", TEST_GAME, TEST_SCORE);
	return 0;
}
