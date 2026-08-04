"""Entry point and menu for the game_controller games.

Run from this folder (assets load via relative paths):

    python main.py

Flow:
    main menu  -> pick a game
    play        -> the game runs its own loop and returns the run's result
    game over   -> Restart (same game) or Main Menu; the result is shown

One window, one screen model: main() creates the display once and every screen
-- this menu, the game-over screen and all three games -- draws into that same
surface. Nothing calls pygame.display.set_mode() again. A game whose natural
geometry differs from the window (minesweeper's board) renders into an
off-screen surface and scales it into place. Shared colours and fonts live in
ui.py.

Adding a game later: write a module with a `run(screen, clock, controller)`
that returns the run's result (int), or None if the window was closed
mid-game, then add one entry to GAMES below -- with a result_label if "Score"
is the wrong word for what it returns. The menu and game-over screens need no
changes.

Every screen is navigated the same three ways:
    UP / DOWN       move the selection,  ENTER / SPACE confirm
    ESC             quit
    BTN0 / 1 / 2    pick the first / second / third option directly
The buttons are physical buttons on a BLE central, relayed to us over UART as
MENU: tokens; see BUTTON_TOKENS and controller.get_menu().
"""

import pygame

import quiz
import snake
import ui
from minesweeper import minesweeper_game

from controller import SerialController

# Window matches snake's grid. New games should draw within this.
WINDOW_SIZE = (snake.cell_number * snake.cell_size,
               snake.cell_number * snake.cell_size)

# Menu-button tokens, in button order: BTN0 relays "MENU:SNAKE", BTN1
# "MENU:QUIZ", BTN2 "MENU:MINESWEEPER". The words name the *button*, not the
# game -- they come from the main menu's original three entries -- so on the
# game-over screen BTN0 ("SNAKE") means Restart. Every screen maps them onto
# its own options by position, which is why choose() needs no token argument.
BUTTON_TOKENS = ("SNAKE", "QUIZ", "MINESWEEPER")


class Game:
    """A menu-selectable game.

    @param name          label in the main menu.
    @param run           entry point, run(screen, clock, controller) -> result.
    @param result_label  how the game-over screen words that result, and the
                         unit to print after it. Minesweeper is timed, so its
                         result is seconds and lower is better; snake and quiz
                         return a higher-is-better score.
    """

    def __init__(self, name, run, result_label="Score", result_unit=""):
        self.name = name
        self.run = run
        self.result_label = result_label
        self.result_unit = result_unit

    def result_text(self, result):
        return f"{self.result_label}: {result}{self.result_unit}"


# Registry of playable games -- extend this as games are added. Minesweeper is
# a package rather than a single module, but its run() means the same thing.
GAMES = [
    Game("Snake", snake.run),
    Game("Quiz", quiz.run),
    Game("Minesweeper", minesweeper_game.run, result_label="Time", result_unit="s"),
]


def choose(screen, clock, controller, title, options, subtitle=None):
    """Render a vertical menu and return the chosen option index.

    @param options   list of label strings, drawn top to bottom.
    @param subtitle  optional line under the title (e.g. the result).
    @return the selected index, or None if the player quit (ESC / window close).

    Keyboard and menu buttons both work; the button hint is derived from
    `options`, so a screen only has to say what its options are.
    """
    title_font = ui.font(72)
    sub_font = ui.font(36)
    item_font = ui.font(48)
    hint_font = ui.font(24)

    # Buttons address options by position; a screen with more options than
    # buttons simply leaves the rest keyboard-only.
    button_map = {token: i for i, token in enumerate(BUTTON_TOKENS[:len(options)])}
    hint = "    ".join(f"BTN{i}: {options[i]}" for i in range(len(button_map)))

    selected = 0
    cx = WINDOW_SIZE[0] // 2

    while True:
        # ---- input --------------------------------------------------------
        # Controller swipes and finger digits queued while a menu is up mean
        # nothing here, so drop them -- but keep the menu queue, which is this
        # screen's navigation.
        controller.drain(menu=False)

        token = controller.get_menu()
        if token in button_map:
            return button_map[token]

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
        screen.fill(ui.BG_COLOR)

        title_surf = title_font.render(title, True, ui.TEXT_COLOR)
        screen.blit(title_surf, title_surf.get_rect(center=(cx, 200)))

        if subtitle:
            sub_surf = sub_font.render(subtitle, True, ui.TEXT_COLOR)
            screen.blit(sub_surf, sub_surf.get_rect(center=(cx, 290)))

        start_y = 430
        gap = 90
        for i, label in enumerate(options):
            is_sel = (i == selected)
            surf = item_font.render(label, True, ui.TEXT_COLOR)
            rect = surf.get_rect(center=(cx, start_y + i * gap))
            if is_sel:
                box = rect.inflate(80, 28)
                pygame.draw.rect(screen, ui.HILITE_BG, box, border_radius=8)
                pygame.draw.rect(screen, ui.TEXT_COLOR, box, 3, border_radius=8)
            screen.blit(surf, rect)

        if hint:
            hint_surf = hint_font.render(hint, True, ui.TEXT_COLOR)
            screen.blit(hint_surf, hint_surf.get_rect(center=(cx, WINDOW_SIZE[1] - 70)))

        pygame.display.update()
        clock.tick(60)


def run_app(screen, clock, controller):
    """Top-level state machine: menu -> play -> game over -> restart/menu."""
    while True:
        # --- main menu: choose a game ---
        choice = choose(screen, clock, controller,
                        "Edge AI Games", [g.name for g in GAMES])
        if choice is None:
            return
        game = GAMES[choice]

        # --- play / game-over loop for the chosen game ---
        while True:
            result = game.run(screen, clock, controller)
            if result is None:  # window closed mid-game -> quit app
                return

            action = choose(
                screen, clock, controller,
                "Game Over",
                ["Restart", "Main Menu"],
                subtitle=f"{game.name}    {game.result_text(result)}",
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
