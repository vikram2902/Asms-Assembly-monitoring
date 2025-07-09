from gpiozero import Button
from signal import pause

sensor = Button(17)  # GPIO17, default pull-up config

def hand_detected():
    print("🖐️ Hand Detected (GPIO LOW)")

def no_hand():
    print("❌ No Hand (GPIO HIGH)")

sensor.when_pressed = hand_detected     # GPIO LOW → pressed → hand detected
sensor.when_released = no_hand          # GPIO HIGH → released → no hand

pause()

