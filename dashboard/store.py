# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Atomic public file snapshots, with optional local SQLite or Postgres storage."""
import json
import os
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from time import time
from urllib.request import urlopen


@lru_cache(maxsize=12)
def _remote_snapshot(url, five_minute_window):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def read_remote_json(url):
    if not url:
        return None
    try:
        return _remote_snapshot(url, int(time() // 300))
    except (OSError, ValueError):
        return None


@contextmanager
def connection():
    url = os.getenv("DATABASE_URL")
    if url:
        import psycopg
        with psycopg.connect(url) as db:
            yield db, "%s"
    else:
        path = Path(os.getenv("RESEARCH_DB", "var/research.sqlite"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=30) as db:
            yield db, "?"


def initialize():
    with connection() as (db, _):
        db.execute("CREATE TABLE IF NOT EXISTS research_snapshots (name TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.commit()


def read_snapshot(name="daily"):
    snapshot_path = os.getenv("RESEARCH_SNAPSHOT_FILE")
    if name == "daily" and snapshot_path:
        snapshot_file = Path(snapshot_path)
        return json.loads(snapshot_file.read_text(encoding="utf-8")) if snapshot_file.exists() else None
    remote_url = os.getenv("RESEARCH_SNAPSHOT_URL")
    if name == "daily" and remote_url:
        return read_remote_json(remote_url)
    initialize()
    with connection() as (db, marker):
        row = db.execute(f"SELECT payload FROM research_snapshots WHERE name = {marker}", (name,)).fetchone()
        return json.loads(row[0]) if row else None


def write_snapshot(payload, name="daily"):
    serialized = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    snapshot_path = os.getenv("RESEARCH_SNAPSHOT_FILE")
    if name == "daily" and snapshot_path:
        path = Path(snapshot_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(serialized + "\n", encoding="utf-8")
        temporary.replace(path)
        return
    initialize()
    with connection() as (db, marker):
        db.execute(f"INSERT INTO research_snapshots(name,payload) VALUES ({marker},{marker}) "
                   "ON CONFLICT(name) DO UPDATE SET payload=excluded.payload", (name, serialized))
        db.commit()
