/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef _MESSAGE_CHANNEL_H_
#define _MESSAGE_CHANNEL_H_

#include <zephyr/kernel.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/logging/log_ctrl.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SEND_FATAL_ERROR()									\
	int not_used = -1;									\
	if (zbus_chan_pub(&FATAL_ERROR_CHAN, &not_used, K_SECONDS(10))) {			\
		LOG_ERR("Sending a message on the fatal error channel failed, rebooting");	\
		LOG_PANIC();									\
		IF_ENABLED(CONFIG_REBOOT, (sys_reboot(0)));					\
	}

struct payload {
	uint8_t data[CONFIG_LTE_CAMERA_PAYLOAD_CHANNEL_STRING_MAX_SIZE];
	size_t len;
};

enum trigger_type {
	TRIGGER_CAPTURE,

	TRIGGER_ANON,
};

enum network_status {
	NETWORK_DISCONNECTED,
	NETWORK_CONNECTED,
};

ZBUS_CHAN_DECLARE(TRIGGER_CHAN, PAYLOAD_CHAN, NETWORK_CHAN, FATAL_ERROR_CHAN);

#ifdef __cplusplus
}
#endif

#endif
