import os
import time
import numpy as np
import pyaudio
import threading
import queue
import uuid

from cartesia import Cartesia

class TtsManager:
    def __init__(self):
        self.client = None
        self.ws = None
        self.p = None
        self.stream = None
        self.voice_id = None
        self.model_id = None
        self.rate = None
        
        # Audio buffer and playback control
        self.audio_queue = queue.Queue()
        self.active_generation_id = None
        self.generation_lock = threading.Lock()
        
        # Thread management
        self.playback_thread = None
        self.generation_threads = {}
        self.stop_all = threading.Event()
        
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
        
        # Set up a single persistent WebSocket connection
        print("Establishing WebSocket connection...")
        self.ws = self.client.tts.websocket()
        
        # Start the playback thread
        self.playback_thread = threading.Thread(
            target=self.playback_worker,
            daemon=True
        )
        self.playback_thread.start()
        
        print("TTS system ready!")
    
    def playback_worker(self):
        """Worker thread that plays audio from the queue."""
        while not self.stop_all.is_set():
            try:
                # Get audio chunk from queue with timeout
                gen_id, audio_chunk = self.audio_queue.get(timeout=0.1)
                
                # Only play if this is from the active generation
                with self.generation_lock:
                    is_active = gen_id == self.active_generation_id
                
                if is_active:
                    self.stream.write(audio_chunk)
                
                self.audio_queue.task_done()
            except queue.Empty:
                # No problem, just continue waiting
                pass
            except Exception as e:
                print(f"Error in playback: {e}")
    
    def speak(self, text):
        """Speak the given text."""
        # Generate a unique ID for this generation
        gen_id = str(uuid.uuid4())
        
        # Set this as the active generation
        with self.generation_lock:
            # Clear out any previous generations
            self.clear_queue()
            self.active_generation_id = gen_id
        
        # Start the generation in a new thread
        generation_thread = threading.Thread(
            target=self.generate_audio,
            args=(text, gen_id),
            daemon=True
        )
        
        # Store the thread reference
        self.generation_threads[gen_id] = generation_thread
        
        # Start the thread
        generation_thread.start()
    
    def interrupt_and_speak(self, text):
        """Interrupt current speech and speak new text."""
        print("Interrupting current speech...")
        
        # Simply start a new speech - it will automatically become the active one
        # and the previous one will stop playing
        self.speak(text)
    
    def clear_queue(self):
        """Clear all pending audio from the queue."""
        try:
            while not self.audio_queue.empty():
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
        except Exception:
            pass
    
    def generate_audio(self, text, gen_id):
        """Generate audio for the given text."""
        if not text:
            return
            
        try:
            # Use a separate context ID for the WebSocket
            context_id = str(uuid.uuid4())
            
            # Buffer initial frames for smoother start
            initial_frames = []
            buffer_size = 2
            
            # Generate the audio
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
                # Check if this generation is still active
                with self.generation_lock:
                    is_active = gen_id == self.active_generation_id
                
                # If no longer active, stop processing
                if not is_active:
                    print(f"Generation {gen_id} is no longer active, stopping")
                    break
                
                # Process the audio chunk
                if chunk.audio:
                    if len(initial_frames) < buffer_size:
                        # Buffer initial frames
                        initial_frames.append(chunk.audio)
                        
                        if len(initial_frames) >= buffer_size:
                            # Send all initial frames to the queue
                            for frame in initial_frames:
                                with self.generation_lock:
                                    if gen_id == self.active_generation_id:
                                        self.audio_queue.put((gen_id, frame))
                    else:
                        # Add frame directly to the queue
                        with self.generation_lock:
                            if gen_id == self.active_generation_id:
                                self.audio_queue.put((gen_id, chunk.audio))
                
        except Exception as e:
            print(f"Error generating audio: {e}")
        finally:
            # Clean up thread reference
            if gen_id in self.generation_threads:
                del self.generation_threads[gen_id]
    
    def shutdown(self):
        """Clean up resources."""
        print("Shutting down TTS system...")
        
        # Signal all threads to stop
        self.stop_all.set()
        
        # Close the WebSocket connection
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                print(f"Error closing WebSocket: {e}")
        
        # Close audio stream
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.p:
            self.p.terminate()
        
        print("TTS system shut down.")


def main():
    # Create TTS Manager
    tts = TtsManager()
    
    try:
        print("System ready! Press Enter to start the demo.")
        input()
        
        # Speak a long first sentence
        print("Speaking long sentence...")
        tts.speak("This is a very long sentence that demonstrates the text-to-speech system with instant response. You should notice that the speech starts immediately with no delay, and when the interruption happens two seconds from now, it will immediately switch to the new text without any jumbling or overlapping of audio.")
        
        # Wait 2 seconds then interrupt
        time.sleep(2)
        print("Interrupting after 2 seconds...")
        tts.interrupt_and_speak("I have successfully interrupted the previous speech with this new sentence. There should be no overlap or jumbling of the audio.")
        
        # Allow time for the second sentence to complete
        time.sleep(5)
        
        # Interactive demo
        print("\nInteractive demo - press Enter at any time to interrupt")
        
        # Start speaking another long text
        tts.speak("This is another demonstration of the text-to-speech system with a very long monologue that will continue until you decide to press the Enter key. At that point, the system should immediately interrupt this speech and start playing the new speech without any overlapping audio or jumbling of sentences. The system is designed to provide clean interruptions for use cases like virtual assistants and interactive applications where responsiveness is critical.")
        
        # Wait for user input to interrupt
        input()
        tts.interrupt_and_speak("You interrupted me by pressing Enter! The interruption should have happened immediately and cleanly without any jumbling of audio.")
        
        # Wait for final speech to complete
        time.sleep(4)
        print("\nDemo complete! Press Enter to exit.")
        input()

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Clean up resources
        tts.shutdown()

if __name__ == "__main__":
    main()