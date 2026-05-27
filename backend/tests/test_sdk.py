from __future__ import annotations

import pytest

from app.sdk import LightweightSDK


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def generate_reply(self, messages):
        self.calls.append(messages)
        return {"text": "ok", "latency_ms": 1, "usage": {"total_tokens": 3}}


@pytest.mark.parametrize(
    "prompt_text",
    [
        "hello",
        "what is data engineering?",
        "## Data Engineering in To",
    ],
)
def test_lightweight_sdk_delegates_to_client(prompt_text):
    fake = FakeClient()
    sdk = LightweightSDK(client=fake)
    msgs = [{"role": "user", "content": prompt_text}]
    out = sdk.generate(msgs, conversation_id="conv-123")
    assert out["text"] == "ok"
    assert out["latency_ms"] == 1
    assert out["usage"] == {"total_tokens": 3}
    assert out["provider"] == "google-generativeai"
    assert out["status"] == "success"
    assert out["error"] is None
    assert out["conversation_id"] == "conv-123"
    assert out["request_id"]
    assert out["timestamps"]["started_at"]
    assert out["timestamps"]["finished_at"]
    assert out["input_preview"] == prompt_text
    assert out["output_preview"] == "ok"
    assert fake.calls and fake.calls[0] is msgs
