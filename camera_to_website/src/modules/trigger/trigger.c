/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>
#if CONFIG_DK_LIBRARY
#include <dk_buttons_and_leds.h>
#endif

#include "message_channel.h"

LOG_MODULE_REGISTER(trigger, CONFIG_LTE_CAMERA_TRIGGER_LOG_LEVEL);

static void message_send(enum trigger_type type)
{
	int err;

	err = zbus_chan_pub(&TRIGGER_CHAN, &type, K_SECONDS(1));
	if (err) {
		LOG_ERR("zbus_chan_pub, error: %d", err);
		SEND_FATAL_ERROR();
	}
}

#if CONFIG_DK_LIBRARY
static void button_handler(uint32_t button_states, uint32_t has_changed)
{
	uint32_t pressed = button_states & has_changed;

	if (pressed & DK_BTN1_MSK) {
		message_send(TRIGGER_CAPTURE);
	} else if (pressed & DK_BTN2_MSK) {
		message_send(TRIGGER_ANON);
	}
}
#endif

static void trigger_task(void)
{
#if CONFIG_DK_LIBRARY
	int err = dk_buttons_init(button_handler);

	if (err) {
		LOG_ERR("dk_buttons_init, error: %d", err);
		SEND_FATAL_ERROR();
		return;
	}
#endif
}

K_THREAD_DEFINE(trigger_task_id,
		CONFIG_LTE_CAMERA_TRIGGER_THREAD_STACK_SIZE,
		trigger_task, NULL, NULL, NULL, 3, 0, 0);
