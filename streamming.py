from cartesia import Cartesia
from cartesia.tts import Controls, OutputFormat_RawParams, TtsRequestIdSpecifierParams
import os
import sounddevice as sd
import numpy as np
import base64

def get_tts_chunks():
    client = Cartesia(
        api_key="sk_car_GZrgghX4KvqNrc41q7KoB"
    )
    response = client.tts.sse(
        model_id="sonic",
        transcript="Hello world! This is a test of the Cartesia text to speech system.",
        voice={
            "id": "f9836c6e-a0bd-460e-9d3c-f7299fa60f94",
            "experimental_controls": {
                "speed": "normal",
                "emotion": [],
            },
        },
        language="en",
        output_format={
            "container": "raw",
            "encoding": "pcm_f32le",
            "sample_rate": 44100,
        },
    )
    
    audio_chunks = []
    for chunk in response:
        audio_chunks.append(chunk)
    return audio_chunks

# Main script
chunks = get_tts_chunks()
print(f"Received {len(chunks)} chunks")

# Collect all audio data
audio_data_bytes = []

for i, chunk in enumerate(chunks):
    print(f"Processing chunk {i+1}/{len(chunks)}")
    
    if hasattr(chunk, 'data') and isinstance(chunk.data, str):
        try:
            # Try to decode base64
            decoded_data = base64.b64decode(chunk.data)
            audio_data_bytes.append(decoded_data)
            print(f"  Successfully decoded chunk {i+1} ({len(decoded_data)} bytes)")
        except Exception as e:
            print(f"  Error decoding chunk {i+1}: {e}")

if audio_data_bytes:
    # Concatenate all raw bytes
    all_bytes = b''.join(audio_data_bytes)
    print(f"Total bytes: {len(all_bytes)}")
    
    # Convert to float32 array (as specified in the API request)
    audio_float32 = np.frombuffer(all_bytes, dtype=np.float32)
    print(f"Total samples: {len(audio_float32)}")
    
    # Check the range of values
    min_val = np.min(audio_float32)
    max_val = np.max(audio_float32)
    print(f"Value range: Min={min_val}, Max={max_val}")
    
    # Normalize audio if the values are way out of range
    if min_val < -1.0 or max_val > 1.0:
        abs_max = max(abs(min_val), abs(max_val))
        if abs_max > 0:
            print(f"Normalizing audio (dividing by {abs_max})")
            audio_float32 = audio_float32 / abs_max
    
    # Play the audio
    sample_rate = 44100  # Same as specified in the request
    print("Playing audio...")
    
    # Ensure audio is not too loud
    sd.play(audio_float32, sample_rate)
    sd.wait()  # Wait until audio is finished playing
    print("Audio playback completed.")
else:
    print("No valid audio data found in chunks")