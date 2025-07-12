from gpiozero import Button
from signal import pause

# Use GPIO17 (Physical pin 11)
TRIGGER_PIN = 17
# Setup button to detect HIGH signal (3.3V pulse)
trigger = Button(TRIGGER_PIN, pull_up=False)

def on_detect():
    print("[✅] HIGH pulse detected on GPIO17")

trigger.when_pressed = on_detect

print("[Ready] Waiting for 3.3V HIGH pulse on GPIO17...")
pause()

