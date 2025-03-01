import os
import time
import uuid
import queue
import threading

import numpy as np
import pyaudio

from cartesia import Cartesia
from cartesia.tts.requests.output_format import OutputFormat_RawParams

class DualTtsManager:
    def __init__(self):
        self.client = None

        # We'll have two websockets: wsA and wsB
        self.wsA = None
        self.wsB = None
        
        # We'll keep track of the active connection: 'A' or 'B'
        self.active_conn = 'A'
        
        # Audio / PyAudio items
        self.p = None
        self.stream = None
        self.rate = None
        
        # Voice / model config
        self.voice_id = None
        self.model_id = None
        
        # For each connection, we store separate queues, events, context IDs, etc.
        self.text_queueA = queue.Queue()
        self.text_queueB = queue.Queue()
        self.current_context_idA = None
        self.current_context_idB = None
        self.context_lockA = threading.Lock()
        self.context_lockB = threading.Lock()
        
        self.stop_eventA = threading.Event()
        self.stop_eventB = threading.Event()
        
        self.is_speakingA = threading.Event()
        self.is_speakingB = threading.Event()
        
        # Add pause events for each connection
        self.pause_eventA = threading.Event()
        self.pause_eventB = threading.Event()
        
        # Worker threads
        self.worker_threadA = None
        self.worker_threadB = None
        
        # Start everything
        self.initialize_tts()

    def initialize_tts(self):
        """Initialize TTS system, including both WebSocket connections."""
        print("Initializing TTS system...")
        
        # Initialize Cartesia client
        self.client = Cartesia(api_key="sk_car_GZrgghX4KvqNrc41q7KoB")
        
        # Config
        self.voice_id = "043cfc81-d69f-4bee-ae1e-7862cb358650"
        self.model_id = "sonic"
        self.rate = 22050
        
        # Initialize PyAudio once (we can share the same output stream)
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.rate,
            output=True,
            frames_per_buffer=1024
        )
        
        # "Warm up" the audio system (optional)
        silence = np.zeros(512, dtype=np.float32)
        self.stream.write(silence.tobytes())
        
        # Create two websockets and start worker threads
        print("Establishing WebSocket connection A...")
        self.wsA = self.client.tts.websocket()
        print("Establishing WebSocket connection B...")
        self.wsB = self.client.tts.websocket()
        
        self.worker_threadA = threading.Thread(
            target=self.tts_workerA,
            daemon=True
        )
        self.worker_threadB = threading.Thread(
            target=self.tts_workerB,
            daemon=True
        )
        
        self.worker_threadA.start()
        self.worker_threadB.start()
        
        print("TTS system ready with two connections (A and B)!\n")

    def speak(self, text):
        """
        Queue text to be spoken on whichever connection is currently active.
        """
        if self.active_conn == 'A':
            self.text_queueA.put((text, None))  # normal speak
        else:
            self.text_queueB.put((text, None))

    def interrupt_and_speak(self, text):
        """
        Immediately interrupt the active connection, switch to the other,
        and speak the new text with near-zero latency (since the other is already connected).
        
        Also optionally refresh/reconnect the WebSocket we just left in the background
        so next time it's fresh.
        """
        if self.active_conn == 'A':
            # Cancel and clear connection A
            with self.context_lockA:
                if self.current_context_idA and self.current_context_idA in self.wsA._contexts:
                    try:
                        self.wsA._remove_context(self.current_context_idA)
                        print(f"Cancelled context A: {self.current_context_idA}")
                    except Exception as e:
                        print(f"Error cancelling context A: {e}")

            while not self.text_queueA.empty():
                try:
                    self.text_queueA.get_nowait()
                    self.text_queueA.task_done()
                except queue.Empty:
                    break

            # Reset pause event for A
            self.pause_eventA.clear()
            
            # Switch to B
            self.active_conn = 'B'
            
            # Reset pause event for B before starting new speech
            self.pause_eventB.clear()
            
            # Now queue text on B
            self.text_queueB.put((text, "new_context"))
            
            # Reconnect A in the background so it's fresh
            threading.Thread(target=self.refresh_wsA, daemon=True).start()

        else:  # currently B
            # Cancel and clear connection B
            with self.context_lockB:
                if self.current_context_idB and self.current_context_idB in self.wsB._contexts:
                    try:
                        self.wsB._remove_context(self.current_context_idB)
                        print(f"Cancelled context B: {self.current_context_idB}")
                    except Exception as e:
                        print(f"Error cancelling context B: {e}")

            while not self.text_queueB.empty():
                try:
                    self.text_queueB.get_nowait()
                    self.text_queueB.task_done()
                except queue.Empty:
                    break

            # Reset pause event for B
            self.pause_eventB.clear()
            
            # Switch to A
            self.active_conn = 'A'
            
            # Reset pause event for A before starting new speech
            self.pause_eventA.clear()
            
            # Now queue text on A
            self.text_queueA.put((text, "new_context"))
            
            # Reconnect B in the background
            threading.Thread(target=self.refresh_wsB, daemon=True).start()

    def toggle_pause_resume(self):
        """
        Toggle between pause and resume for the currently active connection.
        Returns True if paused, False if resumed.
        """
        if self.active_conn == 'A':
            if self.pause_eventA.is_set():
                print("Resuming speech on connection A")
                self.pause_eventA.clear()
                return False
            else:
                print("Pausing speech on connection A")
                self.pause_eventA.set()
                return True
        else:  # B is active
            if self.pause_eventB.is_set():
                print("Resuming speech on connection B")
                self.pause_eventB.clear()
                return False
            else:
                print("Pausing speech on connection B")
                self.pause_eventB.set()
                return True

    def refresh_wsA(self):
        """
        Close and reconnect WebSocket A so that it's "fresh."
        """
        print("Refreshing WebSocket A in the background...")
        try:
            if self.wsA:
                self.wsA.close()
        except Exception as e:
            print(f"Error closing wsA: {e}")
        
        # Recreate WebSocket A
        self.wsA = self.client.tts.websocket()
        print("WebSocket A is refreshed and reconnected.")

    def refresh_wsB(self):
        """
        Close and reconnect WebSocket B so that it's "fresh."
        """
        print("Refreshing WebSocket B in the background...")
        try:
            if self.wsB:
                self.wsB.close()
        except Exception as e:
            print(f"Error closing wsB: {e}")
        
        # Recreate WebSocket B
        self.wsB = self.client.tts.websocket()
        print("WebSocket B is refreshed and reconnected.")

    def tts_workerA(self):
        """Background worker for WebSocket A."""
        min_initial_frames = 3
        while not self.stop_eventA.is_set():
            try:
                try:
                    text, context_action = self.text_queueA.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                # Possibly create a new context
                new_context_id = None
                if context_action == "new_context" or self.current_context_idA is None:
                    new_context_id = str(uuid.uuid4())
                else:
                    new_context_id = self.current_context_idA
                
                with self.context_lockA:
                    self.current_context_idA = new_context_id
                
                print(f"[A] Using context: {new_context_id}")
                initial_frames = []
                collected_enough = False
                self.is_speakingA.set()
                
                try:
                    for chunk in self.wsA.send(
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
                        # If the active connection is A, play audio
                        if self.active_conn == 'A':
                            # Check if we're paused
                            while self.pause_eventA.is_set():
                                # Wait for resume
                                time.sleep(0.1)
                                # If we're no longer active or stopping, exit
                                if self.active_conn != 'A' or self.stop_eventA.is_set():
                                    break
                            
                            # Continue if we're still the active connection
                            if self.active_conn == 'A' and not self.stop_eventA.is_set():
                                if not collected_enough:
                                    initial_frames.append(chunk.audio)
                                    if len(initial_frames) >= min_initial_frames:
                                        # Add a very small buffer to reduce choppiness
                                        time.sleep(0.05)  # ~50 ms buffer
                                        collected_enough = True
                                        # Play all initial frames now
                                        for frame in initial_frames:
                                            self.stream.write(frame)
                                else:
                                    self.stream.write(chunk.audio)
                        else:
                            # If it's no longer active, just discard.
                            break
                except Exception as e:
                    print(f"[A] Error during speech generation: {e}")
                
                self.is_speakingA.clear()
                self.text_queueA.task_done()

            except Exception as e:
                print(f"[A] Unexpected error in TTS worker: {e}")

    def tts_workerB(self):
        """Background worker for WebSocket B."""
        min_initial_frames = 3
        while not self.stop_eventB.is_set():
            try:
                try:
                    text, context_action = self.text_queueB.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                # Possibly create a new context
                new_context_id = None
                if context_action == "new_context" or self.current_context_idB is None:
                    new_context_id = str(uuid.uuid4())
                else:
                    new_context_id = self.current_context_idB
                
                with self.context_lockB:
                    self.current_context_idB = new_context_id
                
                print(f"[B] Using context: {new_context_id}")
                initial_frames = []
                collected_enough = False
                self.is_speakingB.set()
                
                try:
                    for chunk in self.wsB.send(
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
                        # If the active connection is B, play audio
                        if self.active_conn == 'B':
                            # Check if we're paused
                            while self.pause_eventB.is_set():
                                # Wait for resume
                                time.sleep(0.1)
                                # If we're no longer active or stopping, exit
                                if self.active_conn != 'B' or self.stop_eventB.is_set():
                                    break
                            
                            # Continue if we're still the active connection
                            if self.active_conn == 'B' and not self.stop_eventB.is_set():
                                if not collected_enough:
                                    initial_frames.append(chunk.audio)
                                    if len(initial_frames) >= min_initial_frames:
                                        # Add a very small buffer to reduce choppiness
                                        time.sleep(0.1)  # ~100 ms buffer
                                        collected_enough = True
                                        # Play all initial frames now
                                        for frame in initial_frames:
                                            self.stream.write(frame)
                                else:
                                    self.stream.write(chunk.audio)
                        else:
                            # If it's no longer active, discard.
                            break
                except Exception as e:
                    print(f"[B] Error during speech generation: {e}")
                
                self.is_speakingB.clear()
                self.text_queueB.task_done()

            except Exception as e:
                print(f"[B] Unexpected error in TTS worker: {e}")

    def shutdown(self):
        """Clean up resources."""
        print("Shutting down TTS system...")
        self.stop_eventA.set()
        self.stop_eventB.set()
        
        # Drain queues
        for q in (self.text_queueA, self.text_queueB):
            while not q.empty():
                try:
                    q.get_nowait()
                    q.task_done()
                except queue.Empty:
                    pass
        
        if self.worker_threadA and self.worker_threadA.is_alive():
            self.worker_threadA.join(timeout=2.0)
        if self.worker_threadB and self.worker_threadB.is_alive():
            self.worker_threadB.join(timeout=2.0)
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()
        
        # Close websockets
        try:
            if self.wsA:
                self.wsA.close()
            if self.wsB:
                self.wsB.close()
        except Exception as e:
            print(f"Error closing websockets: {e}")
        
        print("TTS system shut down.")

def main():
    # Create the DualTtsManager
    tts = DualTtsManager()
    
    try:
        print("Starting TTS interruption stability test...")
        
        # Initial message
        initial_message = "This is a long message that will be interrupted repeatedly. It contains a lot of text to ensure that it would take a while to speak, giving us plenty of time to test the interruption system. The system should interrupt this message every second and start saying 'This is looping' instead."
        
        # Start with the initial message
        print("Speaking initial message...")
        tts.speak(initial_message)
        
        # Counter for tracking interruptions
        interruption_count = 0
        
        # Loop to continuously interrupt
        while True:
            # Wait for 1 second before interrupting
            time.sleep(2)
            
            # Increment counter
            interruption_count += 1
            
            # Interrupt with a message that includes the count
            interrupt_message = f"This is looping. Interruption number {interruption_count}. "
            print(f"Interrupting with: {interrupt_message}")
            
            # Interrupt the current speech and speak the new message
            tts.interrupt_and_speak(interrupt_message + initial_message)
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        tts.shutdown()

if __name__ == "__main__":
    main()