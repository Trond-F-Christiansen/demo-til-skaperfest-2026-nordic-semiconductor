/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include "button.h"

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

LOG_MODULE_REGISTER(button, CONFIG_LOG_DEFAULT_LEVEL);

#define SW0_NODE DT_ALIAS(sw0)
#define SW1_NODE DT_ALIAS(sw1)
#define SW2_NODE DT_ALIAS(sw2)

#if !DT_NODE_HAS_STATUS(SW0_NODE, okay)
#error "sw0 devicetree alias is not defined"
#endif
#if !DT_NODE_HAS_STATUS(SW1_NODE, okay)
#error "sw1 devicetree alias is not defined"
#endif
#if !DT_NODE_HAS_STATUS(SW2_NODE, okay)
#error "sw2 devicetree alias is not defined"
#endif

/* Debounce delay (ms) used after each interrupt before sampling the pin. */
#define BUTTON_DEBOUNCE_MSEC 20

/* Periodic check interval (ms) used while a button is held to detect long press. */
#define BUTTON_CHECK_PERIOD_MSEC 100

/* Per-button context: hardware spec, ISR callback, work item and state. */
struct button_ctx {
	const struct gpio_dt_spec spec;
	struct gpio_callback cb_data;
	struct k_work_delayable check_work;
	uint8_t id;
	bool pressed_state;          /* current debounced state */
	int64_t press_start_ms;      /* uptime at press time */
	bool long_already_reported;  /* long click already emitted while held */
};

static struct button_ctx buttons[BUTTON_COUNT] = {
	{ .spec = GPIO_DT_SPEC_GET_OR(SW0_NODE, gpios, {0}), .id = 0 },
	{ .spec = GPIO_DT_SPEC_GET_OR(SW1_NODE, gpios, {0}), .id = 1 },
	{ .spec = GPIO_DT_SPEC_GET_OR(SW2_NODE, gpios, {0}), .id = 2 },
};

static button_click_handler_t button_click_handler;

static void emit_click(uint8_t id, button_click_t click)
{
	if (button_click_handler != NULL) {
		button_click_handler(id, click);
	} else {
		LOG_WRN("Click on btn%u (%s) but no handler registered",
			id, click == BUTTON_CLICK_LONG ? "LONG" : "SHORT");
	}
}

static void handle_press_edge(struct button_ctx *b, int64_t now_ms)
{
	if (b->pressed_state) {
		return; /* bounce */
	}

	b->pressed_state = true;
	b->press_start_ms = now_ms;
	b->long_already_reported = false;

	k_work_reschedule(&b->check_work, K_MSEC(BUTTON_CHECK_PERIOD_MSEC));
}

static void handle_release_edge(struct button_ctx *b, int64_t now_ms)
{
	if (!b->pressed_state) {
		return; /* spurious release */
	}

	int64_t held_ms = now_ms - b->press_start_ms;

	b->pressed_state = false;
	(void)k_work_cancel_delayable(&b->check_work);

	if (b->long_already_reported) {
		return;
	}

	if (held_ms < BUTTON_SHORT_CLICK_MSEC) {
		emit_click(b->id, BUTTON_CLICK_SHORT);
	} else {
		LOG_DBG("btn%u click ignored, hold %lld ms (between thresholds)",
			b->id, (long long)held_ms);
	}
}

static void button_check_work_fn(struct k_work *work)
{
	struct k_work_delayable *dwork = k_work_delayable_from_work(work);
	struct button_ctx *b = CONTAINER_OF(dwork, struct button_ctx, check_work);

	int raw = gpio_pin_get_dt(&b->spec);

	if (raw < 0) {
		LOG_ERR("btn%u pin read failed (err %d)", b->id, raw);
		return;
	}

	const bool sampled_pressed = (raw != 0);
	const int64_t now_ms = k_uptime_get();

	if (sampled_pressed != b->pressed_state) {
		if (sampled_pressed) {
			handle_press_edge(b, now_ms);
		} else {
			handle_release_edge(b, now_ms);
		}
		return;
	}

	if (b->pressed_state && !b->long_already_reported) {
		int64_t held_ms = now_ms - b->press_start_ms;

		if (held_ms >= BUTTON_LONG_CLICK_MSEC) {
			b->long_already_reported = true;
			emit_click(b->id, BUTTON_CLICK_LONG);
		}

		k_work_reschedule(&b->check_work, K_MSEC(BUTTON_CHECK_PERIOD_MSEC));
	}
}

static void button_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(pins);

	struct button_ctx *b = CONTAINER_OF(cb, struct button_ctx, cb_data);

	k_work_reschedule(&b->check_work, K_MSEC(BUTTON_DEBOUNCE_MSEC));
}

int button_init(void)
{
	int ret;

	for (int i = 0; i < BUTTON_COUNT; i++) {
		struct button_ctx *b = &buttons[i];

		if (!device_is_ready(b->spec.port)) {
			LOG_ERR("btn%u GPIO %s not ready", b->id, b->spec.port->name);
			return -ENODEV;
		}

		ret = gpio_pin_configure_dt(&b->spec, GPIO_INPUT);
		if (ret != 0) {
			LOG_ERR("btn%u pin %u config failed (err %d)",
				b->id, b->spec.pin, ret);
			return ret;
		}

		k_work_init_delayable(&b->check_work, button_check_work_fn);

		ret = gpio_pin_interrupt_configure_dt(&b->spec, GPIO_INT_EDGE_BOTH);
		if (ret != 0) {
			LOG_ERR("btn%u interrupt config failed (err %d)", b->id, ret);
			return ret;
		}

		gpio_init_callback(&b->cb_data, button_isr, BIT(b->spec.pin));
		ret = gpio_add_callback(b->spec.port, &b->cb_data);
		if (ret != 0) {
			LOG_ERR("btn%u add callback failed (err %d)", b->id, ret);
			return ret;
		}

		LOG_DBG("btn%u ready on %s pin %u", b->id, b->spec.port->name, b->spec.pin);
	}

	return 0;
}

void button_reg_click_handler(button_click_handler_t click_handler)
{
	button_click_handler = click_handler;
}