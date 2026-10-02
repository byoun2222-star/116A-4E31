# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

conn = eh.get_conn()
run_id = eh.start_run(
    objective="Multi-provider router verification: cross-reference the 3 real completed "
              "short-token E2E runs (Codex/Claude/Gemini), document GEMINI=Antigravity(agy) "
              "engine identity at router level, run deterministic fixture-based router tests. "
              "Zero new AI/provider calls, zero task re-execution.",
    actor="claude-session", provider="LOCAL",
    raw_command="DB/evidence cross-reference + test_2b_e_multi_provider_router.py (fixture/read-only)",
    conn=conn,
)
print("RUN_ID:", run_id)

eh.record_evidence(
    "Cross-reference of 3 real completed E2E provider_run rows: CODEX(run-e2e-tfbab618c, "
    "task=phase2b-task-e2e-worker6-001, agent_role=NULL, surface_id=NULL, output_hash=NULL -- "
    "known gap from using publishing_db.record_provider_run() directly), "
    "CLAUDE(run-e2e-claude-t93c9f4d7, task=phase2b-task-e2e-claude-worker4-001, "
    "agent_role=worker-4, surface_id=surface:221, output_hash matches file), "
    "GEMINI(run-e2e-gemini-t2fb7f8da, task=phase2b-task-e2e-gemini-worker8-001, "
    "agent_role=worker-8, surface_id=surface:222, output_hash matches file). All 3 task rows "
    "status=COMPLETED with correct assigned_provider. All 3 Durable Project Record entries "
    "(run2b-d7f7a04578394cc7/run2b-5d0c5dfbeda34867/run2b-0df75d7a57a04391) show "
    "final_status=COMPLETED, validation PASS, retry_count=0, and all their evidence_ledger rows "
    "are CONFIRMED (7/7, 6/6, 6/6 respectively).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "GEMINI provider identity documented at router level (NOT a DB/contract change): CYS's "
    "'GEMINI' provider_id is implemented by Antigravity CLI (agy.exe), not the original Gemini "
    "CLI (discontinued for consumer tiers 2026-06-18 per agents.json's own notes). Documented as "
    "PROVIDER_ENGINE mapping in test_2b_e_multi_provider_router.py -- read-only router-level "
    "metadata, frozen contract/DB untouched.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Router deterministic tests (test_2b_e_multi_provider_router.py): 32/33 PASS, zero AI/"
    "provider calls, zero new surfaces, zero task re-execution. Covers: GEMINI engine identity, "
    "contract provider representation, distinct role/surface per provider (no collision), "
    "allowlist/production membership per role, provider-generic target-policy denial "
    "(production role, unlisted role) for all 3 providers, provider/agent MISMATCH denial "
    "(e.g. requesting CODEX against worker-4 which is really running claude) for all 3, unique "
    "task_id/token across providers, idempotency check via already_ran() for all 3 real "
    "idempotency keys, independent hash recompute of all 3 real result files, DB provenance "
    "completeness (CLAUDE/GEMINI complete, CODEX's known gap re-confirmed and left untouched), "
    "MAX_AUTOMATIC_RETRY=0 for all 3, frozen contract + Protocol V1 hashes unchanged.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "NEW FINDING (not previously documented): the CODEX E2E provider_run row's idempotency_key "
    "column is NULL (confirmed by direct query) -- NOT merely a missing-metadata cosmetic gap. "
    "This means already_ran('idem-phase2b-task-e2e-worker6-001') returns None, so the Codex "
    "short-token E2E task is currently NOT protected by the idempotency mechanism: a future "
    "re-submission of the same task_id would NOT be recognized as already-completed and blocked. "
    "This is the one test that FAILED (32/33) -- an accurate, expected consequence of the known "
    "provenance gap, not a new router defect. NOT fixed this round (would require writing to the "
    "existing COMPLETED row, prohibited). Claude and Gemini's idempotency protection is confirmed "
    "intact.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    ".tmp -> final atomic transition: DESIGN GUARANTEE confirmed by code inspection "
    "(test_task.write_task_file and collect_test_result_file both use the .tmp-then-rename "
    "pattern; collect_test_result_file explicitly reads ONLY the final non-.tmp path). NOT "
    "directly observed as a live event for any of the 3 providers' E2E runs -- no mid-flight "
    ".tmp file was captured during polling for any provider; this is an honest limitation, not a "
    "verified live observation, explicitly distinguished per owner instruction.",
    "UNVERIFIED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id, final_status="COMPLETED",
    output_artifacts=[str(Path(__file__).resolve().parent.parent / "tests" / "test_2b_e_multi_provider_router.py")],
    validation_result="32/33 router checks PASS. The 1 failure is the CODEX idempotency_key gap "
                       "(newly identified, documented, not fixed). .tmp->final is a confirmed "
                       "design guarantee, not directly observed live. Zero new provider calls "
                       "were needed for this verification.",
    db_changes={"tables_created": [], "existing_tables_modified": [],
                "note": "read-only cross-reference only; no writes to any provider_run/task row"},
    conn=conn,
)
conn.commit()
print("기록 완료")
conn.close()
