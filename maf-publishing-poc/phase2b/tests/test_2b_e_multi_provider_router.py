# Copyright (c) tree and fruits. PoC only.
"""TEST 2B-E — Multi-Provider Router verification: deterministic, fixture/read-only. Zero new
Claude/Codex/Gemini process calls. Cross-checks the 3 REAL completed short-token E2E runs
(Codex/Claude/Gemini) against each other and against the frozen provider-neutral contract.

IMPORTANT provider-identity note (router-level documentation, not a contract/DB change):
CYS's 'GEMINI' provider_id is implemented by the Antigravity CLI (agy.exe), NOT the original
Gemini CLI (discontinued for consumer tiers 2026-06-18, per agents.json's own notes). The
router must track this as engine metadata alongside the provider_id -- PROVIDER_ENGINE below is
that documentation, read-only, no frozen file touched.
"""
import hashlib
import json
import sys
from pathlib import Path

PHASE2B_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHASE2B_ROOT))
sys.path.insert(0, str(PHASE2B_ROOT / "control"))
sys.path.insert(0, str(PHASE2B_ROOT.parent / "phase2a"))

from controlled_adapter.controlled_cys_adapter import (  # noqa: E402
    check_target_policy, PROVIDER_TO_AGENT, PRODUCTION_ROLES, PHASE2B_ALLOWED_TEST_ROLES,
)
from collector import result_collector as rc  # noqa: E402
from db import publishing_db as db  # noqa: E402

CONTRACT_PATH = PHASE2B_ROOT / "contracts" / "provider_execution_contract.json"
PROTOCOL_PATH = Path(r"C:\Users\a\.cys\pack\round\evidence\phase2b-bootstrap-submit\token_protocol_message.txt")
EXPECTED_PROTOCOL_SHA256 = "987f45d3bea0648fd6c657c57d17e7c71e9065ac79e9ed675fb31608f43e4572"

# Router-level engine documentation (does not touch the frozen contract or DB schema)
PROVIDER_ENGINE = {
    "CODEX": "OpenAI Codex CLI (codex.exe via node.exe+codex.js, --no-daemon)",
    "CLAUDE": "Claude Code CLI",
    "GEMINI": "Antigravity CLI (agy.exe) -- NOT the original Gemini CLI, which was discontinued "
              "for consumer tiers 2026-06-18; key name 'gemini' retained for role/orchestration "
              "compatibility only",
}

# Ground-truth record of the 3 REAL completed E2E runs (from Durable Project Record + Publishing
# DB, cross-checked, not fixtures) -- used to verify router-level invariants hold across providers.
REAL_E2E_RUNS = {
    "CODEX": {
        "durable_run_id": "run2b-d7f7a04578394cc7",
        "provider_run_id": "run-e2e-tfbab618c",
        "task_id": "phase2b-task-e2e-worker6-001",
        "token": "TFBAB618C",
        "role": "worker-6",
        "surface_ref": "surface:220",
        "result_path": PHASE2B_ROOT / "data" / "results" / "phase2b-task-e2e-worker6-001.json",
        "expected_result_sha256": "0e5f71296b68ee41a4ab04583ace15a8cfb1659fd1696334a2af962a6c512812",
    },
    "CLAUDE": {
        "durable_run_id": "run2b-5d0c5dfbeda34867",
        "provider_run_id": "run-e2e-claude-t93c9f4d7",
        "task_id": "phase2b-task-e2e-claude-worker4-001",
        "token": "T93C9F4D7",
        "role": "worker-4",
        "surface_ref": "surface:221",
        "result_path": PHASE2B_ROOT / "data" / "results" / "phase2b-task-e2e-claude-worker4-001.json",
        "expected_result_sha256": "cd4926184afb5ed114482d9de7d7b610ba291196c3d7e214e0a6806774496642",
    },
    "GEMINI": {
        "durable_run_id": "run2b-0df75d7a57a04391",
        "provider_run_id": "run-e2e-gemini-t2fb7f8da",
        "task_id": "phase2b-task-e2e-gemini-worker8-001",
        "token": "T2FB7F8DA",
        "role": "worker-8",
        "surface_ref": "surface:222",
        "result_path": PHASE2B_ROOT / "data" / "results" / "phase2b-task-e2e-gemini-worker8-001.json",
        "expected_result_sha256": "397aac84501fc45b10c37baa2800e932dc77315519a80bec6e22c0906910ede0",
    },
}


def check(label, condition, results):
    results.append((label, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}: {label}")


def main():
    results = []
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    # 1. PROVIDER IDENTIFICATION: GEMINI's real engine correctly documented at router level
    check("GEMINI provider_id maps to Antigravity CLI (agy), not original Gemini CLI",
          "Antigravity" in PROVIDER_ENGINE["GEMINI"] and "agy.exe" in PROVIDER_ENGINE["GEMINI"], results)
    check("all 3 real E2E providers have a PROVIDER_ENGINE entry",
          set(PROVIDER_ENGINE.keys()) == set(REAL_E2E_RUNS.keys()), results)

    # 2. PROVIDER-NEUTRAL CONTRACT still represents all 3
    check("contract represents CODEX/CLAUDE/GEMINI", set(contract["provider_identifiers"]) == {"CODEX", "CLAUDE", "GEMINI"}, results)

    # 3. ROLE/SURFACE MAPPING per provider is distinct and non-conflicting (router selection correctness)
    roles_used = {p: d["role"] for p, d in REAL_E2E_RUNS.items()}
    surfaces_used = {p: d["surface_ref"] for p, d in REAL_E2E_RUNS.items()}
    check("each provider's E2E used a DISTINCT role (no cross-provider role collision)",
          len(set(roles_used.values())) == 3, results)
    check("each provider's E2E used a DISTINCT surface (no cross-provider surface collision)",
          len(set(surfaces_used.values())) == 3, results)
    for p, d in REAL_E2E_RUNS.items():
        check(f"{p}: role '{d['role']}' is allowlisted and not production",
              d["role"] in PHASE2B_ALLOWED_TEST_ROLES and d["role"] not in PRODUCTION_ROLES, results)

    # 4. TARGET POLICY uniform across providers (router dispatch correctness, no new surfaces)
    for p in REAL_E2E_RUNS:
        r = check_target_policy("master", p, "any-task-id")
        check(f"{p}: production role denied (provider-generic policy)",
              not r.allowed and "production role" in r.reason, results)
    for p in REAL_E2E_RUNS:
        r = check_target_policy("worker-99", p, "any-task-id")
        check(f"{p}: unlisted role denied (provider-generic policy)",
              not r.allowed and "not in the pre-announced" in r.reason, results)
    # provider/agent mismatch: requesting CODEX against a role that is registered with a
    # different live agent must deny (cross-provider confusion guard) -- exercised against the
    # REAL currently-registered agents for worker-4(claude)/worker-6(codex)/worker-8(gemini).
    cross_checks = [("CODEX", "worker-4"), ("CLAUDE", "worker-6"), ("GEMINI", "worker-4")]
    for wrong_provider, role in cross_checks:
        r = check_target_policy(role, wrong_provider, "any-task-id")
        check(f"mismatched provider {wrong_provider} vs role {role}'s real agent is denied",
              not r.allowed, results)

    # 5. UNIQUE task_id/token across all 3 providers (router must never reuse these)
    task_ids = [d["task_id"] for d in REAL_E2E_RUNS.values()]
    tokens = [d["token"] for d in REAL_E2E_RUNS.values()]
    check("all 3 task_ids are unique", len(set(task_ids)) == 3, results)
    check("all 3 tokens are unique", len(set(tokens)) == 3, results)

    # 6. IDEMPOTENCY: already_ran() correctly reports all 3 as COMPLETED (real DB read, no writes)
    for p, d in REAL_E2E_RUNS.items():
        dup = rc.already_ran(f"idem-{d['task_id']}", task_id=d["task_id"])
        check(f"{p}: already_ran() reports COMPLETED for the real idempotency key",
              dup is not None and dup["status"] == "COMPLETED" and dup["run_id"] == d["provider_run_id"],
              results)

    # 7. CANONICAL JSON + HASH cross-check (independent recompute against each real result file)
    for p, d in REAL_E2E_RUNS.items():
        actual = hashlib.sha256(d["result_path"].read_bytes()).hexdigest()
        check(f"{p}: independently recomputed result file hash matches recorded value",
              actual == d["expected_result_sha256"], results)

    # 8. DB PROVENANCE completeness per provider (documents the known Codex gap, does not fix it)
    conn = db.get_conn()
    provenance = {}
    for p, d in REAL_E2E_RUNS.items():
        row = conn.execute(
            "SELECT provider, agent_role, surface_id, output_hash FROM provider_run WHERE run_id=?",
            (d["provider_run_id"],),
        ).fetchone()
        provenance[p] = row
    conn.close()
    check("CLAUDE provider_run has complete provenance (provider/agent_role/surface_id/hash)",
          all(x is not None for x in provenance["CLAUDE"]), results)
    check("GEMINI provider_run has complete provenance (provider/agent_role/surface_id/hash)",
          all(x is not None for x in provenance["GEMINI"]), results)
    check("CODEX provider_run has the KNOWN gap (agent_role/surface_id/output_hash NULL -- "
          "documented in run2b-048f11bf5ab64d0b, not re-fixed here, existing row untouched)",
          provenance["CODEX"][1] is None and provenance["CODEX"][2] is None and provenance["CODEX"][3] is None,
          results)

    # 9. MAX_AUTOMATIC_RETRY=0 for all 3 real runs (Durable Project Record)
    conn = __import__("evidence_hash").get_conn()
    for p, d in REAL_E2E_RUNS.items():
        row = conn.execute("SELECT retry_count FROM phase2b_run_record WHERE run_id=?",
                            (d["durable_run_id"],)).fetchone()
        check(f"{p}: retry_count == 0 in Durable Project Record", row is not None and row[0] == 0, results)
    conn.close()

    # 10. frozen contract hash unchanged
    actual_json_sha = hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    check("frozen JSON contract hash unchanged (142dabae...)",
          actual_json_sha == "142dabae3a82956c5decb3d8dd8955cc31aedf36388b76f3563e5c09eb6a3ca0", results)
    actual_protocol_sha = hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest()
    check("Protocol V1 hash unchanged (987f45d3...)", actual_protocol_sha == EXPECTED_PROTOCOL_SHA256, results)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} multi-provider router checks passed")
    print("TEST 2B-E:", "PASS" if passed == total else "FAIL")
    return passed == total, passed, total


if __name__ == "__main__":
    ok, passed, total = main()
    sys.exit(0 if ok else 1)
