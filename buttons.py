import RPi.GPIO as GPIO
from time import sleep

# pin 36 GPIO 16 is volume on/off 

all = [11,13,15,16,18,22,29,31,32,33,36,37]

GPIO.setmode(GPIO.BOARD)
for x in all:
	GPIO.setup(x, GPIO.IN, pull_up_down=GPIO.PUD_UP)

while True:
	for x in all:
		if GPIO.input(x) == GPIO.HIGH:
			print(x, "is HIGH!")
		elif GPIO.input(x) == GPIO.LOW:
			print(x,"is LOW...")
	sleep(1)
	print()
