# Advanced Streaming Patterns with Cartesia TTS

## Introduction

Beyond basic streaming and interruption, Cartesia's WebSocket API enables sophisticated speech streaming patterns for complex applications. This guide explores advanced techniques for creating responsive, natural-sounding TTS systems.

## 1. Low-Latency Streaming with Pre-buffering

To minimize perceived latency, pre-buffer initial chunks before playback:

```python
import time
import numpy as np
import pyaudio
from cartesia import Cartesia

class LowLatencyTTS:
    def __init__(self, api_key):
        self.client = Cartesia(api_key=api_key)
        self.ws = self.client.tts.websocket()
        self.p = pyaudio.PyAudio()
        self.sample_rate = 22050
        self.stream = self.p.open(
            format=pyaudio.paFloat32, 
            channels=1, 
            rate=self.sample_rate, 
            output=True,
            frames_per_buffer=1024
        )
        
    def speak(self, text, voice_id, min_initial_frames=3):
        # Collect initial frames to reduce startup latency
        initial_frames = []
        collected_enough = False
        
        # Start timing for latency measurement
        start_time = time.time()
        
        # Generate and stream audio
        for chunk in self.ws.send(
            model_id="sonic",
            transcript=text,
            voice={"mode": "id", "id": voice_id},
            output_format={
                "container": "raw",
                "encoding": "pcm_f32le", 
                "sample_rate": self.sample_rate
            },
        ):
            if not collected_enough:
                initial_frames.append(chunk.audio)
                if len(initial_frames) >= min_initial_frames:
                    collected_enough = True
                    # Play all initial frames at once
                    buffer = b''.join(initial_frames)
                    self.stream.write(buffer)
                    
                    # Report initial latency
                    latency = time.time() - start_time
                    print(f"Initial latency: {latency:.3f} seconds")
            else:
                # Play each subsequent chunk as it arrives
                self.stream.write(chunk.audio)
```

## 2. Multi-utterance Streaming with Context Reuse

For sequences of related utterances, reuse the same context to maintain continuity:

```python
import threading
import uuid
from cartesia import Cartesia

class ContinuousTTS:
    def __init__(self, api_key):
        self.client = Cartesia(api_key=api_key)
        self.ws = self.client.tts.websocket()
        self.current_context_id = None
        self.context_lock = threading.Lock()
        
    def speak_sequence(self, sentences, voice_id, pause_seconds=0.5):
        """Speak a sequence of sentences in the same context"""
        # Create a consistent context
        with self.context_lock:
            if not self.current_context_id:
                self.current_context_id = str(uuid.uuid4())
            context_id = self.current_context_id
        
        # Speak first sentence normally
        first = True
        
        for sentence in sentences:
            for chunk in self.ws.send(
                model_id="sonic",
                transcript=sentence,
                voice={"mode": "id", "id": voice_id},
                context_id=context_id,
                # This is the key for continuation - only set continue=True
                # after the first sentence
                continue_=not first, 
                output_format={
                    "container": "raw",
                    "encoding": "pcm_f32le", 
                    "sample_rate": 22050
                },
            ):
                # Process audio data
                process_audio(chunk.audio)
                
            first = False
            
            # Small pause between sentences
            if pause_seconds > 0:
                time.sleep(pause_seconds)
```

## 3. Adaptive Speech Control with Flush and Continue

For real-time adaptive speech that responds to changing conditions:

```python
import asyncio
from cartesia import AsyncCartesia

async def adaptive_tts():
    client = AsyncCartesia(api_key="your_api_key")
    ws = await client.tts.websocket()
    context = ws.context()
    
    # Start with standard speech
    await context.send(
        model_id="sonic",
        transcript="I'm beginning with normal speech parameters.",
        voice={"id": "your-voice-id"},
        output_format={"container": "raw", "encoding": "pcm_f32le", "sample_rate": 22050},
    )
    
    # Process audio chunks
    async def process_chunks():
        async for chunk in context.receive():
            await process_audio(chunk.audio)
    
    # Start processing task
    process_task = asyncio.create_task(process_chunks())
    
    # After some event, adapt the speech (e.g., sensor detects noise)
    await asyncio.sleep(2)  # Simulate waiting for an event
    
    # Flush current generation
    flush_gen = await context.flush()
    async for chunk in flush_gen():
        await process_audio(chunk.audio)
    
    # Continue with adapted parameters
    await context.send(
        model_id="sonic",
        transcript="Now I'm speaking with adapted parameters based on environmental conditions.",
        voice={
            "id": "your-voice-id",
            "experimental_controls": {
                "speed": 0.8,  # Slower to compensate for noise
                "emotion": ["positivity:high"]  # More emphatic
            }
        },
        output_format={"container": "raw", "encoding": "pcm_f32le", "sample_rate": 22050},
        continue_=True,
    )
    
    # Wait for processing to complete
    await process_task
```

## 4. Streaming TTS with Real-time Word Timestamps

For animations or highlighting text as it's spoken:

```python
from cartesia import Cartesia

def tts_with_timestamps(text, voice_id):
    client = Cartesia(api_key="your_api_key")
    ws = client.tts.websocket()
    
    # Request with add_timestamps=True
    for chunk in ws.send(
        model_id="sonic",
        transcript=text,
        voice={"mode": "id", "id": voice_id},
        output_format={
            "container": "raw",
            "encoding": "pcm_f32le", 
            "sample_rate": 22050
        },
        add_timestamps=True,
    ):
        # Process audio
        if chunk.audio:
            process_audio(chunk.audio)
        
        # Process word timestamps when available
        if chunk.word_timestamps:
            for i, word in enumerate(chunk.word_timestamps.words):
                start_time = chunk.word_timestamps.start[i]
                end_time = chunk.word_timestamps.end[i]
                print(f"Word: {word}, Start: {start_time}s, End: {end_time}s")
                
                # Use timestamps for synchronization with UI
                highlight_word_in_ui(word, start_time, end_time)
```

## 5. Parallel Context Management for Multiple Audio Streams

For applications needing multiple simultaneous speech streams:

```python
import threading
import uuid
from queue import Queue
from cartesia import Cartesia

class MultiStreamTTS:
    def __init__(self, api_key):
        self.client = Cartesia(api_key=api_key)
        self.ws = self.client.tts.websocket()
        self.streams = {}  # Dict of active streams by ID
        self.lock = threading.Lock()
        
    def create_stream(self, stream_id=None):
        """Create a new audio stream with dedicated context"""
        if not stream_id:
            stream_id = str(uuid.uuid4())
            
        with self.lock:
            if stream_id in self.streams:
                raise ValueError(f"Stream {stream_id} already exists")
                
            # Create dedicated context and audio queue
            context_id = str(uuid.uuid4())
            audio_queue = Queue()
            
            # Store stream data
            self.streams[stream_id] = {
                "context_id": context_id,
                "queue": audio_queue,
                "active": True,
                "thread": None
            }
            
        return stream_id
    
    def speak_on_stream(self, stream_id, text, voice_id):
        """Speak text on a specific stream"""
        if stream_id not in self.streams:
            raise ValueError(f"Stream {stream_id} doesn't exist")
            
        stream_data = self.streams[stream_id]
        context_id = stream_data["context_id"]
        
        # Start processing thread if not running
        if not stream_data["thread"] or not stream_data["thread"].is_alive():
            stream_data["thread"] = threading.Thread(
                target=self._process_stream,
                args=(stream_id,),
                daemon=True
            )
            stream_data["thread"].start()
        
        # Generate audio on the specified context
        for chunk in self.ws.send(
            model_id="sonic",
            transcript=text,
            voice={"mode": "id", "id": voice_id},
            context_id=context_id,
            output_format={
                "container": "raw",
                "encoding": "pcm_f32le", 
                "sample_rate": 22050
            },
        ):
            # Queue audio for the stream's processor
            stream_data["queue"].put(chunk.audio)
    
    def interrupt_stream(self, stream_id, new_text=None, voice_id=None):
        """Interrupt a stream and optionally start new speech"""
        if stream_id not in self.streams:
            raise ValueError(f"Stream {stream_id} doesn't exist")
            
        stream_data = self.streams[stream_id]
        old_context_id = stream_data["context_id"]
        
        # Cancel the current context
        cancel_request = {
            "context_id": old_context_id,
            "cancel": True
        }
        self.ws.websocket.send(json.dumps(cancel_request))
        self.ws._remove_context(old_context_id)
        
        # Clear the audio queue
        while not stream_data["queue"].empty():
            try:
                stream_data["queue"].get_nowait()
                stream_data["queue"].task_done()
            except queue.Empty:
                break
                
        # Create new context for the stream
        new_context_id = str(uuid.uuid4())
        stream_data["context_id"] = new_context_id
        
        # Optionally start new speech
        if new_text and voice_id:
            self.speak_on_stream(stream_id, new_text, voice_id)
    
    def _process_stream(self, stream_id):
        """Process audio for a specific stream"""
        stream_data = self.streams[stream_id]
        
        while stream_data["active"]:
            try:
                # Get audio with timeout to check active flag
                audio = stream_data["queue"].get(timeout=0.5)
                
                # Process audio (implementation depends on your setup)
                process_audio_for_stream(stream_id, audio)
                
                stream_data["queue"].task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error processing stream {stream_id}: {e}")
                
    def close_stream(self, stream_id):
        """Close a specific stream"""
        if stream_id in self.streams:
            stream_data = self.streams[stream_id]
            
            # Cancel context if exists
            context_id = stream_data["context_id"]
            try:
                cancel_request = {
                    "context_id": context_id,
                    "cancel": True
                }
                self.ws.websocket.send(json.dumps(cancel_request))
                self.ws._remove_context(context_id)
            except:
                pass
                
            # Mark stream as inactive
            stream_data["active"] = False
            
            # Wait for thread to finish
            if stream_data["thread"] and stream_data["thread"].is_alive():
                stream_data["thread"].join(timeout=1.0)
                
            # Remove from streams dict
            with self.lock:
                del self.streams[stream_id]
```

## 6. Advanced Error Recovery

For robust production applications:

```python
import time
import threading
import random

class RobustTTS:
    def __init__(self, api_key):
        self.api_key = api_key
        self.client = None
        self.ws = None
        self.reconnect_lock = threading.Lock()
        self.initialize_client()
        
    def initialize_client(self):
        """Initialize or reinitialize the client connection"""
        with self.reconnect_lock:
            try:
                if self.ws:
                    try:
                        self.ws.close()
                    except:
                        pass
                
                self.client = Cartesia(api_key=self.api_key)
                self.ws = self.client.tts.websocket()
                return True
            except Exception as e:
                print(f"Failed to initialize client: {e}")
                return False
    
    def speak_with_retry(self, text, voice_id, max_retries=3):
        """Speak with automatic error recovery and retry"""
        attempt = 0
        backoff = 1.0  # Base backoff in seconds
        
        while attempt < max_retries:
            try:
                # Ensure connection is active
                if self.ws._is_websocket_closed():
                    self.initialize_client()
                
                # Generate audio
                for chunk in self.ws.send(
                    model_id="sonic",
                    transcript=text,
                    voice={"mode": "id", "id": voice_id},
                    output_format={
                        "container": "raw",
                        "encoding": "pcm_f32le", 
                        "sample_rate": 22050
                    },
                ):
                    # Process audio
                    process_audio(chunk.audio)
                
                # Success - exit retry loop
                return True
                
            except Exception as e:
                attempt += 1
                error_type = type(e).__name__
                
                print(f"TTS error ({error_type}): {e}")
                print(f"Attempt {attempt} of {max_retries} failed")
                
                if attempt >= max_retries:
                    print("Max retries exceeded, giving up")
                    return False
                
                # Calculate jittered exponential backoff
                sleep_time = backoff * (1 + random.random() * 0.5)
                print(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                backoff *= 2  # Exponential backoff
                
                # Force reconnection
                self.initialize_client()
```

## Conclusion

These advanced patterns demonstrate the flexibility of Cartesia's WebSocket API for building sophisticated TTS applications. By leveraging contexts, flushing, continuation, and proper error handling, you can create robust, responsive speech systems that adapt to user needs in real-time.

For the best results:

1. **Minimize Latency**: Pre-buffer initial frames and maintain persistent connections
2. **Manage Contexts**: Use context reuse for related utterances and create new contexts for interruptions
3. **Handle Errors**: Implement robust error recovery and reconnection logic
4. **Coordinate UI**: Use timestamps for synchronizing audio with visual elements
5. **Optimize Resource Usage**: Close unused contexts and properly manage WebSocket connections