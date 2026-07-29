import serial
from config import SERIAL_PORT, BAUDRATE

# Spillnavnet som blir MQTT-topic på 91: "games/<GAME_NAME>/score"
GAME_NAME = "minesweeper"


def send_score(player_name, mines_found, time_seconds, won):
    try:
        # Åpne UART til nRF54 (som videresender til nRF9151)
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)

        if not won:
            mines_found = 0

        #sender slikt 54 koden forventer
        json_payload = '{"playerName": "%s", "minesFound":%d,"timeSeconds":%d,"won":%s}' % (
            player_name,
            mines_found,
            time_seconds,
            "true" if won else "false",
        )

        
        data = "%s|%s\n" % (GAME_NAME, json_payload)

        # Send over UART (må være bytes, derfor .encode())
        ser.write(data.encode())
        ser.close()
        print("Score sendt:", data.strip())
    except Exception as e:
        print("Feil ved sending:", e)


