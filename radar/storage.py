"""SQLite persistence for local mode. The hosted UI never opens this database."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from radar.models import Briefing, Evidence, Preferences


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.touch(mode=0o600, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS bookmarks (url TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scheduled (slot TEXT PRIMARY KEY);
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def preferences(self) -> Preferences:
        with self.connect() as connection:
            row = connection.execute("SELECT body FROM settings WHERE id = 1").fetchone()
        return Preferences.model_validate_json(row[0]) if row else Preferences()

    def save_preferences(self, prefs: Preferences) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO settings VALUES (1, ?)",
                (prefs.model_dump_json(),),
            )

    def save_report(self, report: Briefing) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO reports (body) VALUES (?)", (report.model_dump_json(),))

    def reports(self) -> list[Briefing]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT body FROM reports ORDER BY id DESC LIMIT 50"
            ).fetchall()
        return [Briefing.model_validate_json(body) for (body,) in rows]

    def covered(self) -> list[Evidence]:
        return [
            item.evidence
            for report in self.reports()
            if report.mode == "ai"
            for item in report.items
        ]

    def bookmarks(self) -> dict[str, Evidence]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT url, body FROM bookmarks ORDER BY rowid DESC"
            ).fetchall()
        return {url: Evidence.model_validate_json(body) for url, body in rows}

    def bookmark(self, evidence: Evidence, enabled: bool) -> None:
        url = str(evidence.url)
        with self.connect() as connection:
            if enabled:
                connection.execute(
                    "INSERT OR REPLACE INTO bookmarks VALUES (?, ?)",
                    (url, evidence.model_dump_json()),
                )
            else:
                connection.execute("DELETE FROM bookmarks WHERE url = ?", (url,))

    def claim(self, slot: str) -> bool:
        with self.connect() as connection:
            result = connection.execute("INSERT OR IGNORE INTO scheduled VALUES (?)", (slot,))
            return result.rowcount == 1
