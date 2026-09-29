"""Atomic research snapshot storage. Use Postgres when DATABASE_URL is set."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


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
    initialize()
    with connection() as (db, marker):
        row = db.execute(f"SELECT payload FROM research_snapshots WHERE name = {marker}", (name,)).fetchone()
        return json.loads(row[0]) if row else None


def write_snapshot(payload, name="daily"):
    serialized = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    initialize()
    with connection() as (db, marker):
        db.execute(f"INSERT INTO research_snapshots(name,payload) VALUES ({marker},{marker}) "
                   "ON CONFLICT(name) DO UPDATE SET payload=excluded.payload", (name, serialized))
        db.commit()
