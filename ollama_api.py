import ollama

llm = "llama3.1"

def sentence_buffer(input):
    """
    Accumulate characters and yield sentences.
    Intelligently splits text at sentence boundaries (., ?, !) and commas,
    while avoiding splitting numbers and preserving natural speech chunks for TTS.
    
    For faster initial output:
    - First chunk yields at the first comma (if present)
    - Subsequent chunks yield at full sentence boundaries (., ?, !)
    """
    
    buffer = ""
    first_chunk = True  # Track if this is the first chunk
    
    for each in input:
        buffer += each
        
        # Check for appropriate punctuation based on whether this is the first chunk
        if buffer:
            # For first chunk, split on commas too for faster initial output
            valid_split_chars = ".?!," if first_chunk else ".?!"
            
            if buffer[-1] in valid_split_chars:
                # Don't split if it's a number with decimal point (e.g., 1.0, 3.14, etc.)
                if buffer[-1] == "." and len(buffer) >= 2:
                    # Check if the character before the period is a digit and after is a digit or space
                    if (buffer[-2].isdigit() and 
                        (len(buffer) == 2 or not buffer[-3:].strip().replace('.', '').isdigit())):
                        continue
                
                # Don't split on decimal points within numbers (e.g., 1.000)
                if buffer[-1] == "." and len(buffer) >= 2 and buffer[-2].isdigit():
                    # Look ahead to see if this is part of a number
                    next_char = next((c for c in input), "")
                    if next_char.isdigit():
                        continue
                
                # Yield the buffer as a sentence chunk
                yield buffer
                buffer = ""
                
                # After first yield, switch to full sentence mode
                if first_chunk:
                    first_chunk = False
    
    # Don't forget any remaining text
    if buffer:
        yield buffer


def get_ollama_api(messages, max_tokens=1000, stream=True, model=llm, keep_alive=-1):
    # Ensure messages is a list of dictionaries
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
          # 'num_ctx': 131072,  # Set context size to 128K tokens
            'keep_alive': keep_alive  # Set to -1 to keep the model loaded indefinitely
        }
    )

    if stream:
        # For streaming, we'll return a generator that yields processed chunks
        def response_generator():
            for chunk in response:
                yield chunk['message']['content']
        return response_generator()
    else:
        # For non-streaming, we'll return the full response
        return response['message']['content']

if __name__ == '__main__':
    model = llm
    messages = [
        {'role': 'system', 'content': 'You are a helpful assistant.'},
        {'role': 'user', 'content': '  Tell me a story.'},
    ]

    # For streaming
    print("Streaming response:")
    stream_response = sentence_buffer(get_ollama_api(messages, stream=True))
    for chunk in stream_response:
        print(chunk, end='', flush=True)
    print("\n")  # New line after streaming
    import time

    # For streaming with timing
    print("\nStreaming response with timing:")
    start_time = time.time()
    stream_response = get_ollama_api(messages, stream=True)
    first_chunk = True
    for chunk in stream_response:
        if first_chunk:
            first_chunk_time = time.time()
            print(f"Time to first chunk: {first_chunk_time - start_time:.3f} seconds")
            first_chunk = False
        print(chunk, end='', flush=True)
    end_time = time.time()
    print(f"\nTotal response time: {end_time - start_time:.3f} seconds")
    print()

    # For non-streaming
    print("Non-streaming response:")
    response = get_ollama_api(messages, stream=False)
    print(response)
