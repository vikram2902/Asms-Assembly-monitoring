from gpiozero import LED
from time import sleep

class LED_Asms:
    def __init__(self):
        self.led_true = LED(22)
        self.led_false = LED(23)

    def led_true_func(self):
        print("Blinking TRUE LED")
        self.led_true.on()
        sleep(0.05)
        self.led_true.off()

    def led_false_func(self):
        print("Blinking FALSE LED")
        self.led_false.on()
        sleep(0.05)
        self.led_false.off()

# ---- CALL FUNCTIONS HERE ----
if __name__ == "__main__":
    led_job = LED_Asms()
    led_job.led_true_func()
    led_job.led_false_func()

