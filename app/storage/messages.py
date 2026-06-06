from __future__ import annotations

import sqlite3

from app.storage.db import Database


class MessageStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def mark_processing(
        self,
        *,
        feishu_message_id: str | None,
        event_id: str | None,
        status: str = "processing",
    ) -> bool:
        if not feishu_message_id and not event_id:
            return True

        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO processed_messages
                    (feishu_message_id, event_id, status)
                    VALUES (?, ?, ?)
                    """,
                    (feishu_message_id, event_id, status),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def update_status(
        self,
        *,
        feishu_message_id: str | None,
        event_id: str | None,
        status: str,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE processed_messages
                SET status = ?
                WHERE
                    (? IS NOT NULL AND feishu_message_id = ?)
                    OR (? IS NOT NULL AND event_id = ?)
                """,
                (status, feishu_message_id, feishu_message_id, event_id, event_id),
            )

