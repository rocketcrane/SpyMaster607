# TODO: logarithmic potentiometer

try:
	import RPi.GPIO as GPIO
	import adafruit_mcp3xxx.mcp3008 as MCP
	import busio
	import digitalio
	import board
	from adafruit_mcp3xxx.analog_in import AnalogIn
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
import multiprocessing
from ctypes import c_char_p
load_dotenv()
client = OpenAI()

# whisper config
WHISPER_TEMP = 0
WHISPER_CONTEXT_LENGTH = 400 # context characters to feed into whisper

# recording config
DEVICE = 0
FORMAT = pyaudio.paInt32
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 5
OUTPUT_FILENAME = "recording.wav"
MP3_FILENAME = "recording.mp3"

try:
	# GPIO & potentiometer setup	
	GPIO.setmode(GPIO.BCM)
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
	last_read = 0       # this keeps track of the last potentiometer value
	tolerance = 250     # to keep from being jittery we'll only change
						# volume when the pot has moved a significant amount
						# on a 16-bit ADC
except:
	pass

# ------------------------------------FUNCTIONS----------------------------------
# speech-to-text, uses previous transcription for context
def transcribe_audio(audio_file_path, last_transcription):
	with open(audio_file_path, 'rb') as audio_file:
		curr_transcription = client.audio.transcriptions.create(model="whisper-1", 
																file=audio_file_path,
																# [-x:] gets last x characters of string
																prompt=last_transcription[-WHISPER_CONTEXT_LENGTH:],
																temperature=WHISPER_TEMP,
																response_format="text")
	return curr_transcription

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
		# this remaps a value from original (left) range to new (right) range
		# Figure out how 'wide' each range is
		left_span = left_max - left_min
		right_span = right_max - right_min
		
		# Convert the left range into a 0-1 range (int)
		valueScaled = int(value - left_min) / int(left_span)
		
		# Convert the 0-1 range into a value in the right range.
		return int(right_min + (valueScaled * right_span))
		
def record(transcription):
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
	mp3 =  pydub.AudioSegment.from_wav("recording.wav")
	mp3.export("recording.mp3", format="mp3")
	
	# transcribe audio with OpenAI whisper and save
	current_transcription = transcribe_audio(Path(__file__).parent / MP3_FILENAME, transcription.value)
	transcription.value += " " # add a space for readability
	transcription.value += current_transcription
	print(transcription.value)
# --------------------------------------------------------------------------------

# buttons and volume global variables
volSwitch = False
lever = False
button = False
set_volume = 0
# startup pyAudio
audio = pyaudio.PyAudio()

if __name__ == '__main__':
	# start transcription with current time
	manager = multiprocessing.Manager()
	transcription = manager.Value(c_char_p, str(datetime.now()))
	
	# delete old recordings - might prevent recording issues
	try:
		os.remove("recording.mp3")
		os.remove("recording.wav")
	except:
		pass
		# print("No recordings to delete.")
	
	# are we using the right pyaudio device?
	list_input_device(audio)
	print("using device", DEVICE)
	
	# main loop
	#while True:
		# read GPIO pins
	try:
		if GPIO.input(vol) == GPIO.HIGH:
			volSwitch = False
		elif GPIO.input(vol) == GPIO.LOW:
			volSwitch = True
		if GPIO.input(lev) == GPIO.HIGH:
			lever = True
		elif GPIO.input(lev) == GPIO.LOW:
			lever = False
		if GPIO.input(but) == GPIO.HIGH:
			button = False
		elif GPIO.input(but) == GPIO.LOW:
			button = True
		print("volume switch is ", volSwitch, " lever is ", lever, " button is ", button)
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
			# convert 16bit adc0 (0-65535) trim pot read into 0-100 volume level
			set_volume = remap_range(trim_pot, 0, 65535, 0, 100)
			# set OS volume playback volume
			print('Volume = {volume}%' .format(volume = set_volume))
			#set_vol_cmd = 'sudo amixer cset numid=1 -- {volume}% > /dev/null' \
			#.format(volume = set_volume)
			#os.system(set_vol_cmd)
			# save the potentiometer reading for the next loop
			last_read = trim_pot
	except:
		pass
		
	recording = Process(target=record, args=(transcription,))
	if not recording.is_alive():
		recording.start()
	recording.join()

	# cleanup
	audio.terminate()