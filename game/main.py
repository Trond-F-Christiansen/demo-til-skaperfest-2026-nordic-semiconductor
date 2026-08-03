"""Entry point and menu for the game_controller games.

Run from this folder (assets load via relative paths):

    python main.py

Flow:
    main menu  -> pick a game
    play        -> the game runs its own loop and returns the run's score
    game over   -> Restart (same game) or Main Menu; the score is shown

Adding a game later: write a module with a `run(screen, clock, controller)`
that returns the run's score (int), or None if the window was closed
mid-game, then add one entry to GAMES below. The menu and game-over screens
need no changes.

Menu navigation is keyboard-only for now, as planned:
    UP / DOWN   move selection
    ENTER/SPACE select
    ESC         quit
The next step -- mapping controller (UART) commands onto these keys -- has a
single hook in choose(); see the note there. Nothing else needs to change.
"""

import pygame

import quiz
import snake
import minesweeper

from controller import SerialController

# Window matches snake's 25 x 40px grid. New games should draw within this.
WINDOW_SIZE = (snake.cell_number * snake.cell_size,
               snake.cell_number * snake.cell_size)

BG_COLOR = "#34C3D5"
TEXT_COLOR = (255, 255, 255)
HILITE_BG = "#003C66"

FONT_PATH = 'Font/PoetsenOne-Regular.ttf'
FONT_PATH_HELVETICA = "Font/Helvetica.ttf"

class Game:
    """A menu-selectable game: a display name and its run() entry point."""

    def __init__(self, name, run):
        self.name = name
        self.run = run


# Registry of playable games -- extend this as games are added.
GAMES = [
    Game("Snake", snake.run),
    Game("Quiz", quiz.run),
    Game("Minesweeper", minesweeper.run),
]


def choose(screen, clock, controller, title, options, subtitle=None, menu_map=None, hint=None):
    """Render a vertical menu and return the chosen option index.

    @param options   list of label strings, drawn top to bottom.
    @param subtitle  optional line under the title (e.g. the score).
    @return the selected index, or None if the player quit (ESC / window close).

    Keyboard-only: UP/DOWN move the highlight, ENTER/SPACE confirm.
    """
    title_font = pygame.font.Font(FONT_PATH_HELVETICA, 72)
    sub_font = pygame.font.Font(FONT_PATH_HELVETICA, 36)
    item_font = pygame.font.Font(FONT_PATH_HELVETICA, 48)
    hint_font = pygame.font.Font(FONT_PATH_HELVETICA, 24)

    selected = 0
    cx = WINDOW_SIZE[0] // 2

    while True:
        # ---- input --------------------------------------------------------
        # Controller swipes queued while a menu is up are discarded for now.
        # This is the ONE place to later map UART directions onto navigation
        # (e.g. post K_UP/K_DOWN events); menus stay keyboard-driven so that
        # mapping is all that's needed. Kept keyboard-only on purpose today.
        while not controller.directions.empty():
            controller.directions.get()

        if menu_map is not None:
            token = controller.get_menu()
            if token is not None and token in menu_map:
                return menu_map[token]
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return selected
                elif event.key == pygame.K_ESCAPE:
                    return None

        # ---- draw ---------------------------------------------------------
        screen.fill(BG_COLOR)

        title_surf = title_font.render(title, True, TEXT_COLOR)
        screen.blit(title_surf, title_surf.get_rect(center=(cx, 200)))

        if subtitle:
            sub_surf = sub_font.render(subtitle, True, TEXT_COLOR)
            screen.blit(sub_surf, sub_surf.get_rect(center=(cx, 290)))

        start_y = 430
        gap = 90
        for i, label in enumerate(options):
            is_sel = (i == selected)
            surf = item_font.render(label, True, TEXT_COLOR)
            rect = surf.get_rect(center=(cx, start_y + i * gap))
            if is_sel:
                box = rect.inflate(80, 28)
                pygame.draw.rect(screen, HILITE_BG, box, border_radius=8)
                pygame.draw.rect(screen, TEXT_COLOR, box, 3, border_radius=8)
            screen.blit(surf, rect)

        if hint:
            hint_surf = hint_font.render(hint, True, TEXT_COLOR)
            screen.blit(hint_surf, hint_surf.get_rect(center=(cx, WINDOW_SIZE[1] - 70)))

        pygame.display.update()
        clock.tick(60)


def run_app(screen, clock, controller):
    """Top-level state machine: menu -> play -> game over -> restart/menu."""
    while True:
        # --- main menu: choose a game ---
        menu_map = {g.name.upper(): i for i, g in enumerate(GAMES)}
        choice = choose(screen, clock, controller,
                        "Edge AI Games", [g.name for g in GAMES],
                        menu_map=menu_map,
                        hint="BTN0: Snake    BTN1: Quiz    BTN2: Minesweeper")
        if choice is None:
            return
        game = GAMES[choice]

        # --- play / game-over loop for the chosen game ---
        while True:
            score = game.run(screen, clock, controller)
            if score is None:  # window closed mid-game -> quit app
                return

            action = choose(
                screen, clock, controller,
                "Game Over",
                ["Restart", "Main Menu"],
                subtitle=f"{game.name}    Score: {score}",
                menu_map={"SNAKE": 0, "QUIZ": 1},
                hint="BTN0: Restart    BTN1: Main Menu",
            )
            if action is None:      # quit
                return
            if action == 0:         # Restart the same game
                continue
            break                   # Main Menu -> back to game selection


def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Edge AI Games")
    clock = pygame.time.Clock()

    controller = SerialController(baudrate=115200)  # port=None => auto-detect
    try:
        controller.start()
    except RuntimeError as exc:
        # No board connected: keep going so the menus and keyboard still work.
        print(f"[main] {exc}\n[main] continuing with keyboard input only.")

    try:
        run_app(screen, clock, controller)
    finally:
        controller.stop()
        pygame.quit()


if __name__ == "__main__":
    main()
