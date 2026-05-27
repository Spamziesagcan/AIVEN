from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict
from uuid import uuid4

from .db import connect, dumps_json, ensure_schema, execute
from .schemas import IngestionEvent

LOGGER = logging.getLogger("ollive.pipeline")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema()
    event = IngestionEvent.model_validate(payload)
    log_id = str(uuid4())
    event_id = event.event_id or str(uuid4())
    received_at = now_iso()
    meta = event.meta
    LOGGER.info(
        "stage=ingestion level=validated status=pass conversation_id=%s request_id=%s event_id=%s",
        event.conversation_id,
        meta.request_id,
        event_id,
    )
    connection = connect()
    try:
        execute(
            connection,
            """
            INSERT INTO inference_logs (
                id,
                event_id,
                event,
                conversation_id,
                request_id,
                provider,
                model,
                status,
                error,
                latency_ms,
                started_at,
                finished_at,
                input_preview,
                output_preview,
                usage_json,
                raw_payload_json,
                received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO NOTHING
            """,
            (
                log_id,
                event_id,
                event.event,
                event.conversation_id,
                meta.request_id,
                meta.provider,
                meta.model,
                meta.status,
                meta.error,
                meta.latency_ms,
                meta.timestamps.started_at,
                meta.timestamps.finished_at,
                meta.input_preview,
                meta.output_preview,
                dumps_json(meta.usage) if meta.usage is not None else None,
                dumps_json(event.model_dump(mode="json")),
                received_at,
            ),
        )
        connection.commit()
        row = execute(
            connection,
            """
            SELECT id, event_id, event, conversation_id, request_id, provider, model, status, error,
                   latency_ms, started_at, finished_at, input_preview, output_preview, usage_json,
                   raw_payload_json, received_at
            FROM inference_logs
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
        LOGGER.info(
            "stage=ingestion level=stored status=pass conversation_id=%s request_id=%s log_id=%s event_id=%s",
            event.conversation_id,
            meta.request_id,
            log_id,
            event_id,
        )
    except Exception:
        LOGGER.exception(
            "stage=ingestion level=stored status=fail conversation_id=%s request_id=%s log_id=%s",
            event.conversation_id,
            meta.request_id,
            log_id,
        )
        raise
    finally:
        connection.close()
    return {
        "id": row[0] if row is not None else log_id,
        "event_id": row[1] if row is not None else event_id,
        "received_at": row[16] if row is not None else received_at,
        "event": event.event,
        "conversation_id": event.conversation_id,
        "request_id": meta.request_id,
        "status": meta.status,
    }