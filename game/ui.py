"""Look and feel shared by the menu and every game.

One window, one screen model: main.py creates the display once and hands the
same surface to every screen. Nothing else calls pygame.display.set_mode(). A
game that needs different geometry than the window (minesweeper's board) draws
into an off-screen surface and scales it into place instead.

Fonts are cached here because draw code is called once per frame, and both
pygame.font.Font (parses the TTF) and pygame.font.SysFont (scans the system
font list) are far too slow to sit in a frame loop.
"""

import pygame

# The two bundled fonts. Paths are relative to game/, so run main.py from
# there. Nothing uses pygame's built-in freesansbold or a system font, so the
# games look the same on every machine.
FONT_DISPLAY = 'Font/PoetsenOne-Regular.ttf'   # headings, scores
FONT_TEXT = 'Font/Helvetica.ttf'               # everything else

# Menu and quiz palette. Minesweeper keeps its own board colours in
# minesweeper/config.py -- those are gameplay signals (mine red, flag red,
# per-number colours), not chrome.
BG_COLOR = "#34C3D5"
TEXT_COLOR = (255, 255, 255)
HILITE_BG = "#003C66"

# Answer feedback, used while the quiz holds an answered question on screen
# (quiz.py REVEAL_SECONDS): the correct option turns green, and a wrong pick
# turns red beside it. Both are dark enough for white text to stay readable.
CORRECT_BG = "#1E7B3C"
WRONG_BG = "#A32020"

_fonts = {}


def font(size, path=FONT_TEXT):
    """Return a Font, building it at most once per (path, size).

    Safe to call from inside a draw function or frame loop.
    """
    key = (path, size)
    if key not in _fonts:
        _fonts[key] = pygame.font.Font(path, size)
    return _fonts[key]


def wrap_text(text, font, max_width):
    """Break `text` into lines that each fit within `max_width` pixels.

    Splits on spaces only, so a single word wider than `max_width` is left to
    overflow rather than being broken mid-word.
    """
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
