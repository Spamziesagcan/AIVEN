from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any, Optional

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional dependency for Neon/Postgres
    psycopg = None
    dict_row = None


BASE_DIR = Path(__file__).resolve().parents[2]
SCHEMA_LOCK = Lock()


def get_db_path() -> Path:
    env_path = os.getenv("OLLIVE_DB_PATH")
    if env_path:
        return Path(env_path)
    return BASE_DIR / "data" / "ollive.sqlite3"


def get_database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


def use_postgres() -> bool:
    return bool(get_database_url())


def connect() -> Any:
    database_url = get_database_url()
    if database_url:
        if psycopg is None:
            raise RuntimeError("psycopg is required when DATABASE_URL is set")
        connection = psycopg.connect(database_url, row_factory=dict_row)
        return connection

    get_db_path().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(get_db_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _schema_statements() -> list[str]:
    return [
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS inference_logs (
            id TEXT PRIMARY KEY,
            event_id TEXT,
            event TEXT NOT NULL,
            conversation_id TEXT,
            request_id TEXT,
            provider TEXT,
            model TEXT,
            status TEXT NOT NULL,
            error TEXT,
            latency_ms INTEGER,
            started_at TEXT,
            finished_at TEXT,
            input_preview TEXT,
            output_preview TEXT,
            usage_json TEXT,
            raw_payload_json TEXT NOT NULL,
            received_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_messages_conversation_timestamp ON messages(conversation_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_logs_conversation_received ON inference_logs(conversation_id, received_at)",
        "CREATE INDEX IF NOT EXISTS idx_logs_request_id ON inference_logs(request_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_event_id ON inference_logs(event_id)",
    ]


def execute(connection: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    if use_postgres():
        sql = sql.replace("?", "%s")
    return connection.execute(sql, params)


def ensure_schema() -> None:
    with SCHEMA_LOCK:
        connection = connect()
        try:
            for statement in _schema_statements():
                connection.execute(statement)
            _ensure_column(connection, "inference_logs", "event_id", "TEXT")
            connection.commit()
        finally:
            connection.close()


def _ensure_column(connection: Any, table_name: str, column_name: str, column_definition: str) -> None:
    existing_columns = {
        row[1] if not hasattr(row, "keys") else row["name"]
        for row in execute(connection, f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads_json(value: Optional[str], default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)