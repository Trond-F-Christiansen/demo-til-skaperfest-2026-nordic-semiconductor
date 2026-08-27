#også lånt kode
#
# The status bar across the top of the board surface: title, timer, mines left
# and which input mode is active. Draws onto the board surface it is handed,
# never onto the window.
import pygame

import ui

from .config import MENU_SIZE, RED1, MS_FACE, MS_TEXT
from .game import draw_bevel


class Menu:

    def __init__(self):
        self.label_game_end = self.Label(30, 10)
        self.label_flags = self.Label(250, 45)
        self.label_mode = self.Label(120, 45)
        self.label_time = self.Label(10, 45)
        self.label_minesweeper = self.Label(20, 5)
        self.label_setup = self.Label(30, 40)

    def draw(self, screen, font, game, mode):
        width = screen.get_width()
        header = pygame.Rect(0, 0, width, MENU_SIZE)
        pygame.draw.rect(screen, MS_FACE, header)
        draw_bevel(screen, header, raised=True)

        if game.game_lost:
            self.label_game_end.show(screen, font, "Game Over :(")
        elif game.game_won:
            self.label_game_end.show(
                screen, font, f"You won! Time: {game.get_elapsed_time()}s")
        else:
            # Bundled display font rather than SysFont("impact"), which is not
            # installed on most Linux boxes and silently fell back.
            self.label_minesweeper.show(screen, ui.font(32, ui.FONT_DISPLAY),
                                        "MINESWEEPER", RED1)
            if not game.setup_mode:
                # Position on the bottom row relative to the header width so the
                # labels never run off a narrow board: time left, mode centred,
                # mines right-aligned.
                small = ui.font(16)
                mode_text = "Flag-mode" if mode == "flag" else "Open-mode"
                mines_text = "Mines: " + str(game.num_bombs)

                self.label_time.x = 10
                self.label_time.show(screen, small,
                                     "Time: " + str(game.get_elapsed_time()))

                self.label_mode.x = (width - small.size(mode_text)[0]) // 2
                self.label_mode.show(screen, small, mode_text)

                self.label_flags.x = width - small.size(mines_text)[0] - 10
                self.label_flags.show(screen, small, mines_text)
            else:
                self.label_setup.show(screen, font, "Place your bombs!")

    class Label:

        def __init__(self, x, y):
            self.x = x
            self.y = y

        def show(self, surface, font, value, color=MS_TEXT):
            text = font.render(str(value), True, color)
            surface.blit(text, (self.x, self.y))
