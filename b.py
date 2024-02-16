# TODO: logarithmic potentiometer

try:
	import RPi.GPIO as GPIO
	import adafruit_mcp3xxx.mcp3008 as MCP
	import busio
	import digitalio
	import board
	from adafruit_mcp3xxx.analog_in import AnalogIn
	import pyttsx3
except:
	print("not on Pi")

from datetime import datetime
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from time import sleep
from multiprocessing import Process
import os
import pyaudio
import pydub
import wave
import time
import random
import math
import multiprocessing
from ctypes import c_char_p
from ctypes import c_uint8
load_dotenv()
client = OpenAI()

try:
	# GPIO & potentiometer setup	
	GPIO.setmode(GPIO.BCM)
	# pin numbers for buttons/switches
	vol = 16
	lev = 23
	but = 25
	GPIO.setup(vol, GPIO.IN, pull_up_down=GPIO.PUD_UP)
	GPIO.setup(lev, GPIO.IN, pull_up_down=GPIO.PUD_UP)
	GPIO.setup(but, GPIO.IN, pull_up_down=GPIO.PUD_UP)
	# create the SPI bus
	spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
	# create the CS (chip select)
	cs = digitalio.DigitalInOut(board.D22)
	# create the MCP object
	mcp = MCP.MCP3008(spi, cs)
	# create an analog input channel on pin 0
	chan0 = AnalogIn(mcp, MCP.P0)
except:
	pass

# ------------------------------------FUNCTIONS----------------------------------
# list input devices, p = pyAudio instance
def list_input_device(p):
	nDevices = p.get_device_count()
	print('Found input devices:')
	for i in range(nDevices):
		deviceInfo = p.get_device_info_by_index(i)
		devName = deviceInfo['name']
		print(f"Device ID {i}: {devName}")
		# print("Device Info: ")
		# print(deviceInfo)

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
	# recording config
	DEVICE = 0
	FORMAT = pyaudio.paInt32
	CHANNELS = 1
	RATE = 44100
	CHUNK = 1024
	RECORD_SECONDS = 5
	OUTPUT_FILENAME = "recording.wav"
	MP3_FILENAME = "recording"
	
	# are we using the right pyaudio device?
	list_input_device(audio)
	print("using device", DEVICE)
	
	# start index at 0
	index = 0
	
	# whisper config
	WHISPER_TEMP = 0
	WHISPER_CONTEXT_LENGTH = 400 # context characters to feed into whisper
	
	'''
	try:
		voices = engine.getProperty('voices')
		for voice in voices:
			print("Voice:")
			print(" - ID: %s" % voice.id)
			print(" - Name: %s" % voice.name)
			print(" - Languages: %s" % voice.languages)
			print(" - Gender: %s" % voice.gender)
			print(" - Age: %s" % voice.age)
	except:
		pass
		'''
	
	while True:
		# recording
		stream = audio.open(format=FORMAT, channels=CHANNELS,
							rate=RATE, input=True, input_device_index=DEVICE,
							frames_per_buffer=CHUNK)
		frames = []
		print("Recording started...")
		for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
			data = stream.read(CHUNK)
			frames.append(data)
		print("Recording finished.")
		
		# stop stream - might prevent pyAudio issues
		stream.stop_stream()
		stream.close()
		
		# generate .wav file
		with wave.open(OUTPUT_FILENAME, 'wb') as wf:
			wf.setnchannels(CHANNELS)
			wf.setsampwidth(audio.get_sample_size(FORMAT))
			wf.setframerate(RATE)
			wf.writeframes(b''.join(frames))
		
		# convert .wav to .mp3
		MP3_FILENAME_ALL = MP3_FILENAME + ".mp3"
		mp3 =  pydub.AudioSegment.from_wav(OUTPUT_FILENAME)
		mp3.export(MP3_FILENAME_ALL, format="mp3")
		
		# remove .wav file
		'''
		try:
			os.remove("recording.wav")
		except:
			pass
		'''
	
		try:
			MP3_FILENAME_ALL = MP3_FILENAME + ".mp3"
			audio_file = open(MP3_FILENAME_ALL, 'rb')
			# transcribe audio with OpenAI whisper and save
			current_transcription = client.audio.transcriptions.create(model="whisper-1", 
																file=audio_file,
																temperature=WHISPER_TEMP,
																response_format="text")
			transcription.value += " " # add a space for readability
			transcription.value = current_transcription
			print("transcription:", transcription.value)
			
			# increment index
			index = index + 1
			
			# remove the file
			#os.remove(MP3_FILENAME_ALL)
			
			# response
			output = client.chat.completions.create(
				model="gpt-4-turbo-preview",
				messages=[
				{"role": "system", "content": "You are the spymaster of the world's best, most top secret spy organization. Mentor, teach, and support your spy through the spy walkie-talkie. Don't talk directly about who you are or your organization, be discreet but helpful, and be very concise, because your response will be read out loud."},
				{"role": "user", "content": transcription.value}
			  ]
			)
			response = output.choices[0].message.content
			print("response: ", response)
			
			# save responses and set changed variable
			responses.value = response
			change[0] = 1
			
			engine.setProperty('rate', 150)    # Speed percent (can go over 100)
			# SPEAK THE RESPONSE
			engine.say(str(responses.value))
			engine.runAndWait()
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
				# let the main code know the switch has changed
				inputs[4] = 1
				
				# update values that keep track of changes
				oldVol = inputs[0]
				
				oldBut = inputs[2]
				# print("volume switch is ", inputs[0])
				
			# ditto if lever has changed
			if oldLev != inputs[1]:
				inputs[5] = 1 # let main code know of change
				oldLev = inputs[1] # update values that keep track
				# print(" lever is ", inputs[1])
			
			# or if button has changed
			if oldBut != inputs[2]:
				inputs[6] = 1 # let main code know of change
				oldBut = inputs[2] # update values that keep track
				# print(" button is ", inputs[2])
		except:
			pass
				
		# read potentiometer
		try:
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
				#print(trim_pot)
				inputs[3] = remap_range(trim_pot, 0, 65535, 0, 100)
				# set OS volume playback volume
				# print('Volume = {volume}%' .format(volume = inputs[3]))
				#set_vol_cmd = 'sudo amixer cset numid=1 -- {volume}% > /dev/null' \
				#.format(volume = inputs[3])
				#os.system(set_vol_cmd)
				# save the potentiometer reading for the next loop
				last_read = trim_pot
		except:
			pass
# --------------------------------------------------------------------------------

# only run PyAudio if we need it
#AUDIO = False
AUDIO = True


audio = pyaudio.PyAudio()

# tts initialization
engine = pyttsx3.init()

if __name__ == '__main__':
	# start transcription with current time
	manager = multiprocessing.Manager()
	transcription = manager.Value(c_char_p, str(datetime.now()))
	responses = manager.Value(c_char_p, " ")
	change = multiprocessing.Array('d', 1)
	
	# set the buttons and volume
	inputs = multiprocessing.Array('d', 8)
	
	# main loop
	sensing = Process(target=sensors, args=(inputs,))
	recording = Process(target=record, args=(transcription, responses, change))
	sensing.start()
	
	while True:
		# vol switch has changed
		if inputs[4] == 1:
			try:
				recording.join()
			except:
				pass
			cachedInputs = inputs #cache the inputs to make sure they don't change
			print("volume is now ", cachedInputs[0])
			# reset tracker of input changes
			inputs[4] = 0
			
			# volume switch is on
			while cachedInputs[0] != 1:
				pass
			
			# tts initialization
			engine = pyttsx3.init()
			engine.setProperty('rate', 100)    # Speed percent (can go over 100)
			
			spyMasterChannel = int(random.random()*100)
			
			# SPEAK THE RESPONSE
			engine.say(str("Connect to HQ at "+str(spyMasterChannel)))
			engine.runAndWait()
			
			# potentiometer has changed
			if inputs[7] == 1:
				cachedInputs = inputs #cache the inputs to make sure they don't change
				print("potentiometer is now ", cachedInputs[3], " desired channel is ", spyMasterChannel)
				# reset tracker of input changes
				inputs[7] = 0
				
				# connect to channel
				if cachedInputs[3] > spyMasterChannel:
					# tts initialization
					engine = pyttsx3.init()
					engine.setProperty('rate', 100)    # Speed percent (can go over 100)
					# SPEAK THE RESPONSE
					engine.say(str("Secure Datalink found, enter secret code to connect"))
					engine.runAndWait()
					
					# button has changed
					while inputs[6] != 1:
						pass
						
					cachedInputs = inputs #cache the inputs to make sure they don't change
					print("button is now ", cachedInputs[2])
					# reset tracker of input changes
					inputs[6] = 0
					
					# tts initialization
					engine = pyttsx3.init()
					engine.setProperty('rate', 100)    # Speed percent (can go over 100)
					# SPEAK THE RESPONSE
					engine.say("Connected. Welcome, agent.")
					engine.runAndWait()
					
					# lever has changed
					while inputs[5] != 1:
						pass
					
					cachedInputs = inputs #cache the inputs to make sure they don't change
					print("lever is now ", cachedInputs[1])
					# reset tracker of input changes
					inputs[5] = 0
					
					# start recording
					recording.start()
					
		'''# recording is finished
		if change[0] == 1:
			# reset tracker of recording
			change[0] = 0
			print("playing message")
			# tts initialization
			engine = pyttsx3.init()
			engine.setProperty('rate', 150)    # Speed percent (can go over 100)
			# SPEAK THE RESPONSE
			engine.say(str(responses.value))
			engine.runAndWait()'''
		
	sensing.join()
	
	# cleanup
	audio.terminate()