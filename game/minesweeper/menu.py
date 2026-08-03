#også lånt kode
import pygame

from .config import MARGIN, MENU_SIZE, GREEN1, WHITE, RED1, GRAY, LABEL_SIZE

class Menu:

    def __init__(self, screen):
        self.width = screen.get_width() - 2 * MARGIN
        self.btn_flags = self.Button(280, 16, 10, 10, "")
        self.btn_flags.background = RED1
        self.label_bombs = self.Label(30, 10)
        self.label_game_end = self.Label(30, 10)
        self.label_flags = self.Label(250, 45)      
        self.label_mode = self.Label(120, 45)       
        self.label_time = self.Label(10, 45)        
        self.label_minesweeper = self.Label(20,5)
        self.label_setup = self.Label(30,40)
        self.menu_font = pygame.font.Font('freesansbold.ttf', 16) 

    def draw(self, screen, font, game, mode):
        self.width = screen.get_width() - 2 * MARGIN
        pygame.draw.rect(screen, GRAY, [0, 0, screen.get_width(), MENU_SIZE])

        #self.btn_flags.draw(screen, font)
        #self.label_bombs.show(screen, font, "Total mines: "+str(game.num_bombs))
        if game.game_lost:
            self.label_game_end.show(screen, font, "Game Over :(")
        elif game.game_won:
            self.label_game_end.show(screen, font, f"You won!! Your time: {game.get_elapsed_time()}s")
            
        else:
            TITLE_FONT = pygame.font.SysFont("impact", 48)
            self.label_minesweeper.show(screen, TITLE_FONT, "MINESWEEPER", RED1)
            #vis tid
            elapsed_time=game.get_elapsed_time()
            if not game.setup_mode:
                self.label_time.show(screen, self.menu_font, "Time: " + str(elapsed_time))
                self.label_flags.show(screen, self.menu_font, "Mines: " + str(game.num_bombs - game.flag_count))
                if mode == "flag":
                    self.label_mode.show(screen, self.menu_font, "Flag-mode")
                elif mode == "open":
                    self.label_mode.show(screen, self.menu_font, "Open-mode")
            else:
                self.label_setup.show(screen, font, "Place your bombs!")


    class Label:

        def __init__(self, x, y):
            self.x = x
            self.y = y

        def show(self, surface, font, value, color=GREEN1):
            text = font.render(str(value), True, color)
            surface.blit(text, (self.x, self.y))

    class Button:

        def __init__(self, x, y, width, height, text, xoff=0, yoff=0):
            self.x = x
            self.y = y
            self.height = height
            self.width = width
            self.background = WHITE
            self.text = text
            self.x_offset = xoff
            self.y_offset = yoff

        def draw(self, surface, font):
            pygame.draw.ellipse(surface, self.background,
                                [self.x, self.y, self.width, self.height], 0)
            text = font.render(self.text, True, GREEN1)
            surface.blit(text, (self.x + self.x_offset, self.y + self.y_offset))