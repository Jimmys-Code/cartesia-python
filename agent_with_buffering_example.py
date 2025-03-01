import sys
from agent import Agent
from ollama_api import sentence_buffer

def main():
    """
    Demonstrates how to use the Agent class with optional sentence buffering.
    
    This example shows two approaches:
    1. Using the Agent directly (raw streaming without sentence buffering)
    2. Using the Agent with sentence buffering for TTS-friendly output
    """
    # Create an agent with a custom system prompt
    agent = Agent(system_prompt="You are a helpful and knowledgeable assistant.")
    
    print("\n=== Example 1: Agent without sentence buffering ===")
    query = "Explain the difference between Python and JavaScript in a few sentences."
    print(f"User: {query}")
    print("Assistant: ", end="", flush=True)
    
    # Direct streaming without sentence buffering
    for chunk in agent.ask(query):
        print(chunk, end="", flush=True)
    print("\n")
    
    print("\n=== Example 2: Agent with sentence buffering ===")
    query = "List 3 facts about space exploration, including some numbers like 1.5 million km."
    print(f"User: {query}")
    print("Assistant: ", end="", flush=True)
    
    # Get the raw stream from the agent
    raw_stream = agent.ask(query)
    
    # Wrap it with sentence buffering
    buffered_stream = sentence_buffer(raw_stream)
    
    # Process complete sentences
    for sentence in buffered_stream:
        print(f"\n[SENTENCE]: {sentence}")
        # In a real application, you would send each sentence to TTS here
        # tts.speak(sentence)
    
    print("\n\nConversation history:")
    for msg in agent.get_history():
        role = msg["role"]
        # Truncate content if too long for display
        content = msg["content"]
        if len(content) > 60:
            content = content[:57] + "..."
        print(f"{role}: {content}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
