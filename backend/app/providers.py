from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Protocol


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_reply(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        ...

    def stream_reply(self, messages: List[Dict[str, str]]) -> Iterator[Dict[str, Any]]:
        ...


def _normalize_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized = []
    for message in messages:
        normalized.append({"role": message.get("role", "user"), "content": message.get("content", "")})
    return normalized


def _build_usage_from_counts(prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> Optional[Dict[str, int]]:
    if prompt_tokens is None and completion_tokens is None:
        return None
    prompt = prompt_tokens or 0
    completion = completion_tokens or 0
    return {
        "prompt_tokens": prompt,
        "candidate_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _base_result(provider: str, model_name: str, text: str, latency_ms: int, usage: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    return {
        "text": text,
        "latency_ms": latency_ms,
        "usage": usage,
        "provider": provider,
        "model": model_name,
    }


@dataclass
class GeminiProvider:
    model_name: str
    _model: Any

    provider_name: str = "google-generativeai"

    @classmethod
    def from_env(cls) -> "GeminiProvider":
        import google.generativeai as genai

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GEMINI_API_KEY or GOOGLE_API_KEY.")
        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)
        return cls(model_name=model_name, _model=model)

    def generate_reply(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        contents = []
        for msg in _normalize_messages(messages):
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [msg.get("content", "")]})
        start = time.monotonic()
        response = self._model.generate_content(contents)
        latency_ms = int((time.monotonic() - start) * 1000)
        text = ""
        usage = None
        if response is not None:
            text = (response.text or "").strip()
            usage_meta = getattr(response, "usage_metadata", None)
            if usage_meta:
                usage = _build_usage_from_counts(
                    getattr(usage_meta, "prompt_token_count", None),
                    getattr(usage_meta, "candidates_token_count", None),
                )
        return {"text": text, "latency_ms": latency_ms, "usage": usage}

    def stream_reply(self, messages: List[Dict[str, str]]) -> Iterator[Dict[str, Any]]:
        contents = []
        for msg in _normalize_messages(messages):
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [msg.get("content", "")]})
        start = time.monotonic()
        text_parts: List[str] = []
        response_stream = self._model.generate_content(contents, stream=True)
        for chunk in response_stream:
            chunk_text = (getattr(chunk, "text", "") or "")
            if chunk_text:
                text_parts.append(chunk_text)
                yield {"type": "chunk", "text": chunk_text}
        latency_ms = int((time.monotonic() - start) * 1000)
        yield {
            "type": "done",
            "result": _base_result(self.provider_name, self.model_name, "".join(text_parts).strip(), latency_ms),
        }


@dataclass
class OpenAIProvider:
    model_name: str
    _client: Any

    provider_name: str = "openai"

    @classmethod
    def from_env(cls) -> "OpenAIProvider":
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY.")
        model_name = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        client = OpenAI(api_key=api_key)
        return cls(model_name=model_name, _client=client)

    def generate_reply(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        normalized = _normalize_messages(messages)
        start = time.monotonic()
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": msg["role"], "content": msg["content"]} for msg in normalized],
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        choice = response.choices[0] if getattr(response, "choices", None) else None
        text = (choice.message.content or "").strip() if choice and choice.message else ""
        usage = None
        response_usage = getattr(response, "usage", None)
        if response_usage is not None:
            usage = {
                "prompt_tokens": getattr(response_usage, "prompt_tokens", None),
                "candidate_tokens": getattr(response_usage, "completion_tokens", None),
                "total_tokens": getattr(response_usage, "total_tokens", None),
            }
        return {"text": text, "latency_ms": latency_ms, "usage": usage}

    def stream_reply(self, messages: List[Dict[str, str]]) -> Iterator[Dict[str, Any]]:
        normalized = _normalize_messages(messages)
        start = time.monotonic()
        text_parts: List[str] = []
        stream = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": msg["role"], "content": msg["content"]} for msg in normalized],
            stream=True,
        )
        for chunk in stream:
            delta = getattr(chunk.choices[0], "delta", None) if getattr(chunk, "choices", None) else None
            chunk_text = getattr(delta, "content", "") or ""
            if chunk_text:
                text_parts.append(chunk_text)
                yield {"type": "chunk", "text": chunk_text}
        latency_ms = int((time.monotonic() - start) * 1000)
        yield {
            "type": "done",
            "result": _base_result(self.provider_name, self.model_name, "".join(text_parts).strip(), latency_ms),
        }


@dataclass
class ClaudeProvider:
    model_name: str
    _client: Any

    provider_name: str = "anthropic"

    @classmethod
    def from_env(cls) -> "ClaudeProvider":
        from anthropic import Anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY.")
        model_name = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        client = Anthropic(api_key=api_key)
        return cls(model_name=model_name, _client=client)

    def generate_reply(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        normalized = _normalize_messages(messages)
        system_messages = [msg["content"] for msg in normalized if msg["role"] == "system"]
        user_messages = [msg for msg in normalized if msg["role"] != "system"]
        start = time.monotonic()
        response = self._client.messages.create(
            model=self.model_name,
            system="\n\n".join(system_messages) if system_messages else None,
            max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024")),
            messages=[{"role": "user" if msg["role"] == "user" else "assistant", "content": msg["content"]} for msg in user_messages],
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        text_parts = []
        for block in getattr(response, "content", []) or []:
            text_parts.append(getattr(block, "text", "") or "")
        text = "".join(text_parts).strip()
        usage = None
        response_usage = getattr(response, "usage", None)
        if response_usage is not None:
            usage = {
                "prompt_tokens": getattr(response_usage, "input_tokens", None),
                "candidate_tokens": getattr(response_usage, "output_tokens", None),
                "total_tokens": getattr(response_usage, "input_tokens", 0) + getattr(response_usage, "output_tokens", 0),
            }
        return {"text": text, "latency_ms": latency_ms, "usage": usage}

    def stream_reply(self, messages: List[Dict[str, str]]) -> Iterator[Dict[str, Any]]:
        normalized = _normalize_messages(messages)
        system_messages = [msg["content"] for msg in normalized if msg["role"] == "system"]
        user_messages = [msg for msg in normalized if msg["role"] != "system"]
        start = time.monotonic()
        text_parts: List[str] = []
        with self._client.messages.stream(
            model=self.model_name,
            system="\n\n".join(system_messages) if system_messages else None,
            max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024")),
            messages=[{"role": "user" if msg["role"] == "user" else "assistant", "content": msg["content"]} for msg in user_messages],
        ) as stream:
            for chunk_text in stream.text_stream:
                if chunk_text:
                    text_parts.append(chunk_text)
                    yield {"type": "chunk", "text": chunk_text}
        latency_ms = int((time.monotonic() - start) * 1000)
        yield {
            "type": "done",
            "result": _base_result(self.provider_name, self.model_name, "".join(text_parts).strip(), latency_ms),
        }


def create_llm_provider(provider_name: Optional[str] = None) -> LLMProvider:
    selected = (provider_name or os.getenv("LLM_PROVIDER", "gemini")).lower()
    if selected in {"gemini", "google", "google-generativeai"}:
        return GeminiProvider.from_env()
    if selected in {"openai", "gpt"}:
        return OpenAIProvider.from_env()
    if selected in {"claude", "anthropic"}:
        return ClaudeProvider.from_env()
    raise RuntimeError(f"Unsupported provider: {provider_name or selected}")