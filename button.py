 import RPi.GPIO as GPIO
from time import sleep

# pin 36 is volume on/off pin 16 is the lever, but only works halfway
# pin 22 is the button
pin = 22
GPIO.setmode(GPIO.BOARD)
GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

while True:
  if GPIO.input(pin) == GPIO.HIGH:
    print("Pin is HIGH!")
  elif GPIO.input(pin) == GPIO.LOW:
    print("Pin is LOW...")
  sleep(0.15)
