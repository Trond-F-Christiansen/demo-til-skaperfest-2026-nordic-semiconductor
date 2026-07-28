/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>

#include "message_channel.h"

LOG_MODULE_REGISTER(uart_bridge, CONFIG_MQTT_SAMPLE_UART_BRIDGE_LOG_LEVEL);

/* The nRF54LM20 hub sends one newline-terminated line per highscore:
 *
 *     <game>|<json>\n      e.g.  snake|{"session_id":"snake-0","score":1200}
 *
 * The part before the first '|' becomes the MQTT topic "games/<game>/score";
 * the part after it is the JSON payload the backend already expects.
 */

static const struct device *uart_dev = DEVICE_DT_GET(DT_NODELABEL(uart1));

#define LINE_MAX 256

/* Filled by the ISR one byte at a time. */
static uint8_t line_buf[LINE_MAX];
static size_t line_len;

/* Handed to the task once a full line is received. */
static uint8_t ready_line[LINE_MAX];
static size_t ready_len;

static K_SEM_DEFINE(line_ready_sem, 0, 1);

/* Runs in ISR context: only accumulates bytes into line_buf until a newline,
 * then hands the completed line to the task via the semaphore. Never calls
 * anything blocking (zbus, LOG_INF, ...).
 */
static void uart_cb(const struct device *dev, void *user_data)
{
	uint8_t byte;

	if (!uart_irq_update(dev) || !uart_irq_rx_ready(dev)) {
		return;
	}

	while (uart_fifo_read(dev, &byte, 1) == 1) {
		if (byte == '\r') {
			/* Ignore carriage returns; the newline ends the line. */
			continue;
		}

		if (byte == '\n') {
			memcpy(ready_line, line_buf, line_len);
			ready_len = line_len;
			line_len = 0;
			k_sem_give(&line_ready_sem);
			continue;
		}

		if (line_len < sizeof(line_buf)) {
			line_buf[line_len++] = byte;
		} else {
			/* Overrun: drop the oversized line and resync at the
			 * next newline.
			 */
			line_len = 0;
		}
	}
}

static void uart_bridge_task(void)
{
	while (true) {
		struct payload frame = { 0 };
		uint8_t *sep;
		size_t game_len, json_len;
		int len;
		int err;

		k_sem_take(&line_ready_sem, K_FOREVER);

		if (ready_len == 0) {
			continue;
		}

		/* Split on the first '|': left = game name, right = JSON. */
		sep = memchr(ready_line, '|', ready_len);
		if ((sep == NULL) || (sep == ready_line) ||
		    ((size_t)(sep - ready_line) == ready_len - 1)) {
			LOG_WRN("Malformed line, no game|json separator");
			continue;
		}

		game_len = sep - ready_line;
		json_len = ready_len - game_len - 1;

		len = snprintk(frame.topic, sizeof(frame.topic), "games/%.*s/score",
			       (int)game_len, ready_line);
		if ((len < 0) || (len >= (int)sizeof(frame.topic))) {
			LOG_WRN("Game name too long for topic buffer");
			continue;
		}
		frame.topic_len = len;

		if (json_len > sizeof(frame.data)) {
			LOG_WRN("JSON payload too large (%zu bytes)", json_len);
			continue;
		}
		memcpy(frame.data, sep + 1, json_len);
		frame.len = json_len;

		err = zbus_chan_pub(&PAYLOAD_CHAN, &frame, K_SECONDS(1));
		if (err) {
			LOG_ERR("zbus_chan_pub, error: %d", err);
			continue;
		}

		LOG_INF("Published %u bytes to topic \"%s\"", frame.len, frame.topic);
	}
}

K_THREAD_DEFINE(uart_bridge_task_id, 1024, uart_bridge_task, NULL, NULL, NULL, 7, 0, 0);

static int uart_bridge_init(void)
{
	int err;

	if (!device_is_ready(uart_dev)) {
		LOG_ERR("UART device not ready");
		return -ENODEV;
	}

	err = uart_irq_callback_user_data_set(uart_dev, uart_cb, NULL);
	if (err) {
		LOG_ERR("uart_irq_callback_user_data_set, error: %d", err);
		return err;
	}

	uart_irq_rx_enable(uart_dev);

	LOG_INF("UART bridge ready, listening on uart1");

	return 0;
}

SYS_INIT(uart_bridge_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
