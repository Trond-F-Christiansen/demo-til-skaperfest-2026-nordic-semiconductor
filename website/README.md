# web

The receiving half of the camera system: a Python script that listens on an MQTT
broker, and the static page that shows the result.

The camera board publishes a photo on a button press. Three game consoles publish a score
when a round ends. This project pairs them and uploads the result to static web
hosting. The camera firmware is the companion `camera_to_website` project; the two meet
only at the broker.

```
camera ─┐                    ┌── game consoles
        v                    v
    broker.hivemq.com  <── admin/* from the page
        │
        v
    backend/mqtt_listener.py ──SFTP──> folk.ntnu.no ──polled every 5 s──> site/
```

## Layout

| Path | What it is |
|---|---|
| `backend/mqtt_listener.py` | The whole backend |
| `backend/anon_photos/` | 39 stand-in images for players who opt out |
| `backend/requirements.txt` | `paho-mqtt`, `paramiko` |
| `site/index.html` | The static page |

**`site/` is the only directory that goes public.** Nothing in `backend/` should
reach the web host, the anon photos are meant to be served by chance, not
browsable as a folder.

## Why the backend exists

`folk.ntnu.no` serves files and nothing else: no processes, no database, no MQTT.
It can't subscribe, and the camera board can't write files. So something has to sit in
between, and it has to run elsewhere, a laptop, a Pi, a small VPS.

It's also the only place that can hold state: the photo comes from the camera, the
scores from three consoles, and neither knows the other exists. Only something
watching both can pair them. That constraint is also why the page polls instead of
being pushed to.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create the web host folders once, the script can upload into an existing
directory but can't create a missing one:

```bash
sftp <username>@login.stud.ntnu.no
sftp> cd /web/folk/<username>
sftp> mkdir photos
sftp> mkdir backup
sftp> mkdir backup/photos
sftp> put site/index.html
```

## Running it

```bash
cd backend
source .venv/bin/activate
NTNU_PASSWORD=your_ntnu_password python mqtt_listener.py
```

Expected output:

```
Loaded existing state: N leaderboard entries
Connected to broker.hivemq.com (reason: Success)
Subscribed to: +/my/publish/topic, games/+/score, admin/delete, ...
```

| Variable | Required | Effect |
|---|---|---|
| `NTNU_PASSWORD` | yes | SFTP password. Missing → immediate `KeyError`. |
| `ADMIN_PASSWORD` | no | Enables delete/reset. Unset means always rejected. |
| `LEADERBOARD_SIZE` | no | Entries per game. Default 50. |
| `AWAITING_PHOTO_EXPIRY_SECONDS` | no | Default 300. Lower it to test expiry. |

## Topics

| Topic | Who publishes | Payload |
|---|---|---|
| `+/my/publish/topic` | the camera | raw JPEG bytes, or `ANON_PHOTO_REQUEST` |
| `games/+/score` | consoles | `{"session_id": "...", "score": <number>}` |
| `admin/delete` | the page | `{"game", "entry_id", "password"}` |
| `admin/delete_pending` | the page | `{"session_id", "password"}` |
| `admin/reset` | the page | `{"action": "reset", "password"}` |

The backend subscribes to all five and publishes nothing, its output leaves over
SFTP instead. `+` matches one level: any IMEI in the first case, all three consoles
in the second.

Subscriptions happen inside `on_connect`, not at startup, so a reconnect
re-subscribes. Otherwise the script would sit connected but deaf.

## Pairing rules

A score is ranked against its game's leaderboard, Snake and Quiz high-to-low,
Minesweeper low-to-high because there the score is a completion time. If it doesn't
make the cut it's dropped immediately.

If it qualifies it joins a FIFO queue, and nothing is uploaded yet. When a photo
arrives, the **oldest** queued score is paired with it, the photo is uploaded under
a random filename, and the entry goes on the leaderboard.

Two exceptions worth knowing:

- **A photo with an empty queue is discarded.** Pressing the camera button cold
  looks like a failure for this reason, send a score first.
- **A score waiting past the expiry** is added without a photo. Checked lazily when
  another message arrives, so there's no background timer and no locking.

If the payload is exactly the 18 bytes `ANON_PHOTO_REQUEST`, a random image from
`anon_photos/` is substituted. Real photos start with `FF D8`, which that string
doesn't, so the two can't be confused.

`state.json` is uploaded to a temp name then renamed, so a dropped connection can't
leave unparsable JSON live on the site.

## The page

`site/index.html` fetches `state.json` every 5 seconds and re-renders only when
`updated_at` changed, otherwise images would reload and flicker every poll.

Admin actions go **straight to the broker** over WebSockets at
`wss://broker.hivemq.com:8884/mqtt`, `wss://` and port 8884, since browsers block
plaintext as mixed content on an HTTPS page. There's no backend HTTP API.

It loads `mqtt.js` and the Inter font from CDNs. Without internet access to those,
the page still works but falls back to system fonts.

## Test end to end

```bash
# backend already running in another terminal

mosquitto_pub -h broker.hivemq.com -t 'games/snake/score' \
  -m "{\"session_id\": \"test-$(date +%s)\", \"score\": 999}"

# then press button 1 on the camera board, and open https://<username>.folk.ntnu.no/
```

Give every run a new `session_id`, `$(date +%s)` does that. A repeat is rejected
as a duplicate while the first round is pending.

To test the broker alone:

```bash
mosquitto_sub -h broker.hivemq.com -t 'test/hello'        # terminal 1
mosquitto_pub -h broker.hivemq.com -t 'test/hello' -m hi  # terminal 2
```

## Limitations

- **The broker is public and plaintext.** Anyone can publish or subscribe on these
  topics, including `admin/reset`. Needs a private broker for real use.
- **FIFO pairing can mis-attribute a photo.** One camera, three consoles, no shared
  ID between the games and the camera. If two scores queue close together the next
  photo pairs with the oldest, not necessarily whoever pressed the button. Fix by
  hand-editing `state.json`.
- **Reset doesn't delete.** It moves `photos/` and `state.json` into `backup/`,
  overwriting the previous reset's copy.
