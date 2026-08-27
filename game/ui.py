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

# Menu palette. Minesweeper keeps its own board colours in
# minesweeper/config.py -- those are gameplay signals (mine red, flag red,
# per-number colours), not chrome.
BG_COLOR = "#34C3D5"            # legacy flat fill; prefer draw_background()
BG_TOP = (60, 205, 224)         # gradient top: bright cyan
BG_BOTTOM = (16, 96, 132)       # gradient bottom: deep teal
TEXT_COLOR = (255, 255, 255)
TEXT_MUTED = (206, 232, 240)
SHADOW_COLOR = (6, 32, 46)
HILITE_BG = "#003C66"
ACCENT = (255, 200, 60)         # warm highlight for the current selection
ACCENT_DARK = (196, 138, 12)
PANEL_BG = (13, 43, 66)         # cards / dialogs
PANEL_EDGE = (34, 82, 120)

_fonts = {}
_grad_cache = {}


def _make_gradient(size, top, bottom):
    """Build a vertical two-colour gradient surface of `size`."""
    w, h = size
    h = max(1, h)
    strip = pygame.Surface((1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        strip.set_at((0, y), (
            round(top[0] + (bottom[0] - top[0]) * t),
            round(top[1] + (bottom[1] - top[1]) * t),
            round(top[2] + (bottom[2] - top[2]) * t),
        ))
    return pygame.transform.scale(strip, (max(1, w), h))


def gradient_surface(size, top, bottom):
    """Return a cached vertical gradient; safe to call every frame."""
    key = (size, top, bottom)
    surf = _grad_cache.get(key)
    if surf is None:
        surf = _make_gradient(size, top, bottom)
        _grad_cache[key] = surf
    return surf


def draw_background(surface, top=BG_TOP, bottom=BG_BOTTOM):
    """Fill the whole surface with a smooth vertical gradient."""
    surface.blit(gradient_surface(surface.get_size(), top, bottom), (0, 0))


def rounded_gradient(size, top, bottom, radius=14):
    """Return a cached rounded-rect gradient tile with transparent corners."""
    key = (size, top, bottom, radius, "round")
    surf = _grad_cache.get(key)
    if surf is None:
        grad = _make_gradient(size, top, bottom).convert_alpha()
        mask = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(),
                         border_radius=radius)
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf = grad
        _grad_cache[key] = surf
    return surf


def render_text(text, fnt, color=TEXT_COLOR, shadow=SHADOW_COLOR, offset=2):
    """Render text with an optional soft drop shadow."""
    base = fnt.render(text, True, color)
    if shadow is None:
        return base
    out = pygame.Surface(
        (base.get_width() + offset, base.get_height() + offset), pygame.SRCALPHA)
    out.blit(fnt.render(text, True, shadow), (offset, offset))
    out.blit(base, (0, 0))
    return out


def blit_center(surface, source, center):
    """Blit `source` centred on `center`. Returns the blit rect."""
    rect = source.get_rect(center=center)
    surface.blit(source, rect)
    return rect


def draw_panel(surface, rect, radius=20, fill=PANEL_BG, edge=PANEL_EDGE,
               shadow=8):
    """Draw a rounded card with a soft drop shadow."""
    if shadow:
        sh = pygame.Surface((rect.width, rect.height + shadow), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, 80), sh.get_rect(), border_radius=radius)
        surface.blit(sh, (rect.x, rect.y + shadow))
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    pygame.draw.rect(surface, edge, rect, 3, border_radius=radius)


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
