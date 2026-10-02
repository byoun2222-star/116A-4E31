# Copyright (c) tree and fruits. PoC only — PHASE 2A Publishing DB.
"""PHASE 2A Publishing DB — PoC only, NOT the production Publishing DB.

File: phase2a/data/publishing_poc.db (owner §14 explicit path). Separate SQLite file from
Phase 1's maf-publishing-poc/publishing_poc.sqlite3 — the two PoCs are intentionally kept
apart (Phase 1 tested the state-machine shape; Phase 2A tests the fuller SoT schema + router +
adapter integration around it). Neither touches any existing production DB or file.

13 entities per owner §15: BOOK/CONTRACT/PRODUCTION/DISTRIBUTION/MARKETING/APPROVAL/
FILE_VERSION/WORKFLOW_RUN/TASK/PROVIDER/PROVIDER_RUN/SYSTEM_EVENT/CHECKPOINT_REFERENCE.

Every state-changing table carries actor + timestamp (owner §16 audit requirement).
SYSTEM_EVENT is the append-only audit log itself (previous_state/new_state/reason/source/
workflow_run_id) — a generic audit trail any entity's transition can write into, so the audit
trail isn't duplicated ad hoc per table.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "publishing_poc.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS book (
    book_id TEXT PRIMARY KEY, title TEXT NOT NULL, subtitle TEXT, author TEXT, translator TEXT,
    isbn TEXT, price INTEGER, trim_size TEXT, page_count INTEGER, publication_date TEXT,
    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contract (
    contract_id TEXT PRIMARY KEY, book_id TEXT REFERENCES book(book_id), counterparty TEXT,
    rights_scope TEXT, contract_date TEXT, term TEXT, royalty_terms TEXT, status TEXT,
    document_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS production (
    production_id TEXT PRIMARY KEY, book_id TEXT REFERENCES book(book_id),
    manuscript_version TEXT, editing_status TEXT, proofreading_status TEXT, typesetting_status TEXT,
    print_pdf_status TEXT, ebook_pdf_status TEXT, epub_status TEXT, current_file TEXT,
    next_action TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS distribution (
    distribution_id TEXT PRIMARY KEY, book_id TEXT REFERENCES book(book_id),
    isbn_status TEXT, bookstore TEXT, registration_status TEXT, product_id TEXT,
    product_url TEXT, metadata_version TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS marketing (
    marketing_id TEXT PRIMARY KEY, book_id TEXT REFERENCES book(book_id),
    press_release TEXT, homepage TEXT, social TEXT, campaign TEXT, assets TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approval (
    approval_id TEXT PRIMARY KEY, book_id TEXT REFERENCES book(book_id), action TEXT NOT NULL,
    requested_at TEXT NOT NULL, requested_by TEXT NOT NULL, status TEXT NOT NULL,
    approved_at TEXT, approved_by TEXT, evidence TEXT
);
CREATE TABLE IF NOT EXISTS file_version (
    file_id TEXT PRIMARY KEY, book_id TEXT REFERENCES book(book_id), file_type TEXT,
    path TEXT NOT NULL, version TEXT, hash TEXT NOT NULL, created_at TEXT NOT NULL,
    modified_at TEXT, producer TEXT, associated_task TEXT
);
CREATE TABLE IF NOT EXISTS workflow_run (
    workflow_run_id TEXT PRIMARY KEY, book_id TEXT REFERENCES book(book_id),
    workflow_name TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
    completed_at TEXT, checkpoint_id TEXT
);
CREATE TABLE IF NOT EXISTS task (
    task_id TEXT PRIMARY KEY, workflow_run_id TEXT REFERENCES workflow_run(workflow_run_id),
    book_id TEXT REFERENCES book(book_id), task_type TEXT NOT NULL, status TEXT NOT NULL,
    assigned_provider TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS provider (
    provider_id TEXT PRIMARY KEY, name TEXT NOT NULL,
    health TEXT NOT NULL DEFAULT 'UNKNOWN',
    usage_source TEXT, usage_value TEXT, observed_at TEXT,
    confidence_reliability TEXT NOT NULL DEFAULT 'UNKNOWN',
    stale INTEGER NOT NULL DEFAULT 1,
    error_signal TEXT
);
CREATE TABLE IF NOT EXISTS provider_run (
    run_id TEXT PRIMARY KEY, provider TEXT NOT NULL, task_id TEXT REFERENCES task(task_id),
    task_type TEXT, started_at TEXT, completed_at TEXT, status TEXT,
    duration_seconds REAL, retry_count INTEGER DEFAULT 0, error_type TEXT,
    validation_result TEXT, owner_acceptance TEXT, reviewer_result TEXT,
    usage_before TEXT, usage_after TEXT, usage_reliability TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS system_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
    previous_state TEXT, new_state TEXT, reason TEXT, source TEXT,
    workflow_run_id TEXT, entity_type TEXT, entity_id TEXT
);
CREATE TABLE IF NOT EXISTS checkpoint_reference (
    checkpoint_ref_id TEXT PRIMARY KEY, workflow_run_id TEXT REFERENCES workflow_run(workflow_run_id),
    maf_checkpoint_id TEXT NOT NULL, created_at TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS state_transition_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL,
    actor TEXT NOT NULL, at TEXT NOT NULL,
    UNIQUE(book_id, to_status)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def log_event(conn: sqlite3.Connection, *, actor: str, action: str, previous_state: str | None,
              new_state: str | None, reason: str, source: str, workflow_run_id: str | None = None,
              entity_type: str | None = None, entity_id: str | None = None) -> None:
    conn.execute(
        "INSERT INTO system_event (at, actor, action, previous_state, new_state, reason, source, "
        "workflow_run_id, entity_type, entity_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (now_iso(), actor, action, previous_state, new_state, reason, source, workflow_run_id,
         entity_type, entity_id),
    )


def ensure_book(book_id: str, title: str, actor: str = "system") -> None:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT book_id FROM book WHERE book_id = ?", (book_id,))
        if cur.fetchone() is not None:
            return
        ts = now_iso()
        conn.execute(
            "INSERT INTO book (book_id, title, status, created_at, updated_at) VALUES (?, ?, 'MANUSCRIPT_RECEIVED', ?, ?)",
            (book_id, title, ts, ts),
        )
        log_event(conn, actor=actor, action="book.created", previous_state=None,
                  new_state="MANUSCRIPT_RECEIVED", reason="ensure_book", source="publishing_db",
                  entity_type="book", entity_id=book_id)
        conn.commit()
    finally:
        conn.close()


def set_book_status(book_id: str, status: str, actor: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT status FROM book WHERE book_id = ?", (book_id,))
        row = cur.fetchone()
        from_status = row[0] if row else None
        ts = now_iso()
        try:
            conn.execute(
                "INSERT INTO state_transition_log (book_id, from_status, to_status, actor, at) VALUES (?, ?, ?, ?, ?)",
                (book_id, from_status, status, actor, ts),
            )
        except sqlite3.IntegrityError:
            conn.commit()
            return False
        conn.execute("UPDATE book SET status = ?, updated_at = ? WHERE book_id = ?", (status, ts, book_id))
        log_event(conn, actor=actor, action="book.status_changed", previous_state=from_status,
                  new_state=status, reason="set_book_status", source="publishing_db",
                  entity_type="book", entity_id=book_id)
        conn.commit()
        return True
    finally:
        conn.close()


def get_book_status(book_id: str) -> str | None:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT status FROM book WHERE book_id = ?", (book_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def create_workflow_run(workflow_run_id: str, book_id: str, workflow_name: str, actor: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO workflow_run (workflow_run_id, book_id, workflow_name, status, started_at) "
            "VALUES (?, ?, ?, 'RUNNING', ?)",
            (workflow_run_id, book_id, workflow_name, now_iso()),
        )
        log_event(conn, actor=actor, action="workflow_run.created", previous_state=None, new_state="RUNNING",
                  reason="create_workflow_run", source="publishing_db", workflow_run_id=workflow_run_id,
                  entity_type="workflow_run", entity_id=workflow_run_id)
        conn.commit()
    finally:
        conn.close()


def create_task(task_id: str, workflow_run_id: str, book_id: str, task_type: str, actor: str,
                assigned_provider: str | None = None) -> None:
    conn = get_conn()
    try:
        ts = now_iso()
        conn.execute(
            "INSERT OR IGNORE INTO task (task_id, workflow_run_id, book_id, task_type, status, "
            "assigned_provider, created_at, updated_at) VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?)",
            (task_id, workflow_run_id, book_id, task_type, assigned_provider, ts, ts),
        )
        log_event(conn, actor=actor, action="task.created", previous_state=None, new_state="PENDING",
                  reason=f"task_type={task_type}", source="publishing_db", workflow_run_id=workflow_run_id,
                  entity_type="task", entity_id=task_id)
        conn.commit()
    finally:
        conn.close()


def set_task_status(task_id: str, status: str, actor: str) -> None:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT status FROM task WHERE task_id = ?", (task_id,))
        row = cur.fetchone()
        prev = row[0] if row else None
        conn.execute("UPDATE task SET status = ?, updated_at = ? WHERE task_id = ?", (status, now_iso(), task_id))
        log_event(conn, actor=actor, action="task.status_changed", previous_state=prev, new_state=status,
                  reason="set_task_status", source="publishing_db", entity_type="task", entity_id=task_id)
        conn.commit()
    finally:
        conn.close()


def upsert_provider(provider_id: str, name: str, health: str, usage_source: str | None,
                     usage_value: str | None, confidence_reliability: str, stale: bool,
                     error_signal: str | None, actor: str) -> None:
    conn = get_conn()
    try:
        ts = now_iso()
        cur = conn.execute("SELECT health FROM provider WHERE provider_id = ?", (provider_id,))
        row = cur.fetchone()
        prev_health = row[0] if row else None
        conn.execute(
            "INSERT INTO provider (provider_id, name, health, usage_source, usage_value, observed_at, "
            "confidence_reliability, stale, error_signal) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(provider_id) DO UPDATE SET name=excluded.name, health=excluded.health, "
            "usage_source=excluded.usage_source, usage_value=excluded.usage_value, "
            "observed_at=excluded.observed_at, confidence_reliability=excluded.confidence_reliability, "
            "stale=excluded.stale, error_signal=excluded.error_signal",
            (provider_id, name, health, usage_source, usage_value, ts, confidence_reliability,
             int(stale), error_signal),
        )
        if prev_health != health:
            log_event(conn, actor=actor, action="provider.health_changed", previous_state=prev_health,
                      new_state=health, reason=f"usage_source={usage_source}", source="publishing_db",
                      entity_type="provider", entity_id=provider_id)
        conn.commit()
    finally:
        conn.close()


def get_all_providers() -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT provider_id, name, health, usage_source, usage_value, observed_at, "
            "confidence_reliability, stale, error_signal FROM provider"
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def record_provider_run(run_id: str, provider: str, task_id: str | None, task_type: str, status: str,
                         notes: str, usage_reliability: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO provider_run (run_id, provider, task_id, task_type, started_at, "
            "completed_at, status, retry_count, notes, usage_reliability) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (run_id, provider, task_id, task_type, now_iso(), now_iso(), status, notes, usage_reliability),
        )
        conn.commit()
    finally:
        conn.close()


def record_approval_request(book_id: str, action: str, requested_by: str) -> str:
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
        log_event(conn, actor=requested_by, action="approval.requested", previous_state=None,
                  new_state="PENDING", reason=action, source="publishing_db",
                  entity_type="approval", entity_id=approval_id)
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
        log_event(conn, actor=approved_by, action="approval.decided", previous_state="PENDING",
                  new_state=decision, reason=evidence, source="publishing_db",
                  entity_type="approval", entity_id=approval_id)
        conn.commit()
    finally:
        conn.close()


def record_file_version(file_id: str, book_id: str, file_type: str, path: str, version: str,
                         file_hash: str, producer: str, associated_task: str | None) -> None:
    conn = get_conn()
    try:
        ts = now_iso()
        conn.execute(
            "INSERT OR IGNORE INTO file_version (file_id, book_id, file_type, path, version, hash, "
            "created_at, modified_at, producer, associated_task) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (file_id, book_id, file_type, path, version, file_hash, ts, ts, producer, associated_task),
        )
        log_event(conn, actor=producer, action="file_version.recorded", previous_state=None,
                  new_state=version, reason=path, source="publishing_db",
                  entity_type="file_version", entity_id=file_id)
        conn.commit()
    finally:
        conn.close()


def record_checkpoint_reference(checkpoint_ref_id: str, workflow_run_id: str, maf_checkpoint_id: str,
                                 note: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO checkpoint_reference (checkpoint_ref_id, workflow_run_id, "
            "maf_checkpoint_id, created_at, note) VALUES (?, ?, ?, ?, ?)",
            (checkpoint_ref_id, workflow_run_id, maf_checkpoint_id, now_iso(), note),
        )
        conn.commit()
    finally:
        conn.close()


def get_transition_count(book_id: str, status: str) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) FROM state_transition_log WHERE book_id = ? AND to_status = ?", (book_id, status)
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def get_events_for(entity_type: str, entity_id: str) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT at, actor, action, previous_state, new_state, reason, source FROM system_event "
            "WHERE entity_type = ? AND entity_id = ? ORDER BY event_id",
            (entity_type, entity_id),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def reset_poc_db() -> None:
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            p.unlink()
