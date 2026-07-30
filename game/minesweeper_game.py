import sys
import time
import pygame

from config import (
    WIDTH, HEIGHT, LABEL_SIZE, NSQUARES, MARGIN, MENU_SIZE, LEFT_CLICK, RIGHT_CLICK, DIFFICULTIES, GREEN1
)
from game import Game
from menu import Menu



def handle_voice_input(game, state, controller):
    keyword = controller.get_command(max_square=NSQUARES)
    if keyword is None:
        return
    kind, result = keyword 
    print(kind)
    print(result)
    
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
                #game.setup_mode=True

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

        elif result == "easy" and not game.in_progress():
            state["reset_count"]=0
            game.setup_mode = False
            size= DIFFICULTIES["easy"]["size"]
            bombs=DIFFICULTIES["easy"]["bombs"]
            screen = game.set_difficulty(size, bombs)
            state["row"] = None
            state["column"] = None
            print("easy-mode")

        elif result == "hard" and not game.in_progress():
            state["reset_count"]=0
            game.setup_mode = False
            size= DIFFICULTIES["hard"]["size"]
            bombs=DIFFICULTIES["hard"]["bombs"]
            screen = game.set_difficulty(size, bombs)
            state["row"] = None
            state["column"] = None
            print("hard-mode")

    elif kind=="number" and not game.setup_mode:
        #state["reset_count"]=0
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
        
def draw_info(screen, win_h):
    """Tegn en hjelpetekst i en boks til venstre for brettet."""
    title_font = pygame.font.Font('freesansbold.ttf', 26)
    text_font = pygame.font.Font('freesansbold.ttf', 18)

    lines = [
        ("Stemmestyring", True),
        ("", False),
        ("Si tall (rad og", False),
        ("kolonne) for å", False),
        ("velge en rute.", False),
        ("", False),
        ("'open' åpner ruten", False),
        ("du har valgt.", False),
        ("", False),
        ("'flag' setter et", False),
        ("flagg der du tror", False),
        ("det er en mine.", False),
        ("", False),
        ("'no' angrer hvis", False),
        ("du sa feil tall.", False),
    ]

    # Boks-dimensjoner
    box_x = 15
    box_y = 90
    box_w = 250
    box_h = 470

    # Bakgrunn + ramme
    box = pygame.Rect(box_x, box_y, box_w, box_h)
    pygame.draw.rect(screen, (200, 195, 210), box, border_radius=12)
    pygame.draw.rect(screen, (80, 40, 40), box, 3, border_radius=12)

    # Tekst
    x = box_x + 18
    y = box_y + 20
    for text, is_title in lines:
        if text == "":
            y += 14
            continue
        f = title_font if is_title else text_font
        color = (180, 60, 60) if is_title else (40, 40, 40)
        surf = f.render(text, True, color)
        screen.blit(surf, (x, y))
        y += f.get_height() + 6

def main(controller, screen):
    best_seconds = 0
    
    board_size = (NSQUARES * (WIDTH + MARGIN) + MARGIN + LABEL_SIZE,
                  NSQUARES * (HEIGHT + MARGIN) + MARGIN + MENU_SIZE + LABEL_SIZE)
    board_surf = pygame.Surface(board_size)
    win_w, win_h = screen.get_size()
    info_width = 280                                   # plass til infoboks til venstre
    avail_w = win_w - info_width
    scale = min(avail_w / board_size[0], win_h / board_size[1]) * 0.9
    scaled_size = (int(board_size[0] * scale), int(board_size[1] * scale))
    # sentrer brettet i omradet TIL HOYRE for infoboksen
    offset_x = info_width + (avail_w - scaled_size[0]) // 2
    offset_y = (win_h - scaled_size[1]) // 2

    font = pygame.font.Font('freesansbold.ttf', 24)

    game = Game()
    game.player_name="Anonym"
    menu = Menu(board_surf)
    clock = pygame.time.Clock()

    game_active = True #false før: endrer for å flette med aslak sin kode
    state = {"row": None, "column": None, "mode": "open" , "reset_count" : 0}

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return best_seconds
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if game.setup_mode:
                    x, y = event.pos
                    r= (y - MARGIN - MENU_SIZE - LABEL_SIZE) // (HEIGHT + MARGIN) #må regne pos på brettet
                    c= (x - MARGIN - LABEL_SIZE) // (WIDTH + MARGIN)#må regne pos på brettet
                    if r >= 0 and r < game.squares_y:
                        if c >= 0 and c < game.squares_x:
                            cell = game.grid[r][c]
                            cell.has_bomb = not cell.has_bomb #bombe hvis uten bombe, ikke bombe hvis det er en bombe der allerede

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:     
                    return best_seconds
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
                    #game.start_time = pygame.time.get_ticks()

        screen.fill(GREEN1)
        draw_info(screen, win_h)                      # ← infoboks til venstre
        game.draw(board_surf, font, state)
        handle_voice_input(game, state, controller)

        if game.game_won or game.game_lost:
            best_seconds = game.get_elapsed_time()
            if game.game_won:                                   
                controller.send_score("minesweeper", best_seconds)
            game.draw(board_surf, font, state)
            menu.draw(board_surf, font, game, state["mode"])
            scaled = pygame.transform.smoothscale(board_surf, scaled_size)
            screen.blit(scaled, (offset_x, offset_y))
            pygame.display.flip()
            pygame.time.delay(1500)
            return best_seconds

        menu.draw(board_surf, font, game, state["mode"])
        scaled = pygame.transform.smoothscale(board_surf, scaled_size)
        screen.blit(scaled, (offset_x, offset_y))
        clock.tick(60)
        pygame.display.flip()

