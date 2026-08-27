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

ANON_PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anon_photos")

GAMES = {
    "snake_voice": "desc",
    "snake_geusture": "desc",
    "minesweeper": "asc",
}
LEADERBOARD_SIZE = int(os.environ.get("LEADERBOARD_SIZE", 50))

ALIAS_PREFIXES = (
    "blå", "brisk", "diger", "drøm", "dyp", "fager", "fjell", "flink",
    "fløyel", "frost", "frisk", "fugl", "fyrig", "glad", "glitrende", "gnistrende",
    "gull", "grønn", "gyllen", "hav", "hemmelig", "hvit", "klar", "klok",
    "kvik", "liten", "lunar", "lys", "magisk", "mjuk", "modig", "morgen",
    "mørk", "nord", "ny", "rask", "regn", "rolig", "rød", "rund",
    "safir", "sjarmerende", "skog", "sol", "spretten", "stille", "storm", "stødig",
    "sølv", "tidlig", "trygg", "varm", "vennlig", "vinter", "vill", "våt", "øy",
)
ALIAS_SUFFIXES = (
    "anemone", "bjelle", "bjørn", "bølge", "bregne", "eik", "elg", "falk",
    "fjær", "fjord", "furu", "glimt", "gran", "hare", "havn", "hval",
    "iskrystall", "katt", "klippe", "kråke", "lønn", "lyn", "måne", "mose",
    "nype", "orm", "perle", "pil", "ravn", "rev", "ring", "rose", "seil",
    "sjø", "skjær", "sky", "skog", "sol", "stein", "stjerne", "strand",
    "strå", "svane", "tind", "troll", "trost", "ulv", "varde", "vind", "åre",
)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
DEVICE_API_TOKEN = os.environ.get("DEVICE_API_TOKEN")
HTTP_HOST = os.environ.get("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("PORT", 8000))
MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", 1024 * 1024))

leaderboards = {game: [] for game in GAMES}
state_lock = Lock()
state_updated_at = 0


def ensure_output_dirs():
    WEBSITE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if STATIC_SOURCE_DIR != WEBSITE_OUTPUT_DIR:
        # Refresh the served static files (page + assets) on every start.
        for name in ("index.html", "nordic-logo.png"):
            source = STATIC_SOURCE_DIR / name
            if source.exists():
                shutil.copyfile(source, WEBSITE_OUTPUT_DIR / name)
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
                entry.setdefault("player_alias", new_player_alias())
                entry.setdefault("received_at", 0)
            leaderboards[game] = sort_leaderboard(game, entries)
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
    with temporary.open("w") as f:
        json.dump(
            {"updated_at": state_updated_at, "leaderboards": leaderboards},
            f,
        )
    temporary.replace(destination)


def new_photo_filename():
    return secrets.token_hex(8) + ".jpg"


def new_player_alias():
    return f"{random.choice(ALIAS_PREFIXES)}-{random.choice(ALIAS_SUFFIXES)}"


def would_make_leaderboard(game, score):
    del game, score
    return True


def sort_leaderboard(game, entries):
    if not entries:
        return []

    newest = max(entries, key=lambda row: row["received_at"])
    older_entries = [entry for entry in entries if entry is not newest]
    if game == "minesweeper":
        # Most tiles cleared first, then the fastest time.
        older_entries.sort(key=lambda row: (-row["score"], row.get("time", 0)))
    else:
        older_entries.sort(key=lambda row: row["score"],
                           reverse=(GAMES[game] == "desc"))
    return [newest, *older_entries]


def add_to_leaderboard(game, score, photo_filename, player_alias, extra=None):
    entry = {
        "entry_id": secrets.token_hex(8),
        "player_alias": player_alias,
        "score": score,
        "photo_filename": photo_filename,
        "received_at": time.time_ns(),
    }
    if extra:
        entry.update(extra)
    leaderboards[game].append(entry)
    leaderboards[game] = sort_leaderboard(game, leaderboards[game])
    dropped = leaderboards[game][LEADERBOARD_SIZE:]
    leaderboards[game] = leaderboards[game][:LEADERBOARD_SIZE]

    if dropped:
        for entry in dropped:
            if entry["photo_filename"]:
                move_photo_to_backup(entry["photo_filename"])


def handle_score(game, payload):
    if game not in GAMES:
        print(f"Unknown game '{game}', ignoring")
        return False

    try:
        data = json.loads(payload)
        score = data["score"]
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError("score must be a number")
        extra = {}
        if game == "minesweeper":
            elapsed = data.get("time", 0)
            if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool):
                raise ValueError("time must be a number")
            extra["time"] = elapsed
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        print("Malformed score message, ignoring")
        return False

    photo_payload = pick_anon_photo()
    if photo_payload is None:
        print(f"No random photos found in {ANON_PHOTOS_DIR}, ignoring score")
        return False

    filename = new_photo_filename()
    with (PHOTOS_DIR / filename).open("wb") as f:
        f.write(photo_payload)

    add_to_leaderboard(game, score, filename, new_player_alias(), extra)
    save_state()
    print(f"Added {game} score {score} with a random photo")
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
    del payload
    print("Camera photo ignored; scores always receive a random bundled image")
    return False


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
