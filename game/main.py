"""Entry point and menu for the game_controller games.

Run from this folder (assets load via relative paths):

    python main.py                     # autodetect the game_receiver DK
    python main.py /dev/ttyACM3        # or name its console port yourself
    python main.py --baudrate 115200 /dev/ttyACM3

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
    controller      the buttons on a sender board pick an option directly
Those buttons are physical buttons relayed to us over UART as MENU: tokens; see
controller.get_menu().
"""

import argparse

import pygame

import quiz
import snake
import ui
from minesweeper import minesweeper_game

from controller import SerialController

# Window matches snake's grid. New games should draw within this.
WINDOW_SIZE = (snake.cell_number * snake.cell_size,
               snake.cell_number * snake.cell_size)

# How long the pre-game countdown runs. Sized to cover an engine switch on the
# controller board: the outgoing engine has to notice its stop flag and tear
# down its acquisition before the incoming one starts its own. See countdown().
COUNTDOWN_SECONDS = 3

# Menu tokens name what the player asked for, not which button was pressed --
# game_controller's btn0 and btn1 both send SNAKE, differing only in the engine
# they switch to (voice vs swipe gestures), which is entirely that board's
# business since both feed us the same UP/DOWN/LEFT/RIGHT commands. QUIZ comes
# from the finger_digits board instead.
#
# The main menu maps each token to a game via GAME_TOKENS in run_app().


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


def choose(screen, clock, controller, title, options, subtitle=None,
           values=None, token_map=None, hint=None):
    """Render a vertical menu and return what the player chose.

    @param options    list of label strings, drawn top to bottom.
    @param subtitle   optional line under the title (e.g. the result).
    @param values     what to return per option; defaults to the option index.
    @param token_map  controller menu tokens -> the value to return. Tokens that
                      are absent are ignored, so a screen only honours the
                      buttons that mean something on it. A button token can
                      return something no keyboard option offers -- e.g. on the
                      game-over screen, btn2 jumps straight to minesweeper.
    @param hint       one line about the buttons, drawn along the bottom.
    @return the chosen value, or None if the player quit (ESC / window close).
    """
    title_font = ui.font(72)
    sub_font = ui.font(36)
    item_font = ui.font(48)
    hint_font = ui.font(24)

    token_map = token_map or {}
    if values is None:
        values = list(range(len(options)))

    selected = 0
    cx = WINDOW_SIZE[0] // 2

    while True:
        # ---- input --------------------------------------------------------
        # Controller swipes and finger digits queued while a menu is up mean
        # nothing here, so drop them -- but keep the menu queue, which is this
        # screen's navigation.
        controller.drain(menu=False)

        token = controller.get_menu()
        if token in token_map:
            return token_map[token]

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return values[selected]
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


def countdown(screen, clock, controller, game, seconds=COUNTDOWN_SECONDS):
    """Count down before a game starts, and drop input queued while waiting.

    Pressing a button switches the engine on the controller board, which is not
    instant: the engine that is running has to notice its stop flag, tear down
    its acquisition, and the new one has to start its own (the IMU for gestures,
    the microphone for keyword spotting). Starting the game immediately means
    the first second or two of play has no working input. This screen gives that
    switch time to land, and tells the player what is coming.

    @return True to start the game, False if the player quit.
    """
    title_font = ui.font(56)
    count_font = ui.font(160)
    hint_font = ui.font(28)

    cx, cy = WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2
    deadline = pygame.time.get_ticks() + int(seconds * 1000)

    while True:
        remaining_ms = deadline - pygame.time.get_ticks()
        if remaining_ms <= 0:
            return True

        # Anything the player did before the game began is stale by definition,
        # including menu tokens -- the game is already chosen.
        controller.drain()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False

        screen.fill(ui.BG_COLOR)

        title_surf = title_font.render(f"Get ready: {game.name}", True, ui.TEXT_COLOR)
        screen.blit(title_surf, title_surf.get_rect(center=(cx, cy - 170)))

        # Ceiling, so a 3s countdown reads 3 - 2 - 1 rather than 2 - 1 - 0.
        count_surf = count_font.render(str(-(-remaining_ms // 1000)), True, ui.TEXT_COLOR)
        screen.blit(count_surf, count_surf.get_rect(center=(cx, cy)))

        hint_surf = hint_font.render("ESC to cancel", True, ui.TEXT_COLOR)
        screen.blit(hint_surf, hint_surf.get_rect(center=(cx, WINDOW_SIZE[1] - 70)))

        pygame.display.update()
        clock.tick(60)


# Returned by the game-over screen when the player wants the game list back.

def show_result(screen, clock, controller, game, result):
    """Show the run's result, then wait for any input before the menu.

    Returns True to go on to the main menu, False if the player quit.
    Any keypress or controller button dismisses the screen; the button's
    engine switch is harmless because the main menu re-selects on the next
    game choice anyway.
    """
    title_font = ui.font(72)
    sub_font = ui.font(36)
    hint_font = ui.font(24)
    cx = WINDOW_SIZE[0] // 2

    while True:
        controller.drain(menu=False)
        if controller.get_menu() is not None:
            return True

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                return True

        screen.fill(ui.BG_COLOR)

        title_surf = title_font.render("Game Over", True, ui.TEXT_COLOR)
        screen.blit(title_surf, title_surf.get_rect(center=(cx, 200)))

        sub_surf = sub_font.render(f"{game.name}    {game.result_text(result)}",
                                   True, ui.TEXT_COLOR)
        screen.blit(sub_surf, sub_surf.get_rect(center=(cx, 290)))

        hint_surf = hint_font.render("Trykk en knapp for meny", True, ui.TEXT_COLOR)
        screen.blit(hint_surf, hint_surf.get_rect(center=(cx, WINDOW_SIZE[1] - 70)))

        pygame.display.update()
        clock.tick(60)

def run_app(screen, clock, controller):
    """Top-level state machine: menu -> countdown -> play -> game over -> menu.

    A controller button always means the same thing on every screen: "play this
    game, with the engine this button selects". The main menu maps each token
    straight to a Game; after a round, the game-over screen just shows the
    result and returns to the menu, so there is no per-game restart button to
    keep in sync with the controller's engine switch.
    """
    # Which game each token opens.
    GAME_TOKENS = {g.name.upper(): g for g in GAMES}
    MENU_HINT = ("BTN0: Snake (voice)    BTN1: Snake (gesture)    "
                 "BTN2: Minesweeper")

    game = None
    while True:
        # --- main menu: choose a game ---
        if game is None:
            game = choose(screen, clock, controller,
                          "Edge AI Games", [g.name for g in GAMES],
                          values=GAMES, token_map=GAME_TOKENS, hint=MENU_HINT)
            if game is None:
                return

        # --- countdown, so a just-pressed engine switch has time to land ---
        if not countdown(screen, clock, controller, game):
            return

        result = game.run(screen, clock, controller)
        if result is None:      # window closed mid-game -> quit app
            return

        # --- game over: show the result, then back to the main menu ---
        if not show_result(screen, clock, controller, game, result):
            return              # quit
        game = None             # always return to the game list

def parse_args(argv=None):
    """Parse the command line: an optional serial port, plus its baud rate."""
    parser = argparse.ArgumentParser(description="Edge AI Games")
    parser.add_argument(
        "port", nargs="?", default=None,
        help="console port of the DK running game_receiver, e.g. /dev/ttyACM3. "
             "Omit to autodetect it (see controller.find_controller_port).")
    parser.add_argument(
        "--baudrate", type=int, default=115200,
        help="serial baud rate (default: %(default)s).")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Edge AI Games")
    clock = pygame.time.Clock()

    # port=None => autodetect.
    controller = SerialController(args.port, args.baudrate)
    try:
        controller.start()
    except (RuntimeError, OSError) as exc:
        # No board, or the named port cannot be opened: keep going so the menus
        # and keyboard still work.
        print(f"[main] {exc}\n[main] continuing with keyboard input only.")

    try:
        run_app(screen, clock, controller)
    finally:
        controller.stop()
        pygame.quit()


if __name__ == "__main__":
    main()
