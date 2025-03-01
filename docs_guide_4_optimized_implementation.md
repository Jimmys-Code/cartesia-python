# Optimized Cartesia TTS Implementation for Production

## Introduction

This guide presents a complete, optimized implementation of a production-ready Cartesia TTS system with immediate interruption capabilities. It combines all the best practices and patterns from previous guides into a robust, efficient solution.

## Complete Implementation

```python
import os
import time
import threading
import uuid
import json
import queue
import numpy as np
import pyaudio
from typing import Optional, Dict, Any, List, Tuple

from cartesia import Cartesia
from cartesia.tts import OutputFormat_RawParams

class OptimizedTtsManager:
    """Production-ready TTS Manager with immediate interruption capabilities"""
    
    def __init__(self, api_key: str, voice_id: str, model_id: str = "sonic"):
        """Initialize the TTS Manager
        
        Args:
            api_key: Cartesia API key
            voice_id: Voice ID to use
            model_id: Model ID to use (default: sonic)
        """
        # Core configuration
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.sample_rate = 22050
        
        # Client/connection state
        self.client = None
        self.ws = None
        self.p = None
        self.stream = None
        
        # Threading and synchronization
        self.text_queue = queue.Queue()
        self.current_context_id = None
        self.context_lock = threading.Lock()
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.is_speaking = threading.Event()
        self.reconnect_lock = threading.Lock()
        
        # Audio buffer for pre-buffering
        self.min_initial_frames = 3
        
        # Performance metrics
        self.last_latency = 0
        self.total_interruptions = 0
        self.latencies = []
        
        # Initialize components
        self.initialize_tts()
        
    def initialize_tts(self):
        """Initialize TTS client, WebSocket, and audio systems"""
        with self.reconnect_lock:
            print("Initializing TTS system...")
            
            # Initialize Cartesia client
            self.client = Cartesia(api_key=self.api_key)
            
            # Initialize PyAudio
            if not self.p:
                self.p = pyaudio.PyAudio()
            
            # Initialize audio stream if needed
            if not self.stream:
                self.stream = self.p.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=self.sample_rate,
                    output=True,
                    frames_per_buffer=1024
                )
                
                # "Warm up" the audio system with silence
                silence = np.zeros(512, dtype=np.float32)
                self.stream.write(silence.tobytes())
            
            # Set up WebSocket connection
            print("Establishing WebSocket connection...")
            self.ws = self.client.tts.websocket()
            
            # Start worker thread if not already running
            if not self.worker_thread or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(
                    target=self.tts_worker,
                    daemon=True
                )
                self.worker_thread.start()
                
            print("TTS system ready!")
    
    def ensure_connection(self):
        """Ensure WebSocket connection is active, reconnect if needed"""
        try:
            if not self.ws or self.ws._is_websocket_closed():
                with self.reconnect_lock:
                    print("Reconnecting WebSocket...")
                    self.ws = self.client.tts.websocket()
                return True
        except Exception as e:
            print(f"Error checking/reconnecting WebSocket: {e}")
            # Try full reinitialization
            try:
                self.initialize_tts()
                return True
            except Exception as e2:
                print(f"Failed to reinitialize TTS: {e2}")
                return False
        return True
        
    def speak(self, text: str, priority: int = 1):
        """Queue text to be spoken
        
        Args:
            text: Text to speak
            priority: Priority level (higher numbers = higher priority)
        """
        self.ensure_connection()
        self.text_queue.put((text, None, priority))  # None means create or reuse context
        
    def interrupt_and_speak(self, text: str):
        """Immediately stop current speech and speak this text instead"""
        self.total_interruptions += 1
        
        # Ensure connection
        self.ensure_connection()
        
        # Cancel current context if there is one
        with self.context_lock:
            if self.current_context_id and hasattr(self.ws, 'websocket'):
                try:
                    # 1. Send explicit cancellation request to server
                    cancel_request = {
                        "context_id": self.current_context_id,
                        "cancel": True
                    }
                    self.ws.websocket.send(json.dumps(cancel_request))
                    
                    # 2. Also remove client-side context
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
        
        # Add new text to queue with highest priority
        self.text_queue.put((text, "new_context", 10))
        
    def tts_worker(self):
        """Background worker that processes text from the queue"""
        while not self.stop_event.is_set():
            try:
                # Wait for text in queue with timeout to allow checking stop_event
                try:
                    text, context_action, priority = self.text_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                # Process the TTS request
                try:
                    # Check connection before proceeding
                    if not self.ensure_connection():
                        # Requeue the request if connection failed
                        self.text_queue.put((text, context_action, priority))
                        time.sleep(1)  # Avoid tight loop
                        continue
                    
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
                    
                    # Prepare for latency measurement
                    start_time = time.time()
                    
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
                            "sample_rate": self.sample_rate
                        },
                    ):
                        if not collected_enough:
                            initial_frames.append(chunk.audio)
                            if len(initial_frames) >= self.min_initial_frames:
                                collected_enough = True
                                
                                # Play all initial frames at once
                                buffer = b''.join(initial_frames)
                                self.stream.write(buffer)
                                
                                # Measure and record latency
                                self.last_latency = time.time() - start_time
                                self.latencies.append(self.last_latency)
                                if len(self.latencies) > 100:
                                    self.latencies.pop(0)  # Keep last 100
                        else:
                            self.stream.write(chunk.audio)
                except Exception as e:
                    print(f"Error during speech generation: {e}")
                    # Try to reconnect for next attempt
                    self.ensure_connection()
                
                self.is_speaking.clear()
                self.text_queue.task_done()
                
            except Exception as e:
                print(f"Unexpected error in TTS worker: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        avg_latency = sum(self.latencies) / max(len(self.latencies), 1)
        return {
            "total_interruptions": self.total_interruptions,
            "last_latency": self.last_latency,
            "average_latency": avg_latency,
            "min_latency": min(self.latencies) if self.latencies else 0,
            "max_latency": max(self.latencies) if self.latencies else 0,
            "is_speaking": self.is_speaking.is_set(),
            "queue_size": self.text_queue.qsize()
        }
    
    def pause(self):
        """Pause audio playback"""
        if self.stream:
            self.stream.stop_stream()
            
    def resume(self):
        """Resume audio playback"""
        if self.stream and not self.stream.is_active():
            self.stream.start_stream()
    
    def shutdown(self):
        """Clean up resources"""
        print("Shutting down TTS system...")
        self.stop_event.set()
        
        # Clear the queue
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                break
        
        # Wait for worker thread to finish
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
            
        # Clean up audio resources
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            
        if self.p:
            self.p.terminate()
            
        # Close WebSocket connection
        if self.ws:
            self.ws.close()
            
        print("TTS system shut down.")
```

## Usage Examples

### 1. Basic Usage

```python
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize TTS Manager
tts = OptimizedTtsManager(
    api_key=os.getenv("CARTESIA_API_KEY"),
    voice_id="your-voice-id"
)

try:
    # Simple speaking
    tts.speak("Hello! This is a demonstration of the optimized TTS system.")
    time.sleep(3)
    
    # Interrupt with new text
    tts.interrupt_and_speak("I've interrupted the previous speech to say something important.")
    time.sleep(3)
    
    # Queue multiple utterances
    tts.speak("This is the first queued sentence.")
    tts.speak("This is the second queued sentence.")
    tts.speak("This is the third queued sentence.")
    
    # Wait for all speech to complete
    while tts.is_speaking.is_set() or not tts.text_queue.empty():
        time.sleep(0.1)
        
    # Get performance statistics
    stats = tts.get_stats()
    print(f"Average latency: {stats['average_latency']:.3f} seconds")
    print(f"Total interruptions: {stats['total_interruptions']}")
    
finally:
    # Clean up resources
    tts.shutdown()
```

### 2. Interactive Conversation Loop

```python
import time
import os
import threading
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize TTS Manager
tts = OptimizedTtsManager(
    api_key=os.getenv("CARTESIA_API_KEY"),
    voice_id="your-voice-id"
)

def input_thread():
    """Thread to handle user input"""
    while True:
        user_input = input("> ")
        if user_input.lower() in ['exit', 'quit', 'q']:
            break
            
        if user_input.startswith('!'):
            # Immediate interruption for inputs starting with !
            tts.interrupt_and_speak(user_input[1:])
        else:
            # Normal queued speech
            tts.speak(user_input)

try:
    print("Interactive TTS Demo")
    print("Type text to speak, prefix with ! to interrupt")
    print("Type 'exit', 'quit', or 'q' to exit")
    
    # Start input thread
    thread = threading.Thread(target=input_thread, daemon=True)
    thread.start()
    
    # Main thread just keeps the program alive
    while thread.is_alive():
        time.sleep(0.1)
        
finally:
    # Clean up resources
    tts.shutdown()
```

### 3. Integration with a Voice Assistant

```python
import time
import os
import threading
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize TTS Manager
tts = OptimizedTtsManager(
    api_key=os.getenv("CARTESIA_API_KEY"),
    voice_id="your-voice-id"
)

# Simulated LLM function (replace with your actual LLM call)
def get_llm_response(user_input):
    """Get response from LLM"""
    # Simulate LLM processing
    time.sleep(1)
    return f"I processed your input: '{user_input}' and here is my response."

class VoiceAssistant:
    def __init__(self, tts_manager):
        self.tts = tts_manager
        self.is_listening = False
        self.processing = False
        
    def start_listening(self):
        """Start listening for user input"""
        self.is_listening = True
        self.tts.speak("I'm listening. What can I help you with?")
        
    def stop_listening(self):
        """Stop listening for user input"""
        self.is_listening = False
        
    def process_input(self, user_input):
        """Process user input and generate response"""
        if not self.is_listening:
            return
            
        # Indicate processing
        self.processing = True
        self.tts.speak("Processing your request...")
        
        # Get response from LLM
        try:
            response = get_llm_response(user_input)
            
            # Interrupt "Processing" message with actual response
            self.tts.interrupt_and_speak(response)
        except Exception as e:
            self.tts.interrupt_and_speak(f"Sorry, I encountered an error: {str(e)}")
        finally:
            self.processing = False
            
    def handle_urgent_notification(self, message):
        """Handle urgent notification that should interrupt current speech"""
        self.tts.interrupt_and_speak(f"Urgent notification: {message}")

# Example usage
assistant = VoiceAssistant(tts)
assistant.start_listening()

# Simulate user interaction
time.sleep(2)
assistant.process_input("What's the weather like today?")

# While processing, simulate urgent notification
time.sleep(1.5)  # Wait for processing message to start
assistant.handle_urgent_notification("Your timer is done!")

# Continue normal interaction
time.sleep(3)
assistant.process_input("Tell me a joke")

# Wait for processing to complete
time.sleep(5)

# Clean up
tts.shutdown()
```

## Performance Optimization Tips

1. **Latency Reduction**:
   - Pre-buffer initial audio frames before playback
   - Keep WebSocket connections open rather than reconnecting
   - Use appropriate buffer sizes for your audio system

2. **Voice Quality**:
   - For interruptions, prioritize clean cuts by explicit cancellation
   - Consider using the flush mechanism for less urgent changes
   - Experiment with different `min_initial_frames` values for your use case

3. **Resource Management**:
   - Properly close WebSocket connections and audio streams when done
   - Implement error recovery and automatic reconnection
   - Monitor memory usage, especially for long-running applications

4. **System Integration**:
   - Coordinate TTS with other components using thread-safe synchronization
   - Implement proper handling of background tasks
   - Consider using process isolation for critical system components

5. **Platform-Specific Considerations**:
   - On mobile, handle audio system suspend/resume events
   - On web platforms, manage WebSocket reconnections after network changes
   - On desktop applications, integrate with system audio controls

## Conclusion

This optimized implementation provides a robust foundation for building responsive, low-latency TTS applications with immediate interruption capabilities. The design prioritizes:

- Immediate speech interruption
- Low-latency audio playback
- Robust error handling
- Resource efficiency
- Easy integration

Adapt the implementation to your specific needs while maintaining these core principles for the best results.