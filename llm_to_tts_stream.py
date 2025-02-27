"""
LLM Text to Speech Streaming

This module connects Ollama's LLM streaming responses to Cartesia's TTS service
to create real-time text-to-speech audio from LLM outputs.
"""

import time
import numpy as np
import pyaudio
from cartesia import Cartesia
import ollama_api

class LLMToTTS:
    def __init__(self, api_key="sk_car_GZrgghX4KvqNrc41q7KoB", voice_id="043cfc81-d69f-4bee-ae1e-7862cb358650"):
        """Initialize the LLM to TTS streaming system.
        
        Args:
            api_key: The Cartesia API key
            voice_id: The ID of the voice to use for TTS
        """
        print("Initializing LLM to TTS streaming system...")
        
        # Initialize Cartesia client
        self.client = Cartesia(api_key=api_key)
        
        # Voice and model configuration
        self.voice_id = voice_id
        self.model_id = "sonic"  # TTS model ID
        self.llm_model = ollama_api.llm  # LLM model from ollama_api
        
        # Initialize PyAudio
        self.p = pyaudio.PyAudio()
        self.rate = 22050
        
        # Create an audio stream
        self.stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.rate,
            output=True,
            frames_per_buffer=1024  # Smaller buffer size for lower latency
        )
        
        # Play a tiny bit of silence to "warm up" the audio system
        silence = np.zeros(512, dtype=np.float32)
        self.stream.write(silence.tobytes())
        
        # Set up the websocket connection for TTS
        print("Establishing WebSocket connection...")
        self.ws = self.client.tts.websocket()
        
        # Buffer for accumulating text from LLM
        self.text_buffer = ""
        self.min_chars_to_process = 50  # Minimum characters to process at once
        self.sentence_ending_chars = ['.', '!', '?', ':', ';', '\n']
        
        print("LLM to TTS streaming system ready!")
    
    def process_text_to_speech(self, text):
        """Process the given text through TTS and play it."""
        # Buffer to collect initial frames
        initial_frames = []
        collected_enough = False
        min_initial_frames = 3  # Collect at least this many frames before starting playback
        
        # Generate and stream audio using the websocket
        for output in self.ws.send(
            model_id=self.model_id,
            transcript=text,
            voice={"id": self.voice_id},
            stream=True,
            output_format={
                "container": "raw",
                "encoding": "pcm_f32le", 
                "sample_rate": self.rate
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
                        self.stream.write(frame)
            else:
                # Continue with regular streaming
                self.stream.write(buffer)
    
    def _should_process_buffer(self):
        """Determine if we should process the text buffer based on size or sentence endings."""
        if len(self.text_buffer) > self.min_chars_to_process:
            # Check if the buffer ends with a sentence ending character
            for char in self.sentence_ending_chars:
                if char in self.text_buffer:
                    return True
            
            # If the buffer is significantly larger than min_chars_to_process, process it anyway
            if len(self.text_buffer) > self.min_chars_to_process * 2:
                return True
        
        return False
    
    def stream_llm_to_tts(self, prompt, system_prompt=None):
        """Stream LLM responses to TTS in real-time.
        
        Args:
            prompt: The user prompt to send to the LLM
            system_prompt: Optional system prompt to set LLM behavior
        """
        print("Streaming LLM response to TTS...")
        
        # Prepare messages for LLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Reset text buffer
        self.text_buffer = ""
        
        # Get streaming response from LLM
        stream_response = ollama_api.get_ollama_api(messages, stream=True, model=self.llm_model)
        
        # Process the streaming response
        for chunk in stream_response:
            # Add chunk to buffer
            self.text_buffer += chunk
            
            # Check if we should process the buffer
            if self._should_process_buffer():
                # Find the last sentence boundary
                last_idx = -1
                for char in self.sentence_ending_chars:
                    idx = self.text_buffer.rfind(char)
                    if idx > last_idx:
                        last_idx = idx
                
                if last_idx >= 0:
                    # Process the complete sentence(s)
                    text_to_process = self.text_buffer[:last_idx + 1].strip()
                    if text_to_process:
                        self.process_text_to_speech(text_to_process)
                    
                    # Keep the remainder in the buffer
                    self.text_buffer = self.text_buffer[last_idx + 1:].strip()
                else:
                    # If no sentence boundary found but buffer is large, process it anyway
                    if len(self.text_buffer) > self.min_chars_to_process * 2:
                        text_to_process = self.text_buffer.strip()
                        self.process_text_to_speech(text_to_process)
                        self.text_buffer = ""
        
        # Process any remaining text in the buffer
        if self.text_buffer.strip():
            self.process_text_to_speech(self.text_buffer.strip())
            self.text_buffer = ""
    
    def cleanup(self):
        """Clean up resources."""
        print("Cleaning up resources...")
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        self.ws.close()
        print("Done!")

def main():
    # Example usage
    llm_tts = LLMToTTS()
    
    try:
        while True:
            # Get user input
            user_prompt = input("\nEnter your prompt (or type 'exit' to quit): ")
            
            if user_prompt.lower() == 'exit':
                break
                
            if user_prompt.strip():
                # Optional system prompt to customize LLM behavior
                system_prompt = "You are a helpful assistant. Keep your responses concise and informative."
                
                # Stream the LLM response to TTS
                llm_tts.stream_llm_to_tts(user_prompt, system_prompt)
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    finally:
        # Clean up resources
        llm_tts.cleanup()

if __name__ == "__main__":
    main()
