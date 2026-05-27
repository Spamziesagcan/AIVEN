from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from .db import connect, ensure_schema, execute

LOGGER = logging.getLogger("ollive.pipeline")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def truncate(text: str, limit: int = 60) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)] + "..."


class ConversationStore:
    def __init__(self) -> None:
        ensure_schema()

    def create(self) -> dict:
        conversation_id = str(uuid4())
        now = now_iso()
        conversation = {
            "id": conversation_id,
            "title": "New chat",
            "created_at": now,
            "updated_at": now,
        }
        connection = connect()
        try:
            execute(
                connection,
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, conversation["title"], now, now),
            )
            connection.commit()
        finally:
            connection.close()
        return self._summary(conversation)

    def list(self) -> List[dict]:
        connection = connect()
        try:
            rows = execute(
                connection,
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                """,
            ).fetchall()
            return [self._summary(row) for row in rows]
        finally:
            connection.close()

    def delete(self, conversation_id: str) -> bool:
        connection = connect()
        try:
            deleted = execute(connection, "DELETE FROM conversations WHERE id = ?", (conversation_id,)).rowcount
            connection.commit()
            return deleted > 0
        finally:
            connection.close()

    def get(self, conversation_id: str) -> Optional[dict]:
        connection = connect()
        try:
            conversation = execute(
                connection,
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if not conversation:
                return None

            message_rows = execute(
                connection,
                """
                SELECT id, role, content, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
                """,
                (conversation_id,),
            ).fetchall()
            payload = self._summary(conversation)
            payload["messages"] = [self._message(row) for row in message_rows]
            return payload
        finally:
            connection.close()

    def add_message(self, conversation_id: str, role: str, content: str) -> dict:
        message_id = str(uuid4())
        now = now_iso()
        message = {
            "id": message_id,
            "role": role,
            "content": content,
            "timestamp": now,
        }

        connection = connect()
        try:
            row = execute(
                connection,
                "SELECT title FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not row:
                raise KeyError("Conversation not found")

            title = row[0] or "New chat"
            if role == "user" and title == "New chat":
                title = truncate(content, 60) or "New chat"

            execute(
                connection,
                """
                INSERT INTO messages (id, conversation_id, role, content, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, role, content, now),
            )
            execute(
                connection,
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, now, conversation_id),
            )
            connection.commit()
        finally:
            connection.close()
        return message

    def get_recent_messages(self, conversation_id: str, limit: int) -> List[dict]:
        if limit <= 0:
            return []

        connection = connect()
        try:
            rows = execute(
                connection,
                """
                SELECT role, content
                FROM (
                    SELECT role, content, timestamp
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                ORDER BY timestamp ASC
                """,
                (conversation_id, limit),
            ).fetchall()
            return [{"role": row[0], "content": row[1]} for row in rows]
        finally:
            connection.close()

    def _summary(self, conversation: dict) -> dict:
        return {
            "id": conversation[0] if not hasattr(conversation, "keys") else conversation["id"],
            "title": conversation[1] if not hasattr(conversation, "keys") else conversation["title"],
            "created_at": conversation[2] if not hasattr(conversation, "keys") else conversation["created_at"],
            "updated_at": conversation[3] if not hasattr(conversation, "keys") else conversation["updated_at"],
        }

    def _message(self, message: dict) -> dict:
        return {
            "id": message[0] if not hasattr(message, "keys") else message["id"],
            "role": message[1] if not hasattr(message, "keys") else message["role"],
            "content": message[2] if not hasattr(message, "keys") else message["content"],
            "timestamp": message[3] if not hasattr(message, "keys") else message["timestamp"],
        }
