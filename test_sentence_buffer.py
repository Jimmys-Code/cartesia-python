from ollama_api import sentence_buffer

def simulate_streaming_input(text, chunk_size=3):
    """Simulate streaming input by yielding small chunks of text."""
    for i in range(0, len(text), chunk_size):
        yield text[i:i+chunk_size]

def test_sentence_buffer():
    """Test the modified sentence buffer function."""
    print("Testing modified sentence_buffer function\n")
    
    # Test case 1: Text with commas and periods
    test_text = "Hello, this is a test, with multiple commas. This is the second sentence! And a third? With numbers like 3.14 and 1.000 intact."
    
    print(f"Original text: {test_text}\n")
    print("Buffered output:")
    
    # Simulate streaming input
    stream = simulate_streaming_input(test_text)
    
    # Use the sentence buffer
    buffered = sentence_buffer(stream)
    
    # Print each buffered chunk with its position
    for i, chunk in enumerate(buffered, 1):
        print(f"Chunk {i}: {chunk}")

if __name__ == "__main__":
    test_sentence_buffer()
