"""Pre-game instructions screen: how the chosen game is played.

Shown on the way in to a game, between the main menu and the countdown.
main.py calls show() whenever the chosen game differs from the one just
played, so the page appears when a game is picked from the main menu but not
when "Restart" replays the same game -- nobody wants to re-read the rules
between rounds.

Content is per-game and lives with that game's entry in main.py's GAMES, so
adding a game stays the single edit there that main.py's docstring promises.
An entry carries the text to read, the Graphics/ images to show with it, and
how the player continues:

    Instructions(lines, images, advance, advance_hint)

`advance` is a predicate (controller) -> bool polled once per frame, for
continuing with the same hardware the game itself is played with. The quiz
passes digit(2) -- the shaka -- because a quiz player is holding the
finger_digits board. Snake and minesweeper have no gesture or keyword assigned
for this yet and pass None, so they continue from the keyboard only.

ENTER / SPACE always continues and ESC always quits, on every page, so the
instructions stay usable with no board connected (see main.py, which carries on
with keyboard input only when no port opens).

One window, one screen model: this draws into the surface main.py created and
never calls pygame.display.set_mode(). See ui.py.
"""

from collections import namedtuple

import pygame

import ui

# Every instruction image is scaled to this height, keeping its aspect ratio,
# and laid out in a single centred row. The window is 1026x1026 (snake's grid),
# so a row of five of these fits comfortably.
IMAGE_HEIGHT = 130

# Horizontal gap between images in that row.
IMAGE_GAP = 30

# What one game's instructions page shows and how it is dismissed.
#
# @param lines         paragraphs of body text, drawn top to bottom and wrapped
#                      to the window; keep them short.
# @param images        Graphics/<name>.png basenames, drawn in one row.
# @param advance       predicate (controller) -> bool, or None for keyboard
#                      only. See digit().
# @param advance_hint  the bottom line describing how to continue. Defaults to
#                      the keyboard-only wording when empty.
Instructions = namedtuple(
    "Instructions", "lines images advance advance_hint",
    defaults=((), (), None, ""),
)

_images = {}


def _load(name):
    """Return Graphics/<name>.png scaled to about IMAGE_HEIGHT, loading it once.

    Two kinds of art share this folder and they need opposite treatment. The
    hand photos are large (up to 800x560) and get scaled down, where
    smoothscale's interpolation is what you want. Snake's heads are 40x40 pixel
    art drawn for a 40px cell, so reaching IMAGE_HEIGHT means enlarging them
    3x -- and smoothscale renders that as a blur. Those are enlarged by a whole
    number with nearest-neighbour instead, which keeps the pixels crisp; the
    result is a little shorter than IMAGE_HEIGHT (120px at 3x), which is
    invisible in a row centred on one line.

    Cached because show() runs on every entry to a game and decoding a PNG per
    visit is pointless. Paths are relative to game/, like the fonts in ui.py.
    """
    if name not in _images:
        img = pygame.image.load(f"Graphics/{name}.png").convert_alpha()
        w, h = img.get_size()
        factor = IMAGE_HEIGHT / h
        if factor > 1:
            whole = max(1, int(factor))
            _images[name] = pygame.transform.scale(img, (w * whole, h * whole))
        else:
            _images[name] = pygame.transform.smoothscale(
                img, (round(w * factor), IMAGE_HEIGHT))
    return _images[name]


def digit(n):
    """Build an `advance` predicate that fires when the player shows `n` fingers.

    The finger_digits board only reports a digit after five identical
    predictions in a row, so one settled gesture arrives as one token -- a hand
    held up does not stream.

    The queue is emptied on every call rather than peeked at, for two reasons: a
    non-matching count (a stray 3) must not sit at the head blocking the digit
    we want, and nothing shown on this page may survive into the game and answer
    its first question.
    """
    def advance(controller):
        matched = False
        while not controller.digits.empty():
            if controller.digits.get() == n:
                matched = True
        return matched

    return advance


def show(screen, clock, controller, game):
    """Display `game`'s instructions until the player continues or quits.

    @return True to go on to the game, False if the player quit (ESC or the
            window closing). A game with no instructions returns True
            immediately without drawing anything.
    """
    guide = game.instructions
    if guide is None:
        return True

    title_font = ui.font(64)
    line_font = ui.font(30)
    hint_font = ui.font(26)

    width, height = screen.get_size()
    cx = width // 2
    margin = 60

    imgs = [_load(name) for name in guide.images]
    hint_y = height - 70

    while True:
        # ---- input --------------------------------------------------------
        # Poll the continue gesture before draining: it reads the digit queue,
        # which drain() would otherwise empty first.
        if guide.advance is not None and guide.advance(controller):
            return True

        # The game's own button starts it: btn0 (SNAKE) on Snake's page, etc.
        # Its menu token matches the game name. Checked before drain(), which
        # would otherwise empty the queue.
        if controller.get_menu() == game.token:
            return True

        # Everything else -- swipes, spoken numbers, other buttons -- means
        # nothing on this page and would be stale by the time the game starts.
        controller.drain(menu=False)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return True
                if event.key == pygame.K_ESCAPE:
                    return False

        # ---- draw ---------------------------------------------------------
        screen.fill(ui.BG_COLOR)

        title_surf = title_font.render(f"How to play: {game.name}", True, ui.TEXT_COLOR)
        screen.blit(title_surf, title_surf.get_rect(center=(cx, 100)))

        # Body text, left-aligned and wrapped, with a gap between paragraphs.
        y = 210
        for line in guide.lines:
            for wrapped in ui.wrap_text(line, line_font, width - 2 * margin):
                surf = line_font.render(wrapped, True, ui.TEXT_COLOR)
                screen.blit(surf, surf.get_rect(midleft=(margin, y)))
                y += line_font.get_linesize() + 6
            y += 16

        # Image strip: one centred row, placed midway between the end of the
        # text and the hint rather than pinned to the bottom, so a short page
        # doesn't leave a hole in the middle. Kept clear of the text if the
        # paragraphs run long.
        if imgs:
            total_w = sum(i.get_width() for i in imgs) + IMAGE_GAP * (len(imgs) - 1)
            x = cx - total_w // 2
            row_y = max((y + hint_y) // 2, y + IMAGE_HEIGHT // 2 + 20)
            for img in imgs:
                screen.blit(img, img.get_rect(midleft=(x, row_y)))
                x += img.get_width() + IMAGE_GAP

        hint = guide.advance_hint or "Trykk samme knapp igjen for å starte"
        hint_surf = hint_font.render(hint, True, ui.TEXT_COLOR)
        screen.blit(hint_surf, hint_surf.get_rect(center=(cx, hint_y)))

        pygame.display.update()
        clock.tick(60)
