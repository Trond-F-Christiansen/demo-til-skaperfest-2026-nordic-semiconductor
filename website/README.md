# Website

The website is a single HTTP service. It serves the scoreboard and receives
HTTPS uploads from the camera and game hub; MQTT is not used.

```text
camera --- HTTPS POST /api/photos ---\
hub ------ HTTPS POST /api/scores ---+--> website service
browser -- HTTPS GET/POST ------------/    |
                                             +-- state and photos on disk
```

## API

| Route | Caller | Request |
| --- | --- | --- |
| `POST /api/photos` | Camera | JPEG body and device bearer token |
| `POST /api/scores/<game>` | Hub | Score JSON and device bearer token |
| `GET /api/state` | Browser | Current leaderboard and pending queue |
| `POST /api/admin/delete` | Browser | Entry and admin password |
| `POST /api/admin/delete-pending` | Browser | Session and admin password |
| `POST /api/admin/reset` | Browser | Admin password |

Scores use the existing JSON payload:

```json
{"session_id":"snake-0","score":1200}
```

## Local Run

Start the unified API and static page server:

```bash
cd website
ADMIN_PASSWORD='choose-a-password' \
DEVICE_API_TOKEN='choose-a-device-token' \
python3 backend/mqtt_listener.py
```

Open `http://localhost:8000/`. The service creates `site/state.json`,
`site/photos/`, and `site/backup/photos/` when absent.

## Fly Deployment

1. Set a unique `app` name in `fly.toml`.
2. Create the persistent volume once:

```bash
cd website
fly volumes create website_data --region ams --size 1
```

3. Store credentials as Fly secrets:

```bash
fly secrets set ADMIN_PASSWORD='choose-a-password'
fly secrets set DEVICE_API_TOKEN='choose-a-device-token'
```

4. Deploy one always-on Machine:

```bash
fly deploy
```

The Fly volume mounts at `/data`. It stores the page, state, photos, and backup;
do not scale beyond one Machine because the pending queue is process-local.

## Firmware Configuration

Both nRF9151 applications now use HTTPS POST over port `443`.

Set the Fly hostname and the same device token in the application configuration:

```text
CONFIG_CAMERA_TO_WEBSITE_TRANSPORT_HOSTNAME="<app>.fly.dev"
CONFIG_CAMERA_TO_WEBSITE_TRANSPORT_DEVICE_TOKEN="<device-token>"
CONFIG_MQTT_SAMPLE_TRANSPORT_HOSTNAME="<app>.fly.dev"
CONFIG_MQTT_SAMPLE_TRANSPORT_DEVICE_TOKEN="<device-token>"
```

The modem security tag must contain a CA certificate that trusts the Fly
certificate for `<app>.fly.dev`. The default security tag is `955`. Provision
the CA certificate before flashing the camera or hub firmware.

## Pairing Rules

Snake and Quiz rank high-to-low; Minesweeper ranks low-to-high. Qualifying
scores wait in FIFO order for the next photo. A photo with no pending score is
discarded.
Expired scores are added without a photo when a later request arrives.
