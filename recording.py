import pyaudio
import logging
import pydub
import wave

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
	
# recording configuration
DEVICE = 0
FORMAT = pyaudio.paInt32
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 5
OUTPUT_FILENAME = "recording.wav"
MP3_FILENAME = "recording.mp3"

# recording audio
logging.info("7. recording started")
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

# generate .wav file
with wave.open(OUTPUT_FILENAME, 'wb') as wf:
	wf.setnchannels(CHANNELS)
	wf.setsampwidth(audio.get_sample_size(FORMAT))
	wf.setframerate(RATE)
	wf.writeframes(b''.join(frames))

# convert .wav to .mp3
mp3 =  pydub.AudioSegment.from_wav(OUTPUT_FILENAME)
mp3.export(MP3_FILENAME, format="mp3")