# camera_to_website

```
Arducam Mega --SPI--> nRF9151 DK --MQTT over LTE-M--> broker
```

## Wiring

The camera goes on the DK's Arduino SPI header, already wired as `spi3`.

| Arducam | nRF9151 | Header |
|---|---|---|
| SCK | P0.13 | D13 |
| MISO | P0.12 | D12 |
| MOSI | P0.11 | D11 |
| CS | P0.10 | D10 |
| VCC | VDD | power header |
| GND | GND | power header |

**Set the VDD (nPM VOUT1) rail to 3.3 V in nRF Connect's Board Configurator.**

## Build and flash

```bash
west build -b nrf9151dk/nrf9151/ns
west flash
```

## Configuration

App options use the `LTE_CAMERA_` prefix, in `prj.conf`:

```
CONFIG_LTE_CAMERA_CAMERA_WIDTH=320
CONFIG_LTE_CAMERA_CAMERA_HEIGHT=320
CONFIG_LTE_CAMERA_PAYLOAD_CHANNEL_STRING_MAX_SIZE=16384
CONFIG_LTE_CAMERA_TRANSPORT_BROKER_HOSTNAME="broker.hivemq.com"
```

Resolution must be an **exact pair** the sensor supports, 96x96, 128x128,
320x240, 320x320, 640x480, 1280x720, 1600x1200, or the sensor maximum. Anything
else fails with `-ENOTSUP` and logs `Image resolution not supported`.

The whole JPEG must fit the payload buffer. At 320x320 a capture is 9–13 KB
against the 16 KB cap, so a higher resolution means raising that too ,  and RAM is
the ceiling. Warm-up frame count is `WARMUP_FRAMES` in `src/modules/camera/camera.c`.

## Structure

No `main()`. Zephyr starts one thread per module; they communicate over zbus
channels declared in `src/common/message_channel.c`:

```
trigger ---TRIGGER_CHAN---> camera ---PAYLOAD_CHAN---> transport ---> MQTT
```

| Module | Role |
|---|---|
| `src/modules/trigger/` | Buttons → `TRIGGER_CAPTURE` / `TRIGGER_ANON` |
| `src/modules/camera/` | Owns the camera; captures and publishes the JPEG |
| `src/modules/network/` | Brings up LTE |
| `src/modules/transport/` | Connects to the broker and publishes |

Camera setup that would normally sit in `main()` is in `camera_init()`, called at
the top of `camera_task()`.

Everything except `camera/` and `trigger/` is Nordic's NCS `cellular/mqtt` sample.
`src/drivers/arducam_mega.c` is an Arducam vendor driver adapted by Nordic
(Apache-2.0).

## How a capture works

1. Button interrupt, with a 200 ms debounce.
2. Five frames captured and overwritten, the sixth kept ,  auto-exposure and gain
   are feedback loops that need frames to converge, so the first is nearly black.
3. The camera streams over SPI in chunks of up to 1024 bytes, padded before and
   after the real image. Nothing says where the picture starts or ends.
4. Scan forward for `FF D9` (which also means "photo finished"), then from the
   start for `FF D8`, and keep what's between. Each scan restarts one byte back so
   a marker split across chunks is still caught.
5. The trimmed JPEG goes on `PAYLOAD_CHAN` and `transport` publishes it.

The Arducam does the JPEG encoding in hardware ,  the firmware sets `CAM_REG_FORMAT`
once and never touches a pixel. The photo lives in one static buffer, is never
written to flash, and is overwritten by the next capture.

Button 2 publishes the 18-byte string `ANON_PHOTO_REQUEST` instead of a photo; the
backend substitutes a random stand-in image.

## MQTT

Client ID is the modem's **IMEI** (`CONFIG_LTE_CAMERA_TRANSPORT_CLIENT_ID` is
empty, so `hw_id_get()` supplies it). Publishes to `<IMEI>/my/publish/topic`; the
subscriber uses a `+` wildcard so nothing needs configuring per device.

Payload is the **raw JPEG bytes** ,  no base64, no wrapper. QoS 1, so a photo may
arrive twice but won't silently vanish.

## Limitations

- **Plaintext on a public broker** (port 1883, no TLS). `overlay-tls-nrf91.conf`
  exists but isn't applied unless passed to `west build`.
- **Resolution capped** by the payload buffer and available RAM.
- **The stream is torn down after each photo**, so warm-up is paid every press.

## Status

Builds clean. **Not verified on hardware** ,  wiring, the VDD setting, and capture
timing against a live LTE connection are untested.
