/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>
#include <zephyr/smf.h>
#include <net/mqtt_helper.h>

#include "client_id.h"
#include "message_channel.h"

LOG_MODULE_REGISTER(transport, CONFIG_LTE_CAMERA_TRANSPORT_LOG_LEVEL);

ZBUS_SUBSCRIBER_DEFINE(transport, CONFIG_LTE_CAMERA_TRANSPORT_MESSAGE_QUEUE_SIZE);

#define SUBSCRIBE_TOPIC_ID 2469

static const struct smf_state state[];
static void connect_work_fn(struct k_work *work);

static K_WORK_DELAYABLE_DEFINE(connect_work, connect_work_fn);

K_THREAD_STACK_DEFINE(stack_area, CONFIG_LTE_CAMERA_TRANSPORT_WORKQUEUE_STACK_SIZE);

static struct k_work_q transport_queue;

enum module_state { MQTT_CONNECTED, MQTT_DISCONNECTED };

static char client_id[CONFIG_LTE_CAMERA_TRANSPORT_CLIENT_ID_BUFFER_SIZE];

static uint8_t pub_topic[sizeof(client_id) + sizeof(CONFIG_LTE_CAMERA_TRANSPORT_PUBLISH_TOPIC)];
static uint8_t sub_topic[sizeof(client_id) + sizeof(CONFIG_LTE_CAMERA_TRANSPORT_SUBSCRIBE_TOPIC)];

enum transport_event_type {
	CONNECTED,
	DISCONNECTED,
};

struct transport_event {
	enum transport_event_type type;
};

ZBUS_CHAN_DEFINE(TRANSPORT_PRIVATE_CHANNEL,
		 struct transport_event,
		 NULL,
		 NULL,
		 ZBUS_OBSERVERS(transport),
		 ZBUS_MSG_INIT(0)
);

static struct s_object {
	struct smf_ctx ctx;

	const struct zbus_channel *chan;

	enum network_status status;

	struct payload payload;
} s_obj;

static void on_mqtt_connack(enum mqtt_conn_return_code return_code, bool session_present)
{
	ARG_UNUSED(return_code);
	ARG_UNUSED(session_present);

	int err;
	struct transport_event event = {
		.type = CONNECTED,
	};

	if (return_code != MQTT_CONNECTION_ACCEPTED) {
		LOG_ERR("MQTT broker rejected connection, return code: %d", return_code);
		return;
	}

	err = zbus_chan_pub(&TRANSPORT_PRIVATE_CHANNEL, &event, K_SECONDS(1));
	if (err) {
		LOG_ERR("zbus_chan_pub, error: %d", err);
		SEND_FATAL_ERROR();
	}
}

static void on_mqtt_disconnect(int result)
{
	int err;
	struct transport_event event = {
		.type = DISCONNECTED,
	};

	err = zbus_chan_pub(&TRANSPORT_PRIVATE_CHANNEL, &event, K_SECONDS(1));
	if (err) {
		LOG_ERR("zbus_chan_pub, error: %d", err);
		SEND_FATAL_ERROR();
	}
}

static void on_mqtt_publish(struct mqtt_helper_buf topic, struct mqtt_helper_buf payload)
{
	LOG_INF("Received payload: %.*s on topic: %.*s", payload.size,
							 payload.ptr,
							 topic.size,
							 topic.ptr);
}

static void on_mqtt_suback(uint16_t message_id, int result)
{
	if ((message_id == SUBSCRIBE_TOPIC_ID) && (result == 0)) {
		LOG_INF("Subscribed to topic %s", sub_topic);
	} else if (result) {
		LOG_ERR("Topic subscription failed, error: %d", result);
	} else {
		LOG_WRN("Subscribed to unknown topic, id: %d", message_id);
	}
}

static int topics_prefix(void)
{
	int len;

	len = snprintk(pub_topic, sizeof(pub_topic), "%s/%s", client_id,
		       CONFIG_LTE_CAMERA_TRANSPORT_PUBLISH_TOPIC);
	if ((len < 0) || (len >= sizeof(pub_topic))) {
		LOG_ERR("Publish topic buffer too small");
		return -EMSGSIZE;
	}

	len = snprintk(sub_topic, sizeof(sub_topic), "%s/%s", client_id,
		       CONFIG_LTE_CAMERA_TRANSPORT_SUBSCRIBE_TOPIC);
	if ((len < 0) || (len >= sizeof(sub_topic))) {
		LOG_ERR("Subscribe topic buffer too small");
		return -EMSGSIZE;
	}

	return 0;
}

static void publish(struct payload *payload)
{
	int err;

	struct mqtt_publish_param param = {
		.message.payload.data = payload->data,
		.message.payload.len = payload->len,
		.message.topic.qos = MQTT_QOS_1_AT_LEAST_ONCE,
		.message_id = mqtt_helper_msg_id_get(),
		.message.topic.topic.utf8 = pub_topic,
		.message.topic.topic.size = strlen(pub_topic),
	};

	err = mqtt_helper_publish(&param);
	if (err) {
		LOG_WRN("Failed to send payload, err: %d", err);
		return;
	}

	LOG_INF("Published %u bytes on topic: \"%.*s\"", param.message.payload.len,
							  param.message.topic.topic.size,
							  param.message.topic.topic.utf8);
}

static void subscribe(void)
{
	int err;

	struct mqtt_topic topics[] = {
		{
			.topic.utf8 = sub_topic,
			.topic.size = strlen(sub_topic),
		},
	};
	struct mqtt_subscription_list list = {
		.list = topics,
		.list_count = ARRAY_SIZE(topics),
		.message_id = SUBSCRIBE_TOPIC_ID,
	};

	for (size_t i = 0; i < list.list_count; i++) {
		LOG_INF("Subscribing to: %s", (char *)list.list[i].topic.utf8);
	}

	err = mqtt_helper_subscribe(&list);
	if (err) {
		LOG_ERR("Failed to subscribe to topics, error: %d", err);
		return;
	}
}

static void connect_work_fn(struct k_work *work)
{
	ARG_UNUSED(work);

	int err;
	struct mqtt_helper_conn_params conn_params = {
		.hostname.ptr = CONFIG_LTE_CAMERA_TRANSPORT_BROKER_HOSTNAME,
		.hostname.size = strlen(CONFIG_LTE_CAMERA_TRANSPORT_BROKER_HOSTNAME),
		.device_id.ptr = client_id,
		.device_id.size = strlen(client_id),
	};

	err = client_id_get(client_id, sizeof(client_id));
	if (err) {
		LOG_ERR("client_id_get, error: %d", err);
		SEND_FATAL_ERROR();
		return;
	}

	err = topics_prefix();
	if (err) {
		LOG_ERR("topics_prefix, error: %d", err);
		SEND_FATAL_ERROR();
		return;
	}

	err = mqtt_helper_connect(&conn_params);
	if (err) {
		LOG_ERR("Failed connecting to MQTT, error code: %d", err);
	}

	k_work_reschedule_for_queue(&transport_queue, &connect_work,
			  K_SECONDS(CONFIG_LTE_CAMERA_TRANSPORT_RECONNECTION_TIMEOUT_SECONDS));
}

static void disconnected_entry(void *o)
{
	struct s_object *user_object = o;

	if (user_object->status == NETWORK_CONNECTED) {
		k_work_reschedule_for_queue(&transport_queue, &connect_work, K_NO_WAIT);
	}
}

static enum smf_state_result disconnected_run(void *o)
{
	struct s_object *user_object = o;

	if ((user_object->status == NETWORK_DISCONNECTED) && (user_object->chan == &NETWORK_CHAN)) {
		k_work_cancel_delayable(&connect_work);
	}

	if ((user_object->status == NETWORK_CONNECTED) && (user_object->chan == &NETWORK_CHAN)) {
		k_work_reschedule_for_queue(&transport_queue, &connect_work, K_SECONDS(5));
	}

	return SMF_EVENT_HANDLED;
}

static void connected_entry(void *o)
{
	LOG_INF("Connected to MQTT broker");
	LOG_INF("Hostname: %s", CONFIG_LTE_CAMERA_TRANSPORT_BROKER_HOSTNAME);
	LOG_INF("Client ID: %s", client_id);
	LOG_INF("Port: %d", CONFIG_MQTT_HELPER_PORT);
	LOG_INF("TLS: %s", IS_ENABLED(CONFIG_MQTT_LIB_TLS) ? "Yes" : "No");

	ARG_UNUSED(o);

	k_work_cancel_delayable(&connect_work);

	subscribe();
}

static enum smf_state_result connected_run(void *o)
{
	struct s_object *user_object = o;

	if ((user_object->status == NETWORK_DISCONNECTED) && (user_object->chan == &NETWORK_CHAN)) {
		(void)mqtt_helper_disconnect();
		return SMF_EVENT_HANDLED;
	}

	if (user_object->chan != &PAYLOAD_CHAN) {
		return SMF_EVENT_HANDLED;
	}

	publish(&user_object->payload);

	return SMF_EVENT_HANDLED;
}

static void connected_exit(void *o)
{
	ARG_UNUSED(o);

	LOG_INF("Disconnected from MQTT broker");
}

static const struct smf_state state[] = {
	[MQTT_DISCONNECTED] = SMF_CREATE_STATE(disconnected_entry, disconnected_run, NULL,
					       NULL, NULL),
	[MQTT_CONNECTED] = SMF_CREATE_STATE(connected_entry, connected_run, connected_exit,
					    NULL, NULL),
};

static void transport_task(void)
{
	int err;
	const struct zbus_channel *chan;
	enum network_status status;
	struct payload payload;
	struct mqtt_helper_cfg cfg = {
		.cb = {
			.on_connack = on_mqtt_connack,
			.on_disconnect = on_mqtt_disconnect,
			.on_publish = on_mqtt_publish,
			.on_suback = on_mqtt_suback,
		},
	};

	k_work_queue_init(&transport_queue);
	k_work_queue_start(&transport_queue, stack_area,
			   K_THREAD_STACK_SIZEOF(stack_area),
			   K_HIGHEST_APPLICATION_THREAD_PRIO,
			   NULL);

	err = mqtt_helper_init(&cfg);
	if (err) {
		LOG_ERR("mqtt_helper_init, error: %d", err);
		SEND_FATAL_ERROR();
		return;
	}

	smf_set_initial(SMF_CTX(&s_obj), &state[MQTT_DISCONNECTED]);

	while (!zbus_sub_wait(&transport, &chan, K_FOREVER)) {
		s_obj.chan = chan;

		if (&NETWORK_CHAN == chan) {
			err = zbus_chan_read(&NETWORK_CHAN, &status, K_SECONDS(1));
			if (err) {
				LOG_ERR("zbus_chan_read, error: %d", err);
				SEND_FATAL_ERROR();
				return;
			}

			s_obj.status = status;

			err = smf_run_state(SMF_CTX(&s_obj));
			if (err) {
				LOG_ERR("smf_run_state, error: %d", err);
				SEND_FATAL_ERROR();
				return;
			}
		}

		if (&PAYLOAD_CHAN == chan) {
			err = zbus_chan_read(&PAYLOAD_CHAN, &payload, K_SECONDS(1));
			if (err) {
				LOG_ERR("zbus_chan_read, error: %d", err);
				SEND_FATAL_ERROR();
				return;
			}

			s_obj.payload = payload;

			err = smf_run_state(SMF_CTX(&s_obj));
			if (err) {
				LOG_ERR("smf_run_state, error: %d", err);
				SEND_FATAL_ERROR();
				return;
			}
		}

		if (&TRANSPORT_PRIVATE_CHANNEL == chan) {
			struct transport_event event;

			err = zbus_chan_read(&TRANSPORT_PRIVATE_CHANNEL, &event, K_SECONDS(1));
			if (err) {
				LOG_ERR("zbus_chan_read, error: %d", err);
				SEND_FATAL_ERROR();
				return;
			}

			switch (event.type) {
			case CONNECTED:
				smf_set_state(SMF_CTX(&s_obj), &state[MQTT_CONNECTED]);
				break;
			case DISCONNECTED:
				smf_set_state(SMF_CTX(&s_obj), &state[MQTT_DISCONNECTED]);
				break;
			default:
				LOG_WRN("Unknown MQTT event type: %d", event.type);
				break;
			}
		}
	}
}

K_THREAD_DEFINE(transport_task_id,
		CONFIG_LTE_CAMERA_TRANSPORT_THREAD_STACK_SIZE,
		transport_task, NULL, NULL, NULL, 3, 0, 0);
