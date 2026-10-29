"""Transactional research-attempt ledger and reproducibility fingerprints."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def code_hash(root: Path) -> str:
    files = sorted((root / "src").rglob("*.py")) + sorted((root / "tests").rglob("*.py"))
    files += sorted((root / "scripts").rglob("*.py"))
    files += [root / "pyproject.toml", root / "uv.lock"]
    h = hashlib.sha256()
    for path in sorted(files):
        if path.is_file():
            h.update(path.relative_to(root).as_posix().encode())
            h.update(b"\0")
            h.update(path.read_bytes())
    return h.hexdigest()


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, created TEXT NOT NULL, finished TEXT, kind TEXT NOT NULL, phase TEXT, status TEXT NOT NULL, config_hash TEXT, code_hash TEXT, data_prefix_hash TEXT, details TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=20)

    def start(self, kind: str, details: dict, *, phase: str = "", config_hash: str = "", code: str = "", data_hash: str = "") -> str:
        identifier = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (identifier, utc_now(), None, kind, phase, "started", config_hash, code, data_hash, json.dumps(details, allow_nan=False)))
        return identifier

    def finish(self, identifier: str, status: str, details: dict):
        if status not in ("completed", "failed"):
            raise ValueError("Invalid terminal attempt status")
        with self.connect() as db:
            original = db.execute("SELECT details FROM attempts WHERE id=? AND status='started'", (identifier,)).fetchone()
            if original is None:
                raise ValueError("Unknown or already finalized attempt")
            preserved = {**json.loads(original[0]), "outcome": details}
            if db.execute("UPDATE attempts SET status=?,finished=?,details=? WHERE id=? AND status='started'", (status, utc_now(), json.dumps(preserved, allow_nan=False), identifier)).rowcount != 1:
                raise ValueError("Unknown or already finalized attempt")

    def rows(self) -> list[dict]:
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [{**dict(row), "details": json.loads(row["details"])} for row in db.execute("SELECT * FROM attempts ORDER BY created,id")]

    def matching_selection(self, config_hash: str, code: str, prefix: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM attempts WHERE kind='backtest' AND phase='selection' AND status='completed' AND config_hash=? AND code_hash=? AND data_prefix_hash=?", (config_hash, code, prefix)).fetchone() is not None

    def reserved_count(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM attempts WHERE kind='backtest' AND phase='reserved'").fetchone()[0]
