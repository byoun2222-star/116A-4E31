# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

conn = eh.get_conn()
run_id = eh.start_run(
    objective="Fix the idempotency gap discovered in run2b-42ceff7eef274902 (CODEX "
              "idempotency_key=NULL): add identity/hash fallback to "
              "result_collector.already_ran(), reproduce before/after, run fixture conflict "
              "tests, full regression across Codex/Claude/Gemini. No task re-execution, no "
              "existing COMPLETED row modified.",
    actor="claude-session", provider="LOCAL",
    raw_command="edit result_collector.py + run_baseline.py/run_e2e_*.py call sites + "
                "test_2b_f_idempotency_fallback.py + full test_2b_* regression",
    conn=conn,
)
print("RUN_ID:", run_id)

eh.record_evidence(
    "ROOT CAUSE confirmed by code inspection (not guessed): check_target_policy()'s own "
    "_task_exists_and_open() check already independently blocks re-submission when "
    "task.status=='COMPLETED', regardless of idempotency_key -- so the real submission path "
    "(which always goes through check_target_policy before sending anything) was NEVER actually "
    "exposed to a duplicate-execution risk for the Codex row. The exposure was narrower: any "
    "caller trusting result_collector.already_ran() ALONE (as a pre-check before even reaching "
    "check_target_policy, which is exactly the pattern run_baseline.py and this session's E2E "
    "scripts use) would see None for the Codex row and could in principle proceed further before "
    "being caught by the later target_policy gate -- a defense-in-depth gap, not a fully open hole.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "BEFORE FIX reproduction (real data, read-only): "
    "already_ran('idem-phase2b-task-e2e-worker6-001') returned None for the real Codex row.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "FIX implemented in phase2b/collector/result_collector.py: already_ran() gained an optional "
    "task_id parameter and an identity/hash fallback path, reached only when the idempotency_key "
    "lookup misses. Fallback requires: task.status=='COMPLETED', exactly one COMPLETED "
    "provider_run row for that task_id (raises new IdempotencyConflict exception if 0 is fine/"
    "returns None, but >1 conflicting rows raises), and if that row has an output_hash it must "
    "match the actual result file's recomputed hash (raises IdempotencyConflict on mismatch or "
    "missing file); if no output_hash is recorded, a result file must still exist or it raises "
    "IdempotencyConflict (ambiguous state, never silently trusted). Call sites updated to pass "
    "task_id: workflow/run_baseline.py, control/run_e2e_claude_short_token.py, "
    "control/run_e2e_gemini_short_token.py (control/run_e2e_short_token.py, the original Codex "
    "E2E script, never called already_ran() at all, so it needed no change). No existing "
    "provider_run/task row was modified -- idempotency_key remains NULL on the real Codex row, "
    "by design (owner prohibited retroactive modification).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "AFTER FIX reproduction (real data, read-only): already_ran('idem-phase2b-task-e2e-worker6-001', "
    "task_id='phase2b-task-e2e-worker6-001') now returns "
    "{run_id: run-e2e-tfbab618c, provider: CODEX, status: COMPLETED, output_hash: None, "
    "matched_via: identity_hash_fallback}. Claude/Gemini rows unaffected: both still resolve via "
    "matched_via='idempotency_key' (the original direct lookup), proving the fallback is purely "
    "additive and non-breaking for rows that already work correctly.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Deterministic fixture tests (test_2b_f_idempotency_fallback.py, 12/12 PASS, zero AI/provider "
    "calls, zero task re-execution): real Codex fallback resolution, real Claude/Gemini "
    "non-regression, fallback returns None for a non-COMPLETED fixture task (no false positive), "
    "fallback matches a consistent fixture row, hash-mismatch fixture raises IdempotencyConflict, "
    "multiple-conflicting-COMPLETED-rows fixture raises IdempotencyConflict, "
    "COMPLETED-with-no-hash-and-no-file fixture raises IdempotencyConflict (ambiguous state, not "
    "auto-resolved), target_policy still independently denies re-submission of the real completed "
    "Codex task (regression), retry_count==0 preserved for all 3 real Durable Project Record "
    "entries. All fixture rows/files/tasks created during this test were deleted afterward -- "
    "verified zero residue.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "FULL REGRESSION across all existing Phase2B tests after the fix: test_2b_a (target policy) "
    "PASS, test_2b_b (provider contract) 17/17 PASS, test_2b_c (Claude discovery) 15/15 PASS, "
    "test_2b_d (Gemini discovery) 16/16 PASS, test_2b_e (multi-provider router, updated to pass "
    "task_id to already_ran) now 33/33 PASS (was 32/33 before this fix), test_2b_f (this fix's "
    "own test) 12/12 PASS.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Final state verification: all 4 live surfaces (219/220/221/222) still alive and untouched. "
    "All 3 real provider_run rows (run-e2e-tfbab618c/run-e2e-claude-t93c9f4d7/"
    "run-e2e-gemini-t2fb7f8da) unchanged -- status/idempotency_key/output_hash identical to "
    "before this fix (Codex's idempotency_key is still NULL, by design, not retroactively "
    "patched). No provider executed. No task re-run.",
    "CONFIRMED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id, final_status="COMPLETED",
    output_artifacts=[
        str(Path(__file__).resolve().parent.parent / "collector" / "result_collector.py"),
        str(Path(__file__).resolve().parent.parent / "workflow" / "run_baseline.py"),
        str(Path(__file__).resolve().parent / "run_e2e_claude_short_token.py"),
        str(Path(__file__).resolve().parent / "run_e2e_gemini_short_token.py"),
        str(Path(__file__).resolve().parent.parent / "tests" / "test_2b_e_multi_provider_router.py"),
        str(Path(__file__).resolve().parent.parent / "tests" / "test_2b_f_idempotency_fallback.py"),
    ],
    validation_result="Router-wide idempotency gap fixed via additive identity/hash fallback, "
                       "zero regressions across all 6 test files (2B-A through 2B-F), zero "
                       "existing data modified, zero AI/provider calls, zero task re-execution. "
                       "Full router test suite now 33/33 PASS (previously 32/33).",
    db_changes={"tables_created": [], "existing_tables_modified": [],
                "note": "fixture rows created and deleted during tests only; the 3 real "
                        "provider_run rows are byte-identical before/after"},
    conn=conn,
)
conn.commit()
print("기록 완료")
conn.close()
