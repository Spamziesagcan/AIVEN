from __future__ import annotations

import importlib
import sqlite3

from fastapi.testclient import TestClient

from app.sdk import LightweightSDK
from app.store import ConversationStore

from tests.fakes import FakeRedisClient


class FakeModelClient:
    def __init__(self) -> None:
        self.calls = []
        self._model_name = "fake-model"

    def generate_reply(self, messages):
        self.calls.append(messages)
        return {
            "text": "Hello from the model",
            "latency_ms": 7,
            "usage": {"prompt_tokens": 5, "candidate_tokens": 3, "total_tokens": 8},
        }


def test_chat_request_persists_message_and_inference_log(tmp_path, monkeypatch):
    db_path = tmp_path / "ollive.sqlite3"
    monkeypatch.setenv("OLLIVE_DB_PATH", str(db_path))
    fake_redis = FakeRedisClient()
    monkeypatch.setattr("app.store._create_redis_client", lambda: fake_redis)
    monkeypatch.setattr("app.event_bus.get_redis_client", lambda: fake_redis)

    main = importlib.import_module("app.main")
    main.store = ConversationStore()
    fake_model = FakeModelClient()
    main.llm_client = LightweightSDK(client=fake_model)

    client = TestClient(main.app)
    conversation = client.post("/api/conversations").json()

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"message": "Hello backend"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"]["content"] == "Hello from the model"
    assert body["meta"]["provider"] == "google-generativeai"
    assert body["meta"]["model"] == "fake-model"
    assert body["meta"]["status"] == "success"
    assert fake_model.calls and fake_model.calls[0][0]["content"] == "Hello backend"

    conversation_detail = client.get(f"/api/conversations/{conversation['id']}").json()
    assert len(conversation_detail["messages"]) == 2
    assert conversation_detail["messages"][0]["content"] == "Hello backend"
    assert conversation_detail["messages"][1]["content"] == "Hello from the model"

    with sqlite3.connect(db_path) as connection:
        log_row = connection.execute(
            """
            SELECT conversation_id, request_id, provider, model, status, latency_ms, input_preview, output_preview
            FROM inference_logs
            WHERE conversation_id = ?
            """,
            (conversation["id"],),
        ).fetchone()

    assert log_row[0] == conversation["id"]
    assert log_row[2] == "google-generativeai"
    assert log_row[3] == "fake-model"
    assert log_row[4] == "success"
    assert log_row[5] == 7
    assert log_row[6] == "Hello backend"
    assert log_row[7] == "Hello from the model"