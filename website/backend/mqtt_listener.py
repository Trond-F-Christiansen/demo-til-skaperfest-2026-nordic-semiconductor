import json
import os
import random
import secrets
import shutil
import time
from collections import deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parent
STATIC_SOURCE_DIR = BACKEND_DIR.parent / "site"
WEBSITE_OUTPUT_DIR = Path(
    os.environ.get("WEBSITE_OUTPUT_DIR", BACKEND_DIR.parent / "site")
).expanduser().resolve()
PHOTOS_DIR = WEBSITE_OUTPUT_DIR / "photos"
BACKUP_DIR = WEBSITE_OUTPUT_DIR / "backup"
BACKUP_PHOTOS_DIR = BACKUP_DIR / "photos"

STATE_FILENAME = "state.json"

ANON_PHOTO_MARKER = b"ANON_PHOTO_REQUEST"
ANON_PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anon_photos")

GAMES = {"snake": "desc", "minesweeper": "asc", "quiz": "desc"}
LEADERBOARD_SIZE = int(os.environ.get("LEADERBOARD_SIZE", 50))

AWAITING_PHOTO_EXPIRY_SECONDS = int(os.environ.get("AWAITING_PHOTO_EXPIRY_SECONDS", 300))

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
DEVICE_API_TOKEN = os.environ.get("DEVICE_API_TOKEN")
HTTP_HOST = os.environ.get("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("PORT", 8000))
MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", 1024 * 1024))

leaderboards = {game: [] for game in GAMES}
awaiting_photo = deque()  # {session_id, game, score, queued_at}, oldest first
state_lock = Lock()
state_updated_at = 0


def ensure_output_dirs():
    WEBSITE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_index = STATIC_SOURCE_DIR / "index.html"
    destination_index = WEBSITE_OUTPUT_DIR / "index.html"
    if source_index != destination_index and not destination_index.exists():
        shutil.copyfile(source_index, destination_index)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


def clear_local_dir(directory):
    if not directory.exists():
        return
    for path in directory.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def move_photo_to_backup(filename):
    source = PHOTOS_DIR / filename
    if source.exists():
        source.replace(BACKUP_PHOTOS_DIR / filename)


def download_state():
    """Load existing state.json from the server on startup, so a backend
    restart doesn't wipe the leaderboard. Not repeated on reconnect - only
    called once here, before the MQTT client is even created.
    """
    global state_updated_at

    try:
        with (WEBSITE_OUTPUT_DIR / STATE_FILENAME).open() as f:
            data = json.load(f)
        state_updated_at = int(data.get("updated_at", 0))
        for game in GAMES:
            entries = data.get("leaderboards", {}).get(game, [])
            for entry in entries:
                entry.setdefault("entry_id", secrets.token_hex(8))
            leaderboards[game] = entries
        print(f"Loaded existing state: "
              f"{sum(len(v) for v in leaderboards.values())} leaderboard entries")
        return True
    except (FileNotFoundError, json.JSONDecodeError):
        print("No existing state.json found, starting fresh")
        return False


def save_state():
    global state_updated_at

    destination = WEBSITE_OUTPUT_DIR / STATE_FILENAME
    temporary = destination.with_name(f".{destination.name}.tmp")
    state_updated_at = int(time.time())
    pending = [
        {"session_id": e["session_id"], "game": e["game"], "score": e["score"]}
        for e in awaiting_photo
    ]
    with temporary.open("w") as f:
        json.dump(
            {"updated_at": state_updated_at, "leaderboards": leaderboards, "pending": pending},
            f,
        )
    temporary.replace(destination)


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
        for entry in dropped:
            if entry["photo_filename"]:
                move_photo_to_backup(entry["photo_filename"])


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
        save_state()


def handle_score(game, payload):
    if game not in GAMES:
        print(f"Unknown game '{game}', ignoring")
        return False

    try:
        data = json.loads(payload)
        session_id = str(data["session_id"])
        score = data["score"]
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError("score must be a number")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        print("Malformed score message, ignoring")
        return False

    if not would_make_leaderboard(game, score):
        print(f"{game} score {score} ({session_id}) doesn't make the top "
              f"{LEADERBOARD_SIZE}, ignoring")
        return False

    if any(e["session_id"] == session_id for e in awaiting_photo):
        print(f"session_id {session_id} is already pending, ignoring duplicate score "
              f"message (session_id must be unique per round)")
        return False

    awaiting_photo.append({
        "session_id": session_id,
        "game": game,
        "score": score,
        "queued_at": time.time(),
    })
    save_state()
    print(f"{game} score {score} ({session_id}) qualifies, now pending a photo "
          f"({len(awaiting_photo)} pending)")
    return True


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
        return False

    if payload == ANON_PHOTO_MARKER:
        anon_payload = pick_anon_photo()
        if anon_payload is None:
            print(f"Anonymous photo requested but {ANON_PHOTOS_DIR} has no photos, discarding")
            return False
        print("Anonymous photo requested, using a random placeholder instead")
        payload = anon_payload

    entry = awaiting_photo.popleft()
    filename = new_photo_filename()

    photo_path = PHOTOS_DIR / filename
    with photo_path.open("wb") as f:
        f.write(payload)

    add_to_leaderboard(entry["game"], entry["score"], filename)
    save_state()
    print(f"Added {entry['game']} score {entry['score']} ({entry['session_id']}) to the "
          f"leaderboard ({len(awaiting_photo)} still pending)")
    return True


def handle_delete(payload):
    try:
        data = json.loads(payload)
        game = str(data["game"])
        entry_id = str(data["entry_id"])
        password = str(data["password"])
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"Malformed delete message: {payload!r}, ignoring")
        return False

    if ADMIN_PASSWORD is None or password != ADMIN_PASSWORD:
        print(f"Delete request for {game}/{entry_id} had a wrong or missing password, ignoring")
        return False

    if game not in GAMES:
        print(f"Delete request for unknown game '{game}', ignoring")
        return False

    match = next((e for e in leaderboards[game] if e["entry_id"] == entry_id), None)
    if match is None:
        print(f"Delete request for unknown entry_id {entry_id} in {game}, ignoring")
        return False

    leaderboards[game].remove(match)

    if match["photo_filename"]:
        move_photo_to_backup(match["photo_filename"])

    save_state()
    print(f"Deleted {game} score {match['score']} (entry_id {entry_id})")
    return True


def handle_delete_pending(payload):
    try:
        data = json.loads(payload)
        session_id = str(data["session_id"])
        password = str(data["password"])
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"Malformed delete-pending message: {payload!r}, ignoring")
        return False

    if ADMIN_PASSWORD is None or password != ADMIN_PASSWORD:
        print(f"Delete-pending request for {session_id} had a wrong or missing password, ignoring")
        return False

    match = next((e for e in awaiting_photo if e["session_id"] == session_id), None)
    if match is None:
        print(f"Delete-pending request for unknown session_id {session_id}, ignoring")
        return False

    awaiting_photo.remove(match)
    save_state()
    print(f"Deleted pending {match['game']} score {match['score']} ({session_id}), "
          f"{len(awaiting_photo)} pending remain")
    return True


def handle_reset(payload):
    try:
        data = json.loads(payload)
        if data.get("action") != "reset":
            raise ValueError("not a reset message")
        password = str(data["password"])
    except (json.JSONDecodeError, AttributeError, ValueError, KeyError, TypeError):
        print(f"Malformed reset message: {payload!r}, ignoring")
        return False

    if ADMIN_PASSWORD is None or password != ADMIN_PASSWORD:
        print("Reset request had a wrong or missing password, ignoring")
        return False

    clear_local_dir(BACKUP_PHOTOS_DIR)
    for photo in PHOTOS_DIR.iterdir():
        photo.replace(BACKUP_PHOTOS_DIR / photo.name)

    state_path = WEBSITE_OUTPUT_DIR / STATE_FILENAME
    if state_path.exists():
        state_path.replace(BACKUP_DIR / STATE_FILENAME)

    for game in GAMES:
        leaderboards[game] = []
    awaiting_photo.clear()

    save_state()
    print("Reset: moved current photos/state.json into backup/, cleared live leaderboards")
    return True


class WebsiteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEBSITE_OUTPUT_DIR), **kwargs)

    def send_json(self, status, body):
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def read_body(self):
        try:
            content_length = int(self.headers["Content-Length"])
        except (KeyError, TypeError, ValueError):
            self.send_json(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length is required"})
            return None

        if content_length < 0 or content_length > MAX_REQUEST_BYTES:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Request is too large"})
            return None
        return self.rfile.read(content_length)

    def device_authorized(self):
        return DEVICE_API_TOKEN is not None and self.headers.get("Authorization") == (
            f"Bearer {DEVICE_API_TOKEN}"
        )

    def do_GET(self):
        if urlparse(self.path).path == "/api/state":
            with state_lock:
                self.send_json(HTTPStatus.OK, {
                    "updated_at": state_updated_at,
                    "leaderboards": leaderboards,
                    "pending": [
                        {"session_id": entry["session_id"], "game": entry["game"], "score": entry["score"]}
                        for entry in awaiting_photo
                    ],
                })
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_body()
        if body is None:
            return

        if path == "/api/photos":
            if not self.device_authorized():
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Invalid device token"})
                return
            with state_lock:
                accepted = handle_photo(body)
            self.send_json(HTTPStatus.OK if accepted else HTTPStatus.ACCEPTED, {"accepted": accepted})
            return

        if path.startswith("/api/scores/"):
            if not self.device_authorized():
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Invalid device token"})
                return
            game = path.removeprefix("/api/scores/")
            with state_lock:
                accepted = handle_score(game, body)
            self.send_json(HTTPStatus.OK if accepted else HTTPStatus.ACCEPTED, {"accepted": accepted})
            return

        handlers = {
            "/api/admin/delete": handle_delete,
            "/api/admin/delete-pending": handle_delete_pending,
            "/api/admin/reset": handle_reset,
        }
        handler = handlers.get(path)
        if handler is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown API route"})
            return

        with state_lock:
            accepted = handler(body)
        self.send_json(HTTPStatus.OK if accepted else HTTPStatus.FORBIDDEN, {"accepted": accepted})


def main():
    ensure_output_dirs()
    if not download_state():
        save_state()

    server = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), WebsiteHandler)
    print(f"Serving website and API on http://{HTTP_HOST}:{HTTP_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
