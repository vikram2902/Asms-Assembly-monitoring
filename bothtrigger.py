from gpiozero import Button
from signal import pause

# GPIOs connected to opto outputs
TRIGGER1_PIN = 17  # IN1
TRIGGER2_PIN = 27  # IN2

# Use pull_up=True because opto pulls GPIO LOW when active
trigger1 = Button(TRIGGER1_PIN, pull_up=False, bounce_time=0.1)
trigger2 = Button(TRIGGER2_PIN, pull_up=False,  bounce_time=0.1)

def on_trigger1():
    print("[🔔] Sensor 1 triggered")

def on_trigger2():
    print("[🔔] Sensor 2 triggered")

trigger1.when_pressed = on_trigger1
trigger2.when_pressed = on_trigger2

print("[Ready] Waiting for sensor pulses...")
pause()

