from __future__ import annotations

import json

from app.request_logger import log_request


def test_log_request_writes_jsonl(tmp_path):
    log_file = tmp_path / "llm_requests.jsonl"
    entry = {
        "event": "chat_request",
        "conversation_id": "conv-123",
        "status": "success",
        "meta": {"request_id": "req-1"},
    }

    log_request(entry, log_path=log_file)

    contents = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == 1
    recorded = json.loads(contents[0])
    assert recorded["event"] == "chat_request"
    assert recorded["conversation_id"] == "conv-123"
    assert recorded["status"] == "success"
    assert recorded["meta"]["request_id"] == "req-1"
