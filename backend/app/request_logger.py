from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from .event_bus import publish_ingestion_event, prepare_ingestion_event
from .ingestion import ingest_log

LOGGER = logging.getLogger("ollive.pipeline")


def get_log_path() -> Path:
    env_path = os.getenv("LLM_REQUEST_LOG_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parents[2] / "logs" / "llm_requests.jsonl"


def log_request(entry: Dict[str, Any], log_path: Optional[Path] = None) -> None:
    prepared_entry = prepare_ingestion_event(entry)
    conversation_id = prepared_entry.get("conversation_id")
    request_id = (prepared_entry.get("meta") or {}).get("request_id")
    if log_path is not None:
        target = log_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(prepared_entry, ensure_ascii=False, default=str))
            handle.write("\n")
        LOGGER.info(
            "stage=request_logger level=file_log status=pass conversation_id=%s request_id=%s path=%s",
            conversation_id,
            request_id,
            target,
        )
        return {"status": "file_log", "path": str(target), "event_id": prepared_entry["event_id"]}

    published_event: Dict[str, Any] | None = None
    try:
        LOGGER.info(
            "stage=request_logger level=ingestion_handoff status=started conversation_id=%s request_id=%s",
            conversation_id,
            request_id,
        )
        published_event = publish_ingestion_event(prepared_entry)
        if _should_process_inline():
            result = ingest_log(prepared_entry)
            result["published"] = True
            result["event_id"] = published_event["event_id"]
            return result
        LOGGER.info(
            "stage=request_logger level=ingestion_handoff status=pass conversation_id=%s request_id=%s",
            conversation_id,
            request_id,
        )
        return {
            "queued": True,
            "published": True,
            "event_id": published_event["event_id"],
            "conversation_id": conversation_id,
            "request_id": request_id,
        }
    except Exception:
        if _should_process_inline():
            try:
                result = ingest_log(prepared_entry)
                result["published"] = False
                result["event_id"] = prepared_entry["event_id"]
                return result
            except Exception:
                pass
        target = get_log_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(prepared_entry, ensure_ascii=False, default=str))
            handle.write("\n")
        LOGGER.exception(
            "stage=request_logger level=ingestion_handoff status=fail_fallback_jsonl conversation_id=%s request_id=%s path=%s",
            conversation_id,
            request_id,
            target,
        )
        return {"status": "file_fallback", "path": str(target), "event_id": prepared_entry["event_id"]}


def _should_process_inline() -> bool:
    value = os.getenv("OLLIVE_EVENT_PROCESS_INLINE", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}
