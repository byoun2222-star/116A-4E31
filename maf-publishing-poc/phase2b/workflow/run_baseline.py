# Copyright (c) tree and fruits. PoC only — PHASE 2B baseline run driver.
"""Runs ONE forced-baseline provider run end to end: target-policy check -> submit_test_task
-> poll collect_test_result until the JSON answer appears or timeout -> deterministic
validate_output -> record_run_started/record_run_completed in the Publishing DB -> save raw
result artifact with hash. Used sequentially for RUN-1 (Claude/worker-4), RUN-2 (Codex/worker-5),
RUN-3 (Gemini/worker-6) — never more than one test surface open/running at a time (master's
memory-safety instruction layered on top of owner §14)."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

PHASE2B_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHASE2B_ROOT))
from collector import result_collector as rc  # noqa: E402
from controlled_adapter.controlled_cys_adapter import (  # noqa: E402
    check_target_policy, collect_test_result, submit_test_task,
)
from tasks.test_task import build_task_packet, validate_output  # noqa: E402

PHASE2A_ROOT = PHASE2B_ROOT.parent / "phase2a"
sys.path.insert(0, str(PHASE2A_ROOT))
from db import publishing_db as db  # noqa: E402

BOOK_ID = "BOOK-POC-002"
WORKFLOW_RUN_ID = "phase2b-wfrun-001"


def get_health(role: str) -> str:
    proc = subprocess.run(["cys", "status", "--json"], capture_output=True, text=True, timeout=15.0)
    if proc.returncode != 0:
        return "UNKNOWN"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return "UNKNOWN"
    for s in data.get("surfaces", []):
        if s.get("role") == role:
            if s.get("exited"):
                return "UNAVAILABLE"
            if s.get("agent_alive") is not True:
                return "DEGRADED"
            return "AVAILABLE"
    return "UNKNOWN"


def get_usage(role: str) -> tuple[str, str]:
    """Returns (usage_value_repr, reliability). Honest per Phase 2A finding: claude=HIGH
    (hook-verified statusline), codex=LOW (self-labeled heuristic:stale), gemini=UNKNOWN
    (no observable surface usage entry has ever been found for it)."""
    proc = subprocess.run(["cys", "status", "--json"], capture_output=True, text=True, timeout=15.0)
    if proc.returncode != 0:
        return "UNKNOWN", "UNKNOWN"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return "UNKNOWN", "UNKNOWN"
    for s in data.get("surfaces", []):
        if s.get("role") == role:
            usage = s.get("usage") or {}
            source = usage.get("source")
            if source == "statusline":
                return json.dumps(usage.get("rate")), "HIGH"
            if source and "heuristic" in source:
                return json.dumps(usage.get("rate")), "LOW"
            return json.dumps(usage), "UNKNOWN"
    return "UNKNOWN", "UNKNOWN"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--provider", required=True, choices=["CLAUDE", "CODEX", "GEMINI"])
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--poll-seconds", type=float, default=90.0)
    ap.add_argument("--poll-interval", type=float, default=10.0)
    args = ap.parse_args()

    rc.migrate()
    idempotency_key = f"idem-{args.task_id}"
    dup = rc.already_ran(idempotency_key, task_id=args.task_id)
    if dup is not None:
        print(f"IDEMPOTENT_SKIP: task_id={args.task_id} already COMPLETED as run_id={dup['run_id']} "
              f"(status={dup['status']}) — not re-submitting, not re-invoking provider")
        print(json.dumps(dup))
        return 0

    policy = check_target_policy(args.role, args.provider, args.task_id)
    print("target_policy:", policy)
    if not policy.allowed:
        print("ABORT:", policy.reason)
        return 1

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    health_before = get_health(args.role)
    usage_before, reliability = get_usage(args.role)
    rc.record_run_started(run_id, args.provider, args.task_id, "METADATA_NORMALIZATION",
                           surface_id=policy.surface_ref, agent_role=args.role,
                           health_before=health_before, usage_before=usage_before,
                           usage_reliability=reliability, idempotency_key=idempotency_key)
    db.set_task_status(args.task_id, "RUNNING", actor="run_baseline")

    packet = build_task_packet(args.task_id, WORKFLOW_RUN_ID, BOOK_ID)
    started = time.monotonic()
    submission = submit_test_task(args.role, args.provider, args.task_id, packet)
    print("submission:", submission)
    if not submission["submitted"]:
        rc.record_run_completed(run_id, "SUBMIT_FAILED", output_hash="", validation_result={"passed": False, "reasons": [submission["reason"]]},
                                 health_after=get_health(args.role), usage_after=get_usage(args.role)[0],
                                 error_type="SUBMIT_FAILED", duration_seconds=time.monotonic() - started,
                                 notes=submission["reason"])
        db.set_task_status(args.task_id, "FAILED", actor="run_baseline")
        print("ABORT: submission failed")
        return 1

    deadline = time.monotonic() + args.poll_seconds
    extracted = None
    raw_screen = ""
    while time.monotonic() < deadline:
        time.sleep(args.poll_interval)
        result = collect_test_result(args.role)
        if result.get("ok") and result.get("extracted_json") is not None:
            extracted = result["extracted_json"]
            raw_screen = result["raw_screen"]
            break
        raw_screen = result.get("raw_screen") or raw_screen

    duration = time.monotonic() - started
    health_after = get_health(args.role)
    usage_after, _ = get_usage(args.role)

    if extracted is None:
        validation = {"passed": False, "reasons": ["no JSON answer observed on screen within poll window"]}
        output_hash = ""
        status = "TIMEOUT_NO_RESULT"
        error_type = "TIMEOUT"
    else:
        raw_text = json.dumps(extracted, ensure_ascii=False)
        _, output_hash = rc.save_raw_result(run_id, raw_text)
        vres = validate_output(raw_text)
        validation = vres.to_dict()
        status = "COMPLETED" if vres.passed else "VALIDATION_FAILED"
        error_type = None if vres.passed else "VALIDATION_FAILED"

    rc.record_run_completed(run_id, status, output_hash, validation, health_after, usage_after,
                             error_type, duration, notes=f"role={args.role} provider={args.provider}")
    db.set_task_status(args.task_id, status, actor="run_baseline")

    print("run_id:", run_id)
    print("status:", status)
    print("validation:", validation)
    print("extracted_json:", extracted)
    return 0 if status == "COMPLETED" else 2


if __name__ == "__main__":
    sys.exit(main())
