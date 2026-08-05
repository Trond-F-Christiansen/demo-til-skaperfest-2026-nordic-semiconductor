"""Minesweeper's game loop, played by voice through the shared controller.

@ref run is the menu's entry point, under the same contract as snake.run and
quiz.run: it owns its loop and returns the run's result, or None if the player
closed the window (main.py treats None as "quit the app"). The result here is
elapsed seconds -- lower is better -- which is why main.py labels minesweeper's
result "Time" rather than "Score".

The board has its own aspect ratio, so it is drawn at natural size into an
off-screen surface and scaled into the window main.py owns. Changing difficulty
therefore only changes those numbers; nothing here calls
pygame.display.set_mode().

Spoken input, read off controller.get_command():
    <row> <column>      two numbers pick a square
    open / flag         what the next picked square does
    no                  forget a mis-heard row
    reset (twice)       start over
    easy / hard         swap difficulty between rounds
Keyboard extras for laying out a board by hand: M enters setup mode, click to
toggle mines, SPACE commits. ESC gives up and returns the time so far.
"""

import pygame
import ui

from .config import (
    WIDTH, HEIGHT, MARGIN, MENU_SIZE, LABEL_SIZE, LEFT_CLICK, RIGHT_CLICK,
    DIFFICULTIES, GREEN1
)
from .game import Game
from .menu import Menu

# Width reserved down the left of the window for the help box; the board is
# centred in what is left.
INFO_WIDTH = 280

# Fraction of the available area the board fills, leaving a margin around it.
BOARD_FILL = 0.9

_HELP_LINES = [
    ("Stemmestyring", True),
    ("", False),
    ("Si tall (rad og", False),
    ("kolonne) for å", False),
    ("velge en rute.", False),
    ("", False),
    ("'mark' åpner ruten", False),
    ("du har valgt.", False),
    ("", False),
    ("'bomb' setter et", False),
    ("flagg der du tror", False),
    ("det er en mine.", False),
    ("", False),
    ("'no' angrer hvis", False),
    ("du sa feil tall.", False),
    ("", False),
]


def handle_voice_input(game, state, controller):
    # Numbers name a row or column, so anything at or past the board edge is a
    # mis-hear. The bound follows the board, which "easy"/"hard" can change.
    keyword = controller.get_command(max_square=game.squares_x)
    if keyword is None:
        return
    kind, result = keyword

    if kind=="command":
        if result=="reset":
            state["reset_count"]+=1
            if state["reset_count"]>=2:
                state["reset_count"]=0
                game.reset_game()
                print("------resetter-------")
                state["mode"] = "open"
                state["row"] = None
                state["column"] = None

            else:
                print("Si reset en gang til for å resette")

        elif result=="flag":
            state["reset_count"]=0
            state["row"] = None
            state["column"] = None
            print("flag-mode")
            state["mode"] = "flag"

        elif result=="open":
            state["reset_count"]=0
            print("normal-mode")
            state["mode"] = "open"
            state["row"] = None
            state["column"] = None

        elif result=="no":
            state["reset_count"]=0
            state["row"] = None

        # Difficulty only between rounds, so a losing board can't be swapped
        # out mid-game. The loop picks up the new board size on the next frame.
        elif result in DIFFICULTIES and not game.in_progress():
            state["reset_count"]=0
            game.setup_mode = False
            game.set_difficulty(DIFFICULTIES[result]["size"],
                                DIFFICULTIES[result]["bombs"])
            state["row"] = None
            state["column"] = None
            print(f"{result}-mode")

    elif kind=="number" and not game.setup_mode:
        if state["row"] is None:
            state["row"] = result
            print(state["row"])
        elif state["column"] is None:
            state["column"] = result
            print(state["column"])
            if state["mode"]=="open":
                game.click_handle(state["row"], state["column"], LEFT_CLICK)
                print("åpner")
            elif state["mode"]=="flag":
                game.click_handle(state["row"], state["column"], RIGHT_CLICK)
                print("flagger")
            state["row"] = None
            state["column"] = None


def draw_info(screen):
    """Tegn en hjelpetekst i en boks til venstre for brettet."""
    title_font = ui.font(26)
    text_font = ui.font(18)

    box_x = 15
    box_y = 90
    box_w = 250
    # Sized to the text rather than hardcoded, so lines can be added above.
    box_h = 40 + sum(14 if not text else
                     (title_font if is_title else text_font).get_height() + 6
                     for text, is_title in _HELP_LINES)

    # Bakgrunn + ramme
    box = pygame.Rect(box_x, box_y, box_w, box_h)
    pygame.draw.rect(screen, (200, 195, 210), box, border_radius=12)
    pygame.draw.rect(screen, (80, 40, 40), box, 3, border_radius=12)

    # Tekst
    x = box_x + 18
    y = box_y + 20
    for text, is_title in _HELP_LINES:
        if text == "":
            y += 14
            continue
        f = title_font if is_title else text_font
        color = (180, 60, 60) if is_title else (40, 40, 40)
        surf = f.render(text, True, color)
        screen.blit(surf, (x, y))
        y += f.get_height() + 6


def _layout(screen, game):
    """Board surface, and how big/where to blit it, for the current board size.

    @return (board_surf, scaled_size, offset). Recomputed whenever the board
            changes size, which is what makes difficulty switching work.
    """
    board_size = game.board_pixel_size()
    win_w, win_h = screen.get_size()
    avail_w = win_w - INFO_WIDTH
    scale = min(avail_w / board_size[0], win_h / board_size[1]) * BOARD_FILL
    scaled_size = (int(board_size[0] * scale), int(board_size[1] * scale))
    # sentrer brettet i omradet TIL HOYRE for infoboksen
    offset = (INFO_WIDTH + (avail_w - scaled_size[0]) // 2,
              (win_h - scaled_size[1]) // 2)
    return pygame.Surface(board_size), scaled_size, offset


def run(screen, clock, controller):
    """Play one round; see the module docstring for the return value."""
    font = ui.font(24)

    game = Game()
    menu = Menu()
    board_surf, scaled_size, offset = _layout(screen, game)

    state = {"row": None, "column": None, "mode": "open", "reset_count": 0}

    # Drop anything queued while the menu was up, so a stale number doesn't
    # open a square the moment the board appears.
    controller.drain()

    def blit_board():
        screen.blit(pygame.transform.smoothscale(board_surf, scaled_size), offset)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None            # window closed -> main.py quits the app
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if game.setup_mode:
                    # Window coordinates -> board coordinates: undo the blit
                    # offset and the scaling, then the board's own margins.
                    x = (event.pos[0] - offset[0]) * board_surf.get_width() / scaled_size[0]
                    y = (event.pos[1] - offset[1]) * board_surf.get_height() / scaled_size[1]
                    r = int(y - MARGIN - MENU_SIZE - LABEL_SIZE) // (HEIGHT + MARGIN)
                    c = int(x - MARGIN - LABEL_SIZE) // (WIDTH + MARGIN)
                    if 0 <= r < game.squares_y and 0 <= c < game.squares_x:
                        cell = game.grid[r][c]
                        #bombe hvis uten bombe, ikke bombe hvis det er en bombe der allerede
                        cell.has_bomb = not cell.has_bomb

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return game.get_elapsed_time()   # gir opp
                elif event.key == pygame.K_m:
                    game.setup_mode=True
                    game.reset_game()
                    print("Oppsett-modus: klikk for å plassere bomber. Trykk mellomrom når du er fornøyd.")
                elif event.key == pygame.K_SPACE and game.setup_mode:
                    game.setup_mode=False
                    game.count_all_bombs() #regner ut nabotallene
                    count = 0
                    for r in game.grid:
                        for cell in r:
                            if cell.has_bomb:
                                count+=1
                    game.num_bombs=count
                    game.init=True #hopper over utplassering av bomber

        handle_voice_input(game, state, controller)

        # set_difficulty() may have swapped in a different board.
        if board_surf.get_size() != game.board_pixel_size():
            board_surf, scaled_size, offset = _layout(screen, game)

        screen.fill(GREEN1)
        draw_info(screen)
        game.draw(board_surf, font, state)
        menu.draw(board_surf, font, game, state["mode"])
        blit_board()

        if game.game_won or game.game_lost:
            seconds = game.get_elapsed_time()
            if game.game_won:
                controller.send_score("minesweeper", seconds)
            pygame.display.flip()
            pygame.time.delay(1500)   # la spilleren se resultatet
            return seconds

        clock.tick(60)
        pygame.display.flip()
