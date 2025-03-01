# Understanding the Cartesia TTS WebSocket Architecture

## Overview

Cartesia's TTS WebSocket implementation provides low-latency audio streaming through a well-designed context-based architecture. This guide explains the core components and their interactions.

## Key Components

### 1. WebSocket Connection

The WebSocket connection serves as the persistent communication channel between your application and Cartesia's TTS service:

```python
from cartesia import Cartesia

client = Cartesia(api_key="your_api_key_here")
ws = client.tts.websocket()
```

This connection remains open across multiple audio generations, avoiding the latency of re-establishing connections.

### 2. Contexts

Contexts are the heart of Cartesia's streaming architecture:

- A **context** represents a specific audio generation session
- Each context has a unique `context_id` (auto-generated or user-provided)
- Multiple contexts can exist simultaneously on a single WebSocket connection
- Contexts track state between multiple messages

```python
# Create a context explicitly
context = ws.context()  # Auto-generates a UUID
# Or with specific ID
context = ws.context("my-context-id")

# Context ID is accessible
print(f"Context ID: {context.context_id}")
```

### 3. Message Types

#### Request Messages:

1. **GenerationRequest**: Send text to generate audio
   - Contains model ID, transcript, voice settings, etc.
   - Can include `continue_=True` to signal more text is coming
   - Can include `flush=True` to reset the generation state

2. **CancelContextRequest**: Stop audio generation for a context
   - Contains context ID and `cancel=True`

#### Response Messages:

1. **Chunk**: Contains audio data
2. **Done**: Signals completion of generation
3. **Error**: Contains error information
4. **FlushDone**: Signals completion of a flush operation
5. **Timestamps**: Contains word or phoneme timing information

## Synchronous vs Asynchronous APIs

Cartesia provides both synchronous and asynchronous WebSocket clients:

### Synchronous (Blocking)

```python
from cartesia import Cartesia

client = Cartesia(api_key="your_api_key")
ws = client.tts.websocket()

# Blocking iteration over audio chunks
for chunk in ws.send(
    model_id="sonic",
    transcript="Hello world!",
    voice={"id": "your-voice-id"},
    output_format={
        "container": "raw",
        "encoding": "pcm_f32le", 
        "sample_rate": 22050
    },
):
    # Process audio data
    process_audio(chunk.audio)
```

### Asynchronous (Non-blocking)

```python
import asyncio
from cartesia import AsyncCartesia

async def tts_example():
    client = AsyncCartesia(api_key="your_api_key")
    ws = await client.tts.websocket()
    
    async for chunk in await ws.send(
        model_id="sonic",
        transcript="Hello world!",
        voice={"id": "your-voice-id"},
        output_format={
            "container": "raw",
            "encoding": "pcm_f32le", 
            "sample_rate": 22050
        },
    ):
        # Process audio data asynchronously
        await process_audio(chunk.audio)

asyncio.run(tts_example())
```

## Context Lifecycle

1. **Creation**: Contexts are created explicitly or implicitly when sending a request
2. **Active Use**: Contexts remain active while receiving audio chunks
3. **Completion**: Contexts are automatically closed when a "done" message is received
4. **Cancellation**: Contexts can be manually cancelled when no longer needed
5. **Cleanup**: Resources are released when contexts are closed

Understanding this architecture is fundamental to implementing advanced streaming features like interruption, which we'll cover in the next guide.