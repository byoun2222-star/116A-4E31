# Copyright (c) tree and fruits. PoC only — PHASE 2B Result Collector.
"""Provider Result -> deterministic validation -> Publishing DB -> (MAF workflow reads DB back).

Reuses the SAME Publishing DB file as Phase 2A (`phase2a/data/publishing_poc.db`) — owner's
stated principle is "Publishing DB = single source of truth", so Phase 2B extends rather than
forks it. `provider_run` gains the columns Phase 2A didn't need (surface_id, agent_role,
output_hash, health_before/after, idempotency_key) via additive `ALTER TABLE` (non-destructive
— existing Phase 2A rows/columns untouched).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PHASE2A_ROOT = Path(__file__).resolve().parent.parent.parent / "phase2a"
sys.path.insert(0, str(PHASE2A_ROOT))
from db import publishing_db as db  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent.parent / "data" / "results"

_MIGRATION_COLUMNS = {
    "surface_id": "TEXT",
    "agent_role": "TEXT",
    "output_hash": "TEXT",
    "health_before": "TEXT",
    "health_after": "TEXT",
    "idempotency_key": "TEXT",
}


def migrate() -> None:
    conn = db.get_conn()
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(provider_run)").fetchall()}
        for col, coltype in _MIGRATION_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE provider_run ADD COLUMN {col} {coltype}")
        conn.commit()
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IdempotencyConflict(Exception):
    """Raised when the identity/hash fallback (see already_ran) finds an ambiguous or
    conflicting completion state. Must never be auto-resolved by the caller."""


def already_ran(idempotency_key: str, task_id: str | None = None) -> dict | None:
    """Owner §19: check before submitting. Returns the existing COMPLETED run row if this
    idempotency_key has already been executed, else None.

    Fallback (owner-directed fix, 2026-10-02, for a discovered gap): a provider_run row written
    via publishing_db.record_provider_run() directly (bypassing this module's
    record_run_started/record_run_completed) can have idempotency_key=NULL even though the task
    genuinely COMPLETED -- the known case is the Codex short-token E2E row (run-e2e-tfbab618c).
    If the idempotency_key lookup misses and task_id is supplied, fall back to identity+hash
    verification: task.status=='COMPLETED' AND exactly one provider_run row for this task_id has
    status='COMPLETED', AND (if that row recorded an output_hash) the hash matches the actual
    result file on disk. Any inconsistency (multiple conflicting COMPLETED rows, a recorded hash
    that doesn't match the file, or a COMPLETED state with no result file at all) raises
    IdempotencyConflict rather than silently resolving permissively in either direction. This
    never reads or modifies the idempotency_key column of any existing row."""
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "SELECT run_id, provider, status, output_hash FROM provider_run "
            "WHERE idempotency_key = ? AND status = 'COMPLETED'",
            (idempotency_key,),
        )
        row = cur.fetchone()
        if row is not None:
            return {"run_id": row[0], "provider": row[1], "status": row[2], "output_hash": row[3],
                    "matched_via": "idempotency_key"}

        if task_id is None:
            return None

        task_row = conn.execute("SELECT status FROM task WHERE task_id = ?", (task_id,)).fetchone()
        if task_row is None or task_row[0] != "COMPLETED":
            return None

        completed_rows = conn.execute(
            "SELECT run_id, provider, status, output_hash FROM provider_run "
            "WHERE task_id = ? AND status = 'COMPLETED'",
            (task_id,),
        ).fetchall()
        if len(completed_rows) == 0:
            return None
        if len(completed_rows) > 1:
            raise IdempotencyConflict(
                f"IDEMPOTENCY_CONFLICT: task_id {task_id!r} has {len(completed_rows)} conflicting "
                f"COMPLETED provider_run rows and none carries a resolving idempotency_key"
            )
        fb_run_id, fb_provider, fb_status, fb_output_hash = completed_rows[0]

        result_path = RESULTS_DIR / f"{task_id}.json"
        if fb_output_hash:
            if not result_path.exists():
                raise IdempotencyConflict(
                    f"IDEMPOTENCY_CONFLICT: provider_run {fb_run_id} records output_hash="
                    f"{fb_output_hash} for task_id {task_id!r} but no result file exists at "
                    f"{result_path}"
                )
            actual_hash = hashlib.sha256(result_path.read_bytes()).hexdigest()
            if actual_hash != fb_output_hash:
                raise IdempotencyConflict(
                    f"IDEMPOTENCY_CONFLICT: task_id {task_id!r} result file hash {actual_hash} "
                    f"does not match recorded output_hash {fb_output_hash} in provider_run "
                    f"{fb_run_id}"
                )
        elif not result_path.exists():
            raise IdempotencyConflict(
                f"IDEMPOTENCY_CONFLICT: task_id {task_id!r} is COMPLETED with no recorded "
                f"output_hash and no result file at {result_path} -- cannot safely confirm "
                f"completion identity"
            )
        return {"run_id": fb_run_id, "provider": fb_provider, "status": fb_status,
                "output_hash": fb_output_hash, "matched_via": "identity_hash_fallback"}
    finally:
        conn.close()


def record_run_started(run_id: str, provider: str, task_id: str, task_type: str, surface_id: str,
                        agent_role: str, health_before: str, usage_before: str,
                        usage_reliability: str, idempotency_key: str) -> None:
    migrate()
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO provider_run (run_id, provider, task_id, task_type, started_at, status, "
            "retry_count, surface_id, agent_role, health_before, usage_before, usage_reliability, "
            "idempotency_key) VALUES (?, ?, ?, ?, ?, 'RUNNING', 0, ?, ?, ?, ?, ?, ?)",
            (run_id, provider, task_id, task_type, now_iso(), surface_id, agent_role, health_before,
             usage_before, usage_reliability, idempotency_key),
        )
        db.log_event(conn, actor="result_collector", action="provider_run.started", previous_state=None,
                      new_state="RUNNING", reason=f"provider={provider} surface={surface_id}",
                      source="result_collector", entity_type="provider_run", entity_id=run_id)
        conn.commit()
    finally:
        conn.close()


def save_raw_result(run_id: str, raw_text: str) -> tuple[str, str]:
    """Owner §18: original result saved to a PoC-only result file, with a hash. Returns
    (file_path, sha256_hash)."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{run_id}.txt"
    path.write_text(raw_text, encoding="utf-8")
    file_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return str(path), file_hash


def record_run_completed(run_id: str, status: str, output_hash: str, validation_result: dict,
                          health_after: str, usage_after: str, error_type: str | None,
                          duration_seconds: float, notes: str) -> None:
    conn = db.get_conn()
    try:
        conn.execute(
            "UPDATE provider_run SET completed_at=?, status=?, output_hash=?, validation_result=?, "
            "health_after=?, usage_after=?, error_type=?, duration_seconds=?, notes=? WHERE run_id=?",
            (now_iso(), status, output_hash, json.dumps(validation_result, ensure_ascii=False),
             health_after, usage_after, error_type, duration_seconds, notes, run_id),
        )
        db.log_event(conn, actor="result_collector", action="provider_run.completed",
                      previous_state="RUNNING", new_state=status,
                      reason=f"validation_passed={validation_result.get('passed')}",
                      source="result_collector", entity_type="provider_run", entity_id=run_id)
        conn.commit()
    finally:
        conn.close()


def get_provider_run(run_id: str) -> dict | None:
    """Owner TEST 2B-F (Result Persistence): reconstruct a run's full record from DB alone,
    with NO dependency on any surface's conversational context."""
    conn = db.get_conn()
    try:
        cur = conn.execute("SELECT * FROM provider_run WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        record = dict(zip(cols, row))
        result_path = RESULTS_DIR / f"{run_id}.txt"
        record["result_artifact_path"] = str(result_path) if result_path.exists() else None
        record["result_artifact_exists"] = result_path.exists()
        return record
    finally:
        conn.close()


def get_all_runs_for_task(task_id: str) -> list[dict]:
    conn = db.get_conn()
    try:
        cur = conn.execute("SELECT * FROM provider_run WHERE task_id = ? ORDER BY started_at", (task_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
