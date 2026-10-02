# Copyright (c) tree and fruits. PoC only.
"""TEST 2B-F — Idempotency identity/hash fallback (owner-directed fix, 2026-10-02): verifies
result_collector.already_ran()'s new fallback path for rows with idempotency_key=NULL. Zero
AI/provider calls, zero re-execution of any completed task, zero modification of existing
production rows -- all conflict-path tests use disposable fixture rows/files, cleaned up after.
"""
import hashlib
import sys
from pathlib import Path

PHASE2B_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHASE2B_ROOT))
sys.path.insert(0, str(PHASE2B_ROOT / "control"))
sys.path.insert(0, str(PHASE2B_ROOT.parent / "phase2a"))

from collector import result_collector as rc  # noqa: E402
from controlled_adapter.controlled_cys_adapter import check_target_policy  # noqa: E402
from db import publishing_db as db  # noqa: E402


def check(label, condition, results):
    results.append((label, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}: {label}")


def main():
    results = []
    rc.migrate()
    conn = db.get_conn()

    # 1. REAL Codex row (idempotency_key=NULL): fallback now resolves it, read-only
    dup = rc.already_ran("idem-phase2b-task-e2e-worker6-001", task_id="phase2b-task-e2e-worker6-001")
    check("Codex NULL-idempotency_key row now resolved via identity_hash_fallback",
          dup is not None and dup["run_id"] == "run-e2e-tfbab618c" and dup["matched_via"] == "identity_hash_fallback",
          results)

    # 2. REAL Claude/Gemini rows: unaffected, still matched via idempotency_key (no regression)
    dup_c = rc.already_ran("idem-phase2b-task-e2e-claude-worker4-001", task_id="phase2b-task-e2e-claude-worker4-001")
    check("Claude row still matched via idempotency_key (unaffected by fallback)",
          dup_c is not None and dup_c["matched_via"] == "idempotency_key", results)
    dup_g = rc.already_ran("idem-phase2b-task-e2e-gemini-worker8-001", task_id="phase2b-task-e2e-gemini-worker8-001")
    check("Gemini row still matched via idempotency_key (unaffected by fallback)",
          dup_g is not None and dup_g["matched_via"] == "idempotency_key", results)

    # 3. Fixture: task not COMPLETED -> fallback returns None (no false positive)
    fx_task_id = "contract-test-idem-fallback-not-completed"
    db.create_task(fx_task_id, "wf-test", "BOOK-POC-002", "METADATA_NORMALIZATION", "test")
    r = rc.already_ran("idem-nonexistent-key", task_id=fx_task_id)
    check("fallback returns None for a non-COMPLETED task (no false positive)", r is None, results)
    conn.execute("DELETE FROM task WHERE task_id=?", (fx_task_id,))
    conn.commit()

    # 4. Fixture: COMPLETED task + matching provider_run + matching result file -> fallback PASS
    fx_task_id2 = "contract-test-idem-fallback-match"
    fx_result_path = PHASE2B_ROOT / "data" / "results" / f"{fx_task_id2}.json"
    fx_result_path.write_text('{"ok": true}', encoding="utf-8")
    fx_hash = hashlib.sha256(fx_result_path.read_bytes()).hexdigest()
    db.create_task(fx_task_id2, "wf-test", "BOOK-POC-002", "METADATA_NORMALIZATION", "test")
    db.set_task_status(fx_task_id2, "COMPLETED", "test")
    conn.execute(
        "INSERT INTO provider_run (run_id, provider, task_id, task_type, started_at, status, "
        "retry_count, output_hash) VALUES (?,?,?,?,?,?,0,?)",
        ("fx-run-match", "CODEX", fx_task_id2, "METADATA_NORMALIZATION", "2026-10-02T00:00:00Z",
         "COMPLETED", fx_hash),
    )
    conn.commit()
    r = rc.already_ran("idem-nonexistent-key", task_id=fx_task_id2)
    check("fallback matches when hash is consistent", r is not None and r["run_id"] == "fx-run-match", results)

    # 5. Fixture: hash MISMATCH -> IdempotencyConflict raised (not silently resolved)
    conn.execute("UPDATE provider_run SET output_hash='deadbeef' WHERE run_id='fx-run-match'")
    conn.commit()
    try:
        rc.already_ran("idem-nonexistent-key", task_id=fx_task_id2)
        check("hash mismatch raises IdempotencyConflict", False, results)
    except rc.IdempotencyConflict:
        check("hash mismatch raises IdempotencyConflict", True, results)

    # 6. Fixture: multiple conflicting COMPLETED rows for the same task_id -> IdempotencyConflict
    conn.execute("UPDATE provider_run SET output_hash=? WHERE run_id='fx-run-match'", (fx_hash,))
    conn.execute(
        "INSERT INTO provider_run (run_id, provider, task_id, task_type, started_at, status, "
        "retry_count, output_hash) VALUES (?,?,?,?,?,?,0,?)",
        ("fx-run-match-2", "CLAUDE", fx_task_id2, "METADATA_NORMALIZATION", "2026-10-02T00:00:01Z",
         "COMPLETED", fx_hash),
    )
    conn.commit()
    try:
        rc.already_ran("idem-nonexistent-key", task_id=fx_task_id2)
        check("multiple conflicting COMPLETED rows raise IdempotencyConflict", False, results)
    except rc.IdempotencyConflict:
        check("multiple conflicting COMPLETED rows raise IdempotencyConflict", True, results)

    # 7. Fixture: COMPLETED, no output_hash, no result file -> IdempotencyConflict (ambiguous)
    fx_task_id3 = "contract-test-idem-fallback-ambiguous"
    db.create_task(fx_task_id3, "wf-test", "BOOK-POC-002", "METADATA_NORMALIZATION", "test")
    db.set_task_status(fx_task_id3, "COMPLETED", "test")
    conn.execute(
        "INSERT INTO provider_run (run_id, provider, task_id, task_type, started_at, status, retry_count) "
        "VALUES (?,?,?,?,?,?,0)",
        ("fx-run-ambiguous", "GEMINI", fx_task_id3, "METADATA_NORMALIZATION", "2026-10-02T00:00:00Z", "COMPLETED"),
    )
    conn.commit()
    try:
        rc.already_ran("idem-nonexistent-key", task_id=fx_task_id3)
        check("COMPLETED+no-hash+no-file raises IdempotencyConflict (ambiguous)", False, results)
    except rc.IdempotencyConflict:
        check("COMPLETED+no-hash+no-file raises IdempotencyConflict (ambiguous)", True, results)

    # ---- cleanup all fixtures ----
    for rid in ("fx-run-match", "fx-run-match-2", "fx-run-ambiguous"):
        conn.execute("DELETE FROM provider_run WHERE run_id=?", (rid,))
    for tid in (fx_task_id2, fx_task_id3):
        conn.execute("DELETE FROM task WHERE task_id=?", (tid,))
    conn.commit()
    fx_result_path.unlink(missing_ok=True)

    # 8. REGRESSION: target_policy still independently denies re-submission (unaffected by fix)
    r = check_target_policy("worker-6", "CODEX", "phase2b-task-e2e-worker6-001")
    check("target_policy still denies re-submission of the real COMPLETED Codex task",
          not r.allowed and "already COMPLETED" in r.reason, results)

    # 9. REGRESSION: retry_count == 0 preserved for all 3 real Durable Project Record runs
    import evidence_hash as eh
    econn = eh.get_conn()
    for durable_run_id in ("run2b-d7f7a04578394cc7", "run2b-5d0c5dfbeda34867", "run2b-0df75d7a57a04391"):
        row = econn.execute("SELECT retry_count FROM phase2b_run_record WHERE run_id=?", (durable_run_id,)).fetchone()
        check(f"retry_count==0 preserved for {durable_run_id}", row is not None and row[0] == 0, results)
    econn.close()

    conn.close()

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} idempotency fallback checks passed")
    print("TEST 2B-F:", "PASS" if passed == total else "FAIL")
    return passed == total, passed, total


if __name__ == "__main__":
    ok, passed, total = main()
    sys.exit(0 if ok else 1)
