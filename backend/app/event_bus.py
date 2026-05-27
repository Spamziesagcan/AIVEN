from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple
from uuid import uuid4

from .db import dumps_json, loads_json

INGESTION_STREAM = "ollive:ingestion_events"
INGESTION_CURSOR_KEY = "ollive:ingestion_events:last_id"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_redis_client():
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError("REDIS_URL must be set to use the ingestion event bus")

    try:
        import redis
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("redis package is required to use the ingestion event bus") from exc

    return redis.from_url(redis_url, decode_responses=True)


def prepare_ingestion_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    event = dict(payload)
    event.setdefault("event_id", str(uuid4()))
    event.setdefault("published_at", now_iso())
    return event


def publish_ingestion_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    client = get_redis_client()
    event = prepare_ingestion_event(payload)
    client.xadd(INGESTION_STREAM, {"payload_json": dumps_json(event)})
    return event


def read_ingestion_events(limit: int = 100) -> List[Tuple[str, Dict[str, Any]]]:
    client = get_redis_client()
    last_id = get_ingestion_cursor(client)
    rows = client.xread({INGESTION_STREAM: last_id}, count=limit, block=0)
    events: List[Tuple[str, Dict[str, Any]]] = []
    for _, messages in rows:
        for stream_id, fields in messages:
            payload = loads_json(fields.get("payload_json"), default={})
            events.append((stream_id, payload))
    return events


def get_ingestion_cursor(client: Any | None = None) -> str:
    active_client = client or get_redis_client()
    cursor = active_client.get(INGESTION_CURSOR_KEY)
    return cursor or "0-0"


def set_ingestion_cursor(stream_id: str, client: Any | None = None) -> None:
    active_client = client or get_redis_client()
    active_client.set(INGESTION_CURSOR_KEY, stream_id)