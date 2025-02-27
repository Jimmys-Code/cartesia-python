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
        self.p = None
        self.stream = None
        self.voice_id = None
        self.model_id = None
        self.rate = None
        
        # Queue for audio chunks
        self.audio_queue = queue.Queue()
        
        # Current context tracking
        self.current_context_id = None
        self.interrupt_requested = threading.Event()
        
        # Thread management
        self.audio_thread = None
        self.playback_thread = None
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
        
        # Create audio stream
        self.stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.rate,
            output=True,
            frames_per_buffer=2048
        )
        
        # Start the playback thread
        self.playback_thread = threading.Thread(
            target=self.playback_worker,
            daemon=True
        )
        self.playback_thread.start()
        
        print("TTS system ready!")
    
    def playback_worker(self):
        """Worker thread that continuously plays audio chunks from the queue."""
        while not self.stop_all.is_set():
            try:
                # Get chunk from queue with timeout
                chunk = self.audio_queue.get(timeout=0.1)
                
                # Play the chunk if not None
                if chunk is not None:
                    self.stream.write(chunk)
                
                self.audio_queue.task_done()
            except queue.Empty:
                # No problem, just continue waiting
                pass
            except Exception as e:
                print(f"Error in playback: {e}")
    
    def speak(self, text):
        """Speak the given text."""
        # Stop any current speech first
        self.interrupt_requested.set()
        
        # Wait for any current audio generation to stop
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=0.5)
        
        # Reset the interrupt flag
        self.interrupt_requested.clear()
        
        # Start new audio generation in a separate thread
        self.audio_thread = threading.Thread(
            target=self.generate_audio,
            args=(text,),
            daemon=True
        )
        self.audio_thread.start()
    
    def interrupt_and_speak(self, text):
        """Interrupt current speech and speak new text."""
        print("Interrupting current speech...")
        
        # Signal interruption
        self.interrupt_requested.set()
        
        # Clear the queue
        self.clear_audio_queue()
        
        # Wait for current speech to stop
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=0.5)
        
        # Reset interrupt flag
        self.interrupt_requested.clear()
        
        # Start new speech
        self.audio_thread = threading.Thread(
            target=self.generate_audio,
            args=(text,),
            daemon=True
        )
        self.audio_thread.start()
    
    def clear_audio_queue(self):
        """Clear all pending audio from the queue."""
        try:
            while not self.audio_queue.empty():
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
        except Exception:
            pass
    
    def generate_audio(self, text):
        """Generate audio for the given text."""
        if not text:
            return
            
        try:
            # Create a new websocket for each request to avoid statefulness issues
            ws = self.client.tts.websocket()
            
            # Generate a new context ID
            context_id = str(uuid.uuid4())
            self.current_context_id = context_id
            
            # Buffer for initial frames
            initial_frames = []
            buffer_size = 3
            
            # Request the audio
            for chunk in ws.send(
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
                # Check if interruption was requested
                if self.interrupt_requested.is_set():
                    print(f"Interruption detected, stopping speech for context {context_id}")
                    break
                
                # Process the audio
                if chunk.audio:
                    if len(initial_frames) < buffer_size:
                        # Buffer initial frames
                        initial_frames.append(chunk.audio)
                        
                        if len(initial_frames) >= buffer_size:
                            # Add all buffered frames to the queue
                            for frame in initial_frames:
                                if not self.interrupt_requested.is_set():
                                    self.audio_queue.put(frame)
                    else:
                        # Add frame directly to the queue
                        if not self.interrupt_requested.is_set():
                            self.audio_queue.put(chunk.audio)
                
            # Close the websocket when done
            try:
                ws.close()
            except:
                pass
                
        except Exception as e:
            print(f"Error generating audio: {e}")
    
    def shutdown(self):
        """Clean up resources."""
        print("Shutting down TTS system...")
        
        # Signal all threads to stop
        self.stop_all.set()
        self.interrupt_requested.set()
        
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
        # Demo regular speaking
        print("Speaking first sentence...")
        input(">")
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
            tts.interrupt_and_speak("You interrupted me by pressing Enter! This interruption happens immediately with smooth audio quality.")
            
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