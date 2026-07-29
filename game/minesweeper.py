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
    # 1. Free the serial port for Minesweeper's own serial_input.
    controller.stop()

    # 2. Remember the menu's window size so we can restore it later.
    menu_size = screen.get_size()

    try:
        minesweeper_game.main()   # Minesweeper's existing loop
    except SystemExit:
        # main() calls sys.exit() when the window is closed; swallow it
        # so the whole app doesn't quit.
        pass
    finally:
        # 3. Restore the menu window and restart the shared controller.
        pygame.display.set_mode(menu_size)
        try:
            controller.start()
        except RuntimeError:
            pass

    # Minesweeper doesn't report a score to the menu; return 0 for now.
    return 0