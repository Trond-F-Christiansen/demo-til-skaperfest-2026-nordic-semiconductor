/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include "ble_central.h"

#include <stdlib.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/logging/log.h>

#include <bluetooth/gatt_dm.h>
#include <bluetooth/scan.h>
#include <bluetooth/services/nus.h>
#include <bluetooth/services/nus_client.h>

#include "led_status/led_status.h"
#include "score_bridge/score_bridge.h"

LOG_MODULE_REGISTER(ble_central, LOG_LEVEL_INF);

#define SCORE_PREFIX "SCORE:"
#define MENU_PREFIX "MENU:"

/* Give a connection attempt and its service discovery time to finish before
 * scanning resumes for the next peripheral. Only used on the error paths, where
 * there is nothing to wait for; the success path restarts scanning from the
 * discovery callback instead.
 */
#define SCAN_RESTART_DELAY K_MSEC(100)

/*
 * One slot per peripheral this receiver expects, matched by advertised name.
 *
 * Both boards run the same NUS peripheral role, so they are told apart by name:
 * "Game Controller" is applications/game_controller (voice and gesture commands)
 * and "Axon_Sensor" is nicco_apps/image_classification/finger_digits_py_gs (the
 * finger-digit classifier that drives the quiz). Names, not addresses: the
 * previous single hardcoded address meant swapping a board silently stopped the
 * receiver from ever connecting.
 *
 * Note that finger_digits_py_rgb advertises under the same "Axon_Sensor" name,
 * so if both classifier variants are powered on, whichever answers the scan
 * first takes the slot.
 *
 * Each slot owns its own bt_nus_client: that structure holds the GATT handles
 * discovered on one link, so it cannot be shared between connections.
 */
struct peer {
	/** Advertised complete local name to scan for. */
	const char *name;
	/** Connection to this peripheral, or NULL when not connected. */
	struct bt_conn *conn;
	/** Per-link NUS client state. */
	struct bt_nus_client nus;
};

static struct peer peers[] = {
	{ .name = "Game Controller" },
	{ .name = "Axon_Sensor" },
};

BUILD_ASSERT(ARRAY_SIZE(peers) <= CONFIG_BT_MAX_CONN,
	     "CONFIG_BT_MAX_CONN is too low to hold a link to every peer");
BUILD_ASSERT(ARRAY_SIZE(peers) <= CONFIG_BT_SCAN_NAME_CNT,
	     "CONFIG_BT_SCAN_NAME_CNT is too low to filter on every peer name");

/* The status LEDs are mapped positionally onto this table -- led0 to peers[0],
 * led1 to peers[1] -- so adding a peer without adding an LED must not silently
 * leave the new one unindicated.
 */
BUILD_ASSERT(ARRAY_SIZE(peers) == LED_STATUS_COUNT,
	     "Every peer needs a status LED (see led_status.h)");

/* Set when a scan filter matches, consumed when the connection object appears.
 * Both callbacks run in the Bluetooth RX thread, and the scan module stops
 * scanning for the duration of a connection attempt, so the two cannot
 * interleave for different devices.
 */
static struct peer *connecting_peer;

static void scan_restart_work_handler(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(scan_restart_work, scan_restart_work_handler);

static int scan_start(void);

/* Resume scanning off a work item rather than from inside a Bluetooth callback,
 * so bt_scan_start() is never called from the scan module's own event handler.
 */
static void scan_resume(k_timeout_t delay)
{
	(void)k_work_reschedule(&scan_restart_work, delay);
}

static void scan_restart_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	(void)scan_start();
}

static struct peer *peer_by_conn(const struct bt_conn *conn)
{
	for (size_t i = 0; i < ARRAY_SIZE(peers); i++) {
		if (peers[i].conn == conn) {
			return &peers[i];
		}
	}

	return NULL;
}

/* Index into peers[], which is also the peer's status LED. */
static size_t peer_index(const struct peer *peer)
{
	return (size_t)(peer - peers);
}

static struct peer *peer_by_nus(const struct bt_nus_client *nus)
{
	for (size_t i = 0; i < ARRAY_SIZE(peers); i++) {
		if (&peers[i].nus == nus) {
			return &peers[i];
		}
	}

	return NULL;
}

static uint8_t nus_data_received(struct bt_nus_client *nus, const uint8_t *data, uint16_t len)
{
	const struct peer *peer = peer_by_nus(nus);
	const char *source = (peer != NULL) ? peer->name : "unknown";

	/* The peripherals' tokens are already newline-terminated; strip that so we
	 * don't double up with our own line ending below.
	 */
	while (len && (data[len - 1] == '\r' || data[len - 1] == '\n')) {
		len--;
	}

	/* A highscore notification ("SCORE:<game>:<points>") is forwarded to the
	 * nRF9151 for MQTT publishing instead of being echoed as a command.
	 */
	if ((len >= strlen(SCORE_PREFIX)) &&
	    (memcmp(data, SCORE_PREFIX, strlen(SCORE_PREFIX)) == 0)) {
		char buf[64];
		char *game, *sep, *points_str;

		if (len >= sizeof(buf)) {
			LOG_WRN("Score line too long, ignoring");
			return BT_GATT_ITER_CONTINUE;
		}

		/* NUS data isn't NUL-terminated; copy so we can tokenize it. */
		memcpy(buf, data, len);
		buf[len] = '\0';

		game = buf + strlen(SCORE_PREFIX);
		sep = strchr(game, ':');
		if ((sep == NULL) || (sep == game) || (sep[1] == '\0')) {
			LOG_WRN("Malformed score line: \"%s\"", buf);
			return BT_GATT_ITER_CONTINUE;
		}

		*sep = '\0';
		points_str = sep + 1;

		score_bridge_send(game, (uint32_t)strtoul(points_str, NULL, 10));

		return BT_GATT_ITER_CONTINUE;
	}
	/* Menyvalg fra controller-knappene sendes ut med eget prefiks slik at
	 * PC-en kan skille dem fra vanlige stemmekommandoer.
	 */
	if ((len >= strlen(MENU_PREFIX)) &&
	    (memcmp(data, MENU_PREFIX, strlen(MENU_PREFIX)) == 0)) {
		printk("%.*s\r\n", len, data);
		return BT_GATT_ITER_CONTINUE;
	}

	/* The console format is deliberately unchanged now that two peripherals
	 * feed it, so the host-side parser needs no update. Which board a token
	 * came from is logged instead -- worth knowing because the tokens are not
	 * unique: the Minesweeper keyword model and the finger-digit classifier
	 * both emit "ZERO".
	 */
	LOG_DBG("Command from %s: %.*s", source, len, data);
	printk("Command: %.*s\r\n", len, data);

	return BT_GATT_ITER_CONTINUE;
}

static void discovery_complete(struct bt_gatt_dm *dm, void *context)
{
	struct bt_nus_client *nus = context;
	const struct peer *peer = peer_by_nus(nus);

	LOG_INF("Service discovery completed for %s",
		(peer != NULL) ? peer->name : "unknown peer");

	bt_nus_handles_assign(dm, nus);
	bt_nus_subscribe_receive(nus);

	bt_gatt_dm_data_release(dm);

	/* This link is fully set up, so it is now safe to go looking for the next
	 * peripheral. Deferring the scan until here is what keeps discovery
	 * serialized: bt_gatt_dm handles one discovery at a time, and a second
	 * peer connecting mid-discovery would fail to subscribe and then sit
	 * connected but silent.
	 */
	scan_resume(K_NO_WAIT);
}

static void discovery_service_not_found(struct bt_conn *conn, void *context)
{
	ARG_UNUSED(context);

	LOG_WRN("NUS service not found; disconnecting");

	/* Not one of ours after all -- drop it so the slot frees up and scanning
	 * resumes from the disconnected callback.
	 */
	(void)bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
}

static void discovery_error(struct bt_conn *conn, int err, void *context)
{
	ARG_UNUSED(context);

	LOG_ERR("Service discovery failed (err %d); disconnecting", err);

	(void)bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
}

static const struct bt_gatt_dm_cb discovery_cb = {
	.completed = discovery_complete,
	.service_not_found = discovery_service_not_found,
	.error_found = discovery_error,
};

static void gatt_discover(struct bt_conn *conn)
{
	struct peer *peer = peer_by_conn(conn);
	int err;

	if (peer == NULL) {
		return;
	}

	err = bt_gatt_dm_start(conn, BT_UUID_NUS_SERVICE, &discovery_cb, &peer->nus);
	if (err) {
		LOG_ERR("Could not start service discovery for %s (err %d)", peer->name, err);
		(void)bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
	}
}

static void connected(struct bt_conn *conn, uint8_t conn_err)
{
	char addr[BT_ADDR_LE_STR_LEN];
	struct peer *peer = peer_by_conn(conn);

	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));

	if (conn_err) {
		LOG_WRN("Failed to connect to %s (err %u)", addr, conn_err);

		if (peer != NULL) {
			bt_conn_unref(peer->conn);
			peer->conn = NULL;
		}

		scan_resume(SCAN_RESTART_DELAY);
		return;
	}

	if (peer == NULL) {
		/* A connection we have no slot for: nothing can route its data, so
		 * do not leave it occupying a link.
		 */
		LOG_WRN("Connected to unexpected peer %s; disconnecting", addr);
		(void)bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
		return;
	}

	LOG_INF("Connected %s (%s)", addr, peer->name);
	led_status_set_connected(peer_index(peer), true);

	/* Scanning is already stopped by the scan module for the duration of the
	 * connection attempt; it resumes once discovery on this link finishes.
	 */
	gatt_discover(conn);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	char addr[BT_ADDR_LE_STR_LEN];
	struct peer *peer = peer_by_conn(conn);

	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));
	LOG_INF("Disconnected from %s (%s, reason 0x%02x)", addr,
		(peer != NULL) ? peer->name : "unknown peer", reason);

	if (peer == NULL) {
		/* A link no slot owned -- one connected() rejected, or a peer whose
		 * name did not resolve. Scanning still stopped for that attempt, so
		 * it has to be resumed here or the receiver goes permanently quiet.
		 */
		scan_resume(SCAN_RESTART_DELAY);
		return;
	}

	bt_conn_unref(peer->conn);
	peer->conn = NULL;
	led_status_set_connected(peer_index(peer), false);

	/* The freed slot puts this peer's name back into the filter set. */
	scan_resume(K_NO_WAIT);
}

static struct bt_conn_cb conn_callbacks = {
	.connected = connected,
	.disconnected = disconnected,
};

static void scan_filter_match(struct bt_scan_device_info *device_info,
			      struct bt_scan_filter_match *filter_match, bool connectable)
{
	ARG_UNUSED(device_info);
	ARG_UNUSED(connectable);

	connecting_peer = NULL;

	if (!filter_match->name.match || (filter_match->name.name == NULL)) {
		return;
	}

	/*
	 * Compare over the advertised name's length and require the lengths to be
	 * equal, rather than strcmp()ing the reported filter name.
	 *
	 * The scan module stores filter names with memcpy() and no NUL terminator
	 * (scan_name_filter_add() in nrf/subsys/bluetooth/scan.c), and
	 * bt_scan_filter_remove_all() only zeroes the filter count, not the name
	 * buffers. Since scan_start() rebuilds the filter set on every connect and
	 * disconnect, a shorter name lands in a slot that held a longer one and
	 * keeps its tail: "Axon_Sensor" written over "Game Controller" reads back
	 * as "Axon_Sensorller". The module's own matching is unaffected because it
	 * bounds the comparison by the advertised length, but a strcmp() here would
	 * silently fail to identify the peer, and connected() would then drop a
	 * board it should have kept.
	 *
	 * The length equality also stops one peer name from matching another's
	 * prefix -- worth keeping, because the module's filter is effectively
	 * "starts with": a device advertising "Game" matches a "Game Controller"
	 * filter. Such a device is rejected here and dropped by connected().
	 */
	const size_t match_len = filter_match->name.len;

	for (size_t i = 0; i < ARRAY_SIZE(peers); i++) {
		if ((strlen(peers[i].name) == match_len) &&
		    (strncmp(peers[i].name, filter_match->name.name, match_len) == 0)) {
			connecting_peer = &peers[i];
			return;
		}
	}
}

static void scan_connecting_error(struct bt_scan_device_info *device_info)
{
	ARG_UNUSED(device_info);

	LOG_WRN("Connecting failed");

	connecting_peer = NULL;
	scan_resume(SCAN_RESTART_DELAY);
}

static void scan_connecting(struct bt_scan_device_info *device_info, struct bt_conn *conn)
{
	ARG_UNUSED(device_info);

	if (connecting_peer == NULL) {
		/* The scan module only connects on a filter match, so this means the
		 * matched name is not in the peer table. connected() drops it.
		 */
		LOG_WRN("Connecting to a peripheral with no slot");
		return;
	}

	connecting_peer->conn = bt_conn_ref(conn);
	connecting_peer = NULL;
}

BT_SCAN_CB_INIT(scan_cb, scan_filter_match, NULL, scan_connecting_error, scan_connecting);

static int scan_start(void)
{
	size_t wanted = 0;
	int err;

	/* Idempotent: this runs again after every connect, disconnect and failed
	 * attempt, so drop whatever filters the previous call installed.
	 */
	(void)bt_scan_stop();
	bt_scan_filter_remove_all();

	/* Only filter on peripherals we are not already connected to. The scan
	 * module connects automatically on a match, so leaving a connected peer's
	 * name in the set would make it repeatedly try to connect to a device it
	 * already holds a link to.
	 */
	for (size_t i = 0; i < ARRAY_SIZE(peers); i++) {
		if (peers[i].conn != NULL) {
			continue;
		}

		err = bt_scan_filter_add(BT_SCAN_FILTER_TYPE_NAME, peers[i].name);
		if (err) {
			LOG_ERR("Name filter '%s' cannot be added (err %d)", peers[i].name, err);
			return err;
		}

		wanted++;
	}

	if (wanted == 0) {
		LOG_INF("All peripherals connected; scanning stopped");
		return 0;
	}

	/* match_all = false: any one of the names is enough. */
	err = bt_scan_filter_enable(BT_SCAN_NAME_FILTER, false);
	if (err) {
		LOG_ERR("Filters cannot be turned on (err %d)", err);
		return err;
	}

	err = bt_scan_start(BT_SCAN_TYPE_SCAN_ACTIVE);
	if (err) {
		LOG_ERR("Scanning failed to start (err %d)", err);
		return err;
	}

	LOG_INF("Scanning for %u peripheral(s)", (unsigned int)wanted);
	return 0;
}

static int nus_client_init(void)
{
	struct bt_nus_client_init_param init = {
		.cb = {
			.received = nus_data_received,
		}
	};

	/* One client instance per link; each discovers its own handles. */
	for (size_t i = 0; i < ARRAY_SIZE(peers); i++) {
		int err = bt_nus_client_init(&peers[i].nus, &init);

		if (err) {
			LOG_ERR("NUS client init failed for %s (err %d)", peers[i].name, err);
			return err;
		}
	}

	return 0;
}

int ble_central_init(void)
{
	int err;
	struct bt_scan_init_param scan_init = {
		.connect_if_match = true,
	};

	err = bt_enable(NULL);
	if (err) {
		LOG_ERR("Bluetooth init failed (err %d)", err);
		return err;
	}

	LOG_INF("Bluetooth initialized");

	bt_conn_cb_register(&conn_callbacks);

	err = nus_client_init();
	if (err) {
		return err;
	}

	bt_scan_init(&scan_init);
	bt_scan_cb_register(&scan_cb);

	return scan_start();
}
