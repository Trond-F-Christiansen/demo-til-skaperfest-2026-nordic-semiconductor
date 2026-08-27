"""Snake game.

Refactored out of the old standalone game.py so it can be launched from the
menu (main.py). The whole game is a single `run()` call that owns its own event
loop and *returns the run's score* when the snake dies, instead of quitting the
process. main.py then shows the game-over menu and decides whether to restart.

Run indirectly via `python main.py`; assets load with paths relative to the
current directory, so run from the game/ folder.

Todo:
 - eliminate possibility of doing multiple direction changes before each tick
 - easy/mid/hard modes
    - easy: no borders
    - mid: borders
    - hard: walls? apple moves after x amount of time?
"""

import random

import pygame
from pygame.math import Vector2

import ui
from controller import BACK_TO_MENU

# Grid geometry. Window is cell_number * cell_size on each side (1000 x 1000),
# which main.py uses to size the shared window.
cell_size = 57
cell_number = 18
screen_color = (108, 178, 66)

# Cached grass texture surface, built once on first draw.
_grass_surface = None

# How often the snake advances, in milliseconds.
TICK_MS = 400

# Custom event used to drive the fixed-rate game tick.
SCREEN_UPDATE = pygame.USEREVENT

# Set by run() before any game object is created. The classes below read these
# as module globals (same as the old module-level names in game.py).
screen = None
apple = None
game_font = None


def _make_opaque(surface, bg=(255, 255, 255), threshold=8):
    """Flatten `surface` so it is not see-through, keeping its shape and its
    two-tone shading. The lighter tone is the base colour at reduced alpha, so
    each pixel is composited over `bg` (which reproduces the light tone) and
    then forced fully opaque. Fully transparent pixels stay transparent, so
    only the logo shows -- no rectangle around it.
    """
    out = surface.copy()
    out.lock()
    w, h = out.get_size()
    for x in range(w):
        for y in range(h):
            r, g, b, a = out.get_at((x, y))
            if a <= threshold:
                out.set_at((x, y), (0, 0, 0, 0))
                continue
            t = a / 255.0
            out.set_at((x, y), (
                int(r * t + bg[0] * (1 - t)),
                int(g * t + bg[1] * (1 - t)),
                int(b * t + bg[2] * (1 - t)),
                255,
            ))
    out.unlock()
    return out


def _build_grass():
    """Build the grassy field once: a two-tone checkerboard plus scattered
    blade tufts. Seeded so the texture is stable frame to frame.
    """
    size = cell_number * cell_size
    surf = pygame.Surface((size, size))

    light = (112, 182, 66)
    dark = (98, 168, 56)
    for row in range(cell_number):
        for col in range(cell_number):
            base = light if (row + col) % 2 == 0 else dark
            pygame.draw.rect(surf, base,
                             (col * cell_size, row * cell_size,
                              cell_size, cell_size))

    blades = [(80, 146, 46), (70, 132, 40), (128, 198, 80)]
    rng = random.Random(20260827)
    for _ in range(size * size // 260):
        x = rng.randint(0, size - 1)
        y = rng.randint(2, size - 1)
        h = rng.randint(4, 9)
        lean = rng.randint(-2, 2)
        pygame.draw.line(surf, rng.choice(blades), (x, y), (x + lean, y - h), 1)

    return surf


class FRUIT:
    def __init__(self):
        self.randomize()

    def draw_fruit(self):
        fruit_rect = pygame.Rect(self.pos.x * cell_size,
                                 self.pos.y * cell_size,
                                 cell_size, cell_size)
        screen.blit(apple, fruit_rect)

    def randomize(self):
        self.x = random.randint(0, cell_number - 1)
        self.y = random.randint(0, cell_number - 1)
        self.pos = pygame.math.Vector2(self.x, self.y)
        # different fruit images? axon, neuton, nordic?


class SNAKE:
    def __init__(self):
        self.color = (50, 255, 150)
        self.body = [Vector2(5, 10), Vector2(4, 10), Vector2(3, 10)]
        self.direction = Vector2(1, 0)
        self.next_direction = Vector2(1, 0)
        self.new_block = False

        self.head_up = self._load_cell('head_up')
        self.head_down = self._load_cell('head_down')
        self.head_left = self._load_cell('head_left')
        self.head_right = self._load_cell('head_right')

        self.tail_up = self._load_cell('tail_up')
        self.tail_down = self._load_cell('tail_down')
        self.tail_right = self._load_cell('tail_right')
        self.tail_left = self._load_cell('tail_left')

        self.body_vertical = self._load_cell('body_vertical')
        self.body_horizontal = self._load_cell('body_horizontal')

        self.body_tr = self._load_cell('body_tr')
        self.body_tl = self._load_cell('body_tl')
        self.body_br = self._load_cell('body_br')
        self.body_bl = self._load_cell('body_bl')

    @staticmethod
    def _load_cell(name):
        """Load Graphics/<name>.png scaled to exactly one grid cell.

        The source art is 40x40, sized for the original cell_size of 40. Blits
        ignore the destination rect's size, so the sprites have to be scaled
        here or they render at 40x40 whatever cell_size is set to.
        """
        img = pygame.image.load(f'Graphics/{name}.png').convert_alpha()
        return pygame.transform.smoothscale(img, (cell_size, cell_size))

    def draw_snake(self):
        self.update_head_graphics()
        self.update_tail_graphics()

        for index, block in enumerate(self.body):
            x_pos = block.x * cell_size
            y_pos = block.y * cell_size
            block_rect = pygame.Rect(x_pos, y_pos, cell_size, cell_size)

            if index == 0:  # head
                screen.blit(self.head, block_rect)
            elif index == len(self.body) - 1:  # last item in self.body
                screen.blit(self.tail, block_rect)
            else:
                previous_block = self.body[index + 1] - block
                next_block = self.body[index - 1] - block
                if previous_block.x == next_block.x:
                    screen.blit(self.body_vertical, block_rect)
                elif previous_block.y == next_block.y:
                    screen.blit(self.body_horizontal, block_rect)
                else:
                    if previous_block.x == -1 and next_block.y == -1 or previous_block.y == -1 and next_block.x == -1:
                        screen.blit(self.body_tl, block_rect)
                    elif previous_block.x == -1 and next_block.y == 1 or previous_block.y == 1 and next_block.x == -1:
                        screen.blit(self.body_bl, block_rect)
                    elif previous_block.x == 1 and next_block.y == -1 or previous_block.y == -1 and next_block.x == 1:
                        screen.blit(self.body_tr, block_rect)
                    elif previous_block.x == 1 and next_block.y == 1 or previous_block.y == 1 and next_block.x == 1:
                        screen.blit(self.body_br, block_rect)

    def update_head_graphics(self):
        head_relation = self.body[1] - self.body[0]
        if head_relation == Vector2(1, 0): self.head = self.head_left
        elif head_relation == Vector2(-1, 0): self.head = self.head_right
        elif head_relation == Vector2(0, 1): self.head = self.head_up
        elif head_relation == Vector2(0, -1): self.head = self.head_down

    def update_tail_graphics(self):
        tail_relation = self.body[-2] - self.body[-1]
        if tail_relation == Vector2(1, 0): self.tail = self.tail_left
        elif tail_relation == Vector2(-1, 0): self.tail = self.tail_right
        elif tail_relation == Vector2(0, 1): self.tail = self.tail_up
        elif tail_relation == Vector2(0, -1): self.tail = self.tail_down

    def move_snake(self):
        self.direction = self.next_direction
        if self.new_block == True:
            body_copy = self.body[:]
            body_copy.insert(0, body_copy[0] + self.direction)
            self.body = body_copy[:]
            self.new_block = False
        else:
            body_copy = self.body[:-1]  # last element is 'deleted'
            body_copy.insert(0, body_copy[0] + self.direction)
            self.body = body_copy[:]

    def add_block(self):
        self.new_block = True


class MAIN:
    def __init__(self,controller=None):
        self.snake = SNAKE()
        self.fruit = FRUIT()
        self.alive = True  # cleared by game_over(); run() returns once False
        self.controller = controller

    def update(self):
        self.snake.move_snake()
        self.check_collision()
        self.check_fail()

    def draw_elements(self):
        self.draw_grass()
        self.fruit.draw_fruit()
        self.snake.draw_snake()
        self.draw_score()

    def check_collision(self):
        if self.fruit.pos == self.snake.body[0]:
            self.fruit.randomize()
            self.snake.add_block()

    def check_fail(self):
        if not 0 <= self.snake.body[0].x < cell_number or not 0 <= self.snake.body[0].y < cell_number:
            self.game_over()

        for block in self.snake.body[1:]:  # all blocks except the head
            if block == self.snake.body[0]:
                self.game_over()

    def score(self):
        return len(self.snake.body) - 3

    def game_over(self):
        if not self.alive:
            return
        score = len(self.snake.body) - 3
        if self.controller.score_game is not None:
            self.controller.send_score(self.controller.score_game, score)
        self.alive = False

    def draw_grass(self):
        global _grass_surface
        if _grass_surface is None:
            _grass_surface = _build_grass()
        screen.blit(_grass_surface, (0, 0))

    def draw_score(self):
        score_text = str(self.score())
        score_surface = ui.render_text(score_text, game_font, (255, 255, 255),
                                       offset=2)
        score_x = int(cell_size * cell_number - 60)  # 60 is padding
        score_y = int(cell_size * cell_number - 40)
        score_rect = score_surface.get_rect(center=(score_x, score_y))
        nod_rect = apple.get_rect(midright=(score_rect.left - 20, score_rect.centery))
        pad = 8
        bg_rect = pygame.Rect(nod_rect.left - 12, nod_rect.top - pad,
                              nod_rect.width + score_rect.width + 44,
                              nod_rect.height + 2 * pad)

        ui.draw_panel(screen, bg_rect, radius=14)
        screen.blit(score_surface, score_rect)
        screen.blit(apple, nod_rect)


def run(shared_screen, clock, controller):
    """Play one round of snake on the shared window.

    @param shared_screen  pygame Surface created by main.py.
    @param clock          shared pygame Clock.
    @param controller     SerialController; its direction queue is drained each
                          frame (same behaviour as the old game.py).
    @return the run's score (int) when the snake dies, or None if the player
            closed the window mid-game (main.py treats None as "quit app").
    """
    global screen, apple, game_font
    screen = shared_screen

    apple = pygame.image.load('Graphics/nod.png').convert_alpha()
    apple = pygame.transform.scale(apple, (cell_size, cell_size))
    apple = _make_opaque(apple)
    game_font = ui.font(25, ui.FONT_DISPLAY)

    # Drop anything that piled up in the menu so the snake doesn't lurch off on
    # a stale direction the instant the game starts.
    controller.drain()

    main_game = MAIN(controller)
    pygame.time.set_timer(SCREEN_UPDATE, TICK_MS)
    try:
        while True:
            if controller.check_back():
                return BACK_TO_MENU

            # Controller input: drain the queue before each tick and pick the
            # newest legal turn (can't reverse straight back on yourself).
            while not controller.directions.empty():
                dx, dy = controller.directions.get()
                if dx == 1 and main_game.snake.direction.x != -1:
                    main_game.snake.next_direction = Vector2(dx, dy)
                if dx == -1 and main_game.snake.direction.x != 1:
                    main_game.snake.next_direction = Vector2(dx, dy)
                if dy == 1 and main_game.snake.direction.y != -1:
                    main_game.snake.next_direction = Vector2(dx, dy)
                if dy == -1 and main_game.snake.direction.y != 1:
                    main_game.snake.next_direction = Vector2(dx, dy)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == SCREEN_UPDATE:
                    main_game.update()

            if not main_game.alive:
                return main_game.score()

            screen.fill(screen_color)
            main_game.draw_elements()
            pygame.display.update()
            clock.tick(60)  # render fps
    finally:
        # Stop the tick timer so it doesn't keep firing into the menu loop.
        pygame.time.set_timer(SCREEN_UPDATE, 0)
