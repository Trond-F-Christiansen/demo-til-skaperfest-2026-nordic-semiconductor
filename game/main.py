"""Entry point and menu for the game_controller games.

Run from this folder (assets load via relative paths):

    python main.py                     # autodetect the game_receiver DK
    python main.py /dev/ttyACM3        # or name its console port yourself
    python main.py --baudrate 115200 /dev/ttyACM3

Flow:
    main menu    -> pick a game
    instructions -> how it is played, then continue (skipped when replaying the
                    same game from the game-over screen)
    countdown    -> gives an engine switch time to land
    play         -> the game runs its own loop and returns the run's result
    game over    -> Restart (same game) or Main Menu; the result is shown

One window, one screen model: main() creates the display once and every screen
-- this menu, the game-over screen and all three games -- draws into that same
surface. Nothing calls pygame.display.set_mode() again. A game whose natural
geometry differs from the window (minesweeper's board) renders into an
off-screen surface and scales it into place. Shared colours and fonts live in
ui.py.

Adding a game later: write a module with a `run(screen, clock, controller)`
that returns the run's result (int), or None if the window was closed
mid-game, then add one entry to GAMES below -- with a result_label if "Score"
is the wrong word for what it returns, and an `instructions` block for its
how-to-play page. The menu, instructions and game-over screens need no changes.

Every screen is navigated the same three ways:
    UP / DOWN       move the selection,  ENTER / SPACE confirm
    ESC             quit
    controller      the buttons on a sender board pick an option directly
Those buttons are physical buttons relayed to us over UART as MENU: tokens; see
controller.get_menu().
"""

import argparse

import pygame

import instructions
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
    @param instructions  an instructions.Instructions for the how-to-play page
                         shown on the way in, or None to go straight to the
                         countdown.
    """

    def __init__(self, name, run, result_label="Score", result_unit="",
                 instructions=None):
        self.name = name
        self.run = run
        self.result_label = result_label
        self.result_unit = result_unit
        self.instructions = instructions

    def result_text(self, result):
        return f"{self.result_label}: {result}{self.result_unit}"


# Registry of playable games -- extend this as games are added. Minesweeper is
# a package rather than a single module, but its run() means the same thing.
#
# The instructions text is placeholder wording for now; the images are real,
# taken from the Graphics/ art each game already uses, so the pages show the
# gestures and hand shapes a player actually needs. Only the quiz has a gesture
# assigned for leaving its page -- see instructions.py.
GAMES = [
    Game("Snake", snake.run,
         instructions=instructions.Instructions(
             lines=(
                 "Steer the snake with swipe gestures: swipe up, down, left or "
                 "right to turn.",
                 "Eat the fruit to grow. Hitting a wall or your own tail ends "
                 "the run.",
                 "Placeholder instructions -- to be written.",
             ),
             images=("head_up", "head_left", "head_right", "head_down"),
         )),
    Game("Quiz", quiz.run, instructions=instructions.Instructions(
             lines=(
                 "Each question has up to five answers. Hold up the matching "
                 "number of fingers to pick one.",
                 "The correct answer lights up green for a moment, then the "
                 "After the correct answer is shown, remove your hand from the box.",
                 "Placeholder instructions -- to be written.",
             ),
             # The same hand shapes, in the same order, as the per-option
             # graphics in quiz.py's run().
             images=("one", "shaka", "rocknroll", "four", "five"),
             advance=instructions.digit(2),
             advance_hint="Vis to fingre for å starte",
         )),
    Game("Minesweeper", minesweeper_game.run, result_label="Time", result_unit="s",
         instructions=instructions.Instructions(
             lines=(
                 "Pick a square by saying its row and column number out loud.",
                 "Say \"open\" to uncover it, or \"flag\" to mark a mine.",
                 "Clear every safe square as fast as you can -- your time is "
                 "the score, so lower is better.",
                 "Placeholder instructions -- to be written.",
             ),
             images=("zero", "one", "two", "three"),
         )),
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
# The four DK buttons in their physical 2x2 layout. Each entry is the button
# label, the two text lines under it, and the menu token it selects (None = the
# button does nothing on this screen). Order is row-major: top-left, top-right,
# bottom-left, bottom-right -- matching the board's BTN0/1 over BTN2/3.


MENU_GRID = [
    ("BTN0", "Snake", "(bevegelse)", "SNAKE"),
    ("BTN1", "Quiz", "", "QUIZ"),
    ("BTN2", "Snake", "(stemme)", "SNAKE"),
    ("BTN3", "Minesweeper", "", "MINESWEEPER"),
]

def _draw_button(screen, rect, label, selected, enabled, btn_font):
    """Draw one DK-style push button: a light keycap with a round cap on top."""
    # Colours chosen to read like the real board's white tactile switches.
    base = (235, 235, 235) if enabled else (90, 90, 90)
    cap = (250, 250, 250) if enabled else (110, 110, 110)
    edge = (40, 40, 40)
    ring = ui.TEXT_COLOR if selected else edge

    # Square keycap base with a subtle border.
    pygame.draw.rect(screen, base, rect, border_radius=10)
    pygame.draw.rect(screen, ring, rect, 5 if selected else 3, border_radius=10)

    # Round pressable cap in the middle.
    cx, cy = rect.center
    r = min(rect.width, rect.height) // 3
    pygame.draw.circle(screen, cap, (cx, cy), r)
    pygame.draw.circle(screen, edge, (cx, cy), r, 3)

    # Button name on the cap.
    label_color = (30, 30, 30) if enabled else (150, 150, 150)
    surf = btn_font.render(label, True, label_color)
    screen.blit(surf, surf.get_rect(center=(cx, cy)))

def _draw_dk_board(screen, board_rect):
    """Draw the top half of a stylised DK board (the bottom runs off-screen)."""
    # PCB-plate (Nordic-aktig mørk blå), med en lysere kant rundt.
    pygame.draw.rect(screen, (10, 26, 48), board_rect.inflate(12, 12),
                     border_radius=22)
    pygame.draw.rect(screen, (18, 42, 74), board_rect, border_radius=18)

    # Skruehull i de to øvre hjørnene (de nedre er utenfor skjermen).
    for corner in (board_rect.topleft, board_rect.topright):
        ox = 18 if corner[0] == board_rect.left else -18
        pygame.draw.circle(screen, (8, 20, 38), (corner[0] + ox, corner[1] + 18), 8)

def main_menu(screen, clock, controller, token_map):
    """Child-friendly main menu: a picture of the DK with its buttons.

    The board is drawn with a mic on top and a USB cable below. The four
    tactile switches sit in their real spot -- a 2x2 block in the top-right
    corner (BTN0/1 over BTN2/3) -- each with the game it starts written below.
    Returns the chosen game (via token_map), or None if the player quit.
    """
    try:
        logo = pygame.image.load("Graphics/nod.png").convert_alpha()
        logo_w = 180
        scale = logo_w / logo.get_width()
        logo = pygame.transform.smoothscale(
            logo, (logo_w, int(logo.get_height() * scale)))
    except (pygame.error, FileNotFoundError) as exc:
        print(f"[menu] kunne ikke laste logo: {exc}")
        logo = None

    title_font = ui.font(72)
    btn_font = ui.font(26)
    label_font = ui.font(28)
    sub_font = ui.font(20)

    win_w, win_h = WINDOW_SIZE
    cx = win_w // 2

    # Only the top half of the board shows: it starts under the title and its
    # bottom runs off the bottom of the window, so no USB cable is needed.
    board_w = 520
    board_rect = pygame.Rect(cx - board_w // 2, 200, board_w, win_h)

    # 2x2 button block in the board's top-right corner, like the real switches.
    btn_size = 170
    cap_h = 55                 # space under each button for its two text lines
    gap_x, gap_y = 40, 40
    cell_w = btn_size + gap_x
    cell_h = btn_size + cap_h + gap_y
    grid_w = cell_w * 2 - gap_x
    grid_x = board_rect.right - 50 - grid_w
    grid_y = board_rect.top + 50

    def button_rect(i):
        row, col = divmod(i, 2)
        x = grid_x + col * cell_w
        y = grid_y + row * cell_h
        return pygame.Rect(x, y, btn_size, btn_size)

    playable = [i for i, cell in enumerate(MENU_GRID) if cell[3] is not None]
    selected = 0

    while True:
        controller.drain(menu=False)

        token = controller.get_menu()
        if token in token_map:
            return token_map[token]

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w,
                                 pygame.K_LEFT, pygame.K_a):
                    selected = (selected - 1) % len(playable)
                elif event.key in (pygame.K_DOWN, pygame.K_s,
                                   pygame.K_RIGHT, pygame.K_d):
                    selected = (selected + 1) % len(playable)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return token_map[MENU_GRID[playable[selected]][3]]
                elif event.key == pygame.K_ESCAPE:
                    return None

        # ---- draw ----
        screen.fill(ui.BG_COLOR)

        title_surf = title_font.render("Edge AI Games", True, ui.TEXT_COLOR)
        screen.blit(title_surf, title_surf.get_rect(center=(cx, 90)))

        # The board goes down first, so the buttons sit on top of it.
        _draw_dk_board(screen, board_rect)

        for i, (btn, line1, line2, tok) in enumerate(MENU_GRID):
            rect = button_rect(i)
            enabled = tok is not None
            is_sel = enabled and playable[selected] == i

            # Game name goes on the button itself now, not "BTN0" etc.
            _draw_button(screen, rect, line1, is_sel, enabled, btn_font)

            # Only the sub-line (input method) stays under the button.
            if line2:
                l2 = sub_font.render(line2, True, ui.TEXT_COLOR)
                screen.blit(l2, l2.get_rect(center=(rect.centerx, rect.bottom + 24)))
        
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
    played = None               # the game whose round just finished; see below
    while True:
        # --- main menu: choose a game ---
        if game is None:
            game = main_menu(screen, clock, controller, GAME_TOKENS)
            if game is None:
                return

        # --- how to play, on the way in to a game ---
        # Skipped for a straight "Restart" of the game just played -- re-reading
        # the rules between rounds would only be in the way. Any other route
        # here shows them: from the main menu (which clears `played` below), or
        # by picking a different game with a button on the game-over screen.
        if game is not played:
            if not instructions.show(screen, clock, controller, game):
                return

        # --- countdown, so a just-pressed engine switch has time to land ---
        if not countdown(screen, clock, controller, game):
            return

        result = game.run(screen, clock, controller)
        if result is None:      # window closed mid-game -> quit app
            return
        played = game

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
