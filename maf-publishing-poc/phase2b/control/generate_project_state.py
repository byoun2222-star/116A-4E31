# -*- coding: utf-8 -*-
"""
Deterministically (re)generate phase2b/PROJECT_STATE.json from primary sources:
DB (phase2b_run_record/evidence_ledger), the authoritative checkpoint file, the protocol
V1 file, and controlled_cys_adapter.py's role constants.

This is the ONLY writer of PROJECT_STATE.json. Never hand-edit that file — rerun this script.
No AI calls. Pure deterministic read + compose + write.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent  # maf-publishing-poc/
PHASE2B = ROOT / "phase2b"
CHECKPOINT = Path(r"C:\Users\a\.cys\pack\round\WORKER_PHASE2B_CHECKPOINT_20260918.md")
PROTOCOL_V1 = Path(r"C:\Users\a\.cys\pack\round\evidence\phase2b-bootstrap-submit\token_protocol_message.txt")
ADAPTER = PHASE2B / "controlled_adapter" / "controlled_cys_adapter.py"
OUT_PATH = PHASE2B / "PROJECT_STATE.json"


def _hash_or_none(path: Path):
    return eh.sha256_file(path) if path.exists() else None


def _extract_role_set(src: str, const_name: str):
    m = re.search(rf"{const_name}\s*=\s*\{{([^}}]*)\}}", src)
    if not m:
        return None
    return sorted(re.findall(r'"([^"]+)"', m.group(1)))


def build_state() -> dict:
    conn = eh.get_conn()
    eh.ensure_schema(conn)

    adapter_src = ADAPTER.read_text(encoding="utf-8") if ADAPTER.exists() else ""
    allowed_test_roles = _extract_role_set(adapter_src, "PHASE2B_ALLOWED_TEST_ROLES") or []
    production_roles = _extract_role_set(adapter_src, "PRODUCTION_ROLES") or []

    run_count = conn.execute("SELECT COUNT(*) FROM phase2b_run_record").fetchone()[0]
    completed_count = conn.execute(
        "SELECT COUNT(*) FROM phase2b_run_record WHERE final_status='COMPLETED'"
    ).fetchone()[0]
    safe_stop_count = conn.execute(
        "SELECT COUNT(*) FROM phase2b_run_record WHERE final_status='SAFE_STOP'"
    ).fetchone()[0]
    evidence_count = conn.execute("SELECT COUNT(*) FROM evidence_ledger").fetchone()[0]
    normalization_runs_legacy = 4  # confirmed fact, Publishing DB provider_run COMPLETED/CODEX rows (surface:64/worker-8)

    state = {
        "project_id": "maf-publishing-poc/phase2b",
        "phase": "Phase 2B",
        "subphase": "Identity-Preserving Codex Startup Test",
        "current_status": "SAFE_STOP at STEP 2 (quoting-argv risk unverified) — awaiting owner decision",
        "last_completed_step": "STEP 1 PRECONDITION BATCH CHECK: PASS",
        "next_step": "Owner decision: fix --cmd argv transport (e.g. file-based, per submit_test_task_file precedent) or hold",
        "blockers": [
            "STEP2: cys.exe is a closed-source binary; cannot verify byte-for-byte preservation of "
            "multi-line protocol text (17 newlines, literal '<'/'>' chars) through its internal argv handling",
            "worker-10 (chosen fresh test role) is not in PHASE2B_ALLOWED_TEST_ROLES — would require "
            "TARGET POLICY CONFIG CHANGE REQUIRED — OWNER APPROVAL if STEP2 is cleared",
        ],
        "authoritative_checkpoint": {
            "path": str(CHECKPOINT),
            "sha256": _hash_or_none(CHECKPOINT),
        },
        "protocol_versions": {
            "V1": {
                "source": str(PROTOCOL_V1),
                "sha256": _hash_or_none(PROTOCOL_V1),
                "status": "CONFIRMED FROM LOCAL PRIMARY EVIDENCE",
            }
        },
        "active_test_surfaces": [],
        "protected_surfaces": production_roles,
        "allowed_test_roles": allowed_test_roles,
        "execution_counters": {
            "normalization_runs_legacy_completed": normalization_runs_legacy,
            "phase2b_run_record_total": run_count,
            "phase2b_run_record_completed": completed_count,
            "phase2b_run_record_safe_stop": safe_stop_count,
            "evidence_ledger_entries": evidence_count,
        },
        "pending_approvals": [
            "Identity-Preserving Startup Test STEP 3+ (surface creation) — not approved",
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "_generator": "phase2b/control/generate_project_state.py",
        "_note": "This file is a DERIVED snapshot, not an independent source of truth. "
                 "Authority order: evidence_ledger/phase2b_run_record > Publishing DB > .md checkpoint > conversation.",
    }
    conn.close()
    return state


def write_state() -> dict:
    state = build_state()
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT_PATH)
    return state


if __name__ == "__main__":
    s = write_state()
    print(json.dumps(s, ensure_ascii=False, indent=2))
