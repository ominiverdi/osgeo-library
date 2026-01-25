"""LLM client utilities for doclibrary."""

import re
from typing import Dict, List, Optional

import requests


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> tags from LLM output.

    Some models (like Qwen3) include thinking/reasoning in <think> tags.
    This function removes them for cleaner output.

    Args:
        text: Text that may contain <think> tags

    Returns:
        Text with <think> tags and their content removed
    """
    if not text:
        return text
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


class LLMClient:
    """OpenAI-compatible LLM client.

    Supports local llama.cpp servers and remote APIs like OpenRouter.

    Args:
        url: API endpoint URL (e.g., "http://localhost:8080/v1/chat/completions")
        model: Model name
        api_key: API key (optional for local servers)
        temperature: Sampling temperature (default 0.3)
        max_tokens: Maximum tokens in response (default 1024)
    """

    def __init__(
        self,
        url: str,
        model: str,
        api_key: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ):
        self.url = url
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send chat request to LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            Response content string

        Raises:
            Exception: On API errors
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            # OpenRouter requires HTTP-Referer for free tier models
            headers["HTTP-Referer"] = "https://github.com/ominiverdi/osgeo-library"

        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature or self.temperature,
                "max_tokens": max_tokens or self.max_tokens,
            },
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        # Remove thinking tags if present
        return strip_think_tags(content)

    def check_health(self) -> bool:
        """Check if LLM server is reachable.

        Returns:
            True if server responds to health check
        """
        try:
            health_url = self.url.replace("/v1/chat/completions", "/health")
            response = requests.get(health_url, timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False


def check_llm_health(url: str) -> bool:
    """Check if LLM server is reachable.

    Args:
        url: LLM API URL

    Returns:
        True if server responds to health check
    """
    try:
        health_url = url.replace("/v1/chat/completions", "/health")
        response = requests.get(health_url, timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def chat(prompt: str, context: Optional[str] = None) -> str:
    """Simple chat function for quick queries.

    Uses config for LLM settings.

    Args:
        prompt: User question/prompt
        context: Optional context to include

    Returns:
        LLM response string
    """
    from doclibrary.config import config

    messages = []
    if context:
        messages.append({"role": "system", "content": f"Context:\n{context}"})
    messages.append({"role": "user", "content": prompt})

    return query_llm(
        messages=messages,
        url=config.llm_url,
        model=config.llm_model,
        api_key=config.llm_api_key,
    )


def query_llm(
    messages: List[Dict[str, str]],
    url: str,
    model: str,
    api_key: str = "",
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """Query LLM with messages.

    Convenience function that creates a temporary LLMClient.

    Args:
        messages: List of message dicts
        url: API endpoint URL
        model: Model name
        api_key: API key (optional)
        temperature: Sampling temperature
        max_tokens: Maximum response tokens

    Returns:
        Response content string, or error message on failure
    """
    try:
        client = LLMClient(
            url=url,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return client.chat(messages)
    except Exception as e:
        return f"Error querying LLM: {e}"
