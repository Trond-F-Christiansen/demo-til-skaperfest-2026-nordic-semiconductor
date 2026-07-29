import sys
import time
import pygame

from config import (
    WIDTH, HEIGHT, LABEL_SIZE, NSQUARES, MARGIN, MENU_SIZE, LEFT_CLICK, RIGHT_CLICK, DIFFICULTIES
)
from game import Game
from menu import Menu
from serial_input import check_wakeword, check_input, clear_buffer


def handle_voice_input(game, state):
    keyword = check_input()
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
        
    #venter litt, slik at man ikke leser samme ord flere ganger
    clear_buffer()
    time.sleep(0.6)
    clear_buffer()


def main():
    pygame.init()
    
    size = (NSQUARES * (WIDTH + MARGIN) + MARGIN + LABEL_SIZE,
                NSQUARES * (HEIGHT + MARGIN) + MARGIN + MENU_SIZE + LABEL_SIZE)
    screen = pygame.display.set_mode(size, pygame.RESIZABLE)
    pygame.display.set_caption("Minesweeper")
    font = pygame.font.Font('freesansbold.ttf', 24)

    game = Game()
    game.player_name="Anonym"
    menu = Menu(screen)
    clock = pygame.time.Clock()

    game_active = True #false før: endrer for å flette med aslak sin kode
    state = {"row": None, "column": None, "mode": "open" , "reset_count" : 0}

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            elif event.type == pygame.VIDEORESIZE:
                if game.resize:
                    screen = game.adjust_grid(event.w, event.h)
                    game.reset_game()
                else:
                    game.resize = True
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
                if event.key == pygame.K_m:
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


        if not game_active:
            if check_wakeword():
                game_active = True
        else:
            game.draw(screen, font, state)
            handle_voice_input(game, state)

        menu.draw(screen, font, game, state["mode"])
        clock.tick(60)
        pygame.display.flip()


if __name__ == "__main__":
    run()