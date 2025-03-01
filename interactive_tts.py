import os
import time
import numpy as np
import pyaudio
import threading
import queue
import uuid

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
        self.current_context_id = None
        self.context_lock = threading.Lock()  # To safely update current_context
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.is_speaking = threading.Event()
        
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
        
        # Pre-initialize the audio stream to eliminate initial jitter
        self.stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.rate,
            output=True,
            frames_per_buffer=1024
        )
        
        # "Warm up" the audio system
        silence = np.zeros(512, dtype=np.float32)
        self.stream.write(silence.tobytes())
        
        # Set up a single WebSocket connection
        print("Establishing WebSocket connection...")
        self.ws = self.client.tts.websocket()
        
        # Start worker thread
        self.worker_thread = threading.Thread(
            target=self.tts_worker,
            daemon=True
        )
        self.worker_thread.start()
        
        print("TTS system ready!")
    
    def speak(self, text):
        """Queue text to be spoken."""
        self.text_queue.put((text, None))  # None means create a new context
        
    def interrupt_and_speak(self, text):
        """Stop current speech and speak this text instead."""
        # Cancel current context if there is one
        with self.context_lock:
            if self.current_context_id and self.current_context_id in self.ws._contexts:
                try:
                    # Directly remove the context using the internal method
                    self.ws._remove_context(self.current_context_id)
                    print(f"Cancelled context {self.current_context_id}")
                except Exception as e:
                    print(f"Error cancelling context: {e}")
        
        # Clear the queue
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                break
        
        # Add new text to queue with explicit instruction to create new context
        self.text_queue.put((text, "new_context"))
        
    def tts_worker(self):
        """Background worker that processes text from the queue."""
        min_initial_frames = 3
        
        while not self.stop_event.is_set():
            try:
                # Wait for text in queue with timeout to allow checking stop_event
                try:
                    text, context_action = self.text_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                try:
                    # Create a new context if needed
                    new_context_id = None
                    if context_action == "new_context" or self.current_context_id is None:
                        new_context_id = str(uuid.uuid4())
                    else:
                        new_context_id = self.current_context_id
                    
                    # Update current context ID
                    with self.context_lock:
                        self.current_context_id = new_context_id
                    
                    print(f"Using context: {new_context_id}")
                    
                    # Collect initial frames to avoid "startup" jitter
                    initial_frames = []
                    collected_enough = False
                    self.is_speaking.set()
                    
                    # Generate and stream audio
                    for chunk in self.ws.send(
                        model_id=self.model_id,
                        transcript=text,
                        voice={"mode": "id", "id": self.voice_id},
                        context_id=new_context_id,
                        output_format={
                            "container": "raw",
                            "encoding": "pcm_f32le", 
                            "sample_rate": self.rate
                        },
                    ):
                        if not collected_enough:
                            initial_frames.append(chunk.audio)
                            if len(initial_frames) >= min_initial_frames:
                                collected_enough = True
                                # Play all initial frames at once
                                for frame in initial_frames:
                                    self.stream.write(frame)
                        else:
                            self.stream.write(chunk.audio)
                except Exception as e:
                    print(f"Error during speech generation: {e}")
                
                self.is_speaking.clear()
                self.text_queue.task_done()
                
            except Exception as e:
                print(f"Unexpected error in TTS worker: {e}")
    
    def shutdown(self):
        """Clean up resources."""
        self.stop_event.set()
        
        # Clear the queue and add sentinel to ensure worker exits
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                break
        
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
            
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            
        if self.p:
            self.p.terminate()
            
        if self.ws:
            self.ws.close()
            
        print("TTS system shut down.")

def main():
    # Create TTS Manager
    tts = TtsManager()
    
    try:
        # Demo regular speaking
        print("Speaking first sentence...")
        
        input(">")
        tts.speak("Hello, I am speaking in a background thread.")
        time.sleep(1)

        
        # Demo regular queuing
        print("Queuing second sentence...")
        tts.speak("Here is the second sentence to add to the stream.")
        tts.speak(" This is a very long sentence that will be interrupted. ")
        
        
        # Demo interruption
        print("Interrupting and speaking new text...")
        tts.interrupt_and_speak("I've interrupted the previous speech to say something new and important.")
        time.sleep(4)
        
        # Demo speaking after interruption
        print("Speaking after interruption...")
        tts.speak("And now I'm speaking normally again after the interruption.")
        time.sleep(4)
        
        # Interactive demo
        print("\nInteractive demo - Press Enter to continue")
        input()
        
        print("1. Speaking long text - type anything and press Enter to interrupt")
        tts.speak("This is a very long sentence that I'm going to keep speaking for a while so that you have time to interrupt me. I'll keep talking and talking because that's what I do. I can talk all day about various things like the weather, technology, books, movies, or anything else that comes to mind.")
        
        # Wait for user input to interrupt
        user_input = input()
        tts.interrupt_and_speak(f"You interrupted me to say: {user_input}")
        time.sleep(3)
        
        print("Demo complete!")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Clean up resources
        tts.shutdown()

if __name__ == "__main__":
    main()