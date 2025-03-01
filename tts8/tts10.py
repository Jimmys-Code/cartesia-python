import os
import time
import uuid
import queue
import threading

import numpy as np
import pyaudio

from cartesia import Cartesia

class SingleTtsManager:
    def __init__(self):
        self.client = None
        self.ws = None  # One WebSocket connection only
        
        # Audio / PyAudio items
        self.p = None
        self.stream = None
        self.rate = None
        
        # Voice / model config
        self.voice_id = None
        self.model_id = None
        
        # Shared structures
        self.text_queue = queue.Queue()
        self.stop_event = threading.Event()
        
        self.current_context_id = None
        self.context_lock = threading.Lock()
        
        self.is_speaking = threading.Event()     # True while TTS is actively generating audio
        self.pause_event = threading.Event()     # For pause/resume
        self.canceled_contexts = set()           # Contexts forcibly stopped mid-speech
        
        # Start everything
        self.initialize_tts()

    def initialize_tts(self):
        print("Initializing TTS system...")

        self.client = Cartesia(api_key="sk_car_GZrgghX4KvqNrc41q7KoB")
        self.voice_id = "043cfc81-d69f-4bee-ae1e-7862cb358650"
        self.model_id = "sonic"
        self.rate = 22050

        # Initialize PyAudio
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.rate,
            output=True,
            frames_per_buffer=1024
        )

        # Small “warm-up”
        silence = np.zeros(512, dtype=np.float32)
        self.stream.write(silence.tobytes())

        # Single WebSocket
        print("Establishing single WebSocket connection...")
        self.ws = self.client.tts.websocket()

        # Worker thread
        self.worker_thread = threading.Thread(target=self.tts_worker, daemon=True)
        self.worker_thread.start()

        print("TTS system ready (single connection)!\n")

    def speak(self, text):
        """
        Queue text without forcing a new context. 
        (If `current_context_id` already exists, it reuses it.)
        """
        self.text_queue.put((text, None))

    def interrupt_and_speak(self, text):
        """
        Interrupt by canceling the old context, clearing old text,
        and enqueuing new text in a brand-new context.
        """
        self._cancel_current_context()
        
        # Enqueue new text with a "new_context" marker
        self.text_queue.put((text, "new_context"))

    def _cancel_current_context(self):
        """
        - Remove the old context from the WebSocket (so backend stops sending new chunks).
        - Mark that context as canceled in our local set (so if we do get leftover chunks, we skip them).
        - Clear the queue of any leftover text (true interruption).
        """
        with self.context_lock:
            if self.current_context_id:
                try:
                    # Remove from WebSocket so the server stops generating new chunks
                    if self.current_context_id in self.ws._contexts:
                        self.ws._remove_context(self.current_context_id)
                        print(f"Cancelled context {self.current_context_id}")
                except Exception as e:
                    print(f"Error cancelling context {self.current_context_id}: {e}")
                
                # Locally mark that context as canceled, so the worker loop breaks if leftover chunks arrive
                self.canceled_contexts.add(self.current_context_id)

        # Clear out any leftover text in the queue
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                break
        
        # Clear the pause event in case we were paused
        self.pause_event.clear()

    def toggle_pause_resume(self):
        """
        Toggle pause/resume. Returns True if paused, False if resumed.
        """
        if self.pause_event.is_set():
            print("Resuming speech")
            self.pause_event.clear()
            return False
        else:
            print("Pausing speech")
            self.pause_event.set()
            return True

    def tts_worker(self):
        """
        Reads text from queue and sends it to the WebSocket.
        If the context is canceled mid-stream, we break from chunk loop immediately.
        """
        # You can tweak min_initial_frames or remove it to reduce “leftover” audio
        min_initial_frames = 2

        while not self.stop_event.is_set():
            try:
                # Wait for new text
                try:
                    text, context_action = self.text_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                # Possibly start a new context
                with self.context_lock:
                    if context_action == "new_context" or self.current_context_id is None:
                        self.current_context_id = str(uuid.uuid4())

                    local_context_id = self.current_context_id

                print(f"[Worker] Using context: {local_context_id}")
                self.is_speaking.set()

                # We'll collect a small buffer of frames so playback is smooth
                initial_frames = []
                collected_enough = False

                try:
                    # Use the context_id for streaming
                    for chunk in self.ws.send(
                        model_id=self.model_id,
                        transcript=text,
                        voice={"mode": "id", "id": self.voice_id},
                        context_id=local_context_id,
                        output_format={
                            "container": "raw",
                            "encoding": "pcm_f32le",
                            "sample_rate": self.rate
                        },
                    ):
                        # 1) If the context was canceled, break immediately
                        if local_context_id in self.canceled_contexts:
                            print(f"[Worker] Context {local_context_id} was canceled mid-stream. Stopping.")
                            break

                        # 2) Check if paused
                        while self.pause_event.is_set():
                            if self.stop_event.is_set():
                                break
                            if local_context_id in self.canceled_contexts:
                                break
                            time.sleep(0.05)
                        
                        if self.stop_event.is_set():
                            break
                        if local_context_id in self.canceled_contexts:
                            break

                        # 3) If not canceled or paused, output audio
                        if not collected_enough:
                            initial_frames.append(chunk.audio)
                            if len(initial_frames) >= min_initial_frames:
                                # small buffer for smoothness
                                time.sleep(0.02)
                                collected_enough = True
                                for frame in initial_frames:
                                    self.stream.write(frame)
                        else:
                            self.stream.write(chunk.audio)

                except Exception as e:
                    print(f"[Worker] Error during speech generation: {e}")

                self.is_speaking.clear()
                self.text_queue.task_done()

            except Exception as e:
                print(f"[Worker] Unexpected error in TTS worker: {e}")

    def shutdown(self):
        """Clean up resources."""
        print("Shutting down TTS system...")
        self.stop_event.set()
        
        # Drain the queue
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                pass
        
        # Join worker thread
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        
        # Close audio
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()
        
        # Close the single WebSocket
        try:
            if self.ws:
                self.ws.close()
        except Exception as e:
            print(f"Error closing websocket: {e}")
        
        print("TTS system shut down.")

def main():
    tts = SingleTtsManager()
    print("Single WebSocket: immediate interruption demo.\n")

    # Optionally speak something at startup
    tts.speak(
        "Hello! This is the initial text. Try interrupting me whenever you like."
    )

    try:
        while True:
            input("Press ENTER to interrupt and speak new text, or Ctrl+C to exit...\n")
            # Interrupt with new text
            tts.interrupt_and_speak(
                "New text here! The old speech was cut off immediately."
            )
    except KeyboardInterrupt:
        pass
    finally:
        tts.shutdown()

if __name__ == "__main__":
    main()