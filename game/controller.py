"""Voice/gesture/finger-digit controller: reads BLE-relayed commands over serial.

A sender board (the game_controller dongle, or the finger_digits classifier)
sends short command tokens over BLE (Nordic UART Service); the game_receiver app
on the DK acts as the BLE central and relays each one onto its console UART as a
plain-text line. Two token families are understood:

    Command: UP  / DOWN / LEFT / RIGHT          -> directions (snake)
    Command: ZERO / ONE / ... / FIVE            -> finger digits 0-5 (quiz)

The finger_digits firmware only emits a digit once it has seen the same
prediction five times in a row, so each token here is already a settled choice,
not a raw per-frame prediction; "unknown" is never sent.

This module opens the serial port in a background thread, parses those lines and
pushes each event onto a thread-safe queue that the game loop drains --
directions onto @ref SerialController.directions, digits onto @ref
SerialController.digits. Unrecognized commands and all other status lines are
ignored.
"""

from __future__ import annotations

import queue
import re
import threading
import time

try:
    import serial  # pyserial
    from serial.tools import list_ports
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "pyserial is required for serial input. Install it with:\n"
        "    pip install pyserial"
    ) from exc

# Directions are (dx, dy) with y growing downwards, matching screen coordinates.
DIRECTIONS = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}
# Number tokens -> the number said. Minesweeper reads these as board
# coordinates, so it needs one per row/column (0-7).
NUMBERS = {
    "ZERO": 0, "ONE": 1, "TWO": 2, "THREE": 3,
    "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7,
}

# Finger-digit tokens from the finger_digits classifier -> the digit shown.
# Games map these onto the matching number key (see quiz.py), so a digit is
# equivalent to the player pressing 0-5 on the keyboard. A subset of NUMBERS:
# one hand only shows up to five.
MAX_DIGIT = 5
DIGITS = {word: n for word, n in NUMBERS.items() if n <= MAX_DIGIT}

# Word commands, all of them minesweeper's. "easy"/"hard" pick a difficulty;
# like the MENU: path below, the host side is ready before the firmware emits
# them, so nothing sends these two yet -- keep them.
COMMANDS = {
    "RESET": "reset",
    "BOMB": "flag",
    "MARK": "open",
    "NO": "no",
    "EASY": "easy",
    "HARD": "hard",
}
_COMMAND_RE = re.compile(r"Command:\s*(\w+)")
_MENU_RE = re.compile(r"MENU:(\w+)")
# Lines that only game_receiver's firmware ever prints, used to tell its
# console apart from another DK's console when both are plugged in at once
# (see _probe_is_receiver()). Deliberately narrow: e.g. "Bluetooth
# initialized" is NOT here because game_controller logs that exact line too
# (ble_nus.c), which caused a false-positive match on the wrong board.
_RECEIVER_SIGNATURE_RE = re.compile(
    r"Command:|Scanning for a game controller"
)

# J-Link serial number of the DK that's actually running game_receiver.
# Checked before anything else, since it's deterministic (unlike probing,
# which needs the board to log something during the probe window). Update
# this if game_receiver ever gets flashed onto a different physical DK; get
# the serial with `nrfjprog --ids` or `nrfutil device list`.
_KNOWN_RECEIVER_SERIAL = "001051849885"

# USB vendor IDs of the debug probes used on Nordic DKs (SEGGER J-Link OB,
# Nordic Semiconductor), used to pick out candidate ports.
_KNOWN_VIDS = {0x1366, 0x1915}

# The J-Link OB exposes two CDC VCOMs. The firmware console is the second one,
# at USB interface 2 (/dev/serial/by-id/...-if02). USB interface numbers are
# stable across reboots and replugs, unlike the /dev/ttyACMx ordering, so we
# select on the interface rather than probing traffic.
_CONSOLE_USB_INTERFACE = 2

# How long to listen to a candidate port for its signature before giving up
# and falling back to the next one, in seconds.
_PROBE_TIMEOUT_S = 2.0


def list_candidate_ports() -> list[str]:
    """Return likely DK serial ports, best guesses first.

    Scores each enumerated port by USB vendor ID and description so that the
    debug-probe VCOMs sort ahead of unrelated serial devices.
    """

    def score(p) -> int:
        s = 0
        if p.vid in _KNOWN_VIDS:
            s += 10
        desc = f"{p.description} {p.product or ''}".lower()
        if "j-link" in desc or "nordic" in desc:
            s += 5
        if "ttyacm" in p.device.lower() or "usbmodem" in p.device.lower():
            s += 2
        return s

    ranked = sorted(list_ports.comports(), key=score, reverse=True)
    return [p.device for p in ranked if score(p) > 0]


def _probe_is_receiver(port: str, baudrate: int, timeout: float, result: dict) -> None:
    """Listen briefly on `port` for a line only game_receiver's firmware prints."""
    try:
        with serial.Serial(port, baudrate, timeout=0.2) as ser:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                line = ser.readline().decode("utf-8", errors="replace")
                if _RECEIVER_SIGNATURE_RE.search(line):
                    result[port] = True
                    return
    except (serial.SerialException, OSError):
        pass
    result[port] = False


def _pick_receiver_port(candidates: list[str], baudrate: int) -> str | None:
    """Probe all tied candidates at once; one swipe during the window is enough
    to identify the right one regardless of ttyACMx ordering."""
    result: dict[str, bool] = {}
    threads = [
        threading.Thread(target=_probe_is_receiver, args=(port, baudrate, _PROBE_TIMEOUT_S, result))
        for port in candidates
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for port in candidates:
        if result.get(port):
            return port
    return None


def find_controller_port(baudrate: int = 115200) -> str | None:
    """Return the firmware console port, selected by stable USB interface.

    The J-Link's console VCOM is always at USB interface @ref
    _CONSOLE_USB_INTERFACE, regardless of how Linux numbers the ttyACMx
    devices. If @ref _KNOWN_RECEIVER_SERIAL is plugged in, its port wins
    immediately. Otherwise, if more than one board's console matches (e.g. a
    second DK is plugged in for testing another app), each tied candidate is
    probed briefly and the one actually printing game_receiver's log lines
    wins. Falls back to the highest-ranked candidate if the interface cannot
    be identified (e.g. a board that does not report a location).

    @return Device path, or None if no candidate ports were found.
    """
    # location looks like '5-1:1.2'; the trailing '.N' is the USB interface.
    suffix = f":1.{_CONSOLE_USB_INTERFACE}"
    ports = [
        p
        for p in list_ports.comports()
        if p.vid in _KNOWN_VIDS and p.location and p.location.endswith(suffix)
    ]

    for p in ports:
        if p.serial_number == _KNOWN_RECEIVER_SERIAL:
            return p.device

    tied = [p.device for p in ports]

    if len(tied) == 1:
        return tied[0]
    if len(tied) > 1:
        picked = _pick_receiver_port(tied, baudrate)
        if picked is not None:
            return picked
        print(
            f"[controller] warning: {len(tied)} candidate ports {tied} but none "
            "printed a recognizable game_receiver line within "
            f"{_PROBE_TIMEOUT_S}s; defaulting to {tied[0]}. Pass a port "
            "explicitly if that's wrong."
        )
        return tied[0]

    candidates = list_candidate_ports()
    return candidates[0] if candidates else None


class SerialController:
    """Background reader that turns serial keyword events into game input."""

    def __init__(self, port: str | None = None, baudrate: int = 115200):
        # port=None auto-detects the firmware port at start().
        self.port = port
        self.baudrate = baudrate
        self.directions: "queue.Queue[tuple[int, int]]" = queue.Queue()
        # Settled finger digits (0-5), one entry per token received.
        self.digits: "queue.Queue[int]" = queue.Queue()
        self.commands: "queue.Queue[tuple[str, object]]" = queue.Queue() #minesweeper-commands
        self.menu: "queue.Queue[str]" = queue.Queue()  # menyvalg fra controller-knapper
        self._serial: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        """Open the port (auto-detecting if needed) and read in a daemon thread."""
        if self.port is None:
            self.port = find_controller_port(self.baudrate)
            if self.port is None:
                raise RuntimeError(
                    "No DK serial port found. Connect the board, or pass a port "
                    "explicitly (e.g. SerialController('/dev/ttyACM1'))."
                )
        print(f"[controller] using serial port {self.port}")
        self._serial = serial.Serial(self.port, self.baudrate, timeout=0.5)
        self._thread = threading.Thread(target=self._run, name="serial-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._serial is not None:
            self._serial.close()

    #---new function-----
    #send scores to 54
    def send_score(self, game: str, score: int, extra: dict | None = None) -> None:
        """Send a highscore line to the DK, which forwards it to the nRF9151.

        Format: <game>|<json>\n
        """
        if self._serial is None:
            print("[controller] cannot send score: serial not open")
            return

        import json

        payload = {"score": score}
        if extra:
            payload.update(extra)

        line = "%s|%s\n" % (game, json.dumps(payload))
        try:
            self._serial.write(line.encode("utf-8"))
            print(f"[controller] score sent: {line.strip()}")
        except (serial.SerialException, OSError) as exc:
            print(f"[controller] failed to send score: {exc}")

    def _run(self) -> None:
        assert self._serial is not None
        while not self._stop.is_set():
            try:
                line = self._serial.readline().decode("utf-8", errors="replace").strip()
            except (serial.SerialException, OSError):
                break
            if not line:
                continue
            menu_match = _MENU_RE.search(line)
            if menu_match:
                self.menu.put(menu_match.group(1).upper())
                continue
            match = _COMMAND_RE.search(line)
            if not match:
                continue
            word = match.group(1)

            # 1) Retning (Snake/Quiz)
            direction = DIRECTIONS.get(word)
            if direction is not None:
                self.directions.put(direction)
                continue

            # 2) Tall. Minesweeper reads them as ("number", n) off self.commands;
            #    the quiz reads 0-5 off self.digits. Post to both queues and let
            #    each game take from the one it uses -- drain() clears the rest.
            if word in NUMBERS:
                self.commands.put(("number", NUMBERS[word]))
                if word in DIGITS:
                    self.digits.put(DIGITS[word])
                continue

            # 3) Kommando (Minesweeper)
            if word in COMMANDS:
                self.commands.put(("command", COMMANDS[word]))
                continue

    def drain(self, menu: bool = True) -> None:
        """Discard queued input, so stale events don't leak across screens.

        @param menu  also discard queued menu-button tokens. Menu screens must
                     pass False: those tokens are that screen's navigation, so
                     draining them every frame throws the button press away
                     before get_menu() ever sees it. Games pass the default, so
                     a button pressed during play doesn't act on the game-over
                     screen that follows.
        """
        queues = [self.directions, self.digits, self.commands]
        if menu:
            queues.append(self.menu)
        for q in queues:
            while not q.empty():
                q.get()

    def get_menu(self):
        # Returnerer neste menyvalg ("SNAKE"/"QUIZ"/"MINESWEEPER") eller None.
        try:
            return self.menu.get_nowait()
        except queue.Empty:
            return None

    def get_command(self, max_square: int | None = None):
    #returnerer samme format som minesweeper forventer
        try:
            kind, value = self.commands.get_nowait()
        except queue.Empty:
            return None

        if kind == "number" and max_square is not None and value >= max_square:
            return None  #vil ikke ha tall utafor brettet

        return (kind, value)


if __name__ == "__main__":
    import sys

    port = sys.argv[1] if len(sys.argv) > 1 else None  # None => auto-detect
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    # Reverse map so we can print a readable name, not just the (dx, dy) tuple.
    NAMES = {v: k for k, v in DIRECTIONS.items()}

    controller = SerialController(port, baud)
    #controller = SerialController(port='/dev/ttyACM1', baudrate=115200)
    controller.start()
    print(f"Listening on {controller.port} @ {baud} (Ctrl-C to stop)...")
    try:
        # Poll every queue; which family of tokens arrives depends on the sender
        # board paired with the receiver. Digits are also posted as ("number",
        # n) commands, so a digit token prints on both lines -- that is the
        # queue duplication in _run(), not a double read.
        while True:
            got = False
            while not controller.directions.empty():
                direction = controller.directions.get()
                print(f"{NAMES[direction]:<5} {direction}")
                got = True
            while not controller.digits.empty():
                print(f"digit {controller.digits.get()}")
                got = True
            while not controller.commands.empty():
                kind, value = controller.commands.get()
                print(f"{kind} {value}")
                got = True
            token = controller.get_menu()
            if token is not None:
                print(f"menu {token}")
                got = True
            if not got:
                time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()