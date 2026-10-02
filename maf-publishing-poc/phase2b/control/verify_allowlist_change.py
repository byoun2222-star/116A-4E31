# -*- coding: utf-8 -*-
"""
Verifies the single-line PHASE2B_ALLOWED_TEST_ROLES expansion (worker-10 added).
No surface creation, no Codex/Claude/Gemini calls. Local deterministic checks only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import evidence_hash as eh  # noqa: E402

from controlled_adapter import controlled_cys_adapter as adapter  # noqa: E402

RESULTS = {}


def deny_reason(role, provider="CODEX", task_id="phase2b-nonexistent-probe-task"):
    r = adapter.check_target_policy(role, provider, task_id)
    return r.allowed, r.reason


def main():
    conn = eh.get_conn()
    run_id = eh.start_run(
        objective="Expand PHASE2B_ALLOWED_TEST_ROLES with fresh role worker-10 (owner-approved) "
                   "and verify target-policy behavior is otherwise unchanged",
        actor="claude-session",
        provider="LOCAL",
        raw_command="python verify_allowlist_change.py",
        conn=conn,
    )
    print("RUN_ID:", run_id)

    # 1. worker-10 now passes the allowlist gate (denial, if any, is NOT the allowlist reason)
    allowed, reason = deny_reason("worker-10")
    passes_allowlist_gate = not (reason and "not in the pre-announced" in reason)
    RESULTS["worker10_passes_allowlist_gate"] = passes_allowlist_gate
    RESULTS["worker10_reason"] = reason

    # 2. existing allowed role (worker-8) behaves the same way as before (same denial category:
    #    "no live surface found", since no surface exists for it right now either)
    allowed8, reason8 = deny_reason("worker-8")
    passes8 = not (reason8 and "not in the pre-announced" in reason8)
    RESULTS["worker8_still_passes_allowlist_gate"] = passes8
    RESULTS["worker8_reason"] = reason8

    # 3. unlisted fresh role still denied specifically by the allowlist check
    allowed11, reason11 = deny_reason("worker-11")
    RESULTS["worker11_denied_by_allowlist"] = (not allowed11) and ("not in the pre-announced" in (reason11 or ""))
    RESULTS["worker11_reason"] = reason11

    # 4. production role still denied, and denied specifically by the production check (first gate)
    allowed_master, reason_master = deny_reason("master")
    RESULTS["master_denied_by_production_check"] = (not allowed_master) and ("production role" in (reason_master or ""))
    RESULTS["master_reason"] = reason_master

    # 5. confirm the rest of the policy/constants are untouched
    RESULTS["production_roles_unchanged"] = adapter.PRODUCTION_ROLES == {"master", "cso", "worker", "worker-2", "worker-3"}
    RESULTS["allowlist_now"] = sorted(adapter.PHASE2B_ALLOWED_TEST_ROLES)
    RESULTS["allowlist_is_minimal_expansion"] = (
        adapter.PHASE2B_ALLOWED_TEST_ROLES == {"worker-4", "worker-5", "worker-6", "worker-8", "worker-10"}
    )

    overall_pass = all([
        RESULTS["worker10_passes_allowlist_gate"],
        RESULTS["worker8_still_passes_allowlist_gate"],
        RESULTS["worker11_denied_by_allowlist"],
        RESULTS["master_denied_by_production_check"],
        RESULTS["production_roles_unchanged"],
        RESULTS["allowlist_is_minimal_expansion"],
    ])

    for k, v in RESULTS.items():
        print(f"{k}: {v}")
    print("OVERALL ALLOWLIST CHANGE VERIFICATION:", "PASS" if overall_pass else "FAIL")

    import json
    eh.record_evidence(
        f"PHASE2B_ALLOWED_TEST_ROLES expanded to include worker-10; verification={json.dumps(RESULTS, ensure_ascii=False)}",
        "CONFIRMED" if overall_pass else "FAILED",
        evidence_path=str(Path(__file__).resolve().parent.parent / "controlled_adapter" / "controlled_cys_adapter.py"),
        run_id=run_id,
        conn=conn,
    )
    eh.finalize_run(
        run_id,
        final_status="COMPLETED" if overall_pass else "FAILED",
        validation_result=json.dumps(RESULTS, ensure_ascii=False),
        db_changes={"tables_created": [], "existing_tables_modified": [],
                    "non_db_change": "controlled_cys_adapter.py: PHASE2B_ALLOWED_TEST_ROLES += worker-10 (1 line)"},
        conn=conn,
    )
    conn.commit()
    conn.close()
    print("RUN_ID:", run_id)
    return run_id, overall_pass


if __name__ == "__main__":
    _, ok = main()
    sys.exit(0 if ok else 1)
