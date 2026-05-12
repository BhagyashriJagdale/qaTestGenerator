"""
LLM client abstraction supporting multiple providers (OpenAI, Anthropic).
Provider is selected via the LLM_PROVIDER environment variable.
"""

import json
import threading
from abc import ABC, abstractmethod
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings


class BaseLLMClient(ABC):
    """Abstract base for LLM provider clients."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str: ...

    @abstractmethod
    def generate_json(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> dict: ...

    @abstractmethod
    def generate_with_context(
        self,
        system_prompt: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str: ...


class OpenAIClient(BaseLLMClient):
    """OpenAI (or compatible) LLM client."""

    def __init__(self):
        import openai
        import os
        settings = get_settings()
        base_url = os.environ.get("OPENAI_BASE_URL", None)
        self.client = openai.OpenAI(
            api_key=settings.openai_api_key,
            base_url=base_url
        )
        self.model = settings.model_name
        self.max_tokens = settings.max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate(self, system_prompt, user_message, temperature=0.7, max_tokens=None) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_json(self, system_prompt, user_message, temperature=0.3, max_tokens=None) -> dict:
        json_system_prompt = (
            f"{system_prompt}\n\n"
            "IMPORTANT: You must respond with valid JSON only. No markdown, no explanation, just the JSON object."
        )
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": json_system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return _parse_json_safe(response.choices[0].message.content)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_with_context(self, system_prompt, messages, temperature=0.7, max_tokens=None) -> str:
        all_messages = [{"role": "system", "content": system_prompt}] + messages
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=all_messages,
        )
        return response.choices[0].message.content


class ClaudeClient(BaseLLMClient):
    """Anthropic Claude LLM client."""

    def __init__(self):
        import anthropic
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.model_name
        self.max_tokens = settings.max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate(self, system_prompt, user_message, temperature=0.7, max_tokens=None) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=temperature,
        )
        return response.content[0].text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_json(self, system_prompt, user_message, temperature=0.3, max_tokens=None) -> dict:
        json_system_prompt = (
            f"{system_prompt}\n\n"
            "IMPORTANT: You must respond with valid JSON only. No markdown, no explanation, just the JSON object."
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            system=json_system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=temperature,
        )
        return _parse_json_safe(response.content[0].text)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_with_context(self, system_prompt, messages, temperature=0.7, max_tokens=None) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
        )
        return response.content[0].text


class DeepSeekClient(BaseLLMClient):
    """DeepSeek LLM client (OpenAI-compatible API)."""

    DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    def __init__(self):
        import openai
        settings = get_settings()
        self.client = openai.OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=self.DEEPSEEK_BASE_URL,
        )
        self.model = settings.model_name
        self.max_tokens = settings.max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate(self, system_prompt, user_message, temperature=0.7, max_tokens=None) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
    def generate_json(self, system_prompt, user_message, temperature=0.3, max_tokens=None) -> dict:
        json_system_prompt = (
            f"{system_prompt}\n\n"
            "IMPORTANT: You must respond with valid JSON only. No markdown, no explanation, just the JSON object."
        )
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": json_system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return _parse_json_safe(response.choices[0].message.content)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
    def generate_with_context(self, system_prompt, messages, temperature=0.7, max_tokens=None) -> str:
        all_messages = [{"role": "system", "content": system_prompt}] + messages
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=all_messages,
        )
        return response.choices[0].message.content


class TransformersClient(BaseLLMClient):
    """Local HuggingFace Transformers client — no API key required."""

    def __init__(self):
        from transformers import pipeline, AutoTokenizer
        import torch
        settings = get_settings()
        model_id = settings.model_name
        self.max_tokens = settings.max_tokens

        print(f"Loading local model: {model_id} ...")
        device = 0 if torch.cuda.is_available() else -1
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.pipe = pipeline(
            "text-generation",
            model=model_id,
            tokenizer=self.tokenizer,
            device=device,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )
        print(f"Model loaded on {'GPU' if device == 0 else 'CPU'}.")

    def _chat(self, system_prompt: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
        all_messages = [{"role": "system", "content": system_prompt}] + messages
        output = self.pipe(
            all_messages,
            max_new_tokens=max_tokens,
            temperature=max(temperature, 0.01),
            do_sample=temperature > 0,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        return output[0]["generated_text"][-1]["content"]

    def generate(self, system_prompt, user_message, temperature=0.7, max_tokens=None) -> str:
        return self._chat(
            system_prompt,
            [{"role": "user", "content": user_message}],
            temperature,
            max_tokens or self.max_tokens,
        )

    def generate_json(self, system_prompt, user_message, temperature=0.3, max_tokens=None) -> dict:
        json_system = (
            f"{system_prompt}\n\n"
            "IMPORTANT: Respond with valid JSON only. No markdown, no explanation — just the raw JSON object."
        )
        raw = self._chat(
            json_system,
            [{"role": "user", "content": user_message}],
            temperature,
            max_tokens or self.max_tokens,
        )
        # Strip markdown fences if the model adds them
        text = raw.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        # Find the outermost JSON object/array
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        raise ValueError(f"Could not parse JSON from model output:\n{raw[:500]}")

    def generate_with_context(self, system_prompt, messages, temperature=0.7, max_tokens=None) -> str:
        return self._chat(system_prompt, messages, temperature, max_tokens or self.max_tokens)


def _parse_json_safe(text: str) -> dict:
    """
    Parse JSON from an LLM response, recovering from common issues:
    - Markdown fences (```json ... ```)
    - Truncated output (unterminated strings/arrays) — salvages whatever keys are complete

    Recovery strategy is O(n) scan + at most 20 parse attempts, avoiding the O(n²)
    cost of trying every possible end position.
    """
    text = text.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Recovery: find the outermost `{` in the response
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in response: {text[:200]}")

    candidate = text[start:]

    # Scan once for closing brace positions — O(n) — then try the last 20 in reverse.
    # This covers the common truncation case (cut off mid-string or mid-array) without
    # the O(n²) cost of trying every character position.
    close_positions = [i for i, c in enumerate(candidate) if c == "}"]
    for pos in reversed(close_positions[-20:]):
        try:
            return json.loads(candidate[: pos + 1])
        except json.JSONDecodeError:
            continue

    raise ValueError(f"Could not recover valid JSON from response: {text[:200]}")


_client: Optional[BaseLLMClient] = None
_client_lock = threading.Lock()


def get_llm_client() -> BaseLLMClient:
    """Return a singleton LLM client based on LLM_PROVIDER setting (thread-safe)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # double-checked locking
                settings = get_settings()
                provider = settings.llm_provider.lower()
                if provider == "openai":
                    _client = OpenAIClient()
                elif provider == "anthropic":
                    _client = ClaudeClient()
                elif provider == "huggingface":
                    _client = TransformersClient()
                elif provider == "deepseek":
                    _client = DeepSeekClient()
                else:
                    raise ValueError(
                        f"Unsupported LLM_PROVIDER: '{provider}'. "
                        "Use 'openai', 'anthropic', 'deepseek', or 'huggingface'."
                    )
    return _client


# Keep backward-compatible alias
def get_claude_client() -> BaseLLMClient:
    return get_llm_client()
