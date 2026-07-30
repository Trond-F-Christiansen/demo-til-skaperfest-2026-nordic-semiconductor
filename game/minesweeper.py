"""Menu adapter for Minesweeper.

The menu calls run(screen, clock, controller). Minesweeper has its own loop
(minesweeper_game.main) and its own serial input (serial_input.py), so here we:
  * pause the shared controller so the port is free for serial_input,
  * remember the menu window size and restore it afterwards,
  * translate a closed window into the None the menu expects.
"""

import pygame
import minesweeper_game


def run(screen, clock, controller):

    # siden minesweeper har forskjellig størrelse må vi huske størrelsen- dette endrer jeg på en senere tidspunkt.
    menu_size = screen.get_size()
    seconds = 0
    try:
        result=minesweeper_game.main(controller, screen) 
        if result is not None:
            seconds = result
    except SystemExit:
        pass
    finally:
        pygame.display.set_mode(menu_size)
    

    return seconds