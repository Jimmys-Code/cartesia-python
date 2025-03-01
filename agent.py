import ollama
from typing import List, Dict, Generator, Union, Optional, Any

class Agent:
    """
    A self-contained agent class that maintains conversation history
    and provides streaming responses from an LLM.
    
    Usage:
        agent = Agent(system_prompt="You are a helpful assistant.")
        
        # Streaming usage (yields chunks of text):
        for chunk in agent.ask("Tell me about quantum physics"):
            print(chunk, end="", flush=True)
        
        # Non-streaming usage (returns complete response):
        response = agent.ask("What's the capital of France?", stream=False)
        print(response)
    """
    
    def __init__(
        self, 
        system_prompt: str = "You are a helpful assistant.", 
        model: str = "llama3.1",
        max_tokens: int = 1000,
        keep_alive: int = -1,
        history: Optional[List[Dict[str, str]]] = None
    ):
        """
        Initialize the agent with optional system prompt and history.
        
        Args:
            system_prompt: Initial system prompt to guide the agent's behavior
            model: The LLM model to use (default: "llama3.1")
            max_tokens: Maximum number of tokens to generate per response
            keep_alive: How long to keep the model loaded (-1 = indefinitely)
            history: Optional pre-existing conversation history
        """
        self.model = model
        self.max_tokens = max_tokens
        self.keep_alive = keep_alive
        
        # Initialize history with system prompt if provided
        if history is not None:
            self.history = history
        else:
            self.history = []
            if system_prompt:
                self.history.append({"role": "system", "content": system_prompt})
    
    def ask(
        self, 
        input_text: Union[str, int], 
        stream: bool = True
    ) -> Union[Generator[str, None, None], str]:
        """
        Send a query to the LLM and get a response.
        
        Args:
            input_text: The user's input text or query
            stream: If True, returns a generator that yields text chunks.
                   If False, returns the complete response as a string.
        
        Returns:
            If stream=True: A generator yielding text chunks
            If stream=False: The complete response as a string
        """
        # Add user message to history
        self.history.append({"role": "user", "content": str(input_text)})
        
        # Call Ollama API
        response = ollama.chat(
            model=self.model,
            messages=self.history,
            stream=stream,
            options={
                'num_predict': self.max_tokens,
                'keep_alive': self.keep_alive
            }
        )
        
        if stream:
            # Create a generator that yields text chunks and updates history
            def response_generator():
                full_response = []
                
                for chunk in response:
                    chunk_text = chunk['message']['content']
                    full_response.append(chunk_text)
                    yield chunk_text
                
                # After streaming completes, add the full response to history
                complete_response = ''.join(full_response)
                self.history.append({"role": "assistant", "content": complete_response})
            
            return response_generator()
        else:
            # For non-streaming, get the complete response and update history
            complete_response = response['message']['content']
            self.history.append({"role": "assistant", "content": complete_response})
            return complete_response
    
    def get_history(self) -> List[Dict[str, str]]:
        """Get the current conversation history."""
        return self.history
    
    def clear_history(self, keep_system_prompt: bool = True) -> None:
        """
        Clear the conversation history.
        
        Args:
            keep_system_prompt: If True, retain the system prompt (if any)
        """
        if keep_system_prompt and self.history and self.history[0]["role"] == "system":
            system_prompt = self.history[0]
            self.history = [system_prompt]
        else:
            self.history = []
    
    def add_to_history(self, role: str, content: str) -> None:
        """
        Manually add a message to the conversation history.
        
        Args:
            role: The role of the message sender ("system", "user", or "assistant")
            content: The message content
        """
        if role not in ["system", "user", "assistant"]:
            raise ValueError("Role must be one of: 'system', 'user', 'assistant'")
        
        self.history.append({"role": role, "content": content})


# Example usage
if __name__ == "__main__":
    # Create an agent with a custom system prompt
    agent = Agent(system_prompt="You are a helpful and concise assistant.")
    
    print("Example Agent Usage")
    print("-----------------")
    
    # Example 1: Streaming response
    print("\nStreaming response:")
    user_query = "Tell me a short joke."
    print(f"User: {user_query}")
    print("Assistant: ", end="", flush=True)
    
    for text_chunk in agent.ask(user_query):
        print(text_chunk, end="", flush=True)
    print("\n")
    
    # Example 2: Non-streaming response
    print("\nNon-streaming response:")
    user_query = "What's the capital of France?"
    print(f"User: {user_query}")
    
    response = agent.ask(user_query, stream=False)
    print(f"Assistant: {response}")
    
    # Show conversation history
    print("\nConversation History:")
    for message in agent.get_history():
        print(f"{message['role']}: {message['content']}")
