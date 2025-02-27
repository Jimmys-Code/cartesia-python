import ollama

llm = "llama3.1"

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
        {'role': 'user', 'content': ' Repeat the following sentence back to me. Hello, I am decisive. How can I help you today?'},
    ]

    # For streaming
    print("Streaming response:")
    stream_response = get_ollama_api(messages, stream=True)
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
