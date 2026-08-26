/*
 * Copyright (c) 2020 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <string.h>
#include <zephyr/kernel.h>
#include <stdlib.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/conn_mgr_monitor.h>
#include <zephyr/net/conn_mgr_connectivity.h>
#include <zephyr/net/tls_credentials.h>

#if defined(CONFIG_POSIX_API)
#include <zephyr/posix/arpa/inet.h>
#include <zephyr/posix/netdb.h>
#include <zephyr/posix/unistd.h>
#include <zephyr/posix/sys/socket.h>
#endif

#if CONFIG_MODEM_KEY_MGMT
#include <modem/modem_key_mgmt.h>
#endif

#define HTTPS_PORT		"443"

/* Request template. The game path segment and JSON body come from the UART
 * line received from the hub ("<game>|<json>").
 */
#define HTTP_REQUEST_TEMPLATE						\
				"POST /api/scores/%.*s HTTP/1.1\r\n"		\
				"Host: " CONFIG_HTTPS_HOSTNAME "\r\n"		\
				"Authorization: Bearer " CONFIG_HTTPS_DEVICE_TOKEN "\r\n" \
				"Content-Type: application/json\r\n"		\
				"Content-Length: %u\r\n"			\
				"Connection: close\r\n\r\n"			\
				"%.*s"

#define HTTP_HDR_END		"\r\n\r\n"

#define SEND_BUF_SIZE		512
#define RECV_BUF_SIZE		2048
#define TLS_SEC_TAG		42

/* Longest UART line accepted from the hub: "<game>|<json>". */
#define UART_LINE_MAX		256

/* Macros used to subscribe to specific Zephyr NET management events. */
#define L4_EVENT_MASK		(NET_EVENT_L4_CONNECTED | NET_EVENT_L4_DISCONNECTED)
#define CONN_LAYER_EVENT_MASK	(NET_EVENT_CONN_IF_FATAL_ERROR)

static char send_buf[SEND_BUF_SIZE];
static char recv_buf[RECV_BUF_SIZE];
static K_SEM_DEFINE(network_connected_sem, 0, 1);
static volatile bool network_connected;

/* Link to the hub firmware. It streams one newline-terminated line per score:
 *     <game>|<json>\n   e.g.  snake_voice|{"score":1200}
 */
static const struct device *const uart_dev = DEVICE_DT_GET(DT_NODELABEL(uart1));

struct game_line {
	uint8_t buf[UART_LINE_MAX];
	uint16_t len;
};

K_MSGQ_DEFINE(line_msgq, sizeof(struct game_line), 8, 4);

/* Filled one byte at a time by the ISR. */
static uint8_t rx_line[UART_LINE_MAX];
static uint16_t rx_len;

/* ISR context: accumulate bytes until newline, then queue the completed line.
 * Must not block, so it only touches the msgq with K_NO_WAIT.
 */
static void uart_cb(const struct device *dev, void *user_data)
{
	uint8_t byte;

	if (!uart_irq_update(dev) || !uart_irq_rx_ready(dev)) {
		return;
	}

	while (uart_fifo_read(dev, &byte, 1) == 1) {
		if (byte == '\r') {
			continue;
		}

		if (byte == '\n') {
			if (rx_len > 0) {
				struct game_line line;

				memcpy(line.buf, rx_line, rx_len);
				line.len = rx_len;
				(void)k_msgq_put(&line_msgq, &line, K_NO_WAIT);
			}
			rx_len = 0;
			continue;
		}

		if (rx_len < sizeof(rx_line)) {
			rx_line[rx_len++] = byte;
		} else {
			/* Overrun: drop the line and resync at the next newline. */
			rx_len = 0;
		}
	}
}

static int uart_bridge_init(void)
{
	int err;

	if (!device_is_ready(uart_dev)) {
		printk("UART device not ready\n");
		return -ENODEV;
	}

	err = uart_irq_callback_user_data_set(uart_dev, uart_cb, NULL);
	if (err) {
		printk("uart_irq_callback_user_data_set, err %d\n", err);
		return err;
	}

	uart_irq_rx_enable(uart_dev);
	printk("UART bridge ready, listening on uart1\n");
	return 0;
}
/* Certificate for `example.com` */
static const char cert[] = {
	#include "example_com_ca.pem.inc"

	/* Null terminate certificate if running Mbed TLS on the application core.
	 * Required by TLS credentials API.
	 */
	IF_ENABLED(CONFIG_TLS_CREDENTIALS, (0x00))
};

/* Zephyr NET management event callback structures. */
static struct net_mgmt_event_callback l4_cb;
static struct net_mgmt_event_callback conn_cb;

BUILD_ASSERT(sizeof(cert) < KB(4), "Certificate too large");

/* Provision certificate to modem */
int cert_provision(void)
{
	int err;

	printk("Provisioning certificate\n");

#if CONFIG_MODEM_KEY_MGMT
	bool exists;
	int mismatch;

	/* It may be sufficient for you application to check whether the correct
	 * certificate is provisioned with a given tag directly using modem_key_mgmt_cmp().
	 * Here, for the sake of the completeness, we check that a certificate exists
	 * before comparing it with what we expect it to be.
	 */
	err = modem_key_mgmt_exists(TLS_SEC_TAG, MODEM_KEY_MGMT_CRED_TYPE_CA_CHAIN, &exists);
	if (err) {
		printk("Failed to check for certificates err %d\n", err);
		return err;
	}

	if (exists) {
		mismatch = modem_key_mgmt_cmp(TLS_SEC_TAG, MODEM_KEY_MGMT_CRED_TYPE_CA_CHAIN, cert,
					      sizeof(cert));
		if (!mismatch) {
			printk("Certificate match\n");
			return 0;
		}

		printk("Certificate mismatch\n");
		err = modem_key_mgmt_delete(TLS_SEC_TAG, MODEM_KEY_MGMT_CRED_TYPE_CA_CHAIN);
		if (err) {
			printk("Failed to delete existing certificate, err %d\n", err);
		}
	}

	printk("Provisioning certificate to the modem\n");

	/*  Provision certificate to the modem */
	err = modem_key_mgmt_write(TLS_SEC_TAG, MODEM_KEY_MGMT_CRED_TYPE_CA_CHAIN, cert,
				   sizeof(cert));
	if (err) {
		printk("Failed to provision certificate, err %d\n", err);
		return err;
	}
#else /* CONFIG_MODEM_KEY_MGMT */
	err = tls_credential_add(TLS_SEC_TAG,
				 TLS_CREDENTIAL_CA_CERTIFICATE,
				 cert,
				 sizeof(cert));
	if (err == -EEXIST) {
		printk("CA certificate already exists, sec tag: %d\n", TLS_SEC_TAG);
	} else if (err < 0) {
		printk("Failed to register CA certificate: %d\n", err);
		return err;
	}
#endif /* !CONFIG_MODEM_KEY_MGMT */

	return 0;
}


/* Setup TLS options on a given socket */
int tls_setup(int fd)
{
	int err;
	int verify;

	/* Security tag that we have provisioned the certificate with */
	const sec_tag_t tls_sec_tag[] = {
		TLS_SEC_TAG,
	};

	/* Set up TLS peer verification */
	enum {
		NONE = 0,
		OPTIONAL = 1,
		REQUIRED = 2,
	};

	/* Demo only: skip certificate verification so the fake score reaches the
	 * server without provisioning the Fly (Let's Encrypt) CA. Set to REQUIRED
	 * and provision the correct CA for real use.
	 */
	verify = NONE;

	err = setsockopt(fd, SOL_TLS, TLS_PEER_VERIFY, &verify, sizeof(verify));
	if (err) {
		printk("Failed to setup peer verification, err %d\n", errno);
		return err;
	}

	/* Associate the socket with the security tag
	 * we have provisioned the certificate with.
	 */
	err = setsockopt(fd, SOL_TLS, TLS_SEC_TAG_LIST, tls_sec_tag, sizeof(tls_sec_tag));
	if (err) {
		printk("Failed to setup TLS sec tag, err %d\n", errno);
		return err;
	}

	err = setsockopt(fd, SOL_TLS, TLS_HOSTNAME,
			CONFIG_HTTPS_HOSTNAME,
			sizeof(CONFIG_HTTPS_HOSTNAME) - 1);
	if (err) {
		printk("Failed to setup TLS hostname, err %d\n", errno);
		return err;
	}
	return 0;
}

static void on_net_event_l4_disconnected(void)
{
	network_connected = false;
	printk("Disconnected from the network\n");
}

static void on_net_event_l4_connected(void)
{
	network_connected = true;
	k_sem_give(&network_connected_sem);
}

static void l4_event_handler(struct net_mgmt_event_callback *cb,
			     uint64_t event,
			     struct net_if *iface)
{
	switch (event) {
	case NET_EVENT_L4_CONNECTED:
		printk("Network connectivity established and IP address assigned\n");
		on_net_event_l4_connected();
		break;
	case NET_EVENT_L4_DISCONNECTED:
		printk("Network connectivity lost\n");
		on_net_event_l4_disconnected();
		break;
	default:
		break;
	}
}

static void connectivity_event_handler(struct net_mgmt_event_callback *cb,
				       uint64_t event,
				       struct net_if *iface)
{
	if (event == NET_EVENT_CONN_IF_FATAL_ERROR) {
		printk("Fatal error received from the connectivity layer\n");
		return;
	}
}

static void send_http_request(const char *game, size_t game_len,
			      const char *json, size_t json_len)
{
	int err;
	int fd;
	char *p;
	int bytes;
	int req_len;
	size_t off;
	struct addrinfo *res;
	struct addrinfo hints = {
		.ai_flags = AI_NUMERICSERV, /* Let getaddrinfo() set port */
		.ai_socktype = SOCK_STREAM,
	};
	char peer_addr[INET6_ADDRSTRLEN];

	req_len = snprintk(send_buf, sizeof(send_buf), HTTP_REQUEST_TEMPLATE,
			   (int)game_len, game, (unsigned int)json_len,
			   (int)json_len, json);
	if ((req_len < 0) || (req_len >= (int)sizeof(send_buf))) {
		printk("Request too large for send buffer\n");
		return;
	}

	printk("Posting score to /api/scores/%.*s\n", (int)game_len, game);

	printk("Looking up %s\n", CONFIG_HTTPS_HOSTNAME);

	err = getaddrinfo(CONFIG_HTTPS_HOSTNAME, HTTPS_PORT, &hints, &res);
	if (err) {
		printk("getaddrinfo() failed, err %d\n", errno);
		return;
	}

	inet_ntop(res->ai_family, &((struct sockaddr_in *)(res->ai_addr))->sin_addr, peer_addr,
		  INET6_ADDRSTRLEN);
	printk("Resolved %s (%s)\n", peer_addr, net_family2str(res->ai_family));

	if (IS_ENABLED(CONFIG_SAMPLE_TFM_MBEDTLS)) {
		fd = socket(res->ai_family, SOCK_STREAM | SOCK_NATIVE_TLS, IPPROTO_TLS_1_2);
	} else {
		fd = socket(res->ai_family, SOCK_STREAM, IPPROTO_TLS_1_2);
	}
	if (fd == -1) {
		printk("Failed to open socket!\n");
		goto clean_up;
	}

	/* Setup TLS socket options */
	err = tls_setup(fd);
	if (err) {
		goto clean_up;
	}

	printk("Connecting to %s:%d\n", CONFIG_HTTPS_HOSTNAME,
	       ntohs(((struct sockaddr_in *)(res->ai_addr))->sin_port));
	err = connect(fd, res->ai_addr, res->ai_addrlen);
	if (err) {
		printk("connect() failed, err: %d\n", errno);
		goto clean_up;
	}

	off = 0;
	do {
		bytes = send(fd, &send_buf[off], req_len - off, 0);
		if (bytes < 0) {
			printk("send() failed, err %d\n", errno);
			goto clean_up;
		}
		off += bytes;
	} while (off < (size_t)req_len);

	printk("Sent %d bytes\n", off);

	off = 0;
	do {
		bytes = recv(fd, &recv_buf[off], RECV_BUF_SIZE - off, 0);
		if (bytes < 0) {
			printk("recv() failed, err %d\n", errno);
			goto clean_up;
		}
		off += bytes;
	} while (bytes != 0 /* peer closed connection */);

	printk("Received %d bytes\n", off);

	/* Make sure recv_buf is NULL terminated (for safe use with strstr) */
	if (off < sizeof(recv_buf)) {
		recv_buf[off] = '\0';
	} else {
		recv_buf[sizeof(recv_buf) - 1] = '\0';
	}

	/* Print HTTP response */
	p = strstr(recv_buf, "\r\n");
	if (p) {
		off = p - recv_buf;
		recv_buf[off + 1] = '\0';
		printk("\n>\t %s\n\n", recv_buf);
	}

	printk("Finished, closing socket.\n");

clean_up:
	freeaddrinfo(res);
	(void)close(fd);
}

int main(void)
{
	int err;

	printk("HTTPS client sample started\n\r");

	/* Setup handler for Zephyr NET Connection Manager events. */
	net_mgmt_init_event_callback(&l4_cb, l4_event_handler, L4_EVENT_MASK);
	net_mgmt_add_event_callback(&l4_cb);

	/* Setup handler for Zephyr NET Connection Manager Connectivity layer. */
	net_mgmt_init_event_callback(&conn_cb, connectivity_event_handler, CONN_LAYER_EVENT_MASK);
	net_mgmt_add_event_callback(&conn_cb);

	printk("Bringing network interface up\n");

	/* Connecting to the configured connectivity layer.
	 * Wi-Fi or LTE depending on the board that the sample was built for.
	 */
	err = conn_mgr_all_if_up(true);
	if (err) {
		printk("conn_mgr_all_if_up, error: %d\n", err);
		return err;
	}

	 /* Provision certificates before connecting to the network */
	err = cert_provision();
	if (err) {
		return 0;
	}

	printk("Connecting to the network\n");

	err = conn_mgr_all_if_connect(true);
	if (err) {
		printk("conn_mgr_all_if_connect, error: %d\n", err);
		return 0;
	}

	/* Resend connection status if the sample is built for NATIVE_SIM.
	 * This is necessary because the network interface is automatically brought up
	 * at SYS_INIT() before main() is called.
	 * This means that NET_EVENT_L4_CONNECTED fires before the
	 * appropriate handler l4_event_handler() is registered.
	 */
	if (IS_ENABLED(CONFIG_BOARD_NATIVE_SIM)) {
		conn_mgr_mon_resend_status();
	}

	k_sem_take(&network_connected_sem, K_FOREVER);

	err = uart_bridge_init();
	if (err) {
		return 0;
	}

	printk("Waiting for game scores on uart1...\n");

	while (true) {
		struct game_line line;
		uint8_t *sep;
		size_t game_len, json_len;

		k_msgq_get(&line_msgq, &line, K_FOREVER);

		/* Wait for the network to come back if it dropped. */
		while (!network_connected) {
			k_sem_take(&network_connected_sem, K_FOREVER);
		}

		/* Split on the first '|': left = game name, right = JSON body. */
		sep = memchr(line.buf, '|', line.len);
		if ((sep == NULL) || (sep == line.buf) ||
		    ((size_t)(sep - line.buf) == line.len - 1)) {
			printk("Malformed line, expected <game>|<json>\n");
			continue;
		}

		game_len = sep - line.buf;
		json_len = line.len - game_len - 1;

		send_http_request((const char *)line.buf, game_len,
				  (const char *)(sep + 1), json_len);
	}

	return 0;
}
