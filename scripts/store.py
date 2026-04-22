from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class EventStore:
    def __init__(self, db_path: str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS processed (
                    event_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending_actions (
                    action_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            self._conn.commit()

    def record_event(self, event: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO events (id, payload, created_at) VALUES (?, ?, ?)",
                (event["id"], json.dumps(event), time.time()),
            )
            self._conn.commit()

    def record_outcome(self, event_id: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO outcomes (event_id, payload, created_at) VALUES (?, ?, ?)",
                (event_id, json.dumps(payload), time.time()),
            )
            self._conn.commit()

    def is_processed(self, event_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("SELECT 1 FROM processed WHERE event_id = ?", (event_id,))
            return cur.fetchone() is not None

    def mark_processed(self, event_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO processed (event_id, created_at) VALUES (?, ?)",
                (event_id, time.time()),
            )
            self._conn.commit()

    def add_pending_action(self, action_id: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO pending_actions (action_id, payload, created_at) VALUES (?, ?, ?)",
                (action_id, json.dumps(payload), time.time()),
            )
            self._conn.commit()

    def remove_pending_action(self, action_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM pending_actions WHERE action_id = ?", (action_id,))
            self._conn.commit()

    def list_pending_actions(self) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT action_id, payload, created_at FROM pending_actions ORDER BY created_at ASC")
            rows = cur.fetchall()
        return [
            {"action_id": row["action_id"], "payload": json.loads(row["payload"]), "created_at": row["created_at"]}
            for row in rows
        ]

    def add_dead_letter(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO dead_letters (payload, created_at) VALUES (?, ?)",
                (json.dumps(payload), time.time()),
            )
            self._conn.commit()

    def remember(self, kind: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO memory (kind, payload, created_at) VALUES (?, ?, ?)",
                (kind, json.dumps(payload), time.time()),
            )
            self._conn.commit()

    def recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT payload FROM events ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        return [json.loads(row[0]) for row in rows]
