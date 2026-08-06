#også lånt kode
#
# The status bar across the top of the board surface: title, timer, mines left
# and which input mode is active. Draws onto the board surface it is handed,
# never onto the window.
import pygame

import ui

from .config import MENU_SIZE, GREEN1, RED1, GRAY


class Menu:

    def __init__(self):
        self.label_game_end = self.Label(30, 10)
        self.label_flags = self.Label(250, 45)
        self.label_mode = self.Label(120, 45)
        self.label_time = self.Label(10, 45)
        self.label_minesweeper = self.Label(20, 5)
        self.label_setup = self.Label(30, 40)

    def draw(self, screen, font, game, mode):
        pygame.draw.rect(screen, GRAY, [0, 0, screen.get_width(), MENU_SIZE])

        if game.game_lost:
            self.label_game_end.show(screen, font, "Game Over :(")
        elif game.game_won:
            self.label_game_end.show(screen, font, f"You won!! Your time: {game.get_elapsed_time()}s")
        else:
            # Bundled display font rather than SysFont("impact"), which is not
            # installed on most Linux boxes and silently fell back.
            self.label_minesweeper.show(screen, ui.font(32, ui.FONT_DISPLAY),
                                        "MINESWEEPER", RED1)
            if not game.setup_mode:
                self.label_time.show(screen, ui.font(16),
                                     "Time: " + str(game.get_elapsed_time()))
                self.label_flags.show(screen, ui.font(16),
                                      "Mines: " + str(game.num_bombs))
                if mode == "flag":
                    self.label_mode.show(screen, ui.font(16), "Flag-mode")
                elif mode == "open":
                    self.label_mode.show(screen, ui.font(16), "Open-mode")
            else:
                self.label_setup.show(screen, font, "Place your bombs!")

    class Label:

        def __init__(self, x, y):
            self.x = x
            self.y = y

        def show(self, surface, font, value, color=GREEN1):
            text = font.render(str(value), True, color)
            surface.blit(text, (self.x, self.y))
