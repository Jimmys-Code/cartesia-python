#!/usr/bin/env python
from cartesia import Cartesia
from cartesia.tts import Controls, OutputFormat_RawParams, TtsRequestIdSpecifierParams
import os
import sounddevice as sd
import numpy as np
import base64
import time

def play_audio(audio_bytes):
    """Convert audio bytes to numpy array and play using sounddevice"""
    if not audio_bytes:
        print("No audio data to play")
        return
    
    # Convert to float32 array
    audio_float32 = np.frombuffer(audio_bytes, dtype=np.float32)
    
    # Check the range of values and normalize if needed
    min_val = np.min(audio_float32)
    max_val = np.max(audio_float32)
    
    if min_val < -1.0 or max_val > 1.0:
        abs_max = max(abs(min_val), abs(max_val))
        if abs_max > 0:
            audio_float32 = audio_float32 / abs_max
    
    # Play the audio
    sample_rate = 44100
    sd.play(audio_float32, sample_rate)
    sd.wait()  # Wait until audio is finished playing

def text_to_speech(client, text):
    """Convert text to speech and return audio bytes"""
    response = client.tts.sse(
        model_id="sonic",
        transcript=text,
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
    
    # Collect and decode audio chunks
    audio_data_bytes = []
    for chunk in response:
        if hasattr(chunk, 'data') and isinstance(chunk.data, str):
            try:
                decoded_data = base64.b64decode(chunk.data)
                audio_data_bytes.append(decoded_data)
            except Exception as e:
                print(f"Error decoding chunk: {e}")
    
    # Concatenate all raw bytes
    return b''.join(audio_data_bytes) if audio_data_bytes else None

def main():
    print("Initializing Cartesia TTS system...")
    
    # Initialize the client (only do this once)
    client = Cartesia(
        api_key="sk_car_GZrgghX4KvqNrc41q7KoB"
    )
    
    # Test the connection with a quick hello
    print("Testing connection with a simple greeting...")
    audio_bytes = text_to_speech(client, "System ready")
    play_audio(audio_bytes)
    
    print("\nSetup complete! The TTS system is ready for input.")
    print("Type your text and press Enter to hear it spoken (or type 'exit' to quit):")
    
    while True:
        user_input = input("> ")
        
        if user_input.lower() in ('exit', 'quit'):
            print("Exiting program. Goodbye!")
            break
        
        if user_input.strip():
            start_time = time.time()
            audio_bytes = text_to_speech(client, user_input)
            processing_time = time.time() - start_time
            print(f"Processing time: {processing_time:.2f} seconds")
            
            if audio_bytes:
                play_audio(audio_bytes)
            else:
                print("Failed to generate audio")

if __name__ == "__main__":
    main()
