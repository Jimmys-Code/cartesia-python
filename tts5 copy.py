import os
import time
import numpy as np
import pyaudio
import threading
import queue
import uuid
import json

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
        self.active_contexts = set()  # Keep track of all active contexts
        self.context_lock = threading.Lock()  # To safely update current_context
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.is_speaking = threading.Event()
        
        # Performance optimization
        self.min_initial_frames = 1  # Reduce initial buffering for faster start
        
        # Latency tracking
        self.last_latency = 0
        
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
            frames_per_buffer=512  # Smaller buffer for lower latency
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
        self.text_queue.put((text, None, time.time(), 1))  # Normal priority
        
    def interrupt_and_speak(self, text):
        """Stop current speech and speak this text instead with minimal latency."""
        request_time = time.time()
        
        # Generate a new context ID for the new speech
        new_context_id = str(uuid.uuid4())
        
        # Cancel all active contexts immediately
        self._cancel_active_contexts()
        
        # Clear the queue
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                break
        
        # Queue the new text with highest priority
        self.text_queue.put((text, new_context_id, request_time, 10))  # Priority 10
        
    def _cancel_active_contexts(self):
        """Cancel all active contexts to ensure clean interruption"""
        with self.context_lock:
            # Make a copy to avoid modifying during iteration
            contexts_to_cancel = self.active_contexts.copy()
            
            for ctx_id in contexts_to_cancel:
                if ctx_id:
                    try:
                        # Send explicit cancellation request to the server
                        cancel_request = {
                            "context_id": ctx_id,
                            "cancel": True
                        }
                        try:
                            self.ws.websocket.send(json.dumps(cancel_request))
                            print(f"Sent cancellation request for context {ctx_id}")
                        except Exception as e:
                            print(f"Error sending cancellation request: {e}")
                        
                        # Remove from client tracking
                        if ctx_id in self.ws._contexts:
                            self.ws._remove_context(ctx_id)
                            print(f"Removed context {ctx_id} from client tracking")
                    except Exception as e:
                        print(f"Error cancelling context {ctx_id}: {e}")
            
            # Clear the active contexts set
            self.active_contexts.clear()
            self.current_context_id = None
        
    def tts_worker(self):
        """Background worker that processes text from the queue."""
        while not self.stop_event.is_set():
            try:
                # Get highest priority item from queue with timeout
                highest_priority_item = None
                highest_priority = -1
                
                # Check if there's anything in the queue
                if self.text_queue.empty():
                    time.sleep(0.01)  # Sleep briefly to avoid tight loop
                    continue
                
                # Look at all items in queue to find highest priority
                queue_items = []
                while not self.text_queue.empty():
                    try:
                        item = self.text_queue.get_nowait()
                        queue_items.append(item)
                        text, context_id, request_time, priority = item
                        
                        if priority > highest_priority:
                            highest_priority = priority
                            highest_priority_item = item
                    except queue.Empty:
                        break
                
                # Put all items except highest priority back in queue
                for item in queue_items:
                    if item != highest_priority_item:
                        self.text_queue.put(item)
                
                # Process the highest priority item
                if highest_priority_item:
                    text, context_id, request_time, priority = highest_priority_item
                    
                    # Process the item
                    try:
                        # Use the specified context ID or create a new one
                        new_context_id = context_id if context_id else str(uuid.uuid4())
                        
                        # Update current context ID
                        with self.context_lock:
                            self.current_context_id = new_context_id
                            self.active_contexts.add(new_context_id)
                        
                        print(f"Using context: {new_context_id}")
                        
                        # OPTIMIZATION: Prepare for immediate playback
                        initial_frames = []
                        collected_frames = 0
                        first_audio_time = None
                        start_time = time.time()
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
                            # Track when we get the first audio
                            if first_audio_time is None:
                                first_audio_time = time.time()
                                latency = first_audio_time - request_time
                                self.last_latency = latency
                                print(f"Latency: {latency:.3f}s")
                            
                            if collected_frames < self.min_initial_frames:
                                initial_frames.append(chunk.audio)
                                collected_frames += 1
                                
                                if collected_frames >= self.min_initial_frames:
                                    # Play all collected frames at once
                                    buffer = b''.join(initial_frames)
                                    self.stream.write(buffer)
                            else:
                                self.stream.write(chunk.audio)
                                
                        # Remove context from active contexts when done
                        with self.context_lock:
                            if new_context_id in self.active_contexts:
                                self.active_contexts.remove(new_context_id)
                                
                    except Exception as e:
                        print(f"Error during speech generation: {e}")
                        # If the context failed, clean it up from active contexts
                        with self.context_lock:
                            if new_context_id in self.active_contexts:
                                self.active_contexts.remove(new_context_id)
                    
                    self.is_speaking.clear()
                    self.text_queue.task_done()
                
            except Exception as e:
                print(f"Unexpected error in TTS worker: {e}")
    
    def shutdown(self):
        """Clean up resources."""
        self.stop_event.set()
        
        # Cancel all active contexts
        self._cancel_active_contexts()
        
        # Clear the queue
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
        print("\nSpeaking first sentence...")
        input("> Press Enter to start")
        
        start = time.time()
        tts.speak("Hello, I am speaking in a background thread.")
        
        # Wait a moment to ensure speaking starts
        time.sleep(1)
        
        print("\nInterrupting after 1 second...")
        tts.interrupt_and_speak("I've interrupted the previous speech to say something new and important.")
        
        # Wait for speech to finish
        while tts.is_speaking.is_set():
            time.sleep(0.1)
        
        # Demo speaking after interruption
        print("\nSpeaking after interruption...")
        tts.speak("And now I'm speaking normally again after the interruption.")
        
        # Wait for speech to finish
        while tts.is_speaking.is_set():
            time.sleep(0.1)
        
        # Comparison test
        print("\nLet's compare latency. First normal speech:")
        input("> Press Enter for normal speech")
        start = time.time()
        tts.speak("This is normal speech without prior interruption.")
        
        # Wait for speech to finish
        while tts.is_speaking.is_set():
            time.sleep(0.1)
            
        print("\nNow let's test interrupt and speak:")
        input("> Press Enter to start long speech")
        tts.speak("This is a very long sentence that I'm going to keep speaking for a while so that you have time to interrupt me. I'll keep talking and talking...")
        
        time.sleep(1)  # Let it speak for a moment
        
        input("> Press Enter to interrupt")
        start = time.time()
        tts.interrupt_and_speak("This is speech after interruption.")
        
        # Wait for speech to finish
        while tts.is_speaking.is_set():
            time.sleep(0.1)
        
        print(f"Demo complete! Last measured latency: {tts.last_latency:.3f} seconds")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Clean up resources
        tts.shutdown()

if __name__ == "__main__":
    main()