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
import threading
import queue
import select
import sys
import os
import re

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
        self.initialize_websocket()
        
        # Buffer for accumulating text from LLM
        self.text_buffer = ""
        self.min_chars_to_process = 50  # Minimum characters to process at once
        self.sentence_ending_chars = ['.', '!', '?', ':', ';', '\n']
        
        # Pause/resume state
        self.paused = False
        self.audio_queue = queue.Queue()
        self.audio_thread = None
        self.playback_thread = None
        self.stop_threads = False
        
        print("LLM to TTS streaming system ready!")
    
    def initialize_websocket(self):
        """Initialize or reinitialize the WebSocket connection."""
        # Close existing connection if it exists
        if hasattr(self, 'ws'):
            try:
                self.ws.close()
            except:
                pass
                
        # Create a new WebSocket connection
        self.ws = self.client.tts.websocket()
    
    def contains_speakable_content(self, text):
        """Check if the text contains any speakable content (not just whitespace or punctuation)."""
        # Remove all whitespace and punctuation
        stripped_text = re.sub(r'[\s\.,!?;:"\'-]+', '', text)
        return len(stripped_text) > 0
    
    def process_text_to_speech(self, text):
        """Process the given text through TTS and play it."""
        # Skip empty or punctuation-only texts
        if not text or not self.contains_speakable_content(text):
            print("Skipping empty or punctuation-only text")
            return
            
        try:
            # Generate audio data using the websocket
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
                # Add audio data to the queue for the playback thread
                self.audio_queue.put(output.audio)
        except Exception as e:
            print(f"Error generating audio: {e}")
            
            # Try to reinitialize the WebSocket connection
            print("Reinitializing WebSocket connection...")
            self.initialize_websocket()
    
    def start_playback_thread(self):
        """Start a thread to handle audio playback with pause/resume capability."""
        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.stop_threads = False
            self.playback_thread = threading.Thread(target=self._playback_worker)
            self.playback_thread.daemon = True
            self.playback_thread.start()
    
    def _playback_worker(self):
        """Worker thread function for audio playback."""
        # Buffer to collect initial frames
        initial_frames = []
        collected_enough = False
        min_initial_frames = 3  # Collect at least this many frames before starting playback
        
        while not self.stop_threads:
            try:
                # Only process audio when not paused
                if not self.paused:
                    # Try to get an audio frame from the queue with a short timeout
                    try:
                        buffer = self.audio_queue.get(timeout=0.1)
                        
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
                            
                        self.audio_queue.task_done()
                    except queue.Empty:
                        # No audio data available, just continue
                        pass
                else:
                    # When paused, just sleep a bit to avoid busy waiting
                    time.sleep(0.1)
            except Exception as e:
                print(f"Error in playback worker: {e}")
    
    def _input_monitor(self):
        """Monitor for Enter key presses to toggle pause/resume."""
        while not self.stop_threads:
            # Use select to check if input is available (non-blocking)
            if select.select([sys.stdin], [], [], 0.1)[0]:
                # Read the input (Enter key)
                line = sys.stdin.readline().strip()
                
                # Toggle pause state
                self.paused = not self.paused
                
                if self.paused:
                    print("\n[Paused] Press Enter to resume...")
                else:
                    print("\n[Resumed]")
    
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
        print("[Press Enter during playback to pause/resume]")
        
        # Start the playback thread
        self.start_playback_thread()
        
        # Start the input monitor thread
        self.input_thread = threading.Thread(target=self._input_monitor)
        self.input_thread.daemon = True
        self.input_thread.start()
        
        # Prepare messages for LLM
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Reset text buffer
        self.text_buffer = ""
        
        try:
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
                        if text_to_process and self.contains_speakable_content(text_to_process):
                            self.process_text_to_speech(text_to_process)
                        
                        # Keep the remainder in the buffer
                        self.text_buffer = self.text_buffer[last_idx + 1:].strip()
                    else:
                        # If no sentence boundary found but buffer is large, process it anyway
                        if len(self.text_buffer) > self.min_chars_to_process * 2:
                            text_to_process = self.text_buffer.strip()
                            if text_to_process and self.contains_speakable_content(text_to_process):
                                self.process_text_to_speech(text_to_process)
                            self.text_buffer = ""
            
            # Process any remaining text in the buffer
            if self.text_buffer.strip() and self.contains_speakable_content(self.text_buffer.strip()):
                self.process_text_to_speech(self.text_buffer.strip())
            self.text_buffer = ""
            
        except Exception as e:
            print(f"Error during LLM streaming: {e}")
        
        try:
            # Wait for all audio to be processed (with timeout)
            self.audio_queue.join()
        except Exception as e:
            print(f"Error waiting for audio queue: {e}")
        
        # Stop the monitoring threads
        self.stop_threads = True
        if self.input_thread.is_alive():
            self.input_thread.join(timeout=1.0)
        if self.playback_thread.is_alive():
            self.playback_thread.join(timeout=1.0)
    
    def cleanup(self):
        """Clean up resources."""
        print("Cleaning up resources...")
        self.stop_threads = True
        
        # Clear any remaining items in the queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except queue.Empty:
                break
        
        # Stop and close audio stream
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        
        # Close WebSocket connection
        try:
            self.ws.close()
        except Exception as e:
            print(f"Error closing WebSocket: {e}")
            
        print("Done!")

def main():
    # Set terminal to nonblocking mode for Unix systems
    if sys.platform != 'win32':
        import termios
        import tty
        # Save the terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            # Example usage
            llm_tts = LLMToTTS()
            
            try:
                while True:
                    # Reset terminal for input
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    
                    # Get user input
                    user_prompt = input("\nEnter your prompt (or type 'exit' to quit): ")
                    
                    if user_prompt.lower() == 'exit':
                        break
                        
                    if user_prompt.strip():
                        # Set terminal to cbreak mode for non-blocking input during TTS
                        tty.setcbreak(fd)
                        
                        # Optional system prompt to customize LLM behavior
                        system_prompt = "You are a helpful assistant. Keep your responses concise and informative."
                        
                        # Stream the LLM response to TTS
                        llm_tts.stream_llm_to_tts(user_prompt, system_prompt)
            
            except KeyboardInterrupt:
                print("\nInterrupted by user")
            
            finally:
                # Clean up resources
                llm_tts.cleanup()
        finally:
            # Restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    else:
        # Windows implementation (simpler but may not handle pause/resume as smoothly)
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
