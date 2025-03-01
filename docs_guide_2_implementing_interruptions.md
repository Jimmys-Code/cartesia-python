# Implementing Immediate TTS Interruptions with Cartesia

## Introduction

A key requirement for many real-time TTS applications is the ability to immediately interrupt ongoing speech to prioritize new content. This guide explains how to implement immediate interruption with Cartesia's WebSocket API.

## Understanding Interruption Mechanisms

Cartesia provides multiple mechanisms for interrupting speech:

1. **Context Cancellation**: Immediately stops audio generation for a context
2. **Flushing**: Completes the current utterance then continues with new content
3. **Context Management**: Creating new contexts while abandoning old ones

For immediate interruption, context cancellation is the most effective approach.

## Implementing Immediate Interruption

### 1. Direct Cancellation Method

The most effective approach for immediate interruption combines:
- Sending an explicit cancellation request to the server
- Removing the context from client-side tracking
- Creating a new context for subsequent speech

```python
import json
import uuid

def interrupt_speech(websocket, current_context_id):
    """Immediately stop speech generation for a context"""
    
    # 1. Send explicit cancellation request to the server
    cancel_request = {
        "context_id": current_context_id,
        "cancel": True
    }
    websocket.websocket.send(json.dumps(cancel_request))
    
    # 2. Clean up client-side tracking
    websocket._remove_context(current_context_id)
    
    # 3. Create a new context ID for subsequent speech
    new_context_id = str(uuid.uuid4())
    
    return new_context_id
```

### 2. Complete Implementation with Queue Management

For a production implementation, you'll typically need to:
1. Cancel the current context
2. Clear any pending text/audio in queues
3. Create a new context
4. Start generating new audio

```python
import threading
import queue
import uuid
import json

class TtsManager:
    def __init__(self, api_key):
        self.client = Cartesia(api_key=api_key)
        self.ws = self.client.tts.websocket()
        self.voice_id = "your-voice-id"
        self.model_id = "sonic"
        
        # Audio setup (with your preferred audio library)
        self.setup_audio()
        
        # Thread-safe state management
        self.current_context_id = None
        self.context_lock = threading.Lock()
        self.text_queue = queue.Queue()
        self.is_speaking = threading.Event()
        
        # Start worker thread
        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(
            target=self.tts_worker,
            daemon=True
        )
        self.worker_thread.start()
    
    def speak(self, text):
        """Queue text to be spoken"""
        self.text_queue.put((text, None))  # None means use existing or create new context
    
    def interrupt_and_speak(self, text):
        """Immediately stop current speech and speak new text"""
        # Cancel current context
        with self.context_lock:
            if self.current_context_id:
                try:
                    # 1. Send explicit cancellation request to server
                    cancel_request = {
                        "context_id": self.current_context_id,
                        "cancel": True
                    }
                    self.ws.websocket.send(json.dumps(cancel_request))
                    
                    # 2. Remove from client-side tracking
                    self.ws._remove_context(self.current_context_id)
                    print(f"Cancelled context {self.current_context_id}")
                except Exception as e:
                    print(f"Error cancelling context: {e}")
        
        # Clear the queue of pending text
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                break
        
        # Add new text with explicit instruction to create new context
        self.text_queue.put((text, "new_context"))
    
    def tts_worker(self):
        """Background worker that processes text from the queue"""
        while not self.stop_event.is_set():
            try:
                # Wait for text in queue with timeout to allow checking stop_event
                try:
                    text, context_action = self.text_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                # Create a new context if needed
                if context_action == "new_context" or self.current_context_id is None:
                    new_context_id = str(uuid.uuid4())
                else:
                    new_context_id = self.current_context_id
                
                # Update current context ID
                with self.context_lock:
                    self.current_context_id = new_context_id
                
                self.is_speaking.set()
                try:
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
                        # Process audio chunk (implementation depends on your audio setup)
                        self.process_audio_chunk(chunk.audio)
                except Exception as e:
                    print(f"Error during speech generation: {e}")
                
                self.is_speaking.clear()
                self.text_queue.task_done()
                
            except Exception as e:
                print(f"Unexpected error in TTS worker: {e}")
    
    # ... Additional methods for initialization, cleanup, etc.
```

## Advanced: Asynchronous Interruption

For asynchronous applications, the pattern is similar but uses async/await:

```python
import asyncio
import uuid
import json

class AsyncTtsManager:
    # ... initialization code ...
    
    async def interrupt_and_speak(self, text):
        """Immediately stop current speech and speak new text"""
        async with self.context_lock:
            if self.current_context_id:
                try:
                    # 1. Cancel context with server
                    cancel_request = {
                        "context_id": self.current_context_id,
                        "cancel": True
                    }
                    await self.ws.websocket.send_json(cancel_request)
                    
                    # 2. Remove from client tracking
                    self.ws._remove_context(self.current_context_id)
                except Exception as e:
                    print(f"Error cancelling context: {e}")
        
        # Clear the queue
        self.text_queue = asyncio.Queue()  # Simply create a new queue
        
        # Queue the new text
        await self.text_queue.put((text, "new_context"))
```

## Alternative: Using the Flush Mechanism

For less urgent interruptions where completing the current word or phrase is acceptable, the flush mechanism provides a smoother transition:

```python
import asyncio
from cartesia import AsyncCartesia

async def tts_with_flush():
    client = AsyncCartesia(api_key="your_api_key")
    ws = await client.tts.websocket()
    context = ws.context()
    
    # Start speaking
    send_task = asyncio.create_task(
        context.send(
            model_id="sonic",
            transcript="This is the first part of the speech that will be flushed.",
            voice={"id": "your-voice-id"},
            output_format={"container": "raw", "encoding": "pcm_f32le", "sample_rate": 22050},
        )
    )
    
    # Receive and process audio
    async def process_audio():
        async for chunk in context.receive():
            # Process audio chunk
            print("Processing chunk...")
    
    process_task = asyncio.create_task(process_audio())
    
    # Wait a bit then flush
    await asyncio.sleep(2)
    print("Flushing...")
    flush_generator = await context.flush()
    
    # Process remaining audio before flush point
    async for chunk in flush_generator():
        print("Processing pre-flush chunk...")
    
    # Send new content after flush
    await context.send(
        model_id="sonic",
        transcript="This is new content after the flush.",
        voice={"id": "your-voice-id"},
        output_format={"container": "raw", "encoding": "pcm_f32le", "sample_rate": 22050},
        continue_=True,  # Important: continue in the same context
    )
    
    # Process will continue in the original process_task
    await asyncio.gather(process_task)
```

## Key Considerations

1. **Timing**: For true immediate interruption, use context cancellation rather than just client-side context removal.

2. **Clean Transitions**: Clear audio buffers and queues when interrupting to prevent "leftover" audio.

3. **Error Handling**: Always implement proper error handling as WebSocket connections may encounter issues.

4. **Context Tracking**: Maintain thread-safe or async-safe context tracking to prevent race conditions.

5. **Resource Cleanup**: Ensure proper cleanup of contexts and connections, especially when your application exits.

Using these patterns, you can implement responsive TTS applications that can immediately adapt to changing speech requirements.