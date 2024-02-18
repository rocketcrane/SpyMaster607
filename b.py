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

try:
	from adafruit_mcp3xxx.analog_in import AnalogIn
	import RPi.GPIO as GPIO
	import adafruit_mcp3xxx.mcp3008 as MCP
	import busio
	import digitalio
	import board
except:
	logging.warning("Import failed, probably not on RPi")

# initialize AI
load_dotenv() # .env file for API key
client = OpenAI()
audio = pyaudio.PyAudio() # initialize audio
engine = pyttsx3.init() # initialize text to speech

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

def remap_range(value, left_min, left_max, right_min, right_max):
	# log addition
	if value == 0:
		value = value + 2
	log_left_min = math.log(left_min + 2)
	log_left_max = math.log(left_max)
	log_value = math.log(value)
	
	# this remaps a value from original (left) range to new (right) range
	# Figure out how 'wide' each range is
	left_span = log_left_max - log_left_min
	right_span = right_max - right_min
	
	# Convert the left range into a 0-1 range (int)
	valueScaled = float(log_value - log_left_min) / float(left_span)
	
	# Convert the 0-1 range into a value in the right range.
	return float(right_min + (valueScaled * right_span))
		
def record(transcription, responses, change):
	# recording configuration
	DEVICE = 0
	FORMAT = pyaudio.paInt32
	CHANNELS = 1
	RATE = 44100
	CHUNK = 1024
	RECORD_SECONDS = 5
	OUTPUT_FILENAME = "recording.wav"
	MP3_FILENAME = "recording"
	
	# whisper configuration
	WHISPER_TEMP = 0
	WHISPER_CONTEXT_LENGTH = 400 # context characters to feed into whisper
	
	# are we using the right PyAudio device?
	list_input_device(audio)
	logging.debug("using device", DEVICE)
	
	index = 0 # start recording mp3 index at 0
	
	while True:
		# recording
		stream = audio.open(format=FORMAT, channels=CHANNELS,
							rate=RATE, input=True, input_device_index=DEVICE,
							frames_per_buffer=CHUNK)
		frames = []
		logging.info("Recording started...")
		for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
			data = stream.read(CHUNK)
			frames.append(data)
		logging.info("Recording finished.")
		
		# stop stream - might prevent PyAudio issues
		stream.stop_stream()
		stream.close()
		
		# generate .wav file
		with wave.open(OUTPUT_FILENAME, 'wb') as wf:
			wf.setnchannels(CHANNELS)
			wf.setsampwidth(audio.get_sample_size(FORMAT))
			wf.setframerate(RATE)
			wf.writeframes(b''.join(frames))
		
		# convert .wav to .mp3
		MP3_FILENAME_ALL = MP3_FILENAME + index + ".mp3"
		mp3 =  pydub.AudioSegment.from_wav(OUTPUT_FILENAME)
		mp3.export(MP3_FILENAME_ALL, format="mp3")
	
		try:
			MP3_FILENAME_ALL = MP3_FILENAME + index + ".mp3"
			audio_file = open(MP3_FILENAME_ALL, 'rb')
			# transcribe audio with OpenAI whisper and save
			current_transcription = client.audio.transcriptions.create(model="whisper-1", 
																file=audio_file,
																temperature=WHISPER_TEMP,
																response_format="text")
			transcription.value += " " # add a space for readability
			transcription.value = current_transcription
			logging.info("transcription:", transcription.value)
			
			index = index + 1 # increment mp3 index
			os.remove(MP3_FILENAME_ALL) # remove the file
			
			# response
			output = client.chat.completions.create(
				model="gpt-4-turbo-preview",
				messages=[
				{"role": "system", "content": "You are the spymaster of the world's best, most top secret spy organization. Mentor, teach, and support your spy through the spy walkie-talkie. Don't talk directly about who you are or your organization, be discreet but helpful, and be EXTREMELY concise, because your response will be read out loud."},
				{"role": "user", "content": transcription.value}
			  ]
			)
			response = output.choices[0].message.content
			logging.info("response: ", response)
			
			# save responses and set changed variable
			responses.value = response
			change[0] = 1
			
			# speak
			speech_file_path = Path(__file__).parent / "speech.mp3"
			response = client.audio.speech.create(
			  model="tts-1",
			  voice="onyx",
			  input=response
			)
			response.stream_to_file(speech_file_path)
			
			try:
				os.system('mpg321 speech.mp3 &')
			except:
				pass
		except:
			pass
	
def sensors(inputs):
	# keeps tracks of the buttons
	oldVol = 0
	oldLev = 0
	oldBut = 0
	
	last_read = 0       # this keeps track of the last potentiometer value
	tolerance = 100     # to keep from being jittery we'll only change
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
			# how much has it changed since the last read?
			pot_adjust = abs(trim_pot - last_read)
			if pot_adjust > tolerance:
				trim_pot_changed = True
			if trim_pot_changed:
				# let the main code know the pot has changed
				inputs[7] = 1
				
				# convert 16bit adc0 (0-65535) trim pot read into 0-100 volume level
				logging.debug("potentiometer is ", trim_pot)
				inputs[3] = remap_range(trim_pot, 0, 65535, 0, 100)
				# save the potentiometer reading for the next loop
				last_read = trim_pot
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
		engine.setProperty('rate', 125)    # speed percent (can go over 100)
		spyMasterChannel = random.randrange(30,80) / 10
		engine.say(str("Secret channel found at level " + str(spyMasterChannel)))
		engine.runAndWait()
		
		# wait for potentiometer to change
		while inputs[7] != 1:
			continue
		
		logging.info("3. potentiometer changed, channel is " + spyMasterChannel)
		inputs[7] = 0 # reset tracker of input changes
		
		# connect to channel
		while inputs[3] < spyMasterChannel:
			logging.info("potentiometer is ", inputs[3])
			continue
		
		# speak secret code message
		engine.say(str("Secure connection established, enter secret code to authenticate"))
		engine.runAndWait()
		
		# wait for button to change
		while inputs[6] != 1:
			continue
			
		logging.info("4. code key pressed")
		inputs[6] = 0 # reset tracker of input changes
		engine.say("Connected to MI6 headquarters. Welcome, agent.")
		engine.runAndWait()
		
		# lever has changed
		while inputs[5] != 1:
			pass
		
		cachedInputs = inputs #cache the inputs to make sure they don't change
		logging.debug("lever is now ", cachedInputs[1])
		# reset tracker of input changes
		inputs[5] = 0
		
	sensing.join()
	
	# cleanup
	audio.terminate()