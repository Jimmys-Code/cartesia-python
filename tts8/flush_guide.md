Flushing Audio in Cartesia’s Streaming TTS WebSocket API

Flushing audio in Cartesia’s Voice AI Text-to-Speech (TTS) WebSocket API means stopping or finalizing the current speech output without closing the WebSocket connection. This is useful for real-time voice applications – for example, when you need to interrupt or end the TTS output (such as on a user interruption) but keep the connection alive for subsequent requests. Cartesia’s API uses a context-based approach for streaming TTS, and it provides a specific way to flush or cancel audio output on a given context while leaving the WebSocket open. Below is a detailed guide on how to correctly flush audio, the required API calls/parameters, how it affects queued audio, and an example implementation in Python.

Using Contexts for Streaming and Flushing Audio

Cartesia’s WebSocket TTS API organizes streaming audio by contexts. A context represents a continuous speech generation session that can span multiple input segments (maintaining prosody across them). When streaming text incrementally (e.g., from an LLM), you assign the same context_id to each segment of text. By default, each TTS request is treated as final unless you explicitly indicate more input will follow. Key points about using contexts:
	•	Continuing a context: To send multiple segments of text that should be spoken as one continuous utterance, include a continue: true flag in every generation request except the last. This tells the API that more text will follow for that context ￼. For example, you might send a first chunk of text with "continue": true, then later send the next chunk with the same context_id. The TTS engine will maintain voice tone and rhythm across these segments.
	•	Finalizing a context: For the last segment (or if you only have one), use continue: false (or omit it, since false is the default) to indicate the speech is complete ￼. This final “false” signals the API to wrap up any remaining audio for that context. If you aren’t sure when the last segment is, you can even send an empty string transcript with continue: false as a way to gracefully end the context ￼.

Using continue: false on the final input effectively flushes the remaining audio for that context – ensuring all buffered text is synthesized – without closing the WebSocket connection. This is analogous to a flush in other TTS APIs: it finalizes the output so far while keeping the session open for new contexts or requests.

Canceling a Context to Flush Pending Audio (Keep Connection Open)

If you need to immediately stop or flush ongoing audio output (for example, to interrupt a speaking voice mid-sentence), you should use Cartesia’s cancel context feature. The WebSocket API allows sending a Cancel Context request, which stops further audio on a given context while leaving the WebSocket itself open for future use. This is the correct method to “flush” the audio output of that context without tearing down the connection.

API Call / JSON Structure: To cancel (flush) a context, send a JSON message over the WebSocket with the following structure ￼:

{
  "context_id": "<your-context-id>",
  "cancel": true
}

This message should be sent on the established WebSocket (just like a generation request). In Cartesia’s Python SDK, for example, you can call the WebSocket’s send method with cancel=True and the target context_id to achieve this (under the hood it sends the above JSON). Ensure the context_id exactly matches the one you want to cancel ￼.

What happens when you send a cancel: The Cartesia API documentation specifies two important effects of a cancel (flush) request:
	•	It halts any requests that have not yet started generating a response ￼. In other words, if there are queued TTS inputs that the server hasn’t begun processing (e.g. a second or third segment in the context pipeline), those will be aborted and no audio will be generated for them.
	•	If a request is already in progress (currently generating audio), that request will continue sending responses until completion ￼. This means the TTS will finish the chunk of audio it’s actively generating at the moment of cancellation, and then stop. The WebSocket will typically send a final message of type "done" for that context once the current audio is done, confirming the cancellation of any remaining queue.

Crucially, using the cancel mechanism does not close the WebSocket connection. Only the specified TTS context is affected (flushed), while the socket remains open and can be reused for new TTS requests or new contexts. This contrasts with simply closing the socket to stop audio (which would drop the connection entirely). Cartesia’s design supports long-lived WebSocket connections for efficiency, so you should cancel contexts to stop audio rather than closing and reopening sockets frequently.

Effects of Flushing on Ongoing and Pending Audio

When you flush audio via the cancel request, it’s important to understand how it impacts the audio that’s currently playing versus what’s queued up:
	•	Ongoing audio: If the TTS engine is partway through generating a response for your text, that generation will run to completion for the current segment. The already-streaming audio frames will continue until the end of that segment. In practice, you might still hear the voice finish the word or sentence it was speaking when you hit flush. The API will send all remaining chunks for that in-progress segment and then issue a "done" message for the context ￼. There is no way to cut off mid-chunk via the API; you can always mute or discard the remaining audio client-side if an immediate cut-off is needed.
	•	Pending/queued audio: Any additional text inputs that were sent on the same context (with continue: true) but whose audio had not started generating will be skipped after the cancel. The cancel request prevents those from ever being synthesized ￼. For example, if you sent three segments A, B, C in a row on the same context, and segment A is playing while B and C are waiting, a cancel will allow A to finish but B and C will be flushed from the queue (no output will be produced for them).

In summary, flushing (via cancel) immediately stops the pipeline after the current audio. The current utterance finishes, everything after it is dropped, and the context is considered done. The WebSocket will remain alive, so you can either start a new context (e.g., respond to an interruption or move to the next dialog turn) or reuse the connection for other tasks. Keep in mind that contexts automatically expire a few seconds after completion or last input, so once you flush (cancel) a context, you’d use a new context_id for subsequent speech in most cases.

Example: Implementing Flush in a Python TTS Streaming System

Below is an example outline of how you might implement streaming TTS with Cartesia’s WebSocket API in Python, including how to flush (cancel) audio on demand. This example uses the Cartesia Python SDK for clarity, but the same principles apply if you use a raw WebSocket connection (you would manually send the JSON messages as shown above). The scenario assumes we want to stream a TTS response that could be interrupted by a user (requiring a flush):

from cartesia import Cartesia

# Initialize Cartesia client and WebSocket
client = Cartesia(api_key="YOUR_API_KEY")
ws = client.tts.websocket()  # Open a persistent TTS WebSocket connection

voice_id = "your-voice-id"   # ID of the voice to use
model_id = "sonic"           # TTS model, e.g., "sonic"
context_id = "conversation-123"  # Unique context ID for this utterance

# Example transcript segments (could also come from streaming LLM output)
text_part1 = "Hello, I am an AI assistant" 
text_part2 = " and I will answer your question."

# Send first part of text with continue=True (more to come)
for chunk in ws.send(model_id=model_id, transcript=text_part1, voice={"id": voice_id}, 
                     context_id=context_id, continue=True, stream=True, 
                     output_format={"container": "raw", "encoding": "pcm_s16le", "sample_rate": 22050}):
    # Process the audio chunk (e.g., play or buffer it)
    play_audio(chunk.audio)  # pseudo-function to play audio bytes
    # Check for an interrupt signal from user
    if user_interrupted():
        # Flush the audio by canceling the context (stop any further TTS for this context)
        ws.send(context_id=context_id, cancel=True)
        break  # exit the loop early since we are flushing
# End for

# If not interrupted, send the continuation (final part) with continue=False to finalize the context
if not user_interrupted():
    for chunk in ws.send(model_id=model_id, transcript=text_part2, voice={"id": voice_id}, 
                         context_id=context_id, continue=False, stream=True,
                         output_format={"container": "raw", "encoding": "pcm_s16le", "sample_rate": 22050}):
        play_audio(chunk.audio)
    # Context is finished normally here (all parts spoken)

In this code:
	•	We open one WebSocket connection (ws) and reuse it for multiple sends. We define a context_id for the utterance so that part1 and part2 are spoken one after the other seamlessly.
	•	The first ws.send(...) sends text_part1 with continue=True, signaling that more text will follow for this context. The stream=True parameter makes the SDK yield audio chunks as they arrive, which we loop over to play audio in real-time.
	•	During playback, we check user_interrupted() (this is a placeholder for whatever logic detects a user interruption or a need to stop speaking). If an interruption occurs, we call ws.send(context_id=context_id, cancel=True) to flush the context. This sends the cancel request JSON ({"context_id": "...", "cancel": true}) over the socket. We then break out of the loop, meaning we stop processing further audio chunks from the first part.
	•	After sending the cancel, the TTS service will finish any chunk currently in progress for text_part1 and then send a "done" message for that context ￼. The pending second part (text_part2) will not be synthesized at all because it wasn’t sent yet in this flow (if it had been sent already with continue, the cancel would prevent it from generating output).
	•	If no interruption occurs, we proceed to send text_part2 with continue=False. This marks the end of the context, prompting Cartesia to finish generating all remaining audio for that context and conclude it. We loop over the returned chunks to play them. Once done, the context auto-expires shortly after.
	•	Throughout this process, the WebSocket connection ws remains open. We did not close it when flushing; we only canceled the specific context. This allows us to reuse ws for the next TTS request or conversation turn (possibly with a new context_id). When completely done with all TTS usage (e.g., application exit or long idle), you can call ws.close() to close the connection.

Important details:
	•	Make sure to use a unique context_id for each independent utterance or dialogue turn. If you reuse a context ID improperly, you might cancel or interfere with the wrong speech. In practice, you can generate a random UUID or a unique token for each context.
	•	Flushing via cancel is optional and only needed for interruption scenarios. If you simply want to end the speech normally, just send the final segment with continue:false (or no continue flag, since false is default). This final segment acts as a flush, ensuring all text is voiced, and you’ll get a "done" event from the API when completed.
	•	The Cartesia API documentation confirms that canceling a context will stop further generation on that context while keeping the WebSocket alive ￼ ￼. Always refer to the latest official docs for any changes. As of the latest version, the steps above align with Cartesia’s recommended approach for managing streaming TTS and flush/stop behavior.

By following this guide, you can manage streaming TTS audio output with Cartesia effectively – letting speech flow in real-time, and flushing (canceling) it when needed – all without incurring the overhead of closing or reopening WebSocket connections for each utterance.

Sources:
	•	Cartesia API Documentation – TTS WebSocket and Contexts ￼ ￼ (excerpts on using continue flags and canceling contexts)
	•	Cartesia API Documentation – Canceling Requests ￼ (behavior of cancel requests on ongoing vs. pending audio)