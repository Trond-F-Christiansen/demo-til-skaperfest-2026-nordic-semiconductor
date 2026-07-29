#Div variabler
# Colors
GREEN1 = (80, 140, 70)       # Gressgrønn
WHITE = (240, 235, 225)     # Varm off-white
RED1  = (220, 80, 80)       # Dempet rød
GREEN = (150, 210, 170)     # Myk grønn
RED   = (220, 130, 130)     # Dempet rød/rosa
GRAY  = (200, 195, 210)     # Lys lilla-grå
HIGHLIGHT = (255, 230, 120)   # gul markering for valgt rad


# Grid
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

# Serial
SERIAL_PORT = '/dev/ttyACM3' # '/dev/serial/by-id/usb-SEGGER_J-Link_001051859487-if00' før
BAUDRATE = 115200

#vansklighetsgrader
DIFFICULTIES = {
    "easy":   {"size": 10,  "bombs": 6},
    "hard":   {"size": 10, "bombs": 25},
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

