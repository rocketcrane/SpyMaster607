RECORD_SECONDS = 5
WHISPER_TEMP = 0
WHISPER_CONTEXT_LENGTH = 400 # context characters to feed into whisper

from datetime import datetime
from pathlib import Path

import openai

import os
import pyaudio
import pydub
import wave

MP3_FILENAME = "recording.mp3"

# ------------------------------------OPENAI FUNCTIONS----------------------------------
# speech-to-text, uses previous transcription for context
def transcribe_audio(audio_file_path, last_transcription):
	with open(audio_file_path, 'rb') as audio_file:
		curr_transcription = client.audio.transcriptions.create(model="whisper-1", file=audio_file, prompt=last_transcription, temperature=WHISPER_TEMP)
	return curr_transcription['text']
# --------------------------------------------------------------------------------------

transcription = str(datetime.now())

client = openai(api_key=os.getenv("OPENAI_API_KEY"))

# startup pyaudio instance
audio = pyaudio.PyAudio()

# main loop
while True:
	# start recording
	stream = audio.open(format=pyaudio.paInt16, channels=1,
					rate=44100, input=True,
					frames_per_buffer=1024)
	frames = []

	# record for RECORD_SECONDS
	for i in range(0, int(44100 / 1024 * RECORD_SECONDS)):
		data = stream.read(1024)
		frames.append(data)

	# generate .wav file
	file = wave.open("recording.wav", 'wb')
	file.setnchannels(1)
	file.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
	file.setframerate(44100)
	file.writeframes(b''.join(frames))

	# convert .wav to .mp3
	mp3 =  pydub.AudioSegment.from_wav("recording.wav")
	mp3.export("recording.mp3", format="mp3")
	
	# transcribe audio with openai whisper and store
	current_transcription = client.audio.transcriptions.create(model="whisper-1", file=Path(__file__).parent / MP3_FILENAME,
																prompt=transcription[-WHISPER_CONTEXT_LENGTH:], temperature=WHISPER_TEMP) 
																# [-x:] gets last x characters of string
	transcription += " " # add a space for readability
	transcription += current_transcription
	print(transcription)

# stop recording
stream.stop_stream()
stream.close()
audio.terminate()