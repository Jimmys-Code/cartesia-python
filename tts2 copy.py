import os
import time
import numpy as np
import pyaudio
import threading
import queue
import uuid
import signal

from cartesia import Cartesia
from cartesia.tts.requests.output_format import OutputFormat_RawParams

class TtsManager:
    def __init__(self):
        self.client = None
        self.ws = None
        self.p = None
        self.stream = None
        self.voice_id = None
        self.model_id = None
        self.rate = None
        
        # For managing speech and interruption
        self.text_queue = queue.Queue()
        self.interrupt_event = threading.Event()
        self.new_text_ready = threading.Event()
        self.current_context_id = None
        self.next_text = None
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.ws_lock = threading.Lock()  # Lock for WebSocket operations
        
        # Initialize components
        self.initialize_tts()
        
    def initialize_tts(self):
        """Initialize all the components needed for TTS."""
        print("Initializing TTS system...")
        
        # Initialize Cartesia client
        self.client = Cartesia(
            api_key="sk_car_GZrgghX4KvqNrc41q7KoB"
        )
        
        # Voice and model configuration
        self.voice_id = "043cfc81-d69f-4bee-ae1e-7862cb358650"
        self.model_id = "sonic"
        
        # Initialize PyAudio
        self.p = pyaudio.PyAudio()
        self.rate = 22050
        
        # Initialize silence buffer for smooth transitions
        self.silence_buffer = np.zeros(1024, dtype=np.float32).tobytes()
        
        # Create a higher quality audio stream with larger buffer
        self.stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.rate,
            output=True,
            frames_per_buffer=4096,  # Larger buffer for smoother playback
            start=False  # Don't start yet
        )
        
        # Start the stream
        self.stream.start_stream()
        
        # "Warm up" the audio system with silence
        for _ in range(3):
            self.stream.write(self.silence_buffer)
        
        # Set up a single WebSocket connection
        print("Establishing WebSocket connection...")
        with self.ws_lock:
            self.ws = self.client.tts.websocket()
            # Send a dummy request to fully initialize the connection
            self._send_dummy_request()
        
        # Start worker thread
        self.worker_thread = threading.Thread(
            target=self.tts_worker,
            daemon=True
        )
        self.worker_thread.start()
        
        print("TTS system ready!")
    
    def _send_dummy_request(self):
        """Send a silent dummy request to warm up the TTS system."""
        try:
            dummy_text = "."  # Just a period, almost silent
            context_id = str(uuid.uuid4())
            
            # Collect and discard the output
            for chunk in self.ws.send(
                model_id=self.model_id,
                transcript=dummy_text,
                voice={"mode": "id", "id": self.voice_id},
                context_id=context_id,
                output_format={
                    "container": "raw",
                    "encoding": "pcm_f32le", 
                    "sample_rate": self.rate
                },
                stream=False  # Get it all at once
            ):
                pass  # Discard the audio
        except Exception as e:
            print(f"Dummy request error (non-critical): {e}")
    
    def _ensure_valid_websocket(self):
        """Ensure we have a valid WebSocket connection."""
        with self.ws_lock:
            if self.ws is None:
                print("Reconnecting WebSocket...")
                self.ws = self.client.tts.websocket()
                self._send_dummy_request()
    
    def speak(self, text):
        """Queue text to be spoken."""
        # Set the next text and signal the worker
        self.next_text = text
        self.new_text_ready.set()
        
    def interrupt_and_speak(self, text):
        """Stop current speech and speak this text instead."""
        print("Interrupting current speech...")
        # Set the next text
        self.next_text = text
        # Signal interruption
        self.interrupt_event.set()
        # Signal new text is ready
        self.new_text_ready.set()
        
    def tts_worker(self):
        """Background worker that processes text."""
        while not self.stop_event.is_set():
            # Wait for new text to be ready
            if not self.new_text_ready.wait(timeout=0.2):
                continue
                
            # Get the text and reset the event
            text = self.next_text
            self.new_text_ready.clear()
            
            # Ensure valid WebSocket
            self._ensure_valid_websocket()
            
            # Create a new context ID
            context_id = str(uuid.uuid4())
            self.current_context_id = context_id
            
            # Use a separate thread for streaming to allow interruptions
            stream_thread = threading.Thread(
                target=self.stream_audio,
                args=(text, context_id),
                daemon=True
            )
            stream_thread.start()
            
            # Wait for either:
            # 1. The streaming thread to complete
            # 2. An interruption to be requested
            while stream_thread.is_alive() and not self.interrupt_event.is_set() and not self.stop_event.is_set():
                time.sleep(0.1)
                
            # If we got interrupted, clean up the current context
            if self.interrupt_event.is_set():
                print(f"Interrupt detected, closing context {context_id}")
                try:
                    with self.ws_lock:
                        if self.ws:
                            # Close the current WebSocket connection
                            old_ws = self.ws
                            self.ws = None
                            
                            # Close old connection in background
                            def close_old_ws(ws):
                                try:
                                    ws.close()
                                except:
                                    pass
                            
                            threading.Thread(target=close_old_ws, args=(old_ws,), daemon=True).start()
                except Exception as e:
                    print(f"Error during interruption: {e}")
                    
                # Reset the interrupt event
                self.interrupt_event.clear()
                
                # Add a small amount of silence for smooth transition
                self.stream.write(self.silence_buffer)
    
    def stream_audio(self, text, context_id):
        """Stream audio for a given text and context."""
        try:
            # Buffer for collecting initial frames - larger buffer for smoother start
            initial_frames = []
            collected_enough = False
            min_initial_frames = 5  # Increased buffer size
            
            # Play a small silence before starting to help with smooth transition
            self.stream.write(self.silence_buffer)
            
            with self.ws_lock:
                if self.ws is None or self.interrupt_event.is_set():
                    return
                
                # Generate and stream audio
                for chunk in self.ws.send(
                    model_id=self.model_id,
                    transcript=text,
                    voice={"mode": "id", "id": self.voice_id},
                    context_id=context_id,
                    output_format={
                        "container": "raw",
                        "encoding": "pcm_f32le", 
                        "sample_rate": self.rate
                    },
                ):
                    # Check for interruption before playing each chunk
                    if self.interrupt_event.is_set() or self.stop_event.is_set():
                        print("Interruption detected during streaming")
                        return
                    
                    # Process the audio chunk
                    if chunk.audio:
                        if not collected_enough:
                            # Collect initial frames
                            initial_frames.append(chunk.audio)
                            if len(initial_frames) >= min_initial_frames:
                                collected_enough = True
                                # Play all initial frames at once for smooth start
                                combined_audio = b''.join(initial_frames)
                                self.stream.write(combined_audio)
                        else:
                            # Play the audio chunk directly
                            self.stream.write(chunk.audio)
            
            print(f"Finished speaking text with context {context_id}")
            
            # Add a small amount of silence at the end for smoother transitions
            self.stream.write(self.silence_buffer)
                
        except Exception as e:
            print(f"Error during speech generation: {e}")
    
    def shutdown(self):
        """Clean up resources."""
        self.stop_event.set()
        self.interrupt_event.set()  # Set this to interrupt any ongoing speech
        
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
            
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            
        if self.p:
            self.p.terminate()
            
        with self.ws_lock:
            if self.ws:
                self.ws.close()
                self.ws = None
            
        print("TTS system shut down.")

def signal_handler(sig, frame):
    print("\nInterrupted by CTRL+C")
    raise KeyboardInterrupt

def main():
    # Set up signal handler for keyboard interrupt
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create TTS Manager
    tts = TtsManager()
    
    try:
        # Demo regular speaking
        print("Speaking first sentence...")
        tts.speak("Hello, I am speaking in a background thread. This sentence is quite long so you have time to see that it's working correctly.")
        time.sleep(2)
        
        # Demo interruption
        print("Interrupting and speaking new text in 1 second...")
        time.sleep(1)
        tts.interrupt_and_speak("I've interrupted the previous speech to say something new and important.")
        time.sleep(3)
        
        # Demo speaking after interruption
        print("Speaking after interruption...")
        tts.speak("And now I'm speaking normally again after the interruption.")
        time.sleep(3)
        
        # Interactive demo with a separate thread for handling input
        def input_handler():
            print("\nInteractive demo")
            print("Speaking long text - press Enter at any time to interrupt")
            input()  # Wait for Enter key
            tts.interrupt_and_speak("You interrupted me by pressing Enter! This interruption should happen immediately without any audio jitter.")
            
            # Wait a bit then prompt for another test
            time.sleep(4)
            print("\nOne more test - speaking again. Press Enter to interrupt")
            input()
            tts.interrupt_and_speak("That's another successful interruption! The demo is complete.")
        
        # Start input handler thread
        input_thread = threading.Thread(target=input_handler, daemon=True)
        input_thread.start()
        
        # Start speaking long text for the demo
        tts.speak("This is a very long sentence that I'm going to keep speaking for a while so that you have time to interrupt me. I'll keep talking and talking because that's what I do. I can talk all day about various things like the weather, technology, books, movies, or anything else that comes to mind. The key point is that you should be able to interrupt me at any point during this long monologue without any audio jitter or choppiness. Just press Enter when you want to interrupt me, and I'll immediately stop talking and say something else instead. This demonstrates the smooth real-time interruption capability.")
        
        # Wait for the input thread to finish
        input_thread.join()
        
        # Wait a bit before shutting down
        time.sleep(2)
        print("\nDemo complete!")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Clean up resources
        tts.shutdown()

if __name__ == "__main__":
    main()