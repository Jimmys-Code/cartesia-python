import time
import json
from cartesia import Cartesia

def main():
    # Initialize Cartesia client
    client = Cartesia(api_key="sk_car_GZrgghX4KvqNrc41q7KoB")
    
    # Create a WebSocket connection
    ws = client.tts.websocket()
    
    # Define parameters
    voice_id = "043cfc81-d69f-4bee-ae1e-7862cb358650"
    model_id = "sonic"
    context_id = "test-context-123"
    
    print("Starting TTS generation...")
    
    # Start TTS generation
    for chunk in ws.send(
        model_id=model_id,
        transcript="This is a test of the cancel functionality. This sentence should be interrupted.",
        voice={"mode": "id", "id": voice_id},
        context_id=context_id,
        output_format={"container": "raw", "encoding": "pcm_f32le", "sample_rate": 22050},
    ):
        # Process a few chunks, then cancel
        print("Received audio chunk")
        time.sleep(0.1)
        
        # After a few chunks, cancel the context
        if chunk.context_id == context_id:
            print("Canceling context...")
            
            # Method 1: Using the raw WebSocket
            cancel_request = {
                "context_id": context_id,
                "cancel": True
            }
            ws.websocket.send(json.dumps(cancel_request))
            print("Sent cancel request via raw WebSocket")
            break
    
    # Wait a moment to see what happens
    time.sleep(1)
    
    print("Test complete")
    ws.close()

if __name__ == "__main__":
    main()