# -*- coding: utf-8 -*-
"""
PHASE 2B — ONE short-token real E2E for GEMINI (worker-8/surface:222, Antigravity/agy).
Mirrors run_e2e_claude_short_token.py exactly (same contract, same canonical provenance path
result_collector.record_run_started/record_run_completed). Control payload sent to the surface
is ONLY "RUN <TOKEN>" -- canonical task body never goes over PTY. Result is collected file-based
only (collect_test_result_file), never screen-scraped.
"""
import json
import sys
import time
from pathlib import Path

PHASE2B_CONTROL = Path(__file__).resolve().parent
PHASE2B_ROOT = PHASE2B_CONTROL.parent
MAF_ROOT = PHASE2B_ROOT.parent

sys.path.insert(0, str(PHASE2B_ROOT))
sys.path.insert(0, str(PHASE2B_CONTROL))
sys.path.insert(0, str(MAF_ROOT / "phase2a"))

import evidence_hash as eh  # noqa: E402
import token_manifest as tm  # noqa: E402
from tasks import test_task  # noqa: E402
from controlled_adapter import controlled_cys_adapter as adapter  # noqa: E402
from collector import result_collector as rc  # noqa: E402
from db import publishing_db as db  # noqa: E402

# "workflow" is ambiguous (phase2a/workflow is a REGULAR package) -- import run_baseline by path.
sys.path.insert(0, str(PHASE2B_ROOT / "workflow"))
from run_baseline import get_health, get_usage  # noqa: E402

TASK_ID = "phase2b-task-e2e-gemini-worker8-001"
WORKFLOW_RUN_ID = "wf-e2e-gemini-worker8-001"
BOOK_ID = "BOOK-POC-002"
ROLE = "worker-8"
PROVIDER = "GEMINI"
SURFACE_REF = "surface:222"
ACTOR = "claude-session-phase2b-e2e-gemini"
IDEMPOTENCY_KEY = f"idem-{TASK_ID}"

TASK_PATH = PHASE2B_ROOT / "tasks" / "pending" / f"{TASK_ID}.json"
RESULT_PATH = PHASE2B_ROOT / "data" / "results" / f"{TASK_ID}.json"


def main():
    report = {}
    conn = eh.get_conn()

    # ---- idempotency pre-check (identity+hash fallback included, see result_collector.already_ran) ----
    rc.migrate()
    try:
        dup = rc.already_ran(IDEMPOTENCY_KEY, task_id=TASK_ID)
    except rc.IdempotencyConflict as e:
        print(f"IDEMPOTENCY_CONFLICT — STOP ({e})")
        return
    if dup is not None:
        print(f"IDEMPOTENCY_CONFLICT — STOP (already COMPLETED as {dup['run_id']}, matched_via={dup.get('matched_via')})")
        return
    if TASK_PATH.exists() or RESULT_PATH.exists():
        print("IDEMPOTENCY_CONFLICT — STOP (task/result file already exists)")
        return
    existing_task_row = conn.execute("SELECT status FROM task WHERE task_id=?", (TASK_ID,)).fetchone()
    if existing_task_row is not None:
        print(f"IDEMPOTENCY_CONFLICT — STOP (task row exists, status={existing_task_row[0]})")
        return
    for tok, entry in tm._load_manifest().items():
        if entry.get("task_id") == TASK_ID:
            print(f"IDEMPOTENCY_CONFLICT — STOP (token {tok} already maps to this task_id)")
            return

    # ---- build + write canonical task packet (brand new, not reused from Codex/Claude) ----
    packet = test_task.build_task_packet(TASK_ID, WORKFLOW_RUN_ID, BOOK_ID)
    task_sha256, task_bytes = test_task.write_task_file(packet, TASK_PATH)
    report["TASK_ID"] = TASK_ID
    report["TASK_SHA256"] = task_sha256

    # ---- deterministic token generation + manifest registration (scope-checked) ----
    token = tm.register_token(TASK_ID, TASK_PATH, RESULT_PATH, task_sha256)
    report["TOKEN"] = token

    # ---- DB task row ----
    db.create_task(TASK_ID, WORKFLOW_RUN_ID, BOOK_ID, test_task.TASK_TYPE, ACTOR, assigned_provider=PROVIDER)

    # ---- target policy evaluation WITH the real task now present ----
    policy = adapter.check_target_policy(ROLE, PROVIDER, TASK_ID)
    report["TARGET_POLICY"] = "ALLOW" if policy.allowed else "DENY"
    report["TARGET_POLICY_REASON"] = policy.reason
    print("TARGET POLICY:", report["TARGET_POLICY"], "-", policy.reason)

    run_id = eh.start_run(
        objective=f"ONE short-token real E2E (GEMINI/Antigravity-agy): {TASK_ID} on {ROLE}/GEMINI/"
                   f"{SURFACE_REF} -- canonical provenance path (result_collector.record_run_started/completed)",
        actor="claude-session", provider=PROVIDER, role=ROLE, agent="gemini", surface_ref=SURFACE_REF,
        precondition={"target_policy_allowed": policy.allowed, "target_policy_reason": policy.reason,
                      "task_id": TASK_ID, "token": token, "task_sha256": task_sha256},
        raw_command=f"cys send --surface {SURFACE_REF} 'RUN {token}' ; cys send-key --surface {SURFACE_REF} Return",
        conn=conn,
    )
    report["RUN_ID"] = run_id
    print("RUN_ID:", run_id)

    eh.record_evidence(f"Task file written: {TASK_PATH}, sha256={task_sha256}, {task_bytes} bytes",
                        "CONFIRMED", evidence_path=str(TASK_PATH), run_id=run_id, conn=conn)
    eh.record_evidence(f"Token generated+registered: {token} -> {TASK_ID}", "CONFIRMED", run_id=run_id, conn=conn)
    eh.record_evidence(f"check_target_policy result: {report['TARGET_POLICY']}: {policy.reason}",
                        "CONFIRMED", run_id=run_id, conn=conn)

    if not policy.allowed:
        print("TARGET POLICY DENY -- SAFE-STOP, no control token sent.")
        eh.finalize_run(run_id, final_status="SAFE_STOP", stop_reason=f"Target policy denied: {policy.reason}", conn=conn)
        conn.commit(); conn.close()
        report["CONTROL_SEND_COUNT"] = 0
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report
    conn.commit()

    # ---- canonical provenance: record_run_started BEFORE sending control token ----
    health_before = get_health(ROLE)
    usage_before, reliability = get_usage(ROLE)
    e2e_run_id = f"run-e2e-gemini-{token.lower()}"
    rc.record_run_started(e2e_run_id, PROVIDER, TASK_ID, test_task.TASK_TYPE,
                           surface_id=SURFACE_REF, agent_role=ROLE,
                           health_before=health_before, usage_before=usage_before,
                           usage_reliability=reliability, idempotency_key=IDEMPOTENCY_KEY)
    db.set_task_status(TASK_ID, "RUNNING", ACTOR)
    report["PROVENANCE_RUN_ID"] = e2e_run_id

    # ---- control plane: exactly one RUN <TOKEN> via Python subprocess list-argv ----
    import subprocess
    started = time.monotonic()
    send_proc = subprocess.run(["cys", "send", "--surface", SURFACE_REF, f"RUN {token}"],
                                capture_output=True, text=True)
    sendkey_proc = subprocess.run(["cys", "send-key", "--surface", SURFACE_REF, "Return"],
                                   capture_output=True, text=True)
    report["CONTROL_SEND_COUNT"] = 1
    print("send rc=", send_proc.returncode, "send-key rc=", sendkey_proc.returncode)

    eh.record_evidence(f"Control plane sent EXACTLY ONCE: 'RUN {token}' to {SURFACE_REF} "
                        f"(send rc={send_proc.returncode}, send-key rc={sendkey_proc.returncode})",
                        "CONFIRMED", run_id=run_id, conn=conn)
    conn.commit()
    conn.close()

    # ---- poll for the FINAL result file only (file-based, no screen scraping, no resend) ----
    collected = adapter.collect_test_result_file(TASK_ID, timeout_s=120.0, poll_interval_s=2.0)
    report["result_collected"] = collected.get("ok")
    duration = time.monotonic() - started

    conn = eh.get_conn()
    if not collected.get("ok"):
        print("RESULT NOT OBSERVED within timeout -- SAFE-STOP (no resend/recovery/retry).")
        eh.record_evidence(f"collect_test_result_file timed out: {collected.get('error')}", "FAILED", run_id=run_id, conn=conn)
        rc.record_run_completed(e2e_run_id, "TIMEOUT_NO_RESULT", output_hash="",
                                 validation_result={"passed": False, "reasons": [collected.get("error")]},
                                 health_after=get_health(ROLE), usage_after=get_usage(ROLE)[0],
                                 error_type="TIMEOUT", duration_seconds=duration, notes="no result file observed")
        db.set_task_status(TASK_ID, "TIMEOUT_NO_RESULT", ACTOR)
        eh.finalize_run(run_id, final_status="FAILED", stop_reason=f"No result file observed: {collected.get('error')}",
                         retry_count=0, conn=conn)
        conn.commit(); conn.close()
        report["GEMINI_SHORT_TOKEN_REAL_E2E"] = "FAIL"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    result_sha256 = collected["sha256"]
    raw_text = collected["raw_text"]
    report["RESULT_SHA256"] = result_sha256

    utf8_ok = True
    try:
        raw_text.encode("utf-8").decode("utf-8")
    except UnicodeError:
        utf8_ok = False
    u2014_present = "—" in raw_text
    report["UTF8"] = utf8_ok
    report["U2014_PRESERVED"] = u2014_present

    validation = test_task.validate_output(raw_text)
    report["VALIDATOR_PASSED"] = validation.passed
    report["VALIDATOR_REASONS"] = validation.reasons
    print("VALIDATOR PASSED:", validation.passed, validation.reasons)

    overall_pass = policy.allowed and utf8_ok and u2014_present and validation.passed

    eh.record_evidence(
        f"Result file collected: {RESULT_PATH}, sha256={result_sha256}, {collected['byte_length']} bytes. "
        f"UTF-8 OK={utf8_ok}. U+2014 present={u2014_present}. Validator passed={validation.passed}, "
        f"reasons={validation.reasons}",
        "CONFIRMED" if validation.passed else "FAILED",
        evidence_path=str(RESULT_PATH), run_id=run_id, conn=conn,
    )

    health_after = get_health(ROLE)
    usage_after, _ = get_usage(ROLE)

    if overall_pass:
        manifest = tm._load_manifest()
        manifest[token]["status"] = "COMPLETED"
        tm._save_manifest(manifest)

        rc.record_run_completed(e2e_run_id, "COMPLETED", result_sha256, validation.to_dict(),
                                 health_after, usage_after, None, duration,
                                 notes=f"role={ROLE} provider={PROVIDER} surface={SURFACE_REF}")
        db.set_task_status(TASK_ID, "COMPLETED", ACTOR)

        conn2 = eh.get_conn()
        row = conn2.execute(
            "SELECT provider, agent_role, surface_id, output_hash, status FROM provider_run WHERE run_id=?",
            (e2e_run_id,),
        ).fetchone()
        conn2.close()
        report["DB_PROVIDER"], report["DB_AGENT_ROLE"], report["DB_SURFACE_ID"], report["DB_OUTPUT_HASH"], report["DB_STATUS"] = row

        eh.record_evidence(
            f"Publishing DB updated via canonical result_collector path: provider_run {e2e_run_id} "
            f"COMPLETED, provider={row[0]}, agent_role={row[1]}, surface_id={row[2]}, "
            f"output_hash={row[3]} (matches file sha256={result_sha256}: {row[3] == result_sha256}). "
            f"task.status=COMPLETED.",
            "CONFIRMED", run_id=run_id, conn=conn,
        )
        eh.finalize_run(run_id, final_status="COMPLETED", retry_count=0,
                         input_artifacts=[str(TASK_PATH)], output_artifacts=[str(RESULT_PATH)],
                         validation_result=f"PASS: {validation.to_dict()}",
                         db_changes={"task_status": "COMPLETED", "provider_run_id": e2e_run_id,
                                     "provenance_complete": row[1] is not None and row[2] is not None},
                         conn=conn)
        report["GEMINI_SHORT_TOKEN_REAL_E2E"] = "PASS"
    else:
        rc.record_run_completed(e2e_run_id, "VALIDATION_FAILED", result_sha256, validation.to_dict(),
                                 health_after, usage_after, "VALIDATION_FAILED", duration,
                                 notes="validation failed")
        db.set_task_status(TASK_ID, "VALIDATION_FAILED", ACTOR)
        eh.finalize_run(run_id, final_status="FAILED", retry_count=0,
                         stop_reason="Validation/integrity failed -- see VALIDATOR_REASONS", conn=conn)
        report["GEMINI_SHORT_TOKEN_REAL_E2E"] = "FAIL"

    conn.commit()
    conn.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
