from __future__ import annotations

import sqlite3

from app.ingestion import ingest_log
from app.store import ConversationStore
from app.event_bus import publish_ingestion_event
from app.worker import drain_ingestion_events

from tests.fakes import FakeRedisClient


def test_conversation_store_persists_messages_and_titles(tmp_path, monkeypatch):
    db_path = tmp_path / "ollive.sqlite3"
    monkeypatch.setenv("OLLIVE_DB_PATH", str(db_path))
    fake_redis = FakeRedisClient()
    monkeypatch.setattr("app.store._create_redis_client", lambda: fake_redis)

    store = ConversationStore()
    summary = store.create()
    store.add_message(summary["id"], "user", "Hello from persistence test")

    reopened = ConversationStore()
    conversation = reopened.get(summary["id"])

    assert conversation is not None
    assert conversation["title"] == "Hello from persistence test"
    assert len(conversation["messages"]) == 1
    assert conversation["messages"][0]["content"] == "Hello from persistence test"

def test_ingest_log_stores_extracted_metadata(tmp_path, monkeypatch):
    db_path = tmp_path / "ollive.sqlite3"
    monkeypatch.setenv("OLLIVE_DB_PATH", str(db_path))

    payload = {
        "event": "chat_request",
        "conversation_id": "conv-123",
        "prompt": "Say hi",
        "context": [{"role": "user", "content": "Say hi"}],
        "meta": {
            "provider": "google-generativeai",
            "model": "gemini-1.5-flash",
            "latency_ms": 12,
            "usage": {"total_tokens": 8},
            "timestamps": {
                "started_at": "2026-05-24T00:00:00+00:00",
                "finished_at": "2026-05-24T00:00:01+00:00",
            },
            "status": "success",
            "error": None,
            "conversation_id": "conv-123",
            "request_id": "req-123",
            "input_preview": "Say hi",
            "output_preview": "Hello",
        },
    }

    result = ingest_log(payload)

    assert result["conversation_id"] == "conv-123"
    assert result["status"] == "success"
    assert result["request_id"] == "req-123"

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT conversation_id, request_id, provider, model, status, latency_ms, input_preview, output_preview
            FROM inference_logs
            WHERE conversation_id = ?
            """,
            ("conv-123",),
        ).fetchone()

    assert row == (
        "conv-123",
        "req-123",
        "google-generativeai",
        "gemini-1.5-flash",
        "success",
        12,
        "Say hi",
        "Hello",
    )


def test_streamed_ingestion_event_is_drained_once(tmp_path, monkeypatch):
    db_path = tmp_path / "ollive.sqlite3"
    fake_redis = FakeRedisClient()
    monkeypatch.setenv("OLLIVE_DB_PATH", str(db_path))
    monkeypatch.setattr("app.event_bus.get_redis_client", lambda: fake_redis)

    payload = {
        "event": "chat_request",
        "event_id": "event-123",
        "conversation_id": "conv-456",
        "prompt": "stream this",
        "context": [{"role": "user", "content": "stream this"}],
        "meta": {
            "provider": "google-generativeai",
            "model": "gemini-1.5-flash",
            "latency_ms": 9,
            "usage": {"total_tokens": 4},
            "timestamps": {
                "started_at": "2026-05-24T00:00:00+00:00",
                "finished_at": "2026-05-24T00:00:01+00:00",
            },
            "status": "success",
            "error": None,
            "conversation_id": "conv-456",
            "request_id": "req-456",
            "input_preview": "stream this",
            "output_preview": "done",
        },
    }

    publish_ingestion_event(payload)
    first_pass = drain_ingestion_events()
    second_pass = drain_ingestion_events()

    assert first_pass == 1
    assert second_pass == 0

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT event_id, conversation_id, request_id, provider, model, status, latency_ms
            FROM inference_logs
            WHERE event_id = ?
            """,
            ("event-123",),
        ).fetchall()

    assert rows == [("event-123", "conv-456", "req-456", "google-generativeai", "gemini-1.5-flash", "success", 9)]