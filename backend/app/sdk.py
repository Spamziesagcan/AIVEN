from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Dict, Iterator, List, Optional

from .llm import create_llm_provider
from .request_logger import log_request

LOGGER = logging.getLogger("ollive.pipeline")


class LightweightSDK:
    """A lightweight SDK/wrapper around the project's LLM client.

    This wrapper provides a minimal, testable interface for generating
    assistant replies from a list of messages. The underlying client can be
    injected for easier testing.
    """

    def __init__(self, client: Optional[Any] = None, provider: str = "google-generativeai") -> None:
        self._client = client or create_llm_provider(provider)
        self._provider = provider or getattr(self._client, "provider_name", "unknown")

    def generate(
        self,
        messages: List[Dict[str, str]],
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a reply given a list of messages.

        messages: list of dicts with keys `role` and `content` matching the
        internal store format.
        Returns a dict with response text plus metadata used by the API.
        """
        request_id = str(uuid4())
        request_started_at = now_iso()
        input_preview = build_preview(messages)
        LOGGER.info(
            "stage=sdk level=started status=pass conversation_id=%s request_id=%s",
            conversation_id,
            request_id,
        )

        try:
            reply = self._client.generate_reply(messages)
            request_finished_at = now_iso()
            output_preview = build_preview([{"role": "assistant", "content": reply.get("text", "")}], limit=80)
            result = {
                "text": reply.get("text", ""),
                "latency_ms": reply.get("latency_ms"),
                "usage": reply.get("usage"),
                "provider": getattr(self._client, "provider_name", self._provider),
                "model": getattr(self._client, "model_name", getattr(self._client, "_model_name", None)),
                "timestamps": {
                    "started_at": request_started_at,
                    "finished_at": request_finished_at,
                },
                "status": "success",
                "error": None,
                "conversation_id": conversation_id,
                "request_id": request_id,
                "input_preview": input_preview,
                "output_preview": output_preview,
            }
            log_request(self._build_log_entry(messages, result, conversation_id))
            LOGGER.info(
                "stage=sdk level=completed status=pass conversation_id=%s request_id=%s provider=%s model=%s",
                conversation_id,
                request_id,
                result.get("provider"),
                result.get("model"),
            )
            return result
        except Exception as exc:
            request_finished_at = now_iso()
            result = {
                "text": "",
                "latency_ms": None,
                "usage": None,
                "provider": getattr(self._client, "provider_name", self._provider),
                "model": getattr(self._client, "model_name", getattr(self._client, "_model_name", None)),
                "timestamps": {
                    "started_at": request_started_at,
                    "finished_at": request_finished_at,
                },
                "status": "error",
                "error": str(exc),
                "conversation_id": conversation_id,
                "request_id": request_id,
                "input_preview": input_preview,
                "output_preview": "",
            }
            log_request(self._build_log_entry(messages, result, conversation_id))
            LOGGER.error(
                "stage=sdk level=completed status=fail conversation_id=%s request_id=%s error=%s",
                conversation_id,
                request_id,
                str(exc),
            )
            return result

    def stream_generate_reply(
        self,
        messages: List[Dict[str, str]],
        conversation_id: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        request_id = str(uuid4())
        request_started_at = now_iso()
        input_preview = build_preview(messages)
        LOGGER.info(
            "stage=sdk level=started status=pass conversation_id=%s request_id=%s",
            conversation_id,
            request_id,
        )

        provider_stream = getattr(self._client, "stream_reply", None)
        if provider_stream is None:
            result = self.generate(messages, conversation_id=conversation_id)
            yield {"type": "chunk", "text": result.get("text", "")}
            yield {"type": "done", "result": result}
            return

        text_parts: List[str] = []
        final_result: Dict[str, Any] | None = None

        try:
            for event in provider_stream(messages):
                if event.get("type") == "chunk":
                    chunk_text = event.get("text", "") or ""
                    if chunk_text:
                        text_parts.append(chunk_text)
                        yield {"type": "chunk", "text": chunk_text}
                elif event.get("type") == "done":
                    final_result = event.get("result") or {}

            if final_result is None:
                final_result = {
                    "text": "".join(text_parts).strip(),
                    "latency_ms": None,
                    "usage": None,
                    "provider": getattr(self._client, "provider_name", self._provider),
                    "model": getattr(self._client, "model_name", getattr(self._client, "_model_name", None)),
                }

            finished_at = now_iso()
            result = {
                "text": final_result.get("text", ""),
                "latency_ms": final_result.get("latency_ms"),
                "usage": final_result.get("usage"),
                "provider": final_result.get("provider", getattr(self._client, "provider_name", self._provider)),
                "model": final_result.get("model", getattr(self._client, "model_name", getattr(self._client, "_model_name", None))),
                "timestamps": {
                    "started_at": request_started_at,
                    "finished_at": finished_at,
                },
                "status": "success",
                "error": None,
                "conversation_id": conversation_id,
                "request_id": request_id,
                "input_preview": input_preview,
                "output_preview": build_preview([{"role": "assistant", "content": final_result.get("text", "")}], limit=80),
            }
            log_request(self._build_log_entry(messages, result, conversation_id))
            LOGGER.info(
                "stage=sdk level=completed status=pass conversation_id=%s request_id=%s provider=%s model=%s",
                conversation_id,
                request_id,
                result.get("provider"),
                result.get("model"),
            )
            yield {"type": "done", "result": result}
        except Exception as exc:
            finished_at = now_iso()
            result = {
                "text": "",
                "latency_ms": None,
                "usage": None,
                "provider": getattr(self._client, "provider_name", self._provider),
                "model": getattr(self._client, "model_name", getattr(self._client, "_model_name", None)),
                "timestamps": {
                    "started_at": request_started_at,
                    "finished_at": finished_at,
                },
                "status": "error",
                "error": str(exc),
                "conversation_id": conversation_id,
                "request_id": request_id,
                "input_preview": input_preview,
                "output_preview": "",
            }
            log_request(self._build_log_entry(messages, result, conversation_id))
            LOGGER.error(
                "stage=sdk level=completed status=fail conversation_id=%s request_id=%s error=%s",
                conversation_id,
                request_id,
                str(exc),
            )
            yield {"type": "done", "result": result}

    # Backwards-compatible alias used by the FastAPI app
    def generate_reply(
        self,
        messages: List[Dict[str, str]],
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.generate(messages, conversation_id=conversation_id)

    def _build_log_entry(
        self,
        messages: List[Dict[str, str]],
        result: Dict[str, Any],
        conversation_id: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "event": "chat_request",
            "conversation_id": conversation_id,
            "prompt": messages[-1].get("content", "") if messages else "",
            "context": messages,
            "meta": {
                "provider": result.get("provider"),
                "model": result.get("model"),
                "latency_ms": result.get("latency_ms"),
                "usage": result.get("usage"),
                "timestamps": result.get("timestamps"),
                "status": result.get("status"),
                "error": result.get("error"),
                "conversation_id": result.get("conversation_id"),
                "request_id": result.get("request_id"),
                "input_preview": result.get("input_preview", ""),
                "output_preview": result.get("output_preview", ""),
            },
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_preview(messages: List[Dict[str, str]], limit: int = 120) -> str:
    parts = []
    for message in messages:
        content = " ".join((message.get("content") or "").split())
        if content:
            parts.append(content)
    preview = " | ".join(parts).strip()
    if len(preview) <= limit:
        return preview
    return preview[: max(0, limit - 3)] + "..."


__all__ = ["LightweightSDK"]
