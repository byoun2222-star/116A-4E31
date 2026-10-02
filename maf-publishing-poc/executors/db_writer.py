# Copyright (c) tree and fruits. PoC only — not production Publishing DB.
"""Publishing DB (SQLite) writer for MAF-PUBLISHING-POC.

Scope: PoC-only schema, deliberately smaller than the full 7-entity design in
CYSJAVIS-MAF-PUBLISHING-INTEGRATION-PHASE0.md §6. Only `book`, `production`,
and `approval` are needed to exercise the MANUSCRIPT_RECEIVED..READY_FOR_PUBLICATION
state machine; contract/distribution/marketing/file_version are out of scope
for Phase 1 (no contract, no ISBN, no marketing asset in this PoC).

Idempotency contract (TEST G): writing the same (book_id, status) pair twice
must not create a duplicate transition-log row and must not change updated_at
on the second call. This is what lets `workflow.py` be re-invoked safely after
a crash or a duplicate manual re-run.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "publishing_poc.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS book (
    book_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS production (
    production_id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES book(book_id),
    editing_status TEXT,
    epub_status TEXT,
    current_file TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approval (
    approval_id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES book(book_id),
    action TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL,
    approved_at TEXT,
    approved_by TEXT,
    evidence TEXT
);
CREATE TABLE IF NOT EXISTS state_transition_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    at TEXT NOT NULL,
    UNIQUE(book_id, to_status)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def ensure_book(book_id: str, title: str) -> None:
    """Idempotent: INSERT OR IGNORE — a second call with the same book_id is a no-op."""
    conn = get_conn()
    try:
        ts = now_iso()
        conn.execute(
            "INSERT OR IGNORE INTO book (book_id, title, status, created_at, updated_at) "
            "VALUES (?, ?, 'MANUSCRIPT_RECEIVED', ?, ?)",
            (book_id, title, ts, ts),
        )
        conn.commit()
    finally:
        conn.close()


def set_status(book_id: str, status: str, actor: str) -> bool:
    """Set book status, logging the transition exactly once per (book_id, status).

    Returns True if this call actually recorded a NEW transition, False if the
    transition was already logged before (idempotent no-op — TEST G contract).
    """
    conn = get_conn()
    try:
        cur = conn.execute("SELECT status FROM book WHERE book_id = ?", (book_id,))
        row = cur.fetchone()
        from_status = row[0] if row else None

        ts = now_iso()
        try:
            conn.execute(
                "INSERT INTO state_transition_log (book_id, from_status, to_status, actor, at) "
                "VALUES (?, ?, ?, ?, ?)",
                (book_id, from_status, status, actor, ts),
            )
        except sqlite3.IntegrityError:
            # UNIQUE(book_id, to_status) already hit for this status -> already recorded, no-op.
            conn.commit()
            return False

        conn.execute(
            "UPDATE book SET status = ?, updated_at = ? WHERE book_id = ?",
            (status, ts, book_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_status(book_id: str) -> str | None:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT status FROM book WHERE book_id = ?", (book_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def upsert_production(book_id: str, **fields: str) -> None:
    conn = get_conn()
    try:
        ts = now_iso()
        cur = conn.execute("SELECT production_id FROM production WHERE book_id = ?", (book_id,))
        row = cur.fetchone()
        if row is None:
            cols = ", ".join(fields.keys())
            placeholders = ", ".join("?" for _ in fields)
            conn.execute(
                f"INSERT INTO production (production_id, book_id, {cols}, updated_at) "
                f"VALUES (?, ?, {placeholders}, ?)",
                (f"prod-{book_id}", book_id, *fields.values(), ts),
            )
        else:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE production SET {set_clause}, updated_at = ? WHERE book_id = ?",
                (*fields.values(), ts, book_id),
            )
        conn.commit()
    finally:
        conn.close()


def record_approval_request(book_id: str, action: str, requested_by: str) -> str:
    """Idempotent: if a PENDING approval for this (book_id, action) already exists, reuse it."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT approval_id FROM approval WHERE book_id = ? AND action = ? AND status = 'PENDING'",
            (book_id, action),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        approval_id = f"appr-{book_id}-{action}"
        conn.execute(
            "INSERT OR IGNORE INTO approval (approval_id, book_id, action, requested_at, requested_by, status) "
            "VALUES (?, ?, ?, ?, ?, 'PENDING')",
            (approval_id, book_id, action, now_iso(), requested_by),
        )
        conn.commit()
        return approval_id
    finally:
        conn.close()


def record_approval_decision(approval_id: str, approved_by: str, decision: str, evidence: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE approval SET status = ?, approved_at = ?, approved_by = ?, evidence = ? "
            "WHERE approval_id = ? AND status = 'PENDING'",
            (decision, now_iso(), approved_by, evidence, approval_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_transition_count(book_id: str, status: str) -> int:
    """Test helper (TEST G): how many times has this exact transition been logged (must stay <=1)."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) FROM state_transition_log WHERE book_id = ? AND to_status = ?",
            (book_id, status),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def reset_poc_db() -> None:
    """Test helper: wipe the PoC DB file for a clean TEST run. Never touches production data
    (this file lives only inside maf-publishing-poc/, is a distinct .sqlite3 from anything else)."""
    if DB_PATH.exists():
        DB_PATH.unlink()
