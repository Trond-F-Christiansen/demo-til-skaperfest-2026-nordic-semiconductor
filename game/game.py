#lånt fra nettet

from random import randrange
import pygame
from cloud_sender import send_score

from config import (
    WIDTH, HEIGHT, NSQUARES, MARGIN, MENU_SIZE,
    GREEN1, WHITE, RED1, RED, GRAY,
    LEFT_CLICK, RIGHT_CLICK, LABEL_SIZE, NUM_BOMBS, HIGHLIGHT,  NUMBER_COLORS
)

class Game:
    def __init__(self):
        self.grid = [[self.Cell(x, y) for x in range(NSQUARES)]
                     for y in range(NSQUARES)]
        self.init = False
        self.game_lost = False
        self.game_won = False
        self.num_bombs = NUM_BOMBS
        self.squares_x = NSQUARES
        self.squares_y = NSQUARES
        self.resize = False
        self.flag_count = 0
        self.start_time=None
        self.end_time=None
        self.setup_mode = False
        self.player_name = "Anonym"

    
    def in_progress(self):
        if self.init:
            if not self.game_lost and not self.game_lost:
                return True
        return False

    def get_elapsed_time(self):
        if self.start_time==None:
            return 0
        if self.end_time==None:
            return (pygame.time.get_ticks()-self.start_time)//1000
        else:
            return (self.end_time-self.start_time)//1000
        
    def set_difficulty(self, size, bombs):
        """Bytt brettstørrelse og antall bomber, og start på nytt."""
        self.squares_x = size
        self.squares_y = size
        self.num_bombs = bombs
        # Lag nytt rutenett i ny størrelse
        self.grid = [[self.Cell(x, y) for x in range(size)]
                    for y in range(size)]
        self.reset_game()
        new_size = (size * (WIDTH + MARGIN) + MARGIN + LABEL_SIZE,
            size * (HEIGHT + MARGIN) + MARGIN + MENU_SIZE + LABEL_SIZE)
        return pygame.display.set_mode(new_size, pygame.RESIZABLE)

    def draw(self, screen, font, state=None):
            screen.fill(GREEN1)
            for row in range(self.squares_y):
                for column in range(self.squares_x):
                    
                    color = WHITE
                    if self.grid[row][column].is_visible:
                        color = RED if self.grid[row][column].has_bomb else GRAY
                    elif self.grid[row][column].has_flag:
                        color = RED1
                    #if state["row"]==row and state["column"]==None:
                        #color = HIGHLIGHT
                    if self.setup_mode and self.grid[row][column].has_bomb:
                        color = RED1
                    pygame.draw.rect(screen, color,
                                    [(MARGIN + WIDTH) * column + MARGIN + LABEL_SIZE,
                                    (MARGIN + HEIGHT) * row + MARGIN + MENU_SIZE + LABEL_SIZE,
                                    WIDTH, HEIGHT])
                    self.grid[row][column].show_text(screen, font)

            # Kolonnenummer langs toppen (under menyen, over brettet), tallene som viser koordinatsystemet
            for column in range(self.squares_x):
                label = font.render(str(column), True, WHITE)
                x = (MARGIN + WIDTH) * column + MARGIN + LABEL_SIZE + WIDTH // 3
                y = MENU_SIZE + LABEL_SIZE - 18
                screen.blit(label, (x, y))

            # Radnummer langs venstre side
            for row in range(self.squares_y):
                label = font.render(str(row), True, WHITE)
                x = LABEL_SIZE - 12 
                y = (MARGIN + HEIGHT) * row + MARGIN + MENU_SIZE + LABEL_SIZE + HEIGHT // 4
                screen.blit(label, (x, y))
            #markerer rad som er sagt høyt
            if state and state["row"] is not None and state["column"] is None:
                sel_row = state["row"]
                overlay = pygame.Surface((self.squares_x * (WIDTH + MARGIN), HEIGHT))
                overlay.set_alpha(80)
                overlay.fill(HIGHLIGHT)
                screen.blit(overlay,
                            (MARGIN + LABEL_SIZE,
                            (MARGIN + HEIGHT) * sel_row + MARGIN + MENU_SIZE + LABEL_SIZE))

    def adjust_grid(self, sizex, sizey):
        self.squares_x = (sizex - MARGIN) // (WIDTH + MARGIN)
        self.squares_y = (sizey - MARGIN - MENU_SIZE) // (HEIGHT + MARGIN)
        if self.squares_x < 8:
            self.squares_x = 8
        if self.squares_y < 8:
            self.squares_y = 8
        if self.num_bombs > (self.squares_x * self.squares_y) // 3:
            self.num_bombs = self.squares_x * self.squares_y // 3
        self.grid = [[self.Cell(x, y) for x in range(self.squares_x)]
                     for y in range(self.squares_y)]
        size = ((self.squares_x * (WIDTH + MARGIN) + MARGIN),
                (self.squares_y * (HEIGHT + MARGIN) + MARGIN + MENU_SIZE))
        return pygame.display.set_mode(size, pygame.RESIZABLE)

    def game_over(self):
        for row in range(self.squares_y):
            for column in range(self.squares_x):
                if self.grid[row][column].has_bomb:
                    self.grid[row][column].is_visible = True
                self.grid[row][column].has_flag = False

    def change_num_bombs(self, bombs):
        self.num_bombs += bombs
        if self.num_bombs < 1:
            self.num_bombs = 1
        elif self.num_bombs > (self.squares_x * self.squares_y) // 3:
            self.num_bombs = self.squares_x * self.squares_y // 3
        self.reset_game()

    def place_bombs(self, row, column):
        bombplaced = 0
        while bombplaced < self.num_bombs:
            x = randrange(self.squares_y)
            y = randrange(self.squares_x)
            if not self.grid[x][y].has_bomb and not (row == x and column == y):
                self.grid[x][y].has_bomb = True
                bombplaced += 1
        self.count_all_bombs()
        if self.grid[row][column].bomb_count != 0:
            self.reset_game()
            self.place_bombs(row, column)

    def count_all_bombs(self):
        for row in range(self.squares_y):
            for column in range(self.squares_x):
                self.grid[row][column].count_bombs(
                    self, self.squares_y, self.squares_x)

    def reset_game(self):
        for row in range(self.squares_y):
            for column in range(self.squares_x):
                self.init = False
                self.grid[row][column].is_visible = False
                self.grid[row][column].has_bomb = False
                self.grid[row][column].bomb_count = 0
                self.grid[row][column].test = False
                self.grid[row][column].has_flag = False
                self.game_lost = False
                self.game_won = False
                self.flag_count = 0
        self.start_time=None
        self.end_time=None

    def check_victory(self):
        count = 0
        total = self.squares_x * self.squares_y
        for row in range(self.squares_y):
            for column in range(self.squares_x):
                if self.grid[row][column].is_visible:
                    count += 1
        #HER MÅ VI SENDE SCORE
        if ((total - count) == self.num_bombs) and not self.game_lost:
            self.game_won = True
            self.end_time=pygame.time.get_ticks()

            send_score(
                        player_name = self.player_name,
                        mines_found=self.num_bombs,
                        time_seconds=self.get_elapsed_time(),
                        won=True
                    )

            for row in range(self.squares_y):
                for column in range(self.squares_x):
                    if self.grid[row][column].has_bomb:
                        self.grid[row][column].has_flag = True

    def count_flags(self):
        total_flags = 0
        for row in range(self.squares_y):
            for column in range(self.squares_x):
                if self.grid[row][column].has_flag:
                    total_flags += 1
        self.flag_count = total_flags

    def click_handle(self, row, column, button):
        if button == LEFT_CLICK and self.game_won:
            self.reset_game()
        elif button == LEFT_CLICK and not self.grid[row][column].has_flag:
            if not self.game_lost:
                # Place bombs after first click so you never click a bomb first
                if not self.init:
                    self.place_bombs(row, column)
                    self.start_time=pygame.time.get_ticks()
                    self.init = True
                if self.start_time is None:
                    self.start_time = pygame.time.get_ticks()
                # Set the clicked square to visible
                self.grid[row][column].is_visible = True
                self.grid[row][column].has_flag = False
                if self.grid[row][column].has_bomb:
                    self.game_over()
                    self.game_lost = True #HER MÅ VI SENDE SCORE (?)
                    self.end_time = pygame.time.get_ticks()
                    send_score(
                        player_name = self.player_name,
                        mines_found=self.num_bombs,
                        time_seconds=self.get_elapsed_time(),
                        won=False
                    )
                if (self.grid[row][column].bomb_count == 0
                        and not self.grid[row][column].has_bomb):
                    self.grid[row][column].open_neighbours(
                        self, self.squares_y, self.squares_x)
                self.check_victory()
            else:
                self.game_lost = False
                self.reset_game()

        elif button == RIGHT_CLICK and not self.game_won:
            if not self.grid[row][column].has_flag:
                if (self.flag_count < self.num_bombs
                        and not self.grid[row][column].is_visible):
                    self.grid[row][column].has_flag = True
            else:
                self.grid[row][column].has_flag = False
            self.count_flags()

    # Sub-class for each cell of the grid
    class Cell:

        def __init__(self, x, y):
            self.x = x
            self.y = y
            self.is_visible = False
            self.has_bomb = False
            self.bomb_count = 0
            self.text = ""
            self.test = False
            self.has_flag = False

        def show_text(self, screen, font):
                    if self.is_visible:
                        if self.bomb_count == 0:
                            self.text = font.render("", True, GREEN1)
                        else:
                            color = NUMBER_COLORS.get(self.bomb_count, GREEN1)
                            self.text = font.render(str(self.bomb_count), True, color)
                        screen.blit(self.text,
                                    (self.x * (WIDTH + MARGIN) + 12 + LABEL_SIZE,
                                    self.y * (HEIGHT + MARGIN) + 10 + MENU_SIZE + LABEL_SIZE))
        
        def count_bombs(self, game, squaresx, squaresy):
            if not self.test:
                self.test = True
                if not self.has_bomb:
                    for column in range(self.x - 1, self.x + 2):
                        for row in range(self.y - 1, self.y + 2):
                            if (0 <= row < squaresx and 0 <= column < squaresy
                                    and not (column == self.x and row == self.y)
                                    and game.grid[row][column].has_bomb):
                                self.bomb_count += 1

        def open_neighbours(self, game, squaresx, squaresy):
            column = self.x
            row = self.y
            for row_off in range(-1, 2):
                for column_off in range(-1, 2):
                    if ((row_off == 0 or column_off == 0)
                            and row_off != column_off
                            and 0 <= row + row_off < squaresx
                            and 0 <= column + column_off < squaresy):
                        cell = game.grid[row + row_off][column + column_off]
                        cell.count_bombs(game, game.squares_y, game.squares_x)
                        if not cell.is_visible and not cell.has_bomb:
                            cell.is_visible = True
                            cell.has_flag = False
                            if cell.bomb_count == 0:
                                cell.open_neighbours(
                                    game, game.squares_y, game.squares_x)