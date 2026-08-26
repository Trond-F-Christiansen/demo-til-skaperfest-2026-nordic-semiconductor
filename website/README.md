# Website

The website is a single HTTP service. It serves the scoreboard and receives
HTTPS score uploads from the game hub; MQTT is not used. Every accepted score
receives a random image from `backend/anon_photos/`.

```text
hub ------ HTTPS POST /api/scores ----> website service
browser -- HTTPS GET/POST ------------> |
                                      +-- random photos and state on disk
```

## API

| Route | Caller | Request |
| --- | --- | --- |
| `POST /api/scores/<game>` | Hub | Score JSON and device bearer token |
| `GET /api/state` | Browser | Current leaderboard and pending queue |
| `POST /api/admin/delete` | Browser | Entry and admin password |
| `POST /api/admin/reset` | Browser | Admin password |

Scores use the existing JSON payload:

```json
{"score":1200}
```

The available game IDs are `snake_voice` for __Snake (stemme)__,
`snake_geusture` for __Snake (bevegelse)__, and `minesweeper` for
__Minesweeper__.

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

The Fly volume mounts at `/data`. It stores the page, state, photos, and backup.
Run one Machine because the application uses a local filesystem volume.

## Firmware Configuration

The game hub uses HTTPS POST over port `443`.

Set the Fly hostname and device token in the hub application configuration:

```text
CONFIG_MQTT_SAMPLE_TRANSPORT_HOSTNAME="<app>.fly.dev"
CONFIG_MQTT_SAMPLE_TRANSPORT_DEVICE_TOKEN="<device-token>"
```

The modem security tag must contain a CA certificate that trusts the Fly
certificate for `<app>.fly.dev`. The default security tag is `955`. Provision
the CA certificate before flashing the hub firmware.

## Scoring Rules

Every valid score is added immediately. The last submitted score appears first
without a rank and is highlighted. Older Snake and Quiz scores rank high-to-low;
older Minesweeper scores rank low-to-high. Scores receive a randomly chosen
bundled image and an anonymous two-word player alias. Camera photo uploads are
ignored.
