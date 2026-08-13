import json
import os
import random
import secrets
import time
from collections import deque

import paramiko
import paho.mqtt.client as mqtt

BROKER = "broker.hivemq.com"

NTNU_HOST = "login.stud.ntnu.no"
NTNU_USER = "maholsen"
NTNU_REMOTE_DIR = "/web/folk/maholsen"

STATE_FILENAME = "state.json"

ANON_PHOTO_MARKER = b"ANON_PHOTO_REQUEST"
ANON_PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anon_photos")

GAMES = {"snake": "desc", "minesweeper": "asc", "quiz": "desc"}
LEADERBOARD_SIZE = int(os.environ.get("LEADERBOARD_SIZE", 50))

AWAITING_PHOTO_EXPIRY_SECONDS = int(os.environ.get("AWAITING_PHOTO_EXPIRY_SECONDS", 300))

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

leaderboards = {game: [] for game in GAMES}
awaiting_photo = deque()  # {session_id, game, score, queued_at}, oldest first


def get_sftp():
    password = os.environ["NTNU_PASSWORD"]
    transport = paramiko.Transport((NTNU_HOST, 22))
    transport.connect(username=NTNU_USER, password=password)
    return paramiko.SFTPClient.from_transport(transport)


def close_sftp(sftp):
    sftp.close()
    sftp.get_channel().get_transport().close()


def upload_atomic(sftp, local_path, remote_filename):
    remote_path = f"{NTNU_REMOTE_DIR}/{remote_filename}"
    tmp_path = f"{remote_path}.tmp"
    sftp.put(local_path, tmp_path)
    sftp.posix_rename(tmp_path, remote_path)


def upload_photo(sftp, local_path, filename):
    sftp.put(local_path, f"{NTNU_REMOTE_DIR}/photos/{filename}")


def clear_remote_dir(sftp, remote_dir):
    try:
        filenames = sftp.listdir(remote_dir)
    except FileNotFoundError:
        return
    for filename in filenames:
        sftp.remove(f"{remote_dir}/{filename}")


def move_photo_to_backup(sftp, filename):
    try:
        sftp.posix_rename(f"{NTNU_REMOTE_DIR}/photos/{filename}", f"{NTNU_REMOTE_DIR}/backup/photos/{filename}")
    except FileNotFoundError:
        pass


def download_state():
    """Load existing state.json from the server on startup, so a backend
    restart doesn't wipe the leaderboard. Not repeated on reconnect - only
    called once here, before the MQTT client is even created.
    """
    sftp = get_sftp()
    try:
        with sftp.open(f"{NTNU_REMOTE_DIR}/{STATE_FILENAME}") as f:
            data = json.load(f)
        for game in GAMES:
            entries = data.get("leaderboards", {}).get(game, [])
            for entry in entries:
                entry.setdefault("entry_id", secrets.token_hex(8))
            leaderboards[game] = entries
        print(f"Loaded existing state: "
              f"{sum(len(v) for v in leaderboards.values())} leaderboard entries")
    except (FileNotFoundError, json.JSONDecodeError):
        print("No existing state.json found, starting fresh")
    finally:
        close_sftp(sftp)


def save_and_upload_state():
    local_path = "/tmp/state.json"
    pending = [
        {"session_id": e["session_id"], "game": e["game"], "score": e["score"]}
        for e in awaiting_photo
    ]
    with open(local_path, "w") as f:
        json.dump(
            {"updated_at": int(time.time()), "leaderboards": leaderboards, "pending": pending},
            f,
        )
    sftp = get_sftp()
    try:
        upload_atomic(sftp, local_path, STATE_FILENAME)
    finally:
        close_sftp(sftp)


def new_photo_filename():
    return secrets.token_hex(8) + ".jpg"


def would_make_leaderboard(game, score):
    board = leaderboards[game]
    if len(board) < LEADERBOARD_SIZE:
        return True
    worst = board[-1]["score"]
    return score > worst if GAMES[game] == "desc" else score < worst


def add_to_leaderboard(game, score, photo_filename):
    leaderboards[game].append({
        "entry_id": secrets.token_hex(8),
        "score": score,
        "photo_filename": photo_filename,
        "received_at": int(time.time()),
    })
    leaderboards[game].sort(key=lambda row: row["score"], reverse=(GAMES[game] == "desc"))
    dropped = leaderboards[game][LEADERBOARD_SIZE:]
    leaderboards[game] = leaderboards[game][:LEADERBOARD_SIZE]

    if dropped:
        sftp = get_sftp()
        try:
            for entry in dropped:
                if entry["photo_filename"]:
                    move_photo_to_backup(sftp, entry["photo_filename"])
        finally:
            close_sftp(sftp)


def check_expired_awaiting_photo():
    now = time.time()
    expired_any = False
    while awaiting_photo and now - awaiting_photo[0]["queued_at"] > AWAITING_PHOTO_EXPIRY_SECONDS:
        entry = awaiting_photo.popleft()
        add_to_leaderboard(entry["game"], entry["score"], None)
        print(f"Pending {entry['game']} score {entry['score']} ({entry['session_id']}) expired, "
              f"added to the leaderboard without a photo ({len(awaiting_photo)} still pending)")
        expired_any = True
    if expired_any:
        save_and_upload_state()


def handle_score(topic, payload):
    game = topic.split("/")[1]
    if game not in GAMES:
        print(f"Unknown game '{game}', ignoring")
        return

    try:
        data = json.loads(payload)
        session_id = str(data["session_id"])
        score = data["score"]
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError("score must be a number")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        print(f"Malformed score message on {topic}: {payload!r}, ignoring")
        return

    if not would_make_leaderboard(game, score):
        print(f"{game} score {score} ({session_id}) doesn't make the top "
              f"{LEADERBOARD_SIZE}, ignoring")
        return

    if any(e["session_id"] == session_id for e in awaiting_photo):
        print(f"session_id {session_id} is already pending, ignoring duplicate score "
              f"message (session_id must be unique per round)")
        return

    awaiting_photo.append({
        "session_id": session_id,
        "game": game,
        "score": score,
        "queued_at": time.time(),
    })
    save_and_upload_state()
    print(f"{game} score {score} ({session_id}) qualifies, now pending a photo "
          f"({len(awaiting_photo)} pending)")


def pick_anon_photo():
    try:
        candidates = [f for f in os.listdir(ANON_PHOTOS_DIR) if f.lower().endswith((".jpg", ".jpeg"))]
    except FileNotFoundError:
        return None
    if not candidates:
        return None
    chosen = random.choice(candidates)
    with open(os.path.join(ANON_PHOTOS_DIR, chosen), "rb") as f:
        return f.read()


def handle_photo(payload):
    check_expired_awaiting_photo()

    if not awaiting_photo:
        print("Photo arrived but nothing is pending, discarding")
        return

    if payload == ANON_PHOTO_MARKER:
        anon_payload = pick_anon_photo()
        if anon_payload is None:
            print(f"Anonymous photo requested but {ANON_PHOTOS_DIR} has no photos, discarding")
            return
        print("Anonymous photo requested, using a random placeholder instead")
        payload = anon_payload

    entry = awaiting_photo.popleft()
    filename = new_photo_filename()

    local_path = f"/tmp/{filename}"
    with open(local_path, "wb") as f:
        f.write(payload)

    sftp = get_sftp()
    try:
        upload_photo(sftp, local_path, filename)
    finally:
        close_sftp(sftp)

    add_to_leaderboard(entry["game"], entry["score"], filename)
    save_and_upload_state()
    print(f"Added {entry['game']} score {entry['score']} ({entry['session_id']}) to the "
          f"leaderboard ({len(awaiting_photo)} still pending)")


def handle_delete(payload):
    try:
        data = json.loads(payload)
        game = str(data["game"])
        entry_id = str(data["entry_id"])
        password = str(data["password"])
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"Malformed delete message: {payload!r}, ignoring")
        return

    if ADMIN_PASSWORD is None or password != ADMIN_PASSWORD:
        print(f"Delete request for {game}/{entry_id} had a wrong or missing password, ignoring")
        return

    if game not in GAMES:
        print(f"Delete request for unknown game '{game}', ignoring")
        return

    match = next((e for e in leaderboards[game] if e["entry_id"] == entry_id), None)
    if match is None:
        print(f"Delete request for unknown entry_id {entry_id} in {game}, ignoring")
        return

    leaderboards[game].remove(match)

    if match["photo_filename"]:
        sftp = get_sftp()
        try:
            move_photo_to_backup(sftp, match["photo_filename"])
        finally:
            close_sftp(sftp)

    save_and_upload_state()
    print(f"Deleted {game} score {match['score']} (entry_id {entry_id})")


def handle_delete_pending(payload):
    try:
        data = json.loads(payload)
        session_id = str(data["session_id"])
        password = str(data["password"])
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"Malformed delete-pending message: {payload!r}, ignoring")
        return

    if ADMIN_PASSWORD is None or password != ADMIN_PASSWORD:
        print(f"Delete-pending request for {session_id} had a wrong or missing password, ignoring")
        return

    match = next((e for e in awaiting_photo if e["session_id"] == session_id), None)
    if match is None:
        print(f"Delete-pending request for unknown session_id {session_id}, ignoring")
        return

    awaiting_photo.remove(match)
    save_and_upload_state()
    print(f"Deleted pending {match['game']} score {match['score']} ({session_id}), "
          f"{len(awaiting_photo)} pending remain")


def handle_reset(payload):
    try:
        data = json.loads(payload)
        if data.get("action") != "reset":
            raise ValueError("not a reset message")
        password = str(data["password"])
    except (json.JSONDecodeError, AttributeError, ValueError, KeyError, TypeError):
        print(f"Malformed reset message: {payload!r}, ignoring")
        return

    if ADMIN_PASSWORD is None or password != ADMIN_PASSWORD:
        print("Reset request had a wrong or missing password, ignoring")
        return

    photos_dir = f"{NTNU_REMOTE_DIR}/photos"
    backup_dir = f"{NTNU_REMOTE_DIR}/backup"
    backup_photos_dir = f"{backup_dir}/photos"

    sftp = get_sftp()
    try:
        clear_remote_dir(sftp, backup_photos_dir)
        for filename in sftp.listdir(photos_dir):
            sftp.posix_rename(f"{photos_dir}/{filename}", f"{backup_photos_dir}/{filename}")

        try:
            sftp.posix_rename(f"{NTNU_REMOTE_DIR}/{STATE_FILENAME}", f"{backup_dir}/{STATE_FILENAME}")
        except FileNotFoundError:
            pass
    finally:
        close_sftp(sftp)

    for game in GAMES:
        leaderboards[game] = []
    awaiting_photo.clear()

    save_and_upload_state()
    print("Reset: moved current photos/state.json into backup/, cleared live leaderboards")


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected to {BROKER} (reason: {reason_code})")
    client.subscribe("+/my/publish/topic")
    client.subscribe("games/+/score")
    client.subscribe("admin/delete")
    client.subscribe("admin/delete_pending")
    client.subscribe("admin/reset")
    print("Subscribed to: +/my/publish/topic, games/+/score, admin/delete, "
          "admin/delete_pending, admin/reset")


def on_message(client, userdata, msg):
    if msg.topic.endswith("/my/publish/topic"):
        handle_photo(msg.payload)
    elif msg.topic.endswith("/score"):
        handle_score(msg.topic, msg.payload)
    elif msg.topic == "admin/delete":
        handle_delete(msg.payload)
    elif msg.topic == "admin/delete_pending":
        handle_delete_pending(msg.payload)
    elif msg.topic == "admin/reset":
        handle_reset(msg.payload)


def main():
    download_state()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, 1883)
    client.loop_forever()


if __name__ == "__main__":
    main()
