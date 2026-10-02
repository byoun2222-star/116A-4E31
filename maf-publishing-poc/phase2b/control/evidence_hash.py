# -*- coding: utf-8 -*-
"""
Durable Project Record — evidence/run-record helper library.

Authority split (per OWNER APPROVAL 2026-10-02 — do not collapse into one):
  Publishing DB (book/task/provider_run/...) = publishing workflow/business state authority
  phase2b_run_record                          = CYS/Phase2B execution history authority
  evidence_ledger + preserved evidence files  = factual evidence/provenance authority
  PROJECT_STATE.json                          = derived resume snapshot (NOT an independent source of truth)
  .md checkpoint                              = human-readable recovery/reference document
  AI report/conversation                      = non-authoritative explanatory context

This module performs no AI calls. Pure deterministic local I/O.
"""
import hashlib
import json
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "phase2a"))
from db import publishing_db as _publishing_db  # noqa: E402

VALID_STATUSES = {"CONFIRMED", "UNVERIFIED", "NOT_FOUND", "CONFLICT", "FAILED", "SAFE_STOP"}

# Heuristic patterns that must never be stored as raw command text.
_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|api[_-]?key|secret|token|credential)\s*[=:]\s*\S+"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    return _publishing_db.get_conn()


def sha256_file(path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def redact_command(raw_command: str) -> str:
    """Return a safe-to-store command string: redacted if a secret-like pattern is detected,
    otherwise the raw command unchanged. The sha256 of the RAW command is always computed
    separately by the caller so the redacted/raw distinction never loses traceability."""
    for pat in _SECRET_PATTERNS:
        if pat.search(raw_command):
            return "<REDACTED: possible secret pattern detected>"
    return raw_command


def ensure_schema(conn: sqlite3.Connection = None) -> None:
    """Idempotent. CREATE TABLE IF NOT EXISTS only — never touches existing tables."""
    own_conn = conn is None
    conn = conn or get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS phase2b_run_record (
            run_id TEXT PRIMARY KEY,
            objective TEXT,
            started_at TEXT,
            finished_at TEXT,
            actor TEXT,
            provider TEXT,
            surface_ref TEXT,
            role TEXT,
            agent TEXT,
            precondition_json TEXT,
            command_display TEXT,
            command_sha256 TEXT,
            input_artifacts_json TEXT,
            output_artifacts_json TEXT,
            process_evidence_json TEXT,
            validation_result TEXT,
            db_changes_json TEXT,
            retry_count INTEGER DEFAULT 0,
            final_status TEXT,
            stop_reason TEXT,
            evidence_refs_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_ledger (
            claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            claim TEXT NOT NULL,
            status TEXT NOT NULL,
            evidence_path TEXT,
            sha256 TEXT,
            observed_at TEXT NOT NULL,
            superseded_by INTEGER
        )
        """
    )
    conn.commit()
    if own_conn:
        conn.close()


def start_run(objective, actor, provider=None, surface_ref=None, role=None, agent=None,
              precondition=None, raw_command=None, conn: sqlite3.Connection = None) -> str:
    own_conn = conn is None
    conn = conn or get_conn()
    ensure_schema(conn)
    run_id = "run2b-" + uuid.uuid4().hex[:16]
    command_display = redact_command(raw_command) if raw_command else None
    command_sha256 = sha256_text(raw_command) if raw_command else None
    conn.execute(
        """INSERT INTO phase2b_run_record
           (run_id, objective, started_at, actor, provider, surface_ref, role, agent,
            precondition_json, command_display, command_sha256, retry_count, final_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'RUNNING')""",
        (run_id, objective, _now(), actor, provider, surface_ref, role, agent,
         json.dumps(precondition, ensure_ascii=False) if precondition is not None else None,
         command_display, command_sha256),
    )
    conn.commit()
    if own_conn:
        conn.close()
    return run_id


def finalize_run(run_id, final_status, stop_reason=None, input_artifacts=None,
                  output_artifacts=None, process_evidence=None, validation_result=None,
                  db_changes=None, retry_count=0, evidence_refs=None,
                  conn: sqlite3.Connection = None) -> None:
    own_conn = conn is None
    conn = conn or get_conn()

    def _hash_artifacts(artifacts):
        if not artifacts:
            return None
        out = []
        for a in artifacts:
            path = a if isinstance(a, str) else a.get("path")
            entry = {"path": path}
            try:
                entry["sha256"] = sha256_file(path)
            except (FileNotFoundError, IsADirectoryError, OSError):
                entry["sha256"] = None
            out.append(entry)
        return out

    conn.execute(
        """UPDATE phase2b_run_record SET
             finished_at=?, final_status=?, stop_reason=?,
             input_artifacts_json=?, output_artifacts_json=?,
             process_evidence_json=?, validation_result=?,
             db_changes_json=?, retry_count=?, evidence_refs_json=?
           WHERE run_id=?""",
        (
            _now(), final_status, stop_reason,
            json.dumps(_hash_artifacts(input_artifacts), ensure_ascii=False) if input_artifacts else None,
            json.dumps(_hash_artifacts(output_artifacts), ensure_ascii=False) if output_artifacts else None,
            json.dumps(process_evidence, ensure_ascii=False) if process_evidence is not None else None,
            validation_result,
            json.dumps(db_changes, ensure_ascii=False) if db_changes is not None else None,
            retry_count,
            json.dumps(evidence_refs, ensure_ascii=False) if evidence_refs is not None else None,
            run_id,
        ),
    )
    conn.commit()
    if own_conn:
        conn.close()


def record_evidence(claim: str, status: str, evidence_path=None, run_id=None,
                     conn: sqlite3.Connection = None) -> int:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}, must be one of {sorted(VALID_STATUSES)}")
    own_conn = conn is None
    conn = conn or get_conn()
    ensure_schema(conn)
    sha = None
    if evidence_path is not None and Path(evidence_path).exists() and Path(evidence_path).is_file():
        sha = sha256_file(evidence_path)
    cur = conn.execute(
        """INSERT INTO evidence_ledger (run_id, claim, status, evidence_path, sha256, observed_at)
           VALUES (?,?,?,?,?,?)""",
        (run_id, claim, status, str(evidence_path) if evidence_path else None, sha, _now()),
    )
    conn.commit()
    claim_id = cur.lastrowid
    if own_conn:
        conn.close()
    return claim_id


def correct_evidence(old_claim_id: int, new_claim: str, new_status: str, evidence_path=None,
                      run_id=None, conn: sqlite3.Connection = None) -> int:
    """APPEND-ONLY correction: never UPDATEs the old row's claim/status. Inserts a new row
    and points the old row's superseded_by at it."""
    own_conn = conn is None
    conn = conn or get_conn()
    new_id = record_evidence(new_claim, new_status, evidence_path=evidence_path, run_id=run_id, conn=conn)
    conn.execute("UPDATE evidence_ledger SET superseded_by=? WHERE claim_id=?", (new_id, old_claim_id))
    conn.commit()
    if own_conn:
        conn.close()
    return new_id
