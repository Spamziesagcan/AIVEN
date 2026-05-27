from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .db import connect, execute
from .ingestion import ingest_log
from .request_logger import log_request
from .sdk import LightweightSDK
from .schemas import ChatRequest, ChatResponse
from .store import ConversationStore

MAX_CONTEXT_MESSAGES = 8

LOGGER = logging.getLogger("ollive.pipeline")

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")
STATIC_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Ollive Chatbot")

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

store = ConversationStore()

try:
    llm_client = LightweightSDK()
    llm_init_error = None
except RuntimeError as exc:
    llm_client = None
    llm_init_error = str(exc)


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health")
def health():
    return {"ok": True, "llm_ready": llm_client is not None}


@app.get("/api/observability/metrics")
def observability_metrics():
    connection = connect()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        rows = execute(
            connection,
            """
            SELECT id, status, latency_ms, received_at, provider, model, conversation_id, request_id, error
            FROM inference_logs
            WHERE received_at >= ?
            ORDER BY received_at ASC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        connection.close()

    return build_observability_metrics(rows)


@app.post("/api/ingest")
def ingest(entry: dict):
    return log_request(entry)


@app.post("/api/conversations")
def create_conversation():
    return store.create()


@app.get("/api/conversations")
def list_conversations():
    return store.list()


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    deleted = store.delete(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    conversation = store.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/messages", response_model=ChatResponse)
def send_message(conversation_id: str, request: ChatRequest):
    payload = _handle_chat_request(conversation_id, request)
    return payload


@app.post("/api/conversations/{conversation_id}/messages/stream")
def send_message_stream(conversation_id: str, request: ChatRequest):
    LOGGER.info("stage=chat_api level=received status=pass conversation_id=%s", conversation_id)
    conversation = store.get(conversation_id)
    if conversation is None:
        LOGGER.warning("stage=chat_api level=validation status=fail reason=conversation_not_found conversation_id=%s", conversation_id)
        raise HTTPException(status_code=404, detail="Conversation not found")

    message = request.message.strip()
    if not message:
        LOGGER.warning("stage=chat_api level=validation status=fail reason=empty_message conversation_id=%s", conversation_id)
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if llm_client is None:
        LOGGER.error("stage=chat_api level=llm_init status=fail conversation_id=%s error=%s", conversation_id, llm_init_error or "LLM is not configured")
        raise HTTPException(status_code=500, detail=llm_init_error or "LLM is not configured")

    user_message = store.add_message(conversation_id, "user", message)
    context = store.get_recent_messages(conversation_id, MAX_CONTEXT_MESSAGES)

    def event_stream() -> Iterator[str]:
        yield _sse_event("start", {"conversation_id": conversation_id, "user_message_id": user_message["id"]})
        assistant_parts: list[str] = []
        final_payload: dict | None = None
        for event in llm_client.stream_generate_reply(context, conversation_id=conversation_id):
            if event.get("type") == "chunk":
                chunk_text = event.get("text", "") or ""
                if chunk_text:
                    assistant_parts.append(chunk_text)
                    yield _sse_event("token", {"token": chunk_text})
            elif event.get("type") == "done":
                final_payload = event.get("result") or {}

        reply_text = (final_payload or {}).get("text") or "".join(assistant_parts).strip()
        if not reply_text:
            reply_text = "Sorry, I could not generate a response."

        assistant_message = store.add_message(conversation_id, "assistant", reply_text)
        payload = {
            "reply": assistant_message,
            "conversation_id": conversation_id,
            "meta": final_payload or {},
        }
        yield _sse_event("done", payload)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


def _handle_chat_request(conversation_id: str, request: ChatRequest) -> dict:
    LOGGER.info("stage=chat_api level=received status=pass conversation_id=%s", conversation_id)
    conversation = store.get(conversation_id)
    if conversation is None:
        LOGGER.warning("stage=chat_api level=validation status=fail reason=conversation_not_found conversation_id=%s", conversation_id)
        raise HTTPException(status_code=404, detail="Conversation not found")
    message = request.message.strip()
    if not message:
        LOGGER.warning("stage=chat_api level=validation status=fail reason=empty_message conversation_id=%s", conversation_id)
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if llm_client is None:
        LOGGER.error("stage=chat_api level=llm_init status=fail conversation_id=%s error=%s", conversation_id, llm_init_error or "LLM is not configured")
        raise HTTPException(status_code=500, detail=llm_init_error or "LLM is not configured")

    store.add_message(conversation_id, "user", message)
    context = store.get_recent_messages(conversation_id, MAX_CONTEXT_MESSAGES)
    result = llm_client.generate_reply(context, conversation_id=conversation_id)
    if result.get("status") == "error":
        LOGGER.error(
            "stage=chat_api level=sdk status=fail conversation_id=%s request_id=%s error=%s",
            conversation_id,
            result.get("request_id"),
            result.get("error"),
        )
        raise HTTPException(status_code=500, detail=result.get("error") or "LLM request failed")
    reply_text = result.get("text") or ""
    if not reply_text:
        reply_text = "Sorry, I could not generate a response."
    assistant_message = store.add_message(conversation_id, "assistant", reply_text)
    LOGGER.info(
        "stage=chat_api level=completed status=pass conversation_id=%s request_id=%s",
        conversation_id,
        result.get("request_id"),
    )

    return {
        "reply": assistant_message,
        "conversation_id": conversation_id,
        "meta": result,
    }


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def store_connection():
    return __import__("app.db", fromlist=["connect"]).connect()


def build_observability_metrics(rows):
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=12)
    latest_hour = now.replace(minute=0, second=0, microsecond=0)

    buckets = defaultdict(lambda: {"label": "", "requests": 0, "errors": 0, "latency_total": 0, "latency_count": 0})
    latencies = []
    total_requests = 0
    total_errors = 0
    recent_errors = []
    last_60_minutes = 0

    for row in rows:
        received_at = parse_timestamp(row_value(row, "received_at"))
        if received_at is None or received_at < window_start:
            continue

        total_requests += 1
        latency_ms = row_value(row, "latency_ms")
        status = (row_value(row, "status") or "").lower()
        if received_at >= now - timedelta(minutes=60):
            last_60_minutes += 1

        bucket_key = received_at.replace(minute=0, second=0, microsecond=0)
        bucket = buckets[bucket_key]
        bucket["requests"] += 1
        if status == "error":
            bucket["errors"] += 1
            total_errors += 1
            if len(recent_errors) < 5:
                recent_errors.append(
                    {
                        "received_at": row_value(row, "received_at"),
                        "conversation_id": row_value(row, "conversation_id"),
                        "request_id": row_value(row, "request_id"),
                        "model": row_value(row, "model"),
                        "error": row_value(row, "error") or "Unknown error",
                    }
                )
        if isinstance(latency_ms, int):
            bucket["latency_total"] += latency_ms
            bucket["latency_count"] += 1
            latencies.append(latency_ms)

    series = []
    bucket_cursor = window_start.replace(minute=0, second=0, microsecond=0)
    while bucket_cursor <= latest_hour:
        bucket = buckets.get(bucket_cursor)
        series.append(
            {
                "label": bucket_cursor.strftime("%I %p").lstrip("0"),
                "requests": bucket["requests"] if bucket else 0,
                "errors": bucket["errors"] if bucket else 0,
                "avg_latency_ms": round((bucket["latency_total"] / bucket["latency_count"]) if bucket and bucket["latency_count"] else 0, 1),
            }
        )
        bucket_cursor += timedelta(hours=1)

    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0
    p95_latency = percentile(latencies, 95)
    error_rate = round((total_errors / total_requests) * 100, 1) if total_requests else 0
    throughput_rpm = round(last_60_minutes / 60, 2)

    return {
        "window_hours": 12,
        "summary": {
            "total_requests": total_requests,
            "error_count": total_errors,
            "error_rate_pct": error_rate,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "throughput_rpm": throughput_rpm,
        },
        "series": series,
        "recent_errors": recent_errors,
    }


def parse_timestamp(value):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def percentile(values, percentile_value):
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((percentile_value / 100) * (len(ordered) - 1)))))
    return ordered[index]


def row_value(row, key):
    if hasattr(row, "get"):
        return row.get(key)
    return row[key]
