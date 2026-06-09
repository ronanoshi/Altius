from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    """
    Minimal interface for LLM interactions.
    Swap OpenAIClient for any other provider by implementing this.
    """

    @abstractmethod
    async def chat_json(self, system: str, user: str) -> dict:
        """
        Send a system + user message expecting a JSON response.
        The caller is responsible for the prompt; the client handles transport.
        """
        ...

    @abstractmethod
    async def chat(self, system: str, user: str) -> str:
        """
        Send a system + user message and return the plain-text response.
        Used for free-form answers (chat, summaries) where JSON is not needed.
        """
        ...
