# -*- coding: utf-8 -*-
"""
Deterministic, local-only tests for the Durable Project Record infrastructure.
No Claude/Codex/Gemini calls. Plain asserts, prints PASS/FAIL per check, exits nonzero on any failure.
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh  # noqa: E402
import generate_project_state as gps  # noqa: E402

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}: {name}")


def main():
    conn = eh.get_conn()

    # 0. Baseline: pre-existing Publishing DB table row counts, to prove non-mutation later.
    pre_existing_tables = [
        "book", "contract", "production", "distribution", "marketing", "approval",
        "file_version", "workflow_run", "task", "provider", "provider_run",
        "system_event", "checkpoint_reference", "state_transition_log",
    ]
    pre_counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in pre_existing_tables}

    # 1. schema/table creation (idempotent — call twice)
    eh.ensure_schema(conn)
    eh.ensure_schema(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    check("schema: phase2b_run_record table exists", "phase2b_run_record" in tables)
    check("schema: evidence_ledger table exists", "evidence_ledger" in tables)

    # 2. run creation/finalize
    run_id = eh.start_run(
        objective="durable-record self-test",
        actor="claude-session",
        provider="LOCAL",
        raw_command="python test_durable_record_local.py --selftest password=should_not_be_stored",
        conn=conn,
    )
    row = conn.execute("SELECT final_status FROM phase2b_run_record WHERE run_id=?", (run_id,)).fetchone()
    check("run_record: start_run inserts RUNNING row", row is not None and row[0] == "RUNNING")

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("durable record self-test artifact\n")
        tmp_artifact = f.name
    expected_hash = hashlib.sha256(Path(tmp_artifact).read_bytes()).hexdigest()

    eh.finalize_run(
        run_id, final_status="COMPLETED", stop_reason=None,
        output_artifacts=[tmp_artifact], validation_result="selftest-ok", conn=conn,
    )
    fin = conn.execute(
        "SELECT final_status, output_artifacts_json FROM phase2b_run_record WHERE run_id=?", (run_id,)
    ).fetchone()
    check("run_record: finalize_run sets COMPLETED", fin[0] == "COMPLETED")

    # 3. SHA-256 auto-calculation correctness
    out_artifacts = json.loads(fin[1])
    check("hash: auto-computed sha256 matches manual hashlib", out_artifacts[0]["sha256"] == expected_hash)

    # 4. secret NOT recorded in command_display (redaction)
    cmd_row = conn.execute(
        "SELECT command_display, command_sha256 FROM phase2b_run_record WHERE run_id=?", (run_id,)
    ).fetchone()
    check("secret: raw 'password=' value absent from stored command_display",
          "should_not_be_stored" not in (cmd_row[0] or ""))
    check("secret: command_sha256 still recorded despite redaction",
          cmd_row[1] is not None and len(cmd_row[1]) == 64)

    # 5. evidence registration + auto hash from a real file
    claim_id = eh.record_evidence(
        "selftest artifact exists and is hashed", "CONFIRMED", evidence_path=tmp_artifact,
        run_id=run_id, conn=conn,
    )
    ev = conn.execute("SELECT status, sha256, superseded_by FROM evidence_ledger WHERE claim_id=?",
                       (claim_id,)).fetchone()
    check("evidence: CONFIRMED row inserted with matching sha256", ev[0] == "CONFIRMED" and ev[1] == expected_hash)
    check("evidence: superseded_by NULL on fresh claim", ev[2] is None)

    # 6. append-only correction — old row must remain UNCHANGED except superseded_by
    new_id = eh.correct_evidence(
        claim_id, "selftest artifact exists and is hashed (corrected wording)", "CONFIRMED",
        evidence_path=tmp_artifact, run_id=run_id, conn=conn,
    )
    old_after = conn.execute("SELECT claim, status, superseded_by FROM evidence_ledger WHERE claim_id=?",
                              (claim_id,)).fetchone()
    check("append-only: old claim text unchanged after correction",
          old_after[0] == "selftest artifact exists and is hashed")
    check("append-only: old row now points to new claim_id via superseded_by", old_after[2] == new_id)
    check("append-only: a NEW row was created (not an UPDATE in place)", new_id != claim_id)

    # 7. NOT_FOUND vs FAILED are distinguishable, both storable
    nf_id = eh.record_evidence("surface:66 argv evidence search", "NOT_FOUND", run_id=run_id, conn=conn)
    failed_id = eh.record_evidence("startup command construction", "FAILED", run_id=run_id, conn=conn)
    nf_status = conn.execute("SELECT status FROM evidence_ledger WHERE claim_id=?", (nf_id,)).fetchone()[0]
    failed_status = conn.execute("SELECT status FROM evidence_ledger WHERE claim_id=?", (failed_id,)).fetchone()[0]
    check("status: NOT_FOUND stored distinctly from FAILED", nf_status == "NOT_FOUND" and failed_status == "FAILED"
          and nf_status != failed_status)

    # invalid status must be rejected (keeps the 6-state vocabulary closed)
    try:
        eh.record_evidence("bad status probe", "DID_NOT_HAPPEN", run_id=run_id, conn=conn)
        check("status: invalid status value rejected", False)
    except ValueError:
        check("status: invalid status value rejected", True)

    # 8. PROJECT_STATE generation
    state = gps.write_state()
    check("project_state: file written", gps.OUT_PATH.exists())
    reloaded = json.loads(gps.OUT_PATH.read_text(encoding="utf-8"))
    required_keys = {
        "phase", "subphase", "current_status", "last_completed_step", "next_step", "blockers",
        "authoritative_checkpoint", "protocol_versions", "protected_surfaces", "allowed_test_roles",
        "execution_counters", "pending_approvals", "updated_at",
    }
    check("project_state: required fields present", required_keys.issubset(reloaded.keys()))
    check("project_state: checkpoint sha256 populated", bool(reloaded["authoritative_checkpoint"]["sha256"]))

    # 9. existing Publishing DB data unchanged
    post_counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in pre_existing_tables}
    check("isolation: pre-existing Publishing DB tables row-counts unchanged", pre_counts == post_counts)

    # 10. idempotency on rerun (schema creation + state regeneration)
    eh.ensure_schema(conn)
    tables_after_rerun = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    check("idempotency: rerunning ensure_schema() does not error or duplicate tables",
          tables_after_rerun == tables)
    gps.write_state()
    check("idempotency: rerunning PROJECT_STATE generation succeeds", gps.OUT_PATH.exists())

    conn.commit()
    conn.close()
    Path(tmp_artifact).unlink(missing_ok=True)

    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED CHECKS:", failed)
        sys.exit(1)
    print("ALL DETERMINISTIC TESTS PASSED")
    return run_id


if __name__ == "__main__":
    main()
