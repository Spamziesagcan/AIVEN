from __future__ import annotations

import importlib
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient

from app.db import connect, ensure_schema, execute

from tests.fakes import FakeRedisClient


def test_observability_metrics_returns_latency_throughput_and_errors(tmp_path, monkeypatch):
    db_path = tmp_path / "ollive.sqlite3"
    monkeypatch.setenv("OLLIVE_DB_PATH", str(db_path))
    fake_redis = FakeRedisClient()
    monkeypatch.setattr("app.store._create_redis_client", lambda: fake_redis)
    monkeypatch.setattr("app.event_bus.get_redis_client", lambda: fake_redis)

    app = importlib.import_module("app.main").app

    ensure_schema()
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": "log-1",
            "status": "success",
            "latency_ms": 120,
            "received_at": (now - timedelta(minutes=5)).isoformat(),
            "provider": "google-generativeai",
            "model": "gemini-1.5-flash",
            "conversation_id": "conv-1",
            "request_id": "req-1",
            "error": None,
        },
        {
            "id": "log-2",
            "status": "success",
            "latency_ms": 200,
            "received_at": (now - timedelta(minutes=58)).isoformat(),
            "provider": "google-generativeai",
            "model": "gemini-1.5-flash",
            "conversation_id": "conv-1",
            "request_id": "req-2",
            "error": None,
        },
        {
            "id": "log-3",
            "status": "error",
            "latency_ms": 80,
            "received_at": (now - timedelta(minutes=30)).isoformat(),
            "provider": "google-generativeai",
            "model": "gemini-1.5-flash",
            "conversation_id": "conv-2",
            "request_id": "req-3",
            "error": "Backend timeout",
        },
    ]

    connection = connect()
    try:
        for row in rows:
            execute(
                connection,
                """
                INSERT INTO inference_logs (
                    id, event, conversation_id, request_id, provider, model, status, error,
                    latency_ms, started_at, finished_at, input_preview, output_preview,
                    usage_json, raw_payload_json, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    "chat_request",
                    row["conversation_id"],
                    row["request_id"],
                    row["provider"],
                    row["model"],
                    row["status"],
                    row["error"],
                    row["latency_ms"],
                    row["received_at"],
                    row["received_at"],
                    "hello",
                    "hi",
                    None,
                    "{}",
                    row["received_at"],
                ),
            )
        connection.commit()
    finally:
        connection.close()

    client = TestClient(app)
    response = client.get("/api/observability/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_requests"] == 3
    assert payload["summary"]["error_count"] == 1
    assert payload["summary"]["avg_latency_ms"] == 133.3
    assert payload["summary"]["throughput_rpm"] >= 0
    assert len(payload["series"]) > 0
    assert payload["recent_errors"][0]["error"] == "Backend timeout"