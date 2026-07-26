import abc


class LLMClient(abc.ABC):
    """Pluggable LLM backend interface. All prompts expect JSON-only responses."""

    @abc.abstractmethod
    def complete_json(self, system_prompt, user_prompt):
        """Send a prompt, return parsed JSON (dict). Raises ValueError on bad output."""
        raise NotImplementedError

    @abc.abstractmethod
    def complete_text(self, system_prompt, user_prompt):
        """Send a prompt, return plain text response."""
        raise NotImplementedError

    @abc.abstractmethod
    def stream_text(self, system_prompt, user_prompt):
        """Send a prompt, yield text chunks as they arrive (generator)."""
        raise NotImplementedError
