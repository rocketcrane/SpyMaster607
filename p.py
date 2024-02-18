# SPDX-FileCopyrightText: 2019 Mikey Sklar for Adafruit Industries
#
# SPDX-License-Identifier: MIT

import os
import time
import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn
import math

# create the spi bus
spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)

# create the cs (chip select)
cs = digitalio.DigitalInOut(board.D22)

# create the mcp object
mcp = MCP.MCP3008(spi, cs)

# create an analog input channel on pin 0
chan0 = AnalogIn(mcp, MCP.P0)

last_read = 0       # this keeps track of the last potentiometer value

def remap_range(value, in_min, in_max, out_min, out_max):
    # this remaps a value from original (left) range to new (right) range
    # Figure out how 'wide' each range is
    in_span = in_max - in_min
    out_span = out_max - out_min

    # Convert the left range into a 0-1 range
    valueScaled = float(value - in_min) / float(in_span)
    #print("this should be between 0 and 1: ", valueScaled)
    
    # Logarithmically map the value
    # first, scale the value to a 1-11 range
    valueScaled = float(1 + (valueScaled * 9))
    #print("this should be between 1 and 10: ", valueScaled)
    # then, map it to log base 10
    valueScaled = math.log(valueScaled, 10)
    #print("this should be between 0 and 1: ", valueScaled)
    
    # Linearly scale the value to the new range
    valueScaled = float(out_min + (valueScaled * out_span))

    # Convert the 0-1 range into a value in the right range.
    return valueScaled

while True:
    # read the analog pin
    trim_pot = chan0.value
    
    # if the trim pot is 0 discard the reading
    if trim_pot < 1:
        trim_pot = last_read
        
    # if trim pot only dropped a bit discard the reading (lots of noise there)
    if trim_pot > (last_read - 1000):
        trim_pot = last_read
    
    # convert 16bit adc0 (0-65535) trim pot read into 0-100 volume level
    volume = remap_range(trim_pot, 0, 65535, 0, 100)
    
    print("trim pot is ", trim_pot, " remapped to ", volume)

    # save the potentiometer reading for the next loop
    last_read = trim_pot

    # hang out and do nothing for a half second
    time.sleep(0.01)
