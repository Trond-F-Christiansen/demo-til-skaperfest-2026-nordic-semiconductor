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

_fonts = {}


def font(size, path=FONT_TEXT):
    """Return a Font, building it at most once per (path, size).

    Safe to call from inside a draw function or frame loop.
    """
    key = (path, size)
    if key not in _fonts:
        _fonts[key] = pygame.font.Font(path, size)
    return _fonts[key]
