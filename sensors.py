import RPi.GPIO as GPIO
from time import sleep

GPIO.setmode(GPIO.BCM)

# pin 36 / BCM16 is volume on/off pin 
# pin 16 / BCM23 is the lever, but only works halfway
# pin 22 / BCM25 is the button
vol = 16
lev = 23
but = 25

GPIO.setup(vol, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(lev, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(but, GPIO.IN, pull_up_down=GPIO.PUD_UP)

import board
import os
import time
import busio
import digitalio
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn

# create the spi bus
spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)

# create the cs (chip select)
cs = digitalio.DigitalInOut(board.D22)

# create the mcp object
mcp = MCP.MCP3008(spi, cs)

# create an analog input channel on pin 0
chan0 = AnalogIn(mcp, MCP.P0)

print('Raw ADC Value: ', chan0.value)
print('ADC Voltage: ' + str(chan0.voltage) + 'V')

last_read = 0       # this keeps track of the last potentiometer value
tolerance = 250     # to keep from being jittery we'll only change
					# volume when the pot has moved a significant amount
					# on a 16-bit ADC

def remap_range(value, left_min, left_max, right_min, right_max):
	# this remaps a value from original (left) range to new (right) range
	# Figure out how 'wide' each range is
	left_span = left_max - left_min
	right_span = right_max - right_min

	# Convert the left range into a 0-1 range (int)
	valueScaled = int(value - left_min) / int(left_span)

	# Convert the 0-1 range into a value in the right range.
	return int(right_min + (valueScaled * right_span))

while True:
	if GPIO.input(vol) == GPIO.HIGH:
		print("Volume switch is HIGH!")
	elif GPIO.input(vol) == GPIO.LOW:
		print("Volume switch is LOW...")
	if GPIO.input(lev) == GPIO.HIGH:
		print("Lever is HIGH!")
	elif GPIO.input(lev) == GPIO.LOW:
		print("Lever is LOW...")
	if GPIO.input(but) == GPIO.HIGH:
		print("Button is HIGH!")
	elif GPIO.input(but) == GPIO.LOW:
		print("Button is LOW...")
	
	# we'll assume that the pot didn't move
	trim_pot_changed = False
	
	# read the analog pin
	trim_pot = chan0.value
	
	# how much has it changed since the last read?
	pot_adjust = abs(trim_pot - last_read)
	
	if pot_adjust > tolerance:
		trim_pot_changed = True
	
	if trim_pot_changed:
		# convert 16bit adc0 (0-65535) trim pot read into 0-100 volume level
		set_volume = remap_range(trim_pot, 0, 65535, 0, 100)
	
		# set OS volume playback volume
		print('Volume = {volume}%' .format(volume = set_volume))
		set_vol_cmd = 'sudo amixer cset numid=1 -- {volume}% > /dev/null' \
		.format(volume = set_volume)
		os.system(set_vol_cmd)
	
		# save the potentiometer reading for the next loop
		last_read = trim_pot
	print()
	sleep(0.5)
