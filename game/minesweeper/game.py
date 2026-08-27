#lånt fra nettet
#
# The board is pure model plus a draw() that renders onto whatever surface it
# is handed. It never touches pygame.display: main.py owns the window, and
# minesweeper_game.py scales this board into it (see ui.py).

from random import randrange
import pygame

from .config import (
    WIDTH, HEIGHT, NSQUARES, MARGIN, MENU_SIZE,
    GREEN1, RED1, RED,
    LEFT_CLICK, RIGHT_CLICK, LABEL_SIZE, NUM_BOMBS, HIGHLIGHT, NUMBER_COLORS,
    MS_BG, MS_FACE, MS_LIGHT, MS_SHADOW, MS_OPEN, MS_OPEN_EDGE, MS_TEXT,
    NORDIC_BLUE,
)


def draw_bevel(surface, rect, raised=True, width=3):
    """Classic Minesweeper 3D edge: light top-left, dark bottom-right."""
    light = MS_LIGHT if raised else MS_SHADOW
    dark = MS_SHADOW if raised else MS_LIGHT
    x, y, w, h = rect
    for i in range(width):
        pygame.draw.line(surface, light, (x + i, y + i), (x + w - 1 - i, y + i))
        pygame.draw.line(surface, light, (x + i, y + i), (x + i, y + h - 1 - i))
        pygame.draw.line(surface, dark, (x + i, y + h - 1 - i),
                         (x + w - 1 - i, y + h - 1 - i))
        pygame.draw.line(surface, dark, (x + w - 1 - i, y + i),
                         (x + w - 1 - i, y + h - 1 - i))


def draw_mine(surface, rect):
    """A classic black bomb with spikes and a white glint."""
    cx, cy = rect.center
    r = max(3, min(rect.width, rect.height) // 3)
    d = int(r * 0.95)
    for dx, dy in ((r + 3, 0), (-(r + 3), 0), (0, r + 3), (0, -(r + 3)),
                   (d, d), (d, -d), (-d, d), (-d, -d)):
        pygame.draw.line(surface, (0, 0, 0), (cx, cy), (cx + dx, cy + dy), 2)
    pygame.draw.circle(surface, (0, 0, 0), (cx, cy), r)
    pygame.draw.circle(surface, (255, 255, 255), (cx - r // 3, cy - r // 3),
                       max(2, r // 4))


def draw_flag(surface, rect):
    """A red pennant on a black pole, classic Minesweeper flag."""
    x, y, w, h = rect
    pole_x = int(x + w * 0.56)
    pygame.draw.rect(surface, (0, 0, 0),
                     (int(x + w * 0.28), int(y + h * 0.70),
                      int(w * 0.44), max(2, int(h * 0.12))))
    pygame.draw.line(surface, (0, 0, 0), (pole_x, int(y + h * 0.24)),
                     (pole_x, int(y + h * 0.72)), 2)
    pygame.draw.polygon(surface, (200, 0, 0), [
        (pole_x, int(y + h * 0.22)),
        (pole_x, int(y + h * 0.50)),
        (int(x + w * 0.30), int(y + h * 0.36)),
    ])


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
        self.flag_count = 0
        self.start_time=None
        self.end_time=None
        self.setup_mode = False


    def in_progress(self):
        return self.init and not self.game_lost and not self.game_won

    def board_pixel_size(self):
        """Size of the surface draw() needs for the current board, in pixels.

        Changes with the board, so minesweeper_game.py recomputes its scaling
        from this rather than from NSQUARES.
        """
        return (self.squares_x * (WIDTH + MARGIN) + MARGIN + LABEL_SIZE,
                self.squares_y * (HEIGHT + MARGIN) + MARGIN + MENU_SIZE + LABEL_SIZE)

    def get_elapsed_time(self):
        if self.start_time==None:
            return 0
        if self.end_time==None:
            return (pygame.time.get_ticks()-self.start_time)//1000
        else:
            return (self.end_time-self.start_time)//1000

    def cleared_count(self):
        """Number of safe (non-bomb) tiles the player has opened."""
        return sum(1 for row in self.grid for cell in row
                   if cell.is_visible and not cell.has_bomb)

    def set_difficulty(self, size, bombs):
        """Bytt brettstørrelse og antall bomber, og start på nytt.

        Only the model changes; the caller notices the new
        @ref board_pixel_size and resizes its own surface.
        """
        self.squares_x = size
        self.squares_y = size
        self.num_bombs = bombs
        # Lag nytt rutenett i ny størrelse
        self.grid = [[self.Cell(x, y) for x in range(size)]
                    for y in range(size)]
        self.reset_game()

    def draw(self, screen, font, state=None):
            screen.fill(NORDIC_BLUE)
            for row in range(self.squares_y):
                for column in range(self.squares_x):
                    cell = self.grid[row][column]
                    rect = pygame.Rect(
                        (MARGIN + WIDTH) * column + MARGIN + LABEL_SIZE,
                        (MARGIN + HEIGHT) * row + MARGIN + MENU_SIZE + LABEL_SIZE,
                        WIDTH, HEIGHT)

                    if cell.is_visible:
                        # Opened: flat, sunken. A tripped mine sits on red.
                        pygame.draw.rect(
                            screen, RED if cell.has_bomb else MS_OPEN, rect)
                        pygame.draw.rect(screen, MS_OPEN_EDGE, rect, 1)
                        if cell.has_bomb:
                            draw_mine(screen, rect)
                    else:
                        # Unopened: raised bevel; setup mode reveals bombs.
                        face = RED1 if (self.setup_mode and cell.has_bomb) \
                            else MS_FACE
                        pygame.draw.rect(screen, face, rect)
                        draw_bevel(screen, rect, raised=True)
                        if cell.has_flag:
                            draw_flag(screen, rect)

                    self.grid[row][column].show_text(screen, font)

            # Kolonnenummer langs toppen (under menyen, over brettet), tallene som viser koordinatsystemet
            for column in range(self.squares_x):
                label = font.render(str(column), True, MS_TEXT)
                x = (MARGIN + WIDTH) * column + MARGIN + LABEL_SIZE + WIDTH // 3
                y = MENU_SIZE + LABEL_SIZE - 18
                screen.blit(label, (x, y))

            # Radnummer langs venstre side
            for row in range(self.squares_y):
                label = font.render(str(row), True, MS_TEXT)
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

    def game_over(self):
        for row in range(self.squares_y):
            for column in range(self.squares_x):
                if self.grid[row][column].has_bomb:
                    self.grid[row][column].is_visible = True
                self.grid[row][column].has_flag = False

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

        if ((total - count) == self.num_bombs) and not self.game_lost:
            self.game_won = True
            self.end_time=pygame.time.get_ticks()

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
                    self.game_lost = True
                    self.end_time = pygame.time.get_ticks()

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
