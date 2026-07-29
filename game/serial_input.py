import serial
from config import SERIAL_PORT, BAUDRATE, NSQUARES

ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.01)

""" GAMMEL
KEYWORDS = {
    "Zero": 0, "One": 1, "Two": 2, "Three": 3, "Tree":3,
    "Four": 4, "Five": 5, "Six": 6,
    "Seven": 7, "Eight": 8, "Nine": 9,
}

COMMANDS = {
    "Stop": "reset",
    "Marvin": "flag",     
    "Bird": "open",
    "No" : "no",
    "Happy" : "easy",
    "Learn" : "hard",
}

#NY

KEYWORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3,
    "four": 4, "five": 5, "six": 6,
    "seven": 7,
}

COMMANDS = {
    "reset": "reset",
    "flag": "flag",     
    "open": "open",
    "no" : "no",
}
"""
#ny: store bokstaver, for at den skal kunne gå med aslak sin kode
KEYWORDS = {
    "ZERO": 0, "ONE": 1, "TWO": 2, "THREE": 3,
    "FOUR": 4, "FIVE": 5, "SIX": 6,
    "SEVEN": 7,
}

COMMANDS = {
    "RESET": "reset",
    "FLAG": "flag",
    "OPEN": "open",
    "NO": "no",
}

def check_wakeword():
    return True #endra fordi jeg ikke vil at den skal være avhengig av wakeword lengre
"""
    line = ser.readline().decode('utf-8', errors='ignore').strip()
    #print(line)
    if "Wakeword" in line:
        print("Wakeword detektert!")
        return True
    return False
"""
def check_input():
    line = ser.readline().decode('utf-8', errors='ignore').strip()
    
    for word, value in KEYWORDS.items():
        if word in line:
            print(line)
            if value < NSQUARES:
                return ("number", value)

    for word, command in COMMANDS.items():
        if word in line:
            print(line)
            return ("command", command)

    return None

def clear_buffer():
    ser.reset_input_buffer()