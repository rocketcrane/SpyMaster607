from datetime import datetime
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from time import sleep
from multiprocessing import Process
from ctypes import c_char_p
import os
import pyaudio
import pydub
import wave
import random
import math
import logging
import multiprocessing
import pyttsx3

logging.basicConfig(level=logging.INFO) # set logging level

# audio initialization to suppress the entire page of ALSA errors
from ctypes import *
from contextlib import contextmanager
ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
def py_error_handler(filename, line, function, err, fmt):
	pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
@contextmanager
def noalsaerr():
	asound = cdll.LoadLibrary('libasound.so')
	asound.snd_lib_error_set_handler(c_error_handler)
	yield
	asound.snd_lib_error_set_handler(None)
with noalsaerr():
	audio = pyaudio.PyAudio() # initialize audio
logging.info("PyAudio initialized")

try:
	from adafruit_mcp3xxx.analog_in import AnalogIn
	import RPi.GPIO as GPIO
	import adafruit_mcp3xxx.mcp3008 as MCP
	import busio
	import digitalio
	import board
except:
	logging.warning("Import failed, probably not on RPi")
	
# recording configuration
DEVICE = 0
FORMAT = pyaudio.paInt32
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 5
OUTPUT_FILENAME = "recording.wav"
MP3_FILENAME = "recording.mp3"

# whisper configuration
WHISPER_TEMP = 0
	
# set display variable (needed for FFPlay)
os.system('export DISPLAY=:0.0')

# initialize AI
load_dotenv() # .env file for API key
client = OpenAI()
audio = pyaudio.PyAudio() # initialize audio
engine = pyttsx3.init() # initialize text to speech
engine.setProperty('volume',0.5) # setting up volume level  between 0 and 1
engine.setProperty('rate', 150)    # speed percent (can go over 100)

# are we using the right PyAudio device?
if logging.DEBUG >= logging.root.level:
	list_input_device(audio)
	logging.debug("using device", DEVICE)

# GPIO & potentiometer setup, Raspberry Pi only
try:	
	GPIO.setmode(GPIO.BCM)
	# pin numbers for buttons/switches
	vol = 16
	lev = 23
	but = 25
	GPIO.setup(vol, GPIO.IN, pull_up_down=GPIO.PUD_UP)
	GPIO.setup(lev, GPIO.IN, pull_up_down=GPIO.PUD_UP)
	GPIO.setup(but, GPIO.IN, pull_up_down=GPIO.PUD_UP)
	spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI) # create the SPI bus
	cs = digitalio.DigitalInOut(board.D22) # create the CS (chip select)
	mcp = MCP.MCP3008(spi, cs) # create the MCP object
	chan0 = AnalogIn(mcp, MCP.P0) # create an analog input channel on pin 0
except:
	logging.warning("IO not setup, probably not on RPi")

# ------------------------------------FUNCTIONS----------------------------------
# list input devices, p = pyAudio instance
def list_input_device(p):
	nDevices = p.get_device_count()
	logging.debug('Found input devices:')
	for i in range(nDevices):
		deviceInfo = p.get_device_info_by_index(i)
		devName = deviceInfo['name']
		logging.debug(f"Device ID {i}: {devName}")

def remap_range(value, in_min, in_max, out_min, out_max):
	# this remaps a value from original (left) range to new (right) range
	# Figure out how 'wide' each range is
	in_span = in_max - in_min
	out_span = out_max - out_min
	
	# Convert the left range into a 0-1 range
	valueScaled = float(value - in_min) / float(in_span)
	#print("this should be between 0 and 1: ", valueScaled)
	
	# Logarithmically map the value
	# first, scale the value to a 0.1-10 range
	valueScaled = float(0.1 + (valueScaled * 9.9))
	#print("this should be between 0.1 and 10: ", valueScaled)
	# then, map it to log base 10
	valueScaled = math.log(valueScaled, 10)
	#print("this should be between -1 and 1: ", valueScaled)
	# then scale it to between 0 and 1
	valueScaled = (valueScaled + 1) / 2
	
	# Linearly scale the value to the new range
	valueScaled = float(out_min + (valueScaled * out_span))
	
	# Convert the 0-1 range into a value in the right range.
	return valueScaled
	
def sensors(inputs):
	# keeps tracks of the buttons
	oldVol = 0
	oldLev = 0
	oldBut = 0
	
	last_read = 0       # this keeps track of the last potentiometer value
	tolerance = 250     # to keep from being jittery we'll only change
	# volume when the pot has moved a significant amount
	# on a 16-bit ADC
	
	while True:
		# read GPIO pins
		try:
			if GPIO.input(vol) == GPIO.HIGH:
				inputs[0] = 0
			elif GPIO.input(vol) == GPIO.LOW:
				inputs[0] = 1
			if GPIO.input(lev) == GPIO.HIGH:
				inputs[1] = 1
			elif GPIO.input(lev) == GPIO.LOW:
				inputs[1] = 0
			if GPIO.input(but) == GPIO.HIGH:
				inputs[2] = 0
			elif GPIO.input(but) == GPIO.LOW:
				inputs[2] = 1
			# do stuff if the volume switch changed
			if oldVol != inputs[0]:
				inputs[4] = 1 # let the main code know the switch has changed
				oldVol = inputs[0] # update values that keep track of changes
				logging.debug("volume switch is ", inputs[0])
				
			# ditto if lever has changed
			if oldLev != inputs[1]:
				inputs[5] = 1 # let main code know of change
				oldLev = inputs[1] # update values that keep track
				logging.debug(" lever is ", inputs[1])
			
			# or if button has changed
			if oldBut != inputs[2]:
				inputs[6] = 1 # let main code know of change
				oldBut = inputs[2] # update values that keep track
				logging.debug(" button is ", inputs[2])
				
			# read potentiometer
			# we'll assume that the pot didn't move
			trim_pot_changed = False
			# read the analog pin
			trim_pot = chan0.value
			
			# if the trim pot is 0 and volume switch is ON discard the reading
			if trim_pot < 1 and inputs[0] == 1:
				trim_pot = last_read
				
			# if trim pot only dropped a bit discard the reading (lots of noise there)
			if trim_pot > (last_read - 250) and trim_pot < last_read:
				trim_pot = last_read
			
			# output the volume
			# convert 16bit adc0 (0-65535) trim pot read into 0-100 volume level
			volume = remap_range(trim_pot, 0, 65535, 0, 100)
			inputs[3] = volume
			
			# how much has it changed since the last read?
			pot_adjust = abs(trim_pot - last_read)
			if pot_adjust > tolerance:
				trim_pot_changed = True
			if trim_pot_changed:
				# let the main code know the pot has changed
				inputs[7] = 1
			
			last_read = trim_pot # save the potentiometer reading for the next loop
		except:
			logging.warning("Read sensors failed, probably not on RPi")
# --------------------------------------------------------------------------------

if __name__ == '__main__':
	# start transcription with current time
	manager = multiprocessing.Manager()
	inputs = multiprocessing.Array('d', 8) # set the buttons and volume
	sensing = Process(target=sensors, args=(inputs,))
	sensing.start()
	
	# main loop
	while True:
		# wait for volume switch to change
		while inputs[4] != 1:
			continue
		
		logging.info("1. volume changed")
		inputs[4] = 0 # reset tracker of input changes
		
		# wait for volume switch to turn on
		while inputs[0] != 1:
			continue
		
		# speak intro message
		logging.info("2. volume on")
		spyMasterChannel = random.randrange(30,80)
		engine.say(str("Secret channel found at level " + str(spyMasterChannel/10)))
		engine.runAndWait()
		
		# wait for potentiometer to change
		while inputs[7] != 1:
			continue
		
		logging.info("3. potentiometer changed, channel is " + str(spyMasterChannel))
		inputs[7] = 0 # reset tracker of input changes
		
		# connect to channel
		while True:
			channel = inputs[3]
			logging.debug("potentiometer is " + str(channel))
			if channel > spyMasterChannel and channel < (spyMasterChannel+3):
				break
		
		# speak secret code message
		logging.info("4. channel found")
		engine.say(str("Secure connection established, enter secret code to authenticate"))
		engine.runAndWait()
		
		# wait for button to change
		while inputs[6] != 1:
			continue
			
		logging.info("5. code key pressed")
		inputs[6] = 0 # reset tracker of input changes
		engine.say("Connected to MI6 headquarters. Welcome, agent.")
		engine.runAndWait()
		
		index = 0 # start recording mp3 index at 0
		
		# start transcription with current time
		transcription = str(datetime.now())[0:19]
		
		#AI audio loop
		while True:
			# lever has changed
			while inputs[5] != 1:
				continue
			
			# check for real-time state of the lever
			while inputs[1] != 1:
				continue
			
			logging.info("6. talk lever pressed")
			inputs[5] = 0 # reset tracker of input changes
			
			# recording audio
			logging.info("7. recording started")
			# jump back to try the recording until it works!
			while True:
				try:
					stream = audio.open(format=FORMAT, channels=CHANNELS,
										rate=RATE, input=True, input_device_index=DEVICE,
										frames_per_buffer=CHUNK)
					frames = []
					for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
						data = stream.read(CHUNK)
						frames.append(data)
					
					# stop stream - might prevent PyAudio issues
					stream.stop_stream()
					stream.close()
					logging.info(" 8. recording finished")
				except:
					logging.error("recording failed!")
					continue # jump to beginning of loop so we don't try to use the non-existent recording
				break
			
			# generate .wav file
			with wave.open(OUTPUT_FILENAME, 'wb') as wf:
				wf.setnchannels(CHANNELS)
				wf.setsampwidth(audio.get_sample_size(FORMAT))
				wf.setframerate(RATE)
				wf.writeframes(b''.join(frames))
			
			# convert .wav to .mp3
			mp3 =  pydub.AudioSegment.from_wav(OUTPUT_FILENAME)
			mp3.export(MP3_FILENAME, format="mp3")
			
			# speech-to-text with Whisper
			audio_file = open(MP3_FILENAME, 'rb')
			# transcribe audio with OpenAI whisper and save
			transcribe = client.audio.transcriptions.create(model="whisper-1", 
																file=audio_file,
																temperature=WHISPER_TEMP,
																response_format="text")
			current_transcription = str(transcribe)
			transcription += " " # add a space for readability
			transcription += current_transcription
			logging.info("9. transcription obtained: " + current_transcription)
			os.remove(MP3_FILENAME) # remove the mp3 recording
			
			# save the transcription to a text file
			with open('conversation.txt', 'w') as f:
				f.write(current_transcription)
				f.write('\n')
			
			# spymaster's response via GPT-4 in a trench coat
			output = client.chat.completions.create(
				model="gpt-4-turbo-preview",
				messages=[
				{"role": "system", "content": "You are the spymaster of the world's best, most top secret spy organization. Mentor, teach, and support your spy through the spy walkie-talkie. Don't talk directly about who you are or your organization, be discreet but helpful, and be EXTREMELY EXTREMELY CONCISE, because your response will be read out loud."},
				{"role": "user", "content": current_transcription}
			  ]
			)
			response = output.choices[0].message.content
			logging.info("10. response obtained from MI6: " + str(response))
			
			# save the response to a text file
			with open('conversation.txt', 'w') as f:
				f.write(response)
				f.write('\n')
			
			# text-to-speech with OpenAI
			speech_file_path = Path(__file__).parent / "speech.mp3"
			response = client.audio.speech.create(
			  model="tts-1",
			  voice="onyx",
			  input=response
			)
			response.stream_to_file(speech_file_path)
			
			# play the response out as an mp3
			os.system('mpg321 -q speech.mp3')
	# cleanup
	audio.terminate()
	sensing.join()