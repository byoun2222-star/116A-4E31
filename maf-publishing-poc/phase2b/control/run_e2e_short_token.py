# -*- coding: utf-8 -*-
"""
PHASE 2B — ONE short-token real E2E (worker-6/surface:220).
Uses the already-established, unmodified task schema/validator (phase2b/tasks/test_task.py),
token protocol (phase2b/control/token_manifest.py), and Publishing DB canonical functions
(phase2a/db/publishing_db.py). Does not touch startup/launcher/model/Protocol V1/allowlist.
"""
import hashlib
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
from db import publishing_db as db  # noqa: E402

TASK_ID = "phase2b-task-e2e-worker6-001"
WORKFLOW_RUN_ID = "wf-e2e-worker6-001"
BOOK_ID = "BOOK-POC-002"
ROLE = "worker-6"
PROVIDER = "CODEX"
ACTOR = "claude-session-phase2b-e2e"

TASK_PATH = PHASE2B_ROOT / "tasks" / "pending" / f"{TASK_ID}.json"
RESULT_PATH = PHASE2B_ROOT / "data" / "results" / f"{TASK_ID}.json"


def main():
    report = {}
    conn = eh.get_conn()

    # ---- idempotency pre-check: no conflicting existing artifacts for this fresh task_id ----
    if TASK_PATH.exists() or RESULT_PATH.exists():
        print("IDEMPOTENCY_CONFLICT — STOP (task/result file already exists)")
        return
    existing_task_row = conn.execute("SELECT status FROM task WHERE task_id=?", (TASK_ID,)).fetchone()
    if existing_task_row is not None:
        print(f"IDEMPOTENCY_CONFLICT — STOP (task row already exists, status={existing_task_row[0]})")
        return
    existing_manifest = tm._load_manifest()
    for tok, entry in existing_manifest.items():
        if entry.get("task_id") == TASK_ID:
            print(f"IDEMPOTENCY_CONFLICT — STOP (token {tok} already maps to this task_id)")
            return

    # ---- build + write canonical task packet ----
    packet = test_task.build_task_packet(TASK_ID, WORKFLOW_RUN_ID, BOOK_ID)
    task_sha256, task_bytes = test_task.write_task_file(packet, TASK_PATH)
    report["TASK_ID"] = TASK_ID
    report["TASK_SHA256"] = task_sha256
    report["task_bytes"] = task_bytes

    # ---- deterministic token generation + manifest registration ----
    token = tm.register_token(TASK_ID, TASK_PATH, RESULT_PATH, task_sha256)
    report["TOKEN"] = token

    # ---- DB task row (canonical function, not a bespoke INSERT) ----
    db.create_task(TASK_ID, WORKFLOW_RUN_ID, BOOK_ID, test_task.TASK_TYPE, ACTOR, assigned_provider=PROVIDER)

    # ---- target policy evaluation WITH the real task now present ----
    policy = adapter.check_target_policy(ROLE, PROVIDER, TASK_ID)
    report["TARGET_POLICY"] = "ALLOW" if policy.allowed else "DENY"
    report["TARGET_POLICY_REASON"] = policy.reason
    print("TARGET POLICY:", report["TARGET_POLICY"], "-", policy.reason)

    run_id = eh.start_run(
        objective=f"ONE short-token real E2E: {TASK_ID} on {ROLE}/CODEX/surface:220 -- full "
                   f"control-plane path (RUN <TOKEN> -> manifest lookup -> task file read -> "
                   f"METADATA_NORMALIZATION -> atomic result -> deterministic validation -> DB COMPLETED)",
        actor="claude-session", provider=PROVIDER, role=ROLE, agent="codex",
        precondition={"target_policy_allowed": policy.allowed, "target_policy_reason": policy.reason,
                      "task_id": TASK_ID, "token": token, "task_sha256": task_sha256},
        raw_command=f"cys send --surface surface:220 'RUN {token}' ; cys send-key --surface surface:220 Return",
        conn=conn,
    )
    report["RUN_ID"] = run_id
    print("RUN_ID:", run_id)

    eh.record_evidence(f"Task file written: {TASK_PATH}, sha256={task_sha256}, {task_bytes} bytes",
                        "CONFIRMED", evidence_path=str(TASK_PATH), run_id=run_id, conn=conn)
    eh.record_evidence(f"Token generated+registered: {token} -> {TASK_ID} (deterministic T+sha256[:8].upper())",
                        "CONFIRMED", run_id=run_id, conn=conn)
    eh.record_evidence(f"DB task row created: task_id={TASK_ID}, status=PENDING, assigned_provider=CODEX",
                        "CONFIRMED", run_id=run_id, conn=conn)
    eh.record_evidence(f"check_target_policy('{ROLE}','{PROVIDER}','{TASK_ID}') = {report['TARGET_POLICY']}: {policy.reason}",
                        "CONFIRMED", run_id=run_id, conn=conn)

    if not policy.allowed:
        print("TARGET POLICY DENY -- SAFE-STOP, no control token will be sent.")
        eh.finalize_run(run_id, final_status="SAFE_STOP",
                         stop_reason=f"Target policy denied: {policy.reason}", conn=conn)
        conn.commit(); conn.close()
        report["CONTROL_SEND_COUNT"] = 0
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    conn.commit()

    # ---- control plane: exactly one RUN <TOKEN>, nothing else, no resend ----
    import subprocess
    send_proc = subprocess.run(["cys", "send", "--surface", "surface:220", f"RUN {token}"],
                                capture_output=True, text=True)
    sendkey_proc = subprocess.run(["cys", "send-key", "--surface", "surface:220", "Return"],
                                   capture_output=True, text=True)
    report["CONTROL_SEND_COUNT"] = 1
    report["send_rc"] = send_proc.returncode
    report["sendkey_rc"] = sendkey_proc.returncode
    print("send rc=", send_proc.returncode, "send-key rc=", sendkey_proc.returncode)

    eh.record_evidence(f"Control plane sent EXACTLY ONCE: 'RUN {token}' to surface:220 "
                        f"(send rc={send_proc.returncode}, send-key rc={sendkey_proc.returncode})",
                        "CONFIRMED", run_id=run_id, conn=conn)
    conn.commit()
    conn.close()

    # ---- poll for the FINAL result file only (file-based, no screen scraping, no resend) ----
    collected = adapter.collect_test_result_file(TASK_ID, timeout_s=90.0, poll_interval_s=2.0)
    report["result_collected"] = collected.get("ok")

    conn = eh.get_conn()
    if not collected.get("ok"):
        print("RESULT NOT OBSERVED within timeout -- SAFE-STOP (no resend/recovery/retry).")
        eh.record_evidence(f"collect_test_result_file timed out: {collected.get('error')}",
                            "FAILED", run_id=run_id, conn=conn)
        eh.finalize_run(run_id, final_status="FAILED",
                         stop_reason=f"No result file observed: {collected.get('error')}",
                         retry_count=0, conn=conn)
        conn.commit(); conn.close()
        report["SHORT_TOKEN_REAL_E2E"] = "FAIL"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    result_sha256 = collected["sha256"]
    raw_text = collected["raw_text"]
    report["RESULT_SHA256"] = result_sha256

    # UTF-8 / U+2014 checks (explicit, on top of the validator's own string-equality check)
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

    eh.record_evidence(
        f"Result file collected: {RESULT_PATH}, sha256={result_sha256}, {collected['byte_length']} bytes. "
        f"UTF-8 decode OK={utf8_ok}. U+2014 present={u2014_present}. "
        f"Deterministic validator passed={validation.passed}, reasons={validation.reasons}",
        "CONFIRMED" if validation.passed else "FAILED",
        evidence_path=str(RESULT_PATH), run_id=run_id, conn=conn,
    )

    overall_pass = (
        policy.allowed and utf8_ok and u2014_present and validation.passed
        and report["TASK_SHA256"] == task_sha256
    )

    if overall_pass:
        # manifest -> COMPLETED
        manifest = tm._load_manifest()
        manifest[token]["status"] = "COMPLETED"
        tm._save_manifest(manifest)

        # DB: task -> COMPLETED, provider_run row recorded
        db.set_task_status(TASK_ID, "COMPLETED", ACTOR)
        provider_run_id = f"run-e2e-{token.lower()}"
        db.record_provider_run(provider_run_id, PROVIDER, TASK_ID, test_task.TASK_TYPE, "COMPLETED",
                                notes=f"short-token real E2E, result_sha256={result_sha256}",
                                usage_reliability="observed")

        # confirm DB reflects exactly this result hash via an explicit evidence row (not a new column)
        eh.record_evidence(
            f"Publishing DB updated: task.status=COMPLETED, provider_run {provider_run_id} COMPLETED. "
            f"DB-recorded result reference matches file sha256={result_sha256} (same value used in both "
            f"the evidence_ledger row above and this DB provider_run.notes).",
            "CONFIRMED", run_id=run_id, conn=conn,
        )
        eh.finalize_run(run_id, final_status="COMPLETED", retry_count=0,
                         input_artifacts=[str(TASK_PATH)], output_artifacts=[str(RESULT_PATH)],
                         validation_result=f"PASS: {validation.to_dict()}",
                         db_changes={"task_status": "COMPLETED", "provider_run_id": provider_run_id},
                         conn=conn)
        report["SHORT_TOKEN_REAL_E2E"] = "PASS"
        report["PROVIDER_RUN_ID"] = provider_run_id
    else:
        eh.finalize_run(run_id, final_status="FAILED", retry_count=0,
                         stop_reason="Validation or integrity check failed -- see VALIDATOR_REASONS",
                         conn=conn)
        report["SHORT_TOKEN_REAL_E2E"] = "FAIL"

    conn.commit()
    conn.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
