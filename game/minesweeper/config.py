"""Minesweeper's own constants: board geometry and gameplay colours.
No serial settings live here. Port selection and baud rate belong to
controller.py alone, which autodetects the DK -- minesweeper gets its input
from the shared SerialController like snake and quiz do.
"""

# Colors
GREEN1 = (80, 140, 70)       # Gressgrønn
WHITE = (240, 235, 225)     # Varm off-white
RED1  = (220, 80, 80)       # Dempet rød
GREEN = (150, 210, 170)     # Myk grønn
RED   = (220, 130, 130)     # Dempet rød/rosa
GRAY  = (200, 195, 210)     # Lys lilla-grå
HIGHLIGHT = (255, 230, 120)   # gul markering for valgt rad


# Grid. NSQUARES/NUM_BOMBS are the starting board; "easy"/"hard" swap in a
# DIFFICULTIES entry instead. Cells are square, so one size covers both axes.
WIDTH = 30
HEIGHT = 30
NSQUARES = 8
NUM_BOMBS = 3
MARGIN = 11
MENU_SIZE = 70
LABEL_SIZE = 30   # plass til tall langs kantene

# Mouse buttons
LEFT_CLICK = 1
RIGHT_CLICK = 3

#vansklighetsgrader. Keep size at or below the number of spoken number tokens
# (controller.NUMBERS, 0-7) plus one, or the far rows/columns cannot be named.
DIFFICULTIES = {
    "easy":   {"size": 8,  "bombs": 6},
    "hard":   {"size": 8, "bombs": 16},
}

#fargekodede tall
NUMBER_COLORS = {
    1: (0, 0, 255),      # blå
    2: (0, 128, 0),      # grønn
    3: (255, 0, 0),      # rød
    4: (0, 0, 128),      # mørk blå
    5: (128, 0, 0),      # mørk rød
    6: (0, 128, 128),    # turkis
    7: (0, 0, 0),        # svart
    8: (128, 128, 128),  # grå
}

