/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include "ble_nus.h"

#include <errno.h>
#include <string.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

#include <bluetooth/services/nus.h>
#include "../hw_modules/leds.h"

LOG_MODULE_REGISTER(ble_nus, LOG_LEVEL_INF);

static struct bt_conn *nus_conn;
static bool nus_send_enabled;

static const struct bt_data nus_ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static const struct bt_data nus_sd[] = {
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, BT_UUID_NUS_VAL),
};

/* ASCII tokens sent on the wire, indexed by @ref game_command. GAME_CMD_NONE
 * has no token and is rejected before lookup.
 */
static const char *const command_tokens[] = {
	[GAME_CMD_UP] = "UP\r\n",
	[GAME_CMD_DOWN] = "DOWN\r\n",
	[GAME_CMD_LEFT] = "LEFT\r\n",
	[GAME_CMD_RIGHT] = "RIGHT\r\n",
};

static void nus_send_enabled_cb(enum bt_nus_send_status status)
{
	nus_send_enabled = (status == BT_NUS_SEND_STATUS_ENABLED);
	LOG_INF("NUS notifications %s", nus_send_enabled ? "enabled" : "disabled");
}

static void nus_connected(struct bt_conn *conn, uint8_t err)
{
	char addr[BT_ADDR_LE_STR_LEN];

	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));

	if (err) {
		LOG_ERR("Connection failed to %s (err %u)", addr, err);
		return;
	}

	if (!nus_conn) {
		nus_conn = bt_conn_ref(conn);
	}
	// LED1 fast paa naar tilkoblet
    leds_conn_connected();
	LOG_INF("Connected %s", addr);
}

static int advertising_start(void)
{
	return bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, nus_ad, ARRAY_SIZE(nus_ad),
			       nus_sd, ARRAY_SIZE(nus_sd));
}

static void nus_disconnected(struct bt_conn *conn, uint8_t reason)
{
	char addr[BT_ADDR_LE_STR_LEN];

	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));
	LOG_INF("Disconnected from %s (reason 0x%02x)", addr, reason);

	if (nus_conn == conn) {
		bt_conn_unref(nus_conn);
		nus_conn = NULL;
	}

	nus_send_enabled = false;
	// Blink LED1 igjen mens vi venter paa ny tilkobling
    leds_conn_waiting();

	/* Advertising is deliberately NOT restarted here. This callback runs while
	 * the connection object still exists, and with CONFIG_BT_MAX_CONN at its
	 * default of 1 there is then no free object for a connectable advertiser to
	 * reserve -- bt_le_adv_start() fails with -ENOMEM every time, leaving the
	 * board silent until it is reset. It is restarted from nus_recycled()
	 * instead, once the stack has released the connection.
	 */
}

/* Fires once the disconnected connection object has been fully released, which
 * is the first moment a connectable advertiser can be started again. Zephyr
 * documents this as the event to listen for when restarting a connectable
 * advertiser after an earlier connection.
 */
static void nus_recycled(void)
{
	int err = advertising_start();

	if (err) {
		LOG_ERR("Advertising failed to restart (err %d)", err);
		return;
	}

	LOG_INF("Advertising restarted");
}

static struct bt_nus_cb nus_cb = {
	.send_enabled = nus_send_enabled_cb,
};

static struct bt_conn_cb nus_conn_callbacks = {
	.connected = nus_connected,
	.disconnected = nus_disconnected,
	.recycled = nus_recycled,
};

int ble_nus_init(void)
{
	int err;

	err = bt_enable(NULL);
	if (err) {
		LOG_ERR("Bluetooth init failed (err %d)", err);
		return err;
	}

	LOG_INF("Bluetooth initialized");

	err = bt_nus_init(&nus_cb);
	if (err) {
		LOG_ERR("NUS init failed (err %d)", err);
		return err;
	}

	bt_conn_cb_register(&nus_conn_callbacks);

	err = advertising_start();
	if (err) {
		LOG_ERR("Advertising failed to start (err %d)", err);
		return err;
	}

	LOG_INF("Advertising started");
	// Start med aa blinke LED1 mens vi venter paa tilkobling
    leds_conn_waiting();
	return 0;
}

int ble_nus_send_command(enum game_command cmd)
{
	if (cmd == GAME_CMD_NONE || cmd >= ARRAY_SIZE(command_tokens) ||
	    command_tokens[cmd] == NULL) {
		return -EINVAL;
	}

	if (!nus_conn || !nus_send_enabled) {
		return -ENOTCONN;
	}

	const char *token = command_tokens[cmd];

	return bt_nus_send(nus_conn, (const uint8_t *)token, (uint16_t)strlen(token));
}

int ble_nus_send_raw(const char *token)
{
	if (token == NULL) {
		return -EINVAL;
	}

	if (!nus_conn || !nus_send_enabled) {
		return -ENOTCONN;
	}

	return bt_nus_send(nus_conn, (const uint8_t *)token, (uint16_t)strlen(token));
}