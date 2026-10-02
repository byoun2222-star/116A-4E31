# Copyright (c) tree and fruits. PoC only.
"""TEST 2B-D — Gemini (Antigravity/agy) Adapter Discovery: deterministic, LOCAL ONLY, zero
Claude/Codex/Gemini calls. Mirrors test_2b_c_claude_adapter_discovery.py's structure, reusing
the same contract/adapter functions rather than duplicating logic."""
import hashlib
import json
import sys
from pathlib import Path

PHASE2B_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHASE2B_ROOT))
sys.path.insert(0, str(PHASE2B_ROOT / "control"))
sys.path.insert(0, str(PHASE2B_ROOT.parent / "phase2a"))

from tasks import test_task  # noqa: E402
import token_manifest as tm  # noqa: E402
from controlled_adapter.controlled_cys_adapter import check_target_policy, PROVIDER_TO_AGENT  # noqa: E402
from collector import result_collector as rc  # noqa: E402

CONTRACT_PATH = PHASE2B_ROOT / "contracts" / "provider_execution_contract.json"
MD_CONTRACT_PATH = PHASE2B_ROOT / "contracts" / "PROVIDER_EXECUTION_CONTRACT.md"
AGENTS_JSON_PATH = Path(r"C:\Users\a\.cys\pack\agents.json")

EXPECTED_JSON_SHA256 = "142dabae3a82956c5decb3d8dd8955cc31aedf36388b76f3563e5c09eb6a3ca0"
EXPECTED_MD_SHA256 = "f3b7be00aaf71540be7c3bf972b7452949a2bddb57656dfa1f2eea6d7ee122e8"

CODEX_ONLY_MARKERS = ["node.exe", "codex.js", "--no-daemon", "gpt-6-sol", "codex.cmd", "codex.ps1"]
CLAUDE_ONLY_MARKERS = ["--dangerously-skip-permissions\" --claude-only", "claude.exe"]  # structural sanity only


def check(label, condition, results):
    results.append((label, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}: {label}")


def main():
    results = []
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    agents = json.loads(AGENTS_JSON_PATH.read_text(encoding="utf-8"))
    gemini_cfg = agents["gemini"]

    # 1. provider=GEMINI contract representation
    check("contract represents provider=GEMINI", "GEMINI" in contract["provider_identifiers"], results)

    # 2. GEMINI -> expected CYS agent mapping
    check("PROVIDER_TO_AGENT['GEMINI'] == 'gemini'", PROVIDER_TO_AGENT.get("GEMINI") == "gemini", results)
    check("agents.json has a 'gemini' entry (Antigravity/agy, key retained for compatibility)",
          "gemini" in agents, results)

    # 3. target-policy compatibility (provider-generic, verified with provider=GEMINI)
    r = check_target_policy("master", "GEMINI", "any-task-id")
    check("production role denied for GEMINI too (policy is provider-generic)",
          not r.allowed and "production role" in r.reason, results)
    r2 = check_target_policy("worker-99", "GEMINI", "any-task-id")
    check("unlisted role denied for GEMINI too", not r2.allowed and "not in the pre-announced" in r2.reason, results)

    # 4. task/token/manifest compatibility
    packet = test_task.build_task_packet("contract-test-gemini-001", "wf-contract-test-gemini", "BOOK-POC-002")
    check("task packet has no provider-specific field", "provider" not in packet, results)
    token = tm.generate_token("contract-test-gemini-001")
    check("token format valid regardless of provider", bool(tm.TOKEN_RE.match(token)), results)

    # 5. provenance writer compatibility (dry run + cleanup)
    rc.migrate()
    test_idem_key = "idem-contract-test-gemini-001"
    rc.record_run_started("contract-test-run-gemini-001", "GEMINI", "contract-test-gemini-001",
                           "METADATA_NORMALIZATION", surface_id="surface:TEST-GEMINI",
                           agent_role="worker-TEST", health_before="AVAILABLE",
                           usage_before="{}", usage_reliability="UNKNOWN",
                           idempotency_key=test_idem_key)
    from db import publishing_db as _db
    _conn = _db.get_conn()
    row = _conn.execute(
        "SELECT provider, surface_id, agent_role FROM provider_run WHERE run_id=?",
        ("contract-test-run-gemini-001",),
    ).fetchone()
    check("record_run_started accepts provider=GEMINI with full provenance",
          row == ("GEMINI", "surface:TEST-GEMINI", "worker-TEST"), results)
    _conn.execute("DELETE FROM provider_run WHERE run_id=?", ("contract-test-run-gemini-001",))
    _conn.commit()
    _conn.close()

    # 6. Gemini (agy) startup profile structural validation
    check("gemini agent config has cmd", "cmd" in gemini_cfg, results)
    check("gemini agent config has ready_marker", "ready_marker" in gemini_cfg, results)
    check("gemini agent config has no explicit --model flag (none required)",
          "--model" not in gemini_cfg.get("cmd", ""), results)
    check("gemini agent config has no first_run_gates block (unlike claude -- OAuth is human_only, undocumented gates)",
          "first_run_gates" not in gemini_cfg, results)

    # 7. Codex/Claude-specific mandatory field leakage check
    gemini_cfg_text = json.dumps(gemini_cfg)
    leaked = [m for m in CODEX_ONLY_MARKERS if m in gemini_cfg_text]
    check("no Codex-specific markers present in Gemini's agent config", len(leaked) == 0, results)
    excluded = set(contract["provider_specific_fields_excluded_from_mandatory_envelope"])
    task_envelope_fields = set(contract["task_envelope"]["required_fields"])
    check("Codex-specific fields still excluded from mandatory envelope",
          excluded.isdisjoint(task_envelope_fields), results)

    # 8. frozen contract artifact/hash unchanged
    actual_json_sha = hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    actual_md_sha = hashlib.sha256(MD_CONTRACT_PATH.read_bytes()).hexdigest()
    check("frozen JSON contract hash unchanged", actual_json_sha == EXPECTED_JSON_SHA256, results)
    check("frozen MD contract hash unchanged", actual_md_sha == EXPECTED_MD_SHA256, results)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} Gemini adapter discovery checks passed")
    print("TEST 2B-D:", "PASS" if passed == total else "FAIL")
    return passed == total, passed, total


if __name__ == "__main__":
    ok, passed, total = main()
    sys.exit(0 if ok else 1)
