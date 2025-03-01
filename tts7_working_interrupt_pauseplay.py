import os
import sys
import time
import uuid
import queue
import threading
import select
import termios
import tty

import numpy as np
import pyaudio

# -------------------------
# 1) The DualTtsManager
#    (no changes, except removing the old main() inside it)
# -------------------------
from cartesia import Cartesia
from cartesia.tts.requests.output_format import OutputFormat_RawParams

class DualTtsManager:
    def __init__(self):
        self.client = None

        # We'll have two websockets: wsA and wsB
        self.wsA = None
        self.wsB = None
        
        # We’ll keep track of the active connection: 'A' or 'B'
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
        
        # Worker threads
        self.worker_threadA = None
        self.worker_threadB = None
        
        # Volume management for fades
        self.current_volume = 1.0
        self.volume_lock = threading.Lock()
        
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

    def fade_volume(self, start_volume, end_volume, duration=0.5):
        """
        Gradually change volume from start_volume to end_volume over 'duration' seconds.
        """
        steps = 25  # number of small increments for the fade
        step_time = duration / steps
        diff = end_volume - start_volume
        for i in range(steps):
            with self.volume_lock:
                self.current_volume = start_volume + diff * (i + 1) / steps
            time.sleep(step_time)

    def fade_in(self, duration=0.5):
        """
        Fade current volume from whatever it is up to 1.0 over 'duration' seconds.
        """
        with self.volume_lock:
            start_volume = self.current_volume
        if start_volume < 1.0:
            self.fade_volume(start_volume, 1.0, duration)

    def fade_out(self, duration=0.5):
        """
        Fade current volume from whatever it is down to 0.0 over 'duration' seconds.
        """
        with self.volume_lock:
            start_volume = self.current_volume
        if start_volume > 0.0:
            self.fade_volume(start_volume, 0.0, duration)

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
        and speak the new text with near-zero latency.
        We'll fade out first, then do the switching, then fade back in.
        """
        # Fade out the current speaking
        self.fade_out(0.5)

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

            # Switch to B
            self.active_conn = 'B'
            
            # Now queue text on B (as a new context)
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

            # Switch to A
            self.active_conn = 'A'
            
            # Now queue text on A (as a new context)
            self.text_queueA.put((text, "new_context"))
            
            # Reconnect B in the background
            threading.Thread(target=self.refresh_wsB, daemon=True).start()

        # Fade back in
        self.fade_in(0.5)

    def pause(self):
        """
        Fade out and then effectively pause (stop) volume. 
        """
        print("Pausing (fading out)...")
        self.fade_out(0.5)
        print("Paused. Volume is now 0.")

    def resume(self):
        """
        Fade in and resume audio at full volume.
        """
        print("Resuming (fading in)...")
        self.fade_in(0.5)
        print("Resumed at full volume.")

    def refresh_wsA(self):
        """Close and reconnect WebSocket A so that it’s “fresh.”"""
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
        """Close and reconnect WebSocket B so that it’s “fresh.”"""
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
                        # If the active connection is A, play audio (scaled by current_volume)
                        if self.active_conn == 'A':
                            if not collected_enough:
                                initial_frames.append(chunk.audio)
                                if len(initial_frames) >= min_initial_frames:
                                    collected_enough = True
                                    # Play all initial frames
                                    for frame in initial_frames:
                                        self.write_scaled_audio(frame)
                            else:
                                self.write_scaled_audio(chunk.audio)
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
                        # If the active connection is B, play audio (scaled by current_volume)
                        if self.active_conn == 'B':
                            if not collected_enough:
                                initial_frames.append(chunk.audio)
                                if len(initial_frames) >= min_initial_frames:
                                    collected_enough = True
                                    for frame in initial_frames:
                                        self.write_scaled_audio(frame)
                            else:
                                self.write_scaled_audio(chunk.audio)
                        else:
                            # If it's no longer active, discard.
                            break
                except Exception as e:
                    print(f"[B] Error during speech generation: {e}")
                
                self.is_speakingB.clear()
                self.text_queueB.task_done()

            except Exception as e:
                print(f"[B] Unexpected error in TTS worker: {e}")

    def write_scaled_audio(self, audio_bytes):
        """
        Scale the raw float32 PCM 'audio_bytes' by current_volume, then write to output stream.
        """
        with self.volume_lock:
            volume = self.current_volume
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        audio_array *= volume
        self.stream.write(audio_array.tobytes())

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


# -------------------------
# 2) The Ollama streaming API function
# -------------------------
import ollama

llm = "llama3.1"

def get_ollama_api(messages, max_tokens=1000, stream=True, model=llm, keep_alive=-1):
    """
    Streams or returns a single response from an Ollama LLM.
    If stream=True, returns a generator of chunk dicts.
    If stream=False, returns the full text.
    """
    # Ensure messages is a list of dicts
    if isinstance(messages, int):
        messages = [{'role': 'user', 'content': str(messages)}]
    elif isinstance(messages, str):
        messages = [{'role': 'user', 'content': messages}]
    elif not isinstance(messages, list):
        raise ValueError("messages must be a list of dictionaries, a string, or an integer")
    
    response = ollama.chat(
        model=model,
        messages=messages,
        stream=stream,
        options={
            'num_predict': max_tokens,
            'keep_alive': keep_alive
        }
    )

    if stream:
        # Return the streaming generator
        return response  # yields chunk dicts with 'message'
    else:
        # Non-stream: single final response
        return response['message']['content']


# -------------------------
# 3) Main Chat + Key Handling
# -------------------------

# We'll create a small helper to handle raw single-keystroke input (non-blocking).
# This is a simple Linux/macOS approach using select/termios. 
# On Windows, you'd need a different approach or library.

def configure_terminal():
    """Put the terminal into cbreak mode (non-blocking) so we can detect keystrokes."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    return fd, old_settings

def restore_terminal(fd, old_settings):
    """Restore normal terminal settings."""
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def check_for_keypress():
    """Return a single character if pressed, else None."""
    # Use select to poll stdin
    dr, dw, de = select.select([sys.stdin], [], [], 0)
    if dr:
        return sys.stdin.read(1)
    return None

def sentences_from_text_chunks():
    """
    Generator function that:
      - Accumulates text from yield'ed chunks
      - Splits off full sentences as they appear
      - Yields each complete sentence (including trailing punctuation)
    """
    buffer = ""
    end_punct = {'.', '!', '?'}
    while True:
        chunk = yield  # we receive text from the caller
        if chunk is None:
            # Means we're done streaming
            # If there's leftover buffer, yield it as a final partial
            if buffer.strip():
                yield buffer
            return
        
        buffer += chunk
        # Try to extract sentences
        while True:
            # Find first sentence terminator (with a space or newline or EOL after it)
            # We'll do a naive approach: look for '.', '!', or '?' plus a space or end-of-buffer
            sentence_end_index = None
            for i, char in enumerate(buffer):
                if char in end_punct:
                    # check the next char if it exists
                    if i+1 < len(buffer):
                        # if next is whitespace or newline, we consider that a full sentence break
                        if buffer[i+1].isspace():
                            sentence_end_index = i
                            break
                    else:
                        # punctuation is at the end of buffer
                        sentence_end_index = i
                        break
            if sentence_end_index is not None:
                # We found a full sentence up to sentence_end_index
                # We'll include that punctuation in the sentence
                full_sentence = buffer[:sentence_end_index+1]
                # remove it from buffer
                buffer = buffer[sentence_end_index+1:]
                yield full_sentence
            else:
                break


def main():
    """
    Interactive terminal chatbot:
      - Type user input, press Enter -> asks Ollama -> streams response
      - Streams are printed as they arrive
      - For each full sentence in the stream, a TTS call is queued
      - Press <SPACE> any time to pause/resume TTS
      - Press <ENTER> (again) during streaming to interrupt the TTS and skip the rest 
        of the LLM response
    """
    tts = DualTtsManager()

    messages = [
        {'role': 'system', 'content': 'You are a helpful assistant.'}
    ]

    print("Welcome to the Ollama+TTS Chat!\n")
    print("Type your message and press Enter to send. Type 'exit' to quit.")
    print("During streaming output:\n"
          "  - Press SPACE to pause/resume TTS.\n"
          "  - Press ENTER to interrupt the LLM response.\n")

    # Prepare terminal for non-blocking key detection
    fd, old_settings = configure_terminal()
    try:
        while True:
            user_text = input("You: ")
            if user_text.strip().lower() in ['exit', 'quit']:
                break

            # Add user text to conversation
            messages.append({'role': 'user', 'content': user_text})

            print("Assistant: ", end='', flush=True)

            # Call streaming
            response_gen = get_ollama_api(messages, stream=True)

            # We'll accumulate the final full text as well for conversation memory
            full_response = []
            # We'll feed the chunk text into a sentence parser
            parser = sentences_from_text_chunks()
            next(parser)  # prime the generator

            interrupted = False

            for chunk_dict in response_gen:
                # Check if user pressed space or enter
                key = check_for_keypress()
                if key == ' ':
                    # Toggle pause
                    # We'll guess if volume==0 => resume else pause
                    # (Alternatively track a boolean)
                    # We'll do a simple check:
                    if abs(tts.current_volume) < 0.001:
                        tts.resume()
                    else:
                        tts.pause()
                elif key == '\n':
                    # user pressed Enter again => interrupt
                    print("\n[Interrupted by user]\n")
                    tts.interrupt_and_speak("Interruption!")
                    interrupted = True
                    break

                chunk_text = chunk_dict['message']['content']
                sys.stdout.write(chunk_text)
                sys.stdout.flush()
                full_response.append(chunk_text)

                # Feed chunk_text to the sentence parser
                for sentence in parser.send(chunk_text):
                    # Each 'sentence' is a complete sentence
                    # Queue TTS
                    tts.speak(sentence)

            if not interrupted:
                # We are done streaming => feed None
                leftover = parser.send(None)
                # if there's leftover partial text, we can TTS it as well:
                # If you prefer not to TTS partial sentences, remove this block
                if leftover:
                    tts.speak(leftover)

                print()  # final newline

            # Join the entire chunked response
            assistant_msg = ''.join(full_response)
            if not interrupted:
                messages.append({'role': 'assistant', 'content': assistant_msg})
            else:
                # We might store partial or skip
                messages.append({'role': 'assistant', 'content': assistant_msg + "\n(Interrupted)"})


    except KeyboardInterrupt:
        print("\nDetected Ctrl+C, exiting.")
    finally:
        restore_terminal(fd, old_settings)
        tts.shutdown()


if __name__ == "__main__":
    main()