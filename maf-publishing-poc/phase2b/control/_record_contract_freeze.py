# -*- coding: utf-8 -*-
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

PHASE2B_ROOT = Path(__file__).resolve().parent.parent
JSON_CONTRACT = PHASE2B_ROOT / "contracts" / "provider_execution_contract.json"
MD_CONTRACT = PHASE2B_ROOT / "contracts" / "PROVIDER_EXECUTION_CONTRACT.md"
TEST_FILE = PHASE2B_ROOT / "tests" / "test_2b_b_provider_contract.py"

json_sha256 = hashlib.sha256(JSON_CONTRACT.read_bytes()).hexdigest()
md_sha256 = hashlib.sha256(MD_CONTRACT.read_bytes()).hexdigest()

conn = eh.get_conn()
run_id = eh.start_run(
    objective="PHASE 2B provider-neutral contract extraction (read-only analysis + contract "
              "artifact creation + deterministic tests + regression check). No AI/provider "
              "calls, no new surface, no startup/model/Protocol V1/allowlist change.",
    actor="claude-session", provider="LOCAL",
    raw_command="read-only source analysis + contract file writes + test_2b_b_provider_contract.py",
    conn=conn,
)
print("RUN_ID:", run_id)

eh.record_evidence(
    f"Contract artifacts created: {JSON_CONTRACT} (sha256={json_sha256}), "
    f"{MD_CONTRACT} (sha256={md_sha256}). Version=PHASE2B-PROVIDER-CONTRACT-V1.",
    "CONFIRMED", evidence_path=str(JSON_CONTRACT), run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Source classification (PROVIDER_NEUTRAL vs CODEX_SPECIFIC) performed by reading actual code "
    "(not assumed): token_manifest.py, test_task.py, result_collector.py, run_baseline.py, "
    "check_target_policy/collect_test_result_file/PROVIDER_TO_AGENT = PROVIDER_NEUTRAL. "
    "_codex_submission_exists/CODEX_LOCAL_LOG_PATH, config.toml model, node.exe+codex.js+--no-daemon "
    "invocation values, Codex TUI vim-mode behavior = CODEX_SPECIFIC. Full table in "
    "PROVIDER_EXECUTION_CONTRACT.md section 1.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "DB provenance gap root cause CONFIRMED: result_collector.py:record_run_started() is the "
    "intended canonical writer (accepts surface_id/agent_role/idempotency_key, used by "
    "run_baseline.py); this session's E2E script instead used the simpler "
    "publishing_db.record_provider_run() which lacks those parameters -- explaining the empty "
    "columns in run-e2e-tfbab618c. provider_run table ALREADY has these columns (added by "
    "result_collector.migrate()'s additive ALTER TABLE, already applied previously) -- NO schema "
    "migration required. Fix proposed (route future runs through record_run_started/completed), "
    "NOT implemented this round. Existing COMPLETED row left unmodified.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Deterministic contract tests (test_2b_b_provider_contract.py): 17/17 PASS, zero AI/provider "
    "calls, reuses existing functions (test_task.validate_output, token_manifest.*, "
    "check_target_policy, result_collector.already_ran) rather than duplicating logic. Test "
    "fixtures (temp task/result files, one provider_run row, one token_manifest entry) all "
    "cleaned up after the run -- verified zero residue in token_manifest.json, provider_run "
    "table, and tasks/pending|data/results directories.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Regression check (no Codex re-execution, static/file/DB reads only): Protocol V1 sha256 "
    "UNCHANGED (987f45d3...), config.toml model UNCHANGED (gpt-6-sol), "
    "PHASE2B_ALLOWED_TEST_ROLES UNCHANGED ({worker-4,5,6,8,10}), token_manifest.generate_token() "
    "formula UNCHANGED, run-e2e-tfbab618c COMPLETED DB row UNCHANGED. "
    f"phase2b_startup_launcher.py current sha256={hashlib.sha256((PHASE2B_ROOT/'control'/'phase2b_startup_launcher.py').read_bytes()).hexdigest()} "
    "(unchanged since the REMAINDER-argparse fix + its regression test run2b-062564ecc21c42de, "
    "which preceded both successful live PASS runs -- no edits since).",
    "CONFIRMED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id, final_status="COMPLETED",
    output_artifacts=[str(JSON_CONTRACT), str(MD_CONTRACT), str(TEST_FILE)],
    validation_result="17/17 contract tests PASS; all regression checks PASS; DB provenance gap "
                       "analyzed (no schema change needed, fix proposed not implemented); zero AI "
                       "provider calls; zero new surfaces; surface:219/220 untouched.",
    db_changes={"tables_created": [], "existing_tables_modified": [],
                "note": "test fixture rows created and deleted during test run; no production data touched"},
    conn=conn,
)
conn.commit()
print("JSON_SHA256:", json_sha256)
print("MD_SHA256:", md_sha256)
print("기록 완료")
conn.close()
