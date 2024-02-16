from datetime import datetime
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import os
import pyaudio
import pydub
import wave
load_dotenv()
client = OpenAI()

# whisper config
WHISPER_TEMP = 0
WHISPER_CONTEXT_LENGTH = 400 # context characters to feed into whisper

# recording config
DEVICE = 1
FORMAT = pyaudio.paInt32
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 5
OUTPUT_FILENAME = "recording.wav"
MP3_FILENAME = "recording.mp3"

# delete old recordings - might prevent recording issues
try:
	os.remove("recording.mp3")
	os.remove("recording.wav")
except:
	print("No recordings to delete.")

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
# --------------------------------------------------------------------------------

# start transcription with current time
transcription = str(datetime.now())
# startup pyAudio
audio = pyaudio.PyAudio()

# main loop
while True:
	# are we using the right pyaudio device?
	list_input_device(audio)
	print("using device", DEVICE)
	
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
	current_transcription = transcribe_audio(Path(__file__).parent / MP3_FILENAME, transcription)
	transcription += " " # add a space for readability
	transcription += current_transcription
	print(transcription)

# cleanup
audio.terminate()