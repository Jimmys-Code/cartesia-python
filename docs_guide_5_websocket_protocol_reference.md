# Cartesia TTS WebSocket Protocol Reference

## Introduction

This technical reference documents the WebSocket protocol used by Cartesia's TTS system. Understanding the protocol details enables advanced usage, troubleshooting, and custom implementations.

## Connection

### WebSocket URL Structure

```
wss://api.cartesia.ai/tts/websocket?api_key={API_KEY}&cartesia_version={VERSION}
```

### Connection Parameters

| Parameter | Description |
|-----------|-------------|
| `api_key` | Your Cartesia API key |
| `cartesia_version` | API version string (e.g., "2023-04-12") |

### Connection Example

```python
import websockets

async def connect():
    uri = f"wss://api.cartesia.ai/tts/websocket?api_key={API_KEY}&cartesia_version={VERSION}"
    async with websockets.connect(uri) as websocket:
        # Connection established
        # Now you can send/receive messages
```

## Message Structure

All messages are JSON objects with type-specific fields.

### Request Types

#### 1. GenerationRequest

Requests audio generation for a transcript.

```json
{
  "model_id": "sonic",
  "transcript": "Text to synthesize",
  "voice": {
    "mode": "id",
    "id": "694f9389-aac1-45b6-b726-9d9369183238",
    "experimental_controls": {
      "speed": 0.5,
      "emotion": ["positivity", "curiosity:low"]
    }
  },
  "output_format": {
    "container": "raw",
    "encoding": "pcm_f32le",
    "sample_rate": 44100
  },
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "continue": false,
  "flush": false,
  "add_timestamps": false,
  "language": "en"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_id` | string | Yes | TTS model identifier |
| `transcript` | string | Yes | Text to synthesize |
| `voice` | object | Yes | Voice specification |
| `output_format` | object | Yes | Audio format configuration |
| `context_id` | string | No | Identifier for streaming context |
| `continue` | boolean | No | Indicates if request continues a previous one |
| `flush` | boolean | No | Triggers a flush of the current generation |
| `add_timestamps` | boolean | No | Enables word/phoneme timestamps |
| `language` | string | No | Language code |

#### 2. CancelContextRequest

Cancels an ongoing generation for a specific context.

```json
{
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "cancel": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `context_id` | string | Yes | Context to cancel |
| `cancel` | boolean | Yes | Must be `true` |

### Response Types

Responses are JSON objects with a `type` field that indicates the response type.

#### 1. WebSocketResponse_Chunk

Contains audio data for streaming.

```json
{
  "type": "chunk",
  "data": "base64-encoded-audio-data",
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "step_time": 0.123
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always "chunk" |
| `data` | string | Base64-encoded audio data |
| `context_id` | string | Associated context ID |
| `step_time` | number | Processing time information |

#### 2. WebSocketResponse_Done

Signals completion of audio generation for a context.

```json
{
  "type": "done",
  "context_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always "done" |
| `context_id` | string | Associated context ID |

#### 3. WebSocketResponse_FlushDone

Indicates completion of a flush operation.

```json
{
  "type": "flush_done",
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "flush_id": 1,
  "flush_done": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always "flush_done" |
| `context_id` | string | Associated context ID |
| `flush_id` | integer | Identifier for the flush operation |
| `flush_done` | boolean | Always true |

#### 4. WebSocketResponse_Timestamps

Contains word-level timing information.

```json
{
  "type": "timestamps",
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "word_timestamps": {
    "words": ["word1", "word2", "word3"],
    "start": [0.1, 0.5, 0.9],
    "end": [0.4, 0.8, 1.2]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always "timestamps" |
| `context_id` | string | Associated context ID |
| `word_timestamps` | object | Word timing data |

#### 5. WebSocketResponse_PhonemeTimestamps

Contains phoneme-level timing information.

```json
{
  "type": "phoneme_timestamps",
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "phoneme_timestamps": {
    "phonemes": ["p", "uh", "n", "d"],
    "start": [0.05, 0.1, 0.2, 0.3],
    "end": [0.09, 0.19, 0.29, 0.4]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always "phoneme_timestamps" |
| `context_id` | string | Associated context ID |
| `phoneme_timestamps` | object | Phoneme timing data |

#### 6. WebSocketResponse_Error

Contains error information.

```json
{
  "type": "error",
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "error": "Error message details"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always "error" |
| `context_id` | string | Associated context ID |
| `error` | string | Error message |

## Context Management

Contexts are the fundamental mechanism for managing streaming and state in the WebSocket API.

### Context Creation

Contexts are created:
1. Automatically when sending a `GenerationRequest` without a `context_id`
2. Explicitly by providing a new `context_id` in a `GenerationRequest`

### Context Reuse

To continue generation in the same context:
1. Use the same `context_id` in subsequent requests
2. Set `continue` to `true` to indicate continuation

### Context Termination

Contexts are terminated under the following conditions:
1. Server sends a `WebSocketResponse_Done`
2. Client sends a `CancelContextRequest`
3. An error occurs during processing
4. The WebSocket connection is closed

## Special Operations

### Flushing

Flushing allows resetting the generation state while maintaining the context:

1. Send a `GenerationRequest` with `flush: true`
2. The server will respond with a `WebSocketResponse_FlushDone` after completing pending audio
3. New audio generation can continue on the same context

Example flush request:
```json
{
  "model_id": "sonic",
  "transcript": "",
  "voice": {...},
  "output_format": {...},
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "continue": true,
  "flush": true
}
```

### Immediate Cancellation

For immediate interruption of audio generation:

1. Send a `CancelContextRequest` with the context ID
2. Create a new context for subsequent audio

Example cancel request:
```json
{
  "context_id": "550e8400-e29b-41d4-a716-446655440000",
  "cancel": true
}
```

## Common Patterns

### Basic Audio Generation

```
Client                          Server
  |                               |
  |-- GenerationRequest --------->|
  |                               |
  |<-------- Chunk ---------------|
  |<-------- Chunk ---------------|
  |<-------- Chunk ---------------|
  |<-------- Done ----------------|
  |                               |
```

### Chunked Text Input

```
Client                          Server
  |                               |
  |-- GenerationRequest --------->|
  |   (transcript: "Hello")       |
  |                               |
  |<-------- Chunk ---------------|
  |                               |
  |-- GenerationRequest --------->|
  |   (continue: true,            |
  |    transcript: " world")      |
  |                               |
  |<-------- Chunk ---------------|
  |<-------- Chunk ---------------|
  |                               |
  |-- GenerationRequest --------->|
  |   (continue: false,           |
  |    transcript: "")            |
  |                               |
  |<-------- Done ----------------|
  |                               |
```

### Cancellation

```
Client                          Server
  |                               |
  |-- GenerationRequest --------->|
  |                               |
  |<-------- Chunk ---------------|
  |<-------- Chunk ---------------|
  |                               |
  |-- CancelContextRequest ------>|
  |                               |
  |<-------- Done ----------------|
  |                               |
```

### Flushing

```
Client                          Server
  |                               |
  |-- GenerationRequest --------->|
  |                               |
  |<-------- Chunk ---------------|
  |<-------- Chunk ---------------|
  |                               |
  |-- GenerationRequest --------->|
  |   (flush: true,               |
  |    continue: true)            |
  |                               |
  |<-------- Chunk ---------------|
  |<-------- FlushDone (id:0) ----|
  |                               |
  |-- GenerationRequest --------->|
  |   (continue: true)            |
  |                               |
  |<-------- Chunk ---------------|
  |<-------- Chunk ---------------|
  |<-------- Done ----------------|
  |                               |
```

## Error Handling

### Common Error Scenarios

1. **Invalid API Key**: Connection will fail with HTTP 401
2. **Invalid Parameters**: Server responds with Error message
3. **Rate Limiting**: Connection may close with HTTP 429
4. **Server Errors**: Connection may close with HTTP 5xx

### Best Practices

1. Implement automatic reconnection with exponential backoff
2. Handle specific error types appropriately
3. Maintain context state locally to recover from disconnections
4. Implement end-to-end error recovery strategies

## Performance Considerations

1. **Latency**: Keep WebSocket connections open for faster response
2. **Buffer Management**: Implement appropriate buffer sizes for your application
3. **Context Reuse**: Reuse contexts when possible to avoid initialization overhead
4. **Connection Management**: Implement proper connection lifecycle handling

## Security Considerations

1. **API Key**: Never expose your API key in client-side code
2. **Connection Handling**: Implement proper WebSocket security practices
3. **Error Exposure**: Do not expose raw error messages to end users
4. **Input Validation**: Validate all inputs before sending to the server

This reference documents the Cartesia TTS WebSocket protocol as of the current API version. For the most up-to-date information, consult the official Cartesia documentation.