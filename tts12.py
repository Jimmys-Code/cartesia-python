import os
import time
import uuid
import queue
import threading

import numpy as np
import pyaudio

from cartesia import Cartesia

class TenTtsManager:
    def __init__(self):
        self.client = None
        
        # We'll label our 10 connections from "A" to "J"
        self.conn_labels = ["A","B","C","D","E","F","G","H","I","J"]
        
        # Keep track of the active connection index in self.conn_labels
        self.active_conn_index = 0  # Start with "A"
        
        # Audio / PyAudio items
        self.p = None
        self.stream = None
        self.rate = None
        
        # Voice / model config
        self.voice_id = None
        self.model_id = None
        
        # For each connection label, store separate websockets, queues, locks, events, etc.
        self.websockets = {}
        self.text_queues = {}
        self.current_context_ids = {}
        self.context_locks = {}
        self.stop_events = {}
        self.is_speaking_flags = {}
        self.pause_events = {}
        self.ready_flags = {}
        self.refresh_in_progress_flags = {}
        self.worker_threads = {}
        
        # Housekeeping thread (auto-refresh idle connections)
        self.housekeeper_thread = None
        self.stop_housekeeper = threading.Event()
        
        # Start everything
        self.initialize_tts()

    def initialize_tts(self):
        """Initialize TTS system, including all ten WebSocket connections."""
        print("Initializing TTS system...")

        # Init Cartesia client
        self.client = Cartesia(api_key="YOUR_API_KEY_HERE")

        # Model config
        self.voice_id = "043cfc81-d69f-4bee-ae1e-7862cb358650"
        self.model_id = "sonic"
        self.rate = 22050

        # Initialize PyAudio (shared output)
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

        # Create data structures for each of the 10 connections
        for label in self.conn_labels:
            print(f"Establishing WebSocket connection {label}...")
            ws = self.client.tts.websocket()
            self.websockets[label] = ws
            self.text_queues[label] = queue.Queue()
            self.current_context_ids[label] = None
            self.context_locks[label] = threading.Lock()
            self.stop_events[label] = threading.Event()
            self.is_speaking_flags[label] = threading.Event()
            self.pause_events[label] = threading.Event()
            self.ready_flags[label] = True  # Mark initially as ready
            self.refresh_in_progress_flags[label] = False

        # Spin up a TTS worker thread for each connection
        for label in self.conn_labels:
            t = threading.Thread(target=self.tts_worker, args=(label,), daemon=True)
            self.worker_threads[label] = t
            t.start()

        # Housekeeping thread: auto-refresh idle connections in the background
        self.housekeeper_thread = threading.Thread(target=self.housekeeper, daemon=True)
        self.housekeeper_thread.start()

        print("TTS system ready with ten connections (A through J)!\n")

    def housekeeper(self):
        """
        Background thread that runs every second, checking each connection.
        If a connection is NOT currently active, not speaking, not paused, and not in refresh,
        we refresh it so that it remains open and 'fresh'.
        """
        while not self.stop_housekeeper.is_set():
            time.sleep(1.0)
            for label in self.conn_labels:
                self._maybe_refresh(label)
    
    def _maybe_refresh(self, label):
        """Refresh a connection if it's idle, not active, and not currently speaking."""
        # If this connection is the *active* one, skip
        if label == self.conn_labels[self.active_conn_index]:
            return
        
        if (not self.is_speaking_flags[label].is_set() and 
            not self.pause_events[label].is_set() and
            not self.refresh_in_progress_flags[label] and
            self.ready_flags[label]):
            # Go ahead and refresh in the background
            threading.Thread(target=self.refresh_ws, args=(label,), daemon=True).start()

    def speak(self, text):
        """Queue text on whichever connection is currently active (assuming it's ready)."""
        active_label = self.conn_labels[self.active_conn_index]
        self.text_queues[active_label].put((text, None))

    def interrupt_and_speak(self, text):
        """
        Immediately interrupt the active connection, switch to the next *ready* connection
        in a round-robin (A->B->C->...->J->A), and speak the new text. If the next one
        isn’t ready yet, we check the next, etc. If none is ready, we revert to the old one.
        """
        old_label = self.conn_labels[self.active_conn_index]
        
        # Cancel/clear the old connection
        self._cancel_and_clear(old_label)
        
        # Try up to 10 cycles to find a next ready connection
        candidate_indices = [(self.active_conn_index + i) % 10 for i in range(1, 11)]
        next_label = None

        # We'll do up to 10 tries of scanning
        for _ in range(10):
            for candidate_idx in candidate_indices:
                lbl = self.conn_labels[candidate_idx]
                if self._is_conn_ready(lbl):
                    next_label = lbl
                    self.active_conn_index = candidate_idx
                    break
            if next_label is not None:
                break
            # If none is ready, wait a bit so housekeeping can refresh
            time.sleep(0.3)

        if next_label is None:
            print("Warning: No connections are ready after repeated checks; using the old one anyway!")
            next_label = old_label
            self.active_conn_index = self.conn_labels.index(old_label)

        # Clear the pause flag on the new connection, just in case
        self._clear_pause_flag(next_label)
        
        # Speak new text
        self.text_queues[next_label].put((text, "new_context"))

    def _cancel_and_clear(self, label):
        """
        Cancel the current context on a given connection and empty its text queue.
        Then immediately trigger a refresh in the background so it’s ready next time.
        """
        with self.context_locks[label]:
            if (self.current_context_ids[label] and
                self.ready_flags[label] and
                self.current_context_ids[label] in self.websockets[label]._contexts):
                try:
                    self.websockets[label]._remove_context(self.current_context_ids[label])
                    print(f"Cancelled context {label}: {self.current_context_ids[label]}")
                except Exception as e:
                    print(f"Error cancelling context {label}: {e}")

        # Drain any pending text in that queue
        while not self.text_queues[label].empty():
            try:
                self.text_queues[label].get_nowait()
                self.text_queues[label].task_done()
            except queue.Empty:
                break

        # Clear any pause
        self.pause_events[label].clear()
        
        # Immediately refresh in background
        self._immediate_refresh(label)

    def _immediate_refresh(self, label):
        """
        Spawn a thread that refreshes the connection right away,
        but ONLY if it's truly idle and not the active one.
        """
        if label == self.conn_labels[self.active_conn_index]:
            # It's active, so skip
            return
        
        if (not self.is_speaking_flags[label].is_set() and 
            not self.refresh_in_progress_flags[label] and
            not self.pause_events[label].is_set()):
            threading.Thread(target=self.refresh_ws, args=(label,), daemon=True).start()

    def _is_conn_ready(self, label):
        """Return True if given connection is 'ready' and not currently speaking."""
        return (self.ready_flags[label] and not self.is_speaking_flags[label].is_set())

    def _clear_pause_flag(self, label):
        """Ensure pause event is cleared for the selected next connection."""
        self.pause_events[label].clear()

    def toggle_pause_resume(self):
        """
        Toggle between pause and resume for the currently active connection.
        Returns True if paused, False if resumed.
        """
        active_label = self.conn_labels[self.active_conn_index]
        if self.pause_events[active_label].is_set():
            print(f"Resuming speech on connection {active_label}")
            self.pause_events[active_label].clear()
            return False
        else:
            print(f"Pausing speech on connection {active_label}")
            self.pause_events[active_label].set()
            return True

    def refresh_ws(self, label):
        """Close and reconnect a given WebSocket in the background to keep it fresh."""
        self.refresh_in_progress_flags[label] = True
        self.ready_flags[label] = False
        try:
            print(f"Refreshing WebSocket {label} in the background...")
            if self.websockets[label]:
                self.websockets[label].close()
        except Exception as e:
            print(f"Error closing ws{label}: {e}")
        try:
            self.websockets[label] = self.client.tts.websocket()
            print(f"WebSocket {label} is refreshed and reconnected.")
            self.ready_flags[label] = True
        except Exception as e:
            print(f"Failed to refresh {label}: {e}")
        self.refresh_in_progress_flags[label] = False

    def tts_worker(self, label):
        """Background worker for a given WebSocket label."""
        min_initial_frames = 3
        while not self.stop_events[label].is_set():
            try:
                # Attempt to get text from the queue
                try:
                    text, context_action = self.text_queues[label].get(timeout=0.5)
                except queue.Empty:
                    continue

                # Possibly create a new context
                new_context_id = None
                if context_action == "new_context" or self.current_context_ids[label] is None:
                    new_context_id = str(uuid.uuid4())
                else:
                    new_context_id = self.current_context_ids[label]

                with self.context_locks[label]:
                    self.current_context_ids[label] = new_context_id

                print(f"[{label}] Using context: {new_context_id}")
                initial_frames = []
                collected_enough = False
                self.is_speaking_flags[label].set()

                try:
                    for chunk in self.websockets[label].send(
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
                        # If this connection is still the active one, play audio
                        if label == self.conn_labels[self.active_conn_index]:
                            # Check if we're paused
                            while self.pause_events[label].is_set():
                                time.sleep(0.1)
                                # If it's no longer active or shutting down, break
                                if (label != self.conn_labels[self.active_conn_index] or
                                    self.stop_events[label].is_set()):
                                    break
                            if (label == self.conn_labels[self.active_conn_index] and 
                                not self.stop_events[label].is_set()):
                                if not collected_enough:
                                    initial_frames.append(chunk.audio)
                                    if len(initial_frames) >= min_initial_frames:
                                        # small buffer
                                        time.sleep(0.05)
                                        collected_enough = True
                                        for frame in initial_frames:
                                            self.stream.write(frame)
                                else:
                                    self.stream.write(chunk.audio)
                        else:
                            # Not active, discard
                            break
                except Exception as e:
                    print(f"[{label}] Error during speech generation: {e}")

                self.is_speaking_flags[label].clear()
                self.text_queues[label].task_done()

            except Exception as e:
                print(f"[{label}] Unexpected error in TTS worker: {e}")

    def shutdown(self):
        """Clean up resources."""
        print("Shutting down TTS system...")
        
        # Signal all threads to stop
        for label in self.conn_labels:
            self.stop_events[label].set()
        
        # Stop housekeeper
        self.stop_housekeeper.set()
        
        # Drain queues
        for label in self.conn_labels:
            q = self.text_queues[label]
            while not q.empty():
                try:
                    q.get_nowait()
                    q.task_done()
                except queue.Empty:
                    pass
        
        # Join worker threads
        for label in self.conn_labels:
            t = self.worker_threads[label]
            if t.is_alive():
                t.join(timeout=2.0)
        
        if self.housekeeper_thread and self.housekeeper_thread.is_alive():
            self.housekeeper_thread.join(timeout=2.0)
        
        # Close audio
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()
        
        # Close websockets
        for label in self.conn_labels:
            try:
                if self.websockets[label]:
                    self.websockets[label].close()
            except Exception as e:
                print(f"Error closing websocket {label}: {e}")
        
        print("TTS system shut down.")


def main():
    tts = TenTtsManager()
    
    print("Starting TTS interruption stability test with TEN connections...")

    # A long message that we'd like to keep interrupting
    initial_message = (
        "This is a long message that will be interrupted repeatedly. "
        "It contains a lot of text to ensure that it would take a while "
        "to speak, giving us plenty of time to test the interruption system. "
        "The system should interrupt this message every so often and switch connections!"
    )
    
    # Just as an example: start speaking the initial long message
    tts.speak(initial_message)

    try:
        while True:
            input("\nPress ENTER to interrupt and speak again (or Ctrl+C to exit)...\n")
            tts.interrupt_and_speak(
                "This is a really long sentence that we can interrupt at any point and it will restart."
            )
    except KeyboardInterrupt:
        pass
    finally:
        tts.shutdown()

if __name__ == "__main__":
    main()