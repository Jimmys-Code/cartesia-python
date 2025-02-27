from cartesia import Cartesia
from cartesia.tts import TtsRequestEmbeddingSpecifierParams, OutputFormat_RawParams
import pyaudio
import os
import time
import numpy as np

def initialize_tts():
    """Initialize all the components needed for TTS."""
    print("Initializing TTS system...")
    
    # Initialize Cartesia client
    client = Cartesia(
        api_key="sk_car_GZrgghX4KvqNrc41q7KoB"
    )
    
    # Voice and model configuration
    voice_id = "043cfc81-d69f-4bee-ae1e-7862cb358650"
    model_id = "sonic"  # You can check out models at https://docs.cartesia.ai/getting-started/available-models
    
    # Initialize PyAudio
    p = pyaudio.PyAudio()
    rate = 22050
    
    # Pre-initialize the audio stream to eliminate initial jitter
    # Create a silent stream that's ready to go
    stream = p.open(
        format=pyaudio.paFloat32,
        channels=1,
        rate=rate,
        output=True,
        frames_per_buffer=1024  # Smaller buffer size for lower latency
    )
    
    # Play a tiny bit of silence to "warm up" the audio system
    silence = np.zeros(512, dtype=np.float32)
    stream.write(silence.tobytes())
    
    # Set up the websocket connection
    print("Establishing WebSocket connection...")
    ws = client.tts.websocket()
    
    print("TTS system ready!")
    return client, ws, p, stream, voice_id, model_id, rate

def process_text_to_speech(ws, p, stream, voice_id, model_id, rate, text):
    """Process the given text through TTS and play it."""
    # Buffer to collect initial frames
    initial_frames = []
    collected_enough = False
    min_initial_frames = 3  # Collect at least this many frames before starting playback
    
    # Generate and stream audio using the websocket
    for output in ws.send(
        model_id=model_id,
        transcript=text,
        voice={"id": voice_id},
        stream=True,
        output_format={
            "container": "raw",
            "encoding": "pcm_f32le", 
            "sample_rate": rate
        },
    ):
        buffer = output.audio
        
        if not collected_enough:
            # Collect initial frames to reduce jitter
            initial_frames.append(buffer)
            if len(initial_frames) >= min_initial_frames:
                collected_enough = True
                # Play all initial frames at once
                for frame in initial_frames:
                    stream.write(frame)
        else:
            # Continue with regular streaming
            stream.write(buffer)
    
    # No need to close the stream as we're keeping it open for the next utterance

def main():
    # Initialize everything first
    client, ws, p, stream, voice_id, model_id, rate = initialize_tts()
    
    try:
        # Main interaction loop
        while True:
            # Get user input
            # user_text = input("\nEnter text to speak (or type 'exit' to quit): ")
            
            # if user_text.lower() == 'exit':
            #     break
                
            # if user_text.strip():
            print("Speaking...")
            # Process the text immediately
            process_text_to_speech(ws, p, stream, voice_id, model_id, rate, 'testing 1 2 3')
            print("Done speaking.") 
            process_text_to_speech(ws, p, stream, voice_id, model_id, rate, 'testing 1 2 3')
            print("Done speaking. 2")
            process_text_to_speech(ws, p, stream, voice_id, model_id, rate, 'testing 1 2 3')

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    finally:
        # Clean up resources
        print("\nCleaning up resources...")
        stream.stop_stream()
        stream.close()
        p.terminate()
        ws.close()
        print("Done!")

if __name__ == "__main__":
    main()
