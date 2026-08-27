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
import snake
import ui
from minesweeper import minesweeper_game

from controller import SerialController, BACK_TO_MENU

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
# business since both feed us the same UP/DOWN/LEFT/RIGHT commands.
#
# The main menu maps each token to a game via GAME_TOKENS in run_app().


class Game:
    """A menu-selectable game.

    @param name          label in the main menu.
    @param run           entry point, run(screen, clock, controller) -> result.
    @param result_label  how the game-over screen words that result, and the
                         unit to print after it. Minesweeper is timed, so its
                         result is seconds and lower is better; snake
                         returns a higher-is-better score.
    @param instructions  an instructions.Instructions for the how-to-play page
                         shown on the way in, or None to go straight to the
                         countdown.
    """

    def __init__(self, name, run, result_label="Score", result_unit="",
                 instructions=None, token=None, score_game=None):
        self.name = name
        self.run = run
        self.result_label = result_label
        self.result_unit = result_unit
        self.instructions = instructions
        self.token = token
        self.score_game = score_game

    def result_text(self, result):
        return f"{self.result_label}: {result}{self.result_unit}"


# Registry of playable games -- extend this as games are added. Minesweeper is
# a package rather than a single module, but its run() means the same thing.
#
# The instructions text is placeholder wording for now; the images are real,
# taken from the Graphics/ art each game already uses, so the pages show the
# gestures and hand shapes a player actually needs.
GAMES = [
    Game("Snake (stemme)", snake.run, token="SNAKE_VOICE", score_game="snake_voice",
         instructions=instructions.Instructions(
             lines=(
                 "Styr slangen med stemmen: si opp, ned, venstre eller høyre.",
                 "Spis frukten for å vokse. Treffer du veggen eller din egen "
                 "hale, er runden over.",
             ),
             images=("head_up", "head_left", "head_right", "head_down"),
             advance_hint="Trykk BTN3 for å starte",
         )),
    Game("Snake (bevegelse)", snake.run, token="SNAKE_GESTURE", score_game="snake_geusture",
         instructions=instructions.Instructions(
             lines=(
                 "Styr slangen med håndbevegelser: sveip opp, ned, venstre "
                 "eller høyre for å svinge.",
                 "Spis frukten for å vokse. Treffer du veggen eller din egen "
                 "hale, er runden over.",
             ),
             images=("head_up", "head_left", "head_right", "head_down"),
             advance_hint="Trykk BTN1 for å starte",
         )),
        Game("Minesweeper", minesweeper_game.run, token="MINESWEEPER",
            result_label="Tid", result_unit="s", score_game="minesweeper",
         instructions=instructions.Instructions(
             lines=(
                 "Si \"mark\" for å åpne ruter, eller \"bomb\" for å markere "
                 "en bombe. Modusen henger igjen til du bytter -- du sier den "
                 "bare én gang, ikke for hver rute.",
                 "Velg en rute: si radnummeret på engelsk (0-7), vent litt, "
                 "og si så kolonnenummeret.",
                 "Si \"no\" for å angre, eller \"reset\" to ganger for å "
                 "starte på nytt.",
                 "Åpne alle trygge ruter så raskt du kan -- tiden din er "
                 "poengsummen, så jo lavere jo bedre. Lykke til!",
             ),
             images=("flag", "bomb"),
             advance_hint="Trykk BTN2 for å starte",
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

        # ---- draw ---------------------------------------------------------
        ui.draw_background(screen)

        title_surf = ui.render_text(title, title_font, offset=3)
        ui.blit_center(screen, title_surf, (cx, 200))

        if subtitle:
            sub_surf = ui.render_text(subtitle, sub_font, ui.TEXT_MUTED)
            ui.blit_center(screen, sub_surf, (cx, 290))

        start_y = 430
        gap = 90
        for i, label in enumerate(options):
            is_sel = (i == selected)
            surf = item_font.render(label, True, ui.TEXT_COLOR)
            rect = surf.get_rect(center=(cx, start_y + i * gap))
            # if is_sel:
            #     box = rect.inflate(80, 28)
            #     pygame.draw.rect(screen, ui.HILITE_BG, box, border_radius=10)
            #     pygame.draw.rect(screen, ui.ACCENT, box, 3, border_radius=10)
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
        if controller.check_back():
            return BACK_TO_MENU
        controller.drain()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

        ui.draw_background(screen)

        title_surf = ui.render_text(f"Gjør deg klar: {game.name}", title_font, offset=2)
        ui.blit_center(screen, title_surf, (cx, cy - 195))

        # A disc and ring behind the number frame the count.
        R = 150
        disc = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
        pygame.draw.circle(disc, (10, 40, 62, 190), (R, R), R)
        screen.blit(disc, disc.get_rect(center=(cx, cy)))
        pygame.draw.circle(screen, ui.ACCENT, (cx, cy), R, 6)
        pygame.draw.circle(screen, ui.PANEL_EDGE, (cx, cy), R - 12, 2)

        # Ceiling, so a 3s countdown reads 3 - 2 - 1 rather than 2 - 1 - 0.
        count_surf = ui.render_text(str(-(-remaining_ms // 1000)), count_font,
                                    offset=4)
        ui.blit_center(screen, count_surf, (cx, cy))

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

        ui.draw_background(screen)

        panel = pygame.Rect(0, 0, 760, 300)
        panel.center = (cx, WINDOW_SIZE[1] // 2 - 20)
        ui.draw_panel(screen, panel)

        title_surf = ui.render_text("Game Over", title_font, ui.ACCENT, offset=3)
        ui.blit_center(screen, title_surf, (cx, panel.top + 90))

        sub_surf = ui.render_text(f"{game.name}    {game.result_text(result)}",
                                  sub_font)
        ui.blit_center(screen, sub_surf, (cx, panel.centery + 30))

        hint_surf = ui.render_text("Trykk en knapp for meny", hint_font,
                                   ui.TEXT_MUTED)
        ui.blit_center(screen, hint_surf, (cx, WINDOW_SIZE[1] - 70))

        pygame.display.update()
        clock.tick(60)
# One entry per DK button, indexed by button number (BTN0..BTN3). Each entry is
# the button label, the game name and input method, and the menu token it
# selects (None = the button starts no game -- BTN0 is "back"). The DK is held
# sideways, so _draw_mini_dk() places these into their physical positions.



MENU_GRID = [
    ("BTN0", "", "", None),
    ("BTN1", "Snake", "(bevegelse)", "SNAKE_GESTURE"),
    ("BTN2", "Minesweeper", "(stemme)", "MINESWEEPER"),
    ("BTN3", "Snake", "(stemme)", "SNAKE_VOICE"),
]

# Order the games appear in the list, by BTN index: both Snakes together, then
# Minesweeper. Display only -- each row's mini-DK still shows its real button.
MENU_ORDER = [1, 3, 2]

def _draw_mini_dk(screen, rect, active_index, btn_font):
    """A small nRF54LM20 DK: a 2x2 of buttons, the selecting one lit in accent,
    the other three greyed out. `active_index` is the MENU_GRID button index.

    The DK is held sideways, so the 2x2 reads BTN1 BTN3 / BTN0 BTN2.
    """
    pygame.draw.rect(screen, (10, 26, 48), rect, border_radius=12)
    pygame.draw.rect(screen, (44, 92, 138), rect, 2, border_radius=12)

    # Screen cell (TL, TR, BL, BR) -> the MENU_GRID button index that sits there.
    layout = (1, 3, 0, 2)
    pad, gap = 14, 12
    bw = (rect.width - 2 * pad - gap) // 2
    bh = (rect.height - 2 * pad - gap) // 2
    for j in range(4):
        row, col = divmod(j, 2)
        brect = pygame.Rect(rect.x + pad + col * (bw + gap),
                            rect.y + pad + row * (bh + gap), bw, bh)
        btn_index = layout[j]
        if btn_index == active_index:
            pygame.draw.rect(screen, ui.ACCENT, brect, border_radius=8)
            pygame.draw.rect(screen, (150, 110, 0), brect, 2, border_radius=8)
            txt_col = (40, 30, 0)
        else:
            pygame.draw.rect(screen, (58, 66, 80), brect, border_radius=8)
            pygame.draw.rect(screen, (34, 40, 52), brect, 2, border_radius=8)
            txt_col = (140, 146, 156)
        label = btn_font.render(MENU_GRID[btn_index][0], True, txt_col)
        screen.blit(label, label.get_rect(center=brect.center))


def _draw_game_row(screen, rect, grid_i, btn_label, name, sub_label, selected,
                   name_font, sub_font, mini_font):
    """One list row: a mini DK (button to press highlighted) plus the game."""
    radius = 18

    shadow = pygame.Surface((rect.width, rect.height + 8), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 80), shadow.get_rect(),
                     border_radius=radius)
    screen.blit(shadow, (rect.x, rect.y + 8))

    pygame.draw.rect(screen, ui.PANEL_BG, rect, border_radius=radius)
    # if selected:
    #     pygame.draw.rect(screen, ui.ACCENT, rect.inflate(12, 12), 5,
    #                      border_radius=radius + 5)
    #     pygame.draw.rect(screen, ui.ACCENT, rect, 3, border_radius=radius)
    # else:
    pygame.draw.rect(screen, ui.PANEL_EDGE, rect, 2, border_radius=radius)

    # Mini DK on the left, showing which button selects this game.
    mini = pygame.Rect(0, 0, rect.height - 30, rect.height - 30)
    mini.midleft = (rect.left + 24, rect.centery)
    _draw_mini_dk(screen, mini, grid_i, mini_font)

    # Game name + input method to the right of the diagram.
    text_x = mini.right + 34
    name_surf = name_font.render(name, True, ui.TEXT_COLOR)
    screen.blit(name_surf,
                name_surf.get_rect(midleft=(text_x, rect.centery - 22)))
    if sub_label:
        sub_surf = sub_font.render(sub_label, True, ui.TEXT_MUTED)
        screen.blit(sub_surf,
                    sub_surf.get_rect(midleft=(text_x, rect.centery + 24)))

def main_menu(screen, clock, controller, token_map):
    """Main menu: a vertical list of the games.

    Each row pairs the game with a small nRF54LM20 DK diagram whose four
    buttons show which one to press -- the selecting button is highlighted and
    the other three greyed out. Returns the chosen game (via token_map), or None
    if the player quit.
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

    title_font = ui.font(58)
    name_font = ui.font(38, ui.FONT_DISPLAY)
    sub_font = ui.font(24)
    mini_font = ui.font(15, ui.FONT_DISPLAY)

    win_w, win_h = WINDOW_SIZE
    cx = win_w // 2

    # The playable games in list order, keeping each one's physical button
    # position (its MENU_GRID index) so the mini-DK lights the right button.
    games = [(i, MENU_GRID[i]) for i in MENU_ORDER if MENU_GRID[i][3] is not None]

    row_w, row_h, row_gap = 740, 170, 34
    total_h = len(games) * row_h + (len(games) - 1) * row_gap
    start_y = 250

    selected = 0

    while True:
        controller.drain(menu=False)

        token = controller.get_menu()
        if token in token_map:
            return token_map[token]

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None

        # ---- draw ----
        ui.draw_background(screen)

        title_surf = ui.render_text("Nordic Edge AI Spill", title_font, offset=3)
        ui.blit_center(screen, title_surf, (cx, 96))
        sub_surf = ui.render_text(
            "Trykk knappen på DK-en for å starte spillet",
            sub_font, ui.TEXT_MUTED, offset=1)
        ui.blit_center(screen, sub_surf, (cx, 156))

        for k, (grid_i, cell) in enumerate(games):
            btn_label, name, sub_label, tok = cell
            rect = pygame.Rect(cx - row_w // 2,
                               start_y + k * (row_h + row_gap), row_w, row_h)
            _draw_game_row(screen, rect, grid_i, btn_label, name, sub_label,
                           k == selected, name_font, sub_font, mini_font)

        if logo is not None:
            ui.blit_center(screen, logo, (cx, win_h - 100))

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
    GAME_TOKENS = {g.token: g for g in GAMES}
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
            res = instructions.show(screen, clock, controller, game)
            if res is False:            # window closed / ESC -> quit app
                return
            if res is BACK_TO_MENU:     # hold to go back -> main menu
                game = None
                played = None
                continue

        # --- countdown, so a just-pressed engine switch has time to land ---
        res = countdown(screen, clock, controller, game)
        if res is False:
            return
        if res is BACK_TO_MENU:
            game = None
            played = None
            continue

        controller.set_score_game(game.score_game)
        result = game.run(screen, clock, controller)
        if result is None:      # window closed mid-game -> quit app
            return
        if result is BACK_TO_MENU:   # controller BACK -> straight to menu
            game = None
            played = None
            continue
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
