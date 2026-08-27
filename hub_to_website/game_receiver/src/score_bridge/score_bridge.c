/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include "score_bridge.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(score_bridge, LOG_LEVEL_INF);

/* Dedicated 2-wire link to the nRF9151 on expansion-header pins
 * (uart21: TX P1.04 / RX P1.05). Enabled by the board overlay.
 */
static const struct device *uart_dev = DEVICE_DT_GET(DT_NODELABEL(uart21));
/* Game-control link to the PC on VCOM1 (uart30): scores in, commands out. */
static const struct device *uart_game = DEVICE_DT_GET(DT_NODELABEL(uart30));

/*variables for uart_game*/
#define LINE_MAX 256
static uint8_t line_buf[LINE_MAX];   /* ISR bygger linja her */
static size_t line_len;
static uint8_t ready_line[LINE_MAX]; /* ferdig linje til tasken */
static size_t ready_len;
static K_SEM_DEFINE(line_ready_sem, 0, 1);

static void uart_game_cb(const struct device *dev, void *user_data);

static void uart_send_str(const char *s, size_t len)
{
	for (size_t i = 0; i < len; i++) {
		uart_poll_out(uart_dev, (uint8_t)s[i]);
	}
}

void score_bridge_send(const char *game, uint32_t points)
{
	char line[128];
	int len;

	len = snprintf(line, sizeof(line),
		       "%s|{\"score\":%u}\n", game, points);
	if ((len < 0) || (len >= (int)sizeof(line))) {
		LOG_ERR("Score line too long, dropping (game=%s, score=%u)", game, points);
		return;
	}

	uart_send_str(line, len);

	LOG_INF("Forwarded to nRF9151: %.*s", len - 1, line);
}

void score_bridge_write_game(const char *buf, size_t len)
{
	for (size_t i = 0; i < len; i++) {
		uart_poll_out(uart_game, (uint8_t)buf[i]);
	}
}


int score_bridge_init(void)
{
	int err;

	if (!device_is_ready(uart_dev)) {
		LOG_ERR("nRF9151 link (uart21) not ready");
		return -ENODEV;
	}
/* new for uart_game*/
	if (!device_is_ready(uart_game)) {
		LOG_ERR("game UART not ready");
		return -ENODEV;
	}

	err = uart_irq_callback_user_data_set(uart_game, uart_game_cb, NULL);
	if (err) {
		LOG_ERR("uart_irq_callback_user_data_set, error: %d", err);
		return err;
	}

	uart_irq_rx_enable(uart_game);

	LOG_INF("Score bridge ready, forwarding highscores on uart21");
	return 0;
}


/*new for uart_game*/

static void uart_game_cb(const struct device *dev, void *user_data)
{
	uint8_t byte;

	ARG_UNUSED(user_data);

	if (!uart_irq_update(dev) || !uart_irq_rx_ready(dev)) {
		return;
	}

	while (uart_fifo_read(dev, &byte, 1) == 1) {
		if (byte == '\r') {
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
			line_len = 0;
		}
	}
}
/*new for uart_game: sender linje mottat videre */


/* Parse the legacy BLE form "SCORE:<game>:<points>" into game + points. The
 * pygame "game|{json}" form is not parsed here -- it is forwarded verbatim so
 * any extra fields (e.g. minesweeper's time) reach the nRF9151.
 */
static int parse_score_line(char *line, const char **game, uint32_t *points)
{
	char *p = line + 6;   /* past "SCORE:" */
	char *sep = strchr(p, ':');

	if ((sep == NULL) || (sep == p) || (sep[1] == '\0')) {
		return -EINVAL;
	}
	*sep = '\0';
	*game = p;
	*points = (uint32_t)strtoul(sep + 1, NULL, 10);
	return 0;
}

static void score_bridge_task(void)
{
	while (true) {
		char line[LINE_MAX + 1];

		k_sem_take(&line_ready_sem, K_FOREVER);

		if ((ready_len == 0) || (ready_len > LINE_MAX)) {
			continue;
		}

		memcpy(line, ready_line, ready_len);
		line[ready_len] = '\0';

		if (strncmp(line, "SCORE:", 6) == 0) {
			const char *game;
			uint32_t points;

			if (parse_score_line(line, &game, &points) != 0) {
				LOG_WRN("Unparsable SCORE line: \"%s\"", line);
				continue;
			}
			score_bridge_send(game, points);
		} else if (strchr(line, '|') != NULL) {
			/* pygame "game|{json}" form: forward verbatim so extra
			 * fields (e.g. minesweeper's time) reach the nRF9151.
			 */
			uart_send_str(line, ready_len);
			uart_poll_out(uart_dev, (uint8_t)'\n');
			LOG_INF("Forwarded to nRF9151: %s", line);
		} else {
			LOG_WRN("Unparsable line from game UART: \"%s\"", line);
		}
	}
}

K_THREAD_DEFINE(score_bridge_task_id, 2048, score_bridge_task, NULL, NULL, NULL, 7, 0, 0);
