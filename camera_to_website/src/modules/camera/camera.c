/*
 * Copyright (c) 2026 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/led.h>
#include <zephyr/drivers/video.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>

#include "message_channel.h"

LOG_MODULE_REGISTER(camera, CONFIG_CAMERA_TO_WEBSITE_CAMERA_LOG_LEVEL);

ZBUS_SUBSCRIBER_DEFINE(camera, CONFIG_CAMERA_TO_WEBSITE_CAMERA_MESSAGE_QUEUE_SIZE);

#define CAM_WIDTH  CONFIG_CAMERA_TO_WEBSITE_CAMERA_WIDTH
#define CAM_HEIGHT CONFIG_CAMERA_TO_WEBSITE_CAMERA_HEIGHT

#define WARMUP_FRAMES 5

#define ANON_PHOTO_MARKER "ANON_PHOTO_REQUEST"

static const struct device *const video = DEVICE_DT_GET(DT_NODELABEL(arducam_mega));
static const struct device *const leds = DEVICE_DT_GET_ANY(gpio_leds);

#define LED_CAPTURE 0

static struct payload capture;

static void capture_led_set(bool on)
{
	int err;

	if (!device_is_ready(leds)) {
		return;
	}

	err = on ? led_on(leds, LED_CAPTURE) : led_off(leds, LED_CAPTURE);
	if (err) {
		LOG_WRN("Failed to drive capture LED (err %d)", err);
	}
}

static int capture_one_frame(uint8_t *out, size_t out_size)
{
	size_t total = 0;
	size_t scan = 0;
	int consecutive_timeouts = 0;

	while (true) {
		struct video_buffer *vbuf;
		int err = video_dequeue(video, &vbuf, K_MSEC(500));

		if (err == -EAGAIN) {
			consecutive_timeouts++;
			LOG_WRN("video_dequeue timed out (%d/6), %u bytes accumulated so far",
				consecutive_timeouts, total);
			if (consecutive_timeouts >= 6) {
				LOG_ERR("video_dequeue: no data for 3s, giving up on this capture");
				return -ETIMEDOUT;
			}
			continue;
		}
		consecutive_timeouts = 0;

		if (err) {
			LOG_ERR("video_dequeue failed: %d", err);
			return err;
		}

		const size_t chunk = MIN(vbuf->bytesused, out_size - total);

		memcpy(&out[total], vbuf->buffer, chunk);
		total += chunk;

		vbuf->type = VIDEO_BUF_TYPE_OUTPUT;
		video_enqueue(video, vbuf);

		for (size_t i = (scan == 0 ? 1 : scan); i < total; i++) {
			if (out[i - 1] == 0xFF && out[i] == 0xD9) {
				const size_t end = i + 1;

				for (size_t j = 1; j < end; j++) {
					if (out[j - 1] == 0xFF && out[j] == 0xD8) {
						const size_t soi = j - 1;
						const size_t len = end - soi;

						memmove(out, &out[soi], len);
						return (int)len;
					}
				}

				LOG_ERR("Found EOI but no SOI marker");
				return -EILSEQ;
			}
		}
		scan = total;

		if (total >= out_size) {
			LOG_ERR("JPEG larger than buffer (%u)", out_size);
			return -ENOMEM;
		}
	}
}

static void payload_publish(void)
{
	int err = zbus_chan_pub(&PAYLOAD_CHAN, &capture, K_SECONDS(1));

	if (err) {
		LOG_ERR("zbus_chan_pub, error: %d", err);
		SEND_FATAL_ERROR();
		return;
	}

	LOG_INF("Published %u bytes to PAYLOAD_CHAN", capture.len);
}

static void capture_and_publish(void)
{
	int err;
	int len;

	capture_led_set(true);

	err = video_stream_start(video, VIDEO_BUF_TYPE_OUTPUT);
	if (err) {
		LOG_ERR("Failed to start stream (err %d)", err);
		capture_led_set(false);
		return;
	}

	for (int i = 0; i <= WARMUP_FRAMES; i++) {
		len = capture_one_frame(capture.data, sizeof(capture.data));
		if (len < 0) {
			LOG_ERR("Failed to capture frame (err %d)", len);
			(void)video_stream_stop(video, VIDEO_BUF_TYPE_OUTPUT);
			capture_led_set(false);
			return;
		}
	}

	err = video_stream_stop(video, VIDEO_BUF_TYPE_OUTPUT);
	if (err) {
		LOG_ERR("Failed to stop stream (err %d)", err);
		capture_led_set(false);
		return;
	}

	capture.len = (size_t)len;
	LOG_INF("Captured JPEG: %d bytes", len);

	payload_publish();

	capture_led_set(false);
}

static void publish_anon_request(void)
{
	capture_led_set(true);

	memcpy(capture.data, ANON_PHOTO_MARKER, sizeof(ANON_PHOTO_MARKER) - 1);
	capture.len = sizeof(ANON_PHOTO_MARKER) - 1;
	payload_publish();

	k_sleep(K_MSEC(150));
	capture_led_set(false);
}

static int camera_init(void)
{
	static struct video_buffer *vbufs[2];
	struct video_format fmt = {
		.type = VIDEO_BUF_TYPE_INPUT,
		.pixelformat = VIDEO_PIX_FMT_JPEG,
		.width = CAM_WIDTH,
		.height = CAM_HEIGHT,
	};
	int err;

	if (!device_is_ready(video)) {
		LOG_ERR("Video device not ready");
		return -ENODEV;
	}

	err = video_set_format(video, &fmt);
	if (err) {
		LOG_ERR("Setting video format %ux%u failed (err %d)", CAM_WIDTH, CAM_HEIGHT, err);
		return err;
	}

	for (size_t i = 0; i < ARRAY_SIZE(vbufs); i++) {
		vbufs[i] = video_buffer_alloc(1024, K_NO_WAIT);
		if (vbufs[i] == NULL) {
			LOG_ERR("Allocation failed for video buffer %u", i);
			return -ENOMEM;
		}
		vbufs[i]->type = VIDEO_BUF_TYPE_OUTPUT;
		video_enqueue(video, vbufs[i]);
	}

	return 0;
}

static void camera_task(void)
{
	const struct zbus_channel *chan;

	if (camera_init() != 0) {
		SEND_FATAL_ERROR();
		return;
	}

	LOG_INF("Camera ready at %ux%u: button 1 = photo, button 2 = anonymous photo",
		CAM_WIDTH, CAM_HEIGHT);

	while (!zbus_sub_wait(&camera, &chan, K_FOREVER)) {
		enum trigger_type type;

		if (&TRIGGER_CHAN != chan) {
			continue;
		}

		if (zbus_chan_read(&TRIGGER_CHAN, &type, K_SECONDS(1))) {
			LOG_WRN("Failed to read trigger type, ignoring press");
			continue;
		}

		switch (type) {
		case TRIGGER_CAPTURE:
			capture_and_publish();
			break;
		case TRIGGER_ANON:
			publish_anon_request();
			break;
		default:
			LOG_WRN("Unknown trigger type %d", type);
			break;
		}
	}
}

K_THREAD_DEFINE(camera_task_id,
		CONFIG_CAMERA_TO_WEBSITE_CAMERA_THREAD_STACK_SIZE,
		camera_task, NULL, NULL, NULL, 3, 0, 0);
