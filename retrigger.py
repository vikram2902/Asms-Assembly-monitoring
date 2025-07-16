from gpiozero import Button
from gpiozero.pins.lgpio import LGPIOFactory
from time import sleep

# Use the lgpio backend
Button.pin_factory = LGPIOFactory()

# GPIO26 = Pin 37
button = Button(26, pull_up=True)

print("Press the button connected to GPIO26...")

while True:
    if button.is_pressed:
        print("Button pressed!")
        sleep(0.3)

