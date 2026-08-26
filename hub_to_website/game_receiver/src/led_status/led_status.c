/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include "led_status.h"

#include <errno.h>

#include <zephyr/kernel.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

LOG_MODULE_REGISTER(led_status, LOG_LEVEL_INF);

/* Half a blink: 500 ms lit, 500 ms dark. Slow enough to read as "searching"
 * rather than as an error indication, and slow enough that a glance is enough to
 * count which LEDs are pulsing.
 */
#define BLINK_HALF_PERIOD K_MSEC(500)

static const struct gpio_dt_spec leds[LED_STATUS_COUNT] = {
	GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios),
};

/* Per-peer link state, and the phase every blinking LED shares so they pulse
 * together instead of drifting apart.
 */
static bool peer_connected[LED_STATUS_COUNT];
static bool blink_on;

/* Calls before led_status_init() are ignored rather than driving unconfigured
 * pins: ble_central_init() reports state, and nothing guarantees the two are
 * initialized in that order.
 */
static bool leds_ready;

static void blink_work_handler(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(blink_work, blink_work_handler);

/* Drive all LEDs from the current state. A connected peer is solid on; the rest
 * follow the shared blink phase.
 *
 * Called both from the Bluetooth callbacks (via led_status_set_connected) and
 * from the system workqueue (the blink tick). Interleaving those is harmless:
 * every call writes the full picture, so the worst case is one LED showing a
 * stale level for less than a blink half-period.
 */
static void leds_apply(void)
{
	for (size_t i = 0; i < ARRAY_SIZE(leds); i++) {
		const bool on = peer_connected[i] ? true : blink_on;

		(void)gpio_pin_set_dt(&leds[i], on ? 1 : 0);
	}
}

static bool any_blinking(void)
{
	for (size_t i = 0; i < ARRAY_SIZE(leds); i++) {
		if (!peer_connected[i]) {
			return true;
		}
	}

	return false;
}

/* Keep the blink running only while at least one peer is still missing, so once
 * everything is connected the LEDs sit solid with no periodic wakeups.
 */
static void blink_update(void)
{
	if (any_blinking()) {
		(void)k_work_reschedule(&blink_work, BLINK_HALF_PERIOD);
	} else {
		(void)k_work_cancel_delayable(&blink_work);
	}
}

static void blink_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	blink_on = !blink_on;
	leds_apply();
	blink_update();
}

int led_status_init(void)
{
	for (size_t i = 0; i < ARRAY_SIZE(leds); i++) {
		int err;

		if (!gpio_is_ready_dt(&leds[i])) {
			LOG_ERR("LED %u not ready", (unsigned int)i);
			return -ENODEV;
		}

		err = gpio_pin_configure_dt(&leds[i], GPIO_OUTPUT_INACTIVE);
		if (err) {
			LOG_ERR("Failed to configure LED %u (err %d)", (unsigned int)i, err);
			return err;
		}
	}

	leds_ready = true;

	/* Start lit so the board shows life the moment it boots, rather than
	 * spending the first half-period looking dead.
	 */
	blink_on = true;
	leds_apply();
	blink_update();

	LOG_INF("Status LED ready: led0 = peer 0");
	return 0;
}

void led_status_set_connected(size_t idx, bool connected)
{
	if (!leds_ready || (idx >= ARRAY_SIZE(leds))) {
		return;
	}

	peer_connected[idx] = connected;
	leds_apply();
	blink_update();
}
