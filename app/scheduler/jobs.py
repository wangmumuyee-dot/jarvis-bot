from __future__ import annotations

import logging
import threading
from typing import Callable

from app.services.todo import TodoService

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(
        self,
        *,
        todo_service: TodoService,
        send_text: Callable[[str, str], None],
        interval_seconds: int,
    ) -> None:
        self.todo_service = todo_service
        self.send_text = send_text
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="reminder-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("Reminder scheduler started, interval=%ss", self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Reminder scheduler stopped")

    def tick(self) -> int:
        return self.todo_service.process_due_reminders(self.send_text)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                processed = self.tick()
                if processed:
                    logger.info("Processed %s due reminders", processed)
            except Exception:
                logger.exception("Reminder scheduler tick failed")
            self._stop.wait(self.interval_seconds)
