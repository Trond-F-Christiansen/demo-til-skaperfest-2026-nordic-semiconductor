/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <errno.h>
#include <string.h>

#include <zephyr/logging/log.h>
#include <zephyr/net/socket.h>
#include <zephyr/zbus/zbus.h>

#include "message_channel.h"

LOG_MODULE_REGISTER(transport, CONFIG_MQTT_SAMPLE_TRANSPORT_LOG_LEVEL);

ZBUS_SUBSCRIBER_DEFINE(transport, CONFIG_MQTT_SAMPLE_TRANSPORT_MESSAGE_QUEUE_SIZE);

#define HTTP_PORT "443"
#define REQUEST_HEADER_MAX 512
#define RESPONSE_MAX 128

static int send_all(int socket_fd, const void *buffer, size_t length)
{
	const uint8_t *data = buffer;
	size_t offset = 0;

	while (offset < length) {
		int sent = send(socket_fd, data + offset, length - offset, 0);

		if (sent <= 0) {
			return -errno;
		}
		offset += sent;
	}

	return 0;
}

static int post_score(const struct payload *payload)
{
	struct addrinfo hints = {
		.ai_flags = AI_NUMERICSERV,
		.ai_socktype = SOCK_STREAM,
	};
	struct addrinfo *result;
	sec_tag_t sec_tag = CONFIG_MQTT_SAMPLE_TRANSPORT_SEC_TAG;
	char request[REQUEST_HEADER_MAX];
	char response[RESPONSE_MAX];
	int socket_fd = -1;
	int err;
	int request_length;

	err = getaddrinfo(CONFIG_MQTT_SAMPLE_TRANSPORT_HOSTNAME, HTTP_PORT, &hints, &result);
	if (err) {
		LOG_ERR("getaddrinfo failed: %d", err);
		return -EHOSTUNREACH;
	}

	socket_fd = socket(result->ai_family, SOCK_STREAM | SOCK_NATIVE_TLS, IPPROTO_TLS_1_2);
	if (socket_fd < 0) {
		err = -errno;
		goto cleanup;
	}

	err = setsockopt(socket_fd, SOL_TLS, TLS_SEC_TAG_LIST, &sec_tag, sizeof(sec_tag));
	if (err) {
		err = -errno;
		goto cleanup;
	}

	err = setsockopt(socket_fd, SOL_TLS, TLS_HOSTNAME, CONFIG_MQTT_SAMPLE_TRANSPORT_HOSTNAME,
			 strlen(CONFIG_MQTT_SAMPLE_TRANSPORT_HOSTNAME));
	if (err) {
		err = -errno;
		goto cleanup;
	}

	err = connect(socket_fd, result->ai_addr, result->ai_addrlen);
	if (err) {
		err = -errno;
		goto cleanup;
	}

	request_length = snprintk(
		request, sizeof(request),
		"POST /api/scores/%.*s HTTP/1.1\r\n"
		"Host: %s\r\n"
		"Authorization: Bearer %s\r\n"
		"Content-Type: application/json\r\n"
		"Content-Length: %u\r\n"
		"Connection: close\r\n\r\n",
		(int)(payload->topic_len - strlen("games//score")),
		payload->topic + strlen("games/"),
		CONFIG_MQTT_SAMPLE_TRANSPORT_HOSTNAME,
		CONFIG_MQTT_SAMPLE_TRANSPORT_DEVICE_TOKEN,
		(unsigned int)payload->len);
	if (request_length < 0 || request_length >= sizeof(request)) {
		err = -EMSGSIZE;
		goto cleanup;
	}

	err = send_all(socket_fd, request, request_length);
	if (!err) {
		err = send_all(socket_fd, payload->data, payload->len);
	}
	if (err) {
		goto cleanup;
	}

	int received = recv(socket_fd, response, sizeof(response) - 1, 0);
	if (received <= 0) {
		err = received == 0 ? -ECONNRESET : -errno;
		goto cleanup;
	}
	response[received] = '\0';
	if (strncmp(response, "HTTP/1.1 200", strlen("HTTP/1.1 200")) != 0 &&
	    strncmp(response, "HTTP/1.1 202", strlen("HTTP/1.1 202")) != 0) {
		LOG_ERR("Server rejected score: %.32s", response);
		err = -EIO;
	}

cleanup:
	if (socket_fd >= 0) {
		close(socket_fd);
	}
	freeaddrinfo(result);
	return err;
}

static void transport_task(void)
{
	const struct zbus_channel *channel;
	struct payload payload;
	int err;

	while (!zbus_sub_wait(&transport, &channel, K_FOREVER)) {
		if (channel != &PAYLOAD_CHAN) {
			continue;
		}

		err = zbus_chan_read(&PAYLOAD_CHAN, &payload, K_NO_WAIT);
		if (err) {
			LOG_ERR("zbus_chan_read failed: %d", err);
			continue;
		}

		err = post_score(&payload);
		if (err) {
			LOG_ERR("Score upload failed: %d", err);
		} else {
			LOG_INF("Uploaded score to %.*s", payload.topic_len, payload.topic);
		}
	}
}

K_THREAD_DEFINE(transport_task_id, CONFIG_MQTT_SAMPLE_TRANSPORT_THREAD_STACK_SIZE,
		transport_task, NULL, NULL, NULL, 3, 0, 0);
