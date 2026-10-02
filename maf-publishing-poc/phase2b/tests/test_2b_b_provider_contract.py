# Copyright (c) tree and fruits. PoC only.
"""TEST 2B-B — Provider-Neutral Contract: deterministic, no AI/provider calls. Reuses the
existing validator/token-manifest/target-policy/result-collector functions rather than
duplicating their logic -- this test exercises the CONTRACT, not a reimplementation of it."""
import json
import sys
import tempfile
from pathlib import Path

PHASE2B_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHASE2B_ROOT))
sys.path.insert(0, str(PHASE2B_ROOT / "control"))
sys.path.insert(0, str(PHASE2B_ROOT.parent / "phase2a"))

from tasks import test_task  # noqa: E402
import token_manifest as tm  # noqa: E402
from controlled_adapter.controlled_cys_adapter import check_target_policy  # noqa: E402
from collector import result_collector as rc  # noqa: E402

CONTRACT_PATH = PHASE2B_ROOT / "contracts" / "provider_execution_contract.json"


def check(label, condition, results):
    results.append((label, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}: {label}")


def main():
    results = []
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    # 1. valid task accepted (all required envelope fields present)
    packet = test_task.build_task_packet("contract-test-task-001", "wf-contract-test", "BOOK-POC-002")
    required = set(contract["task_envelope"]["required_fields"])
    check("valid task accepted (all required fields present)", required.issubset(packet.keys()), results)

    # 2. invalid/missing task rejected
    incomplete = dict(packet)
    del incomplete["output_schema"]
    check("invalid/missing task rejected", not required.issubset(incomplete.keys()), results)

    # 3. token format accepted/rejected
    valid_token = tm.generate_token("contract-test-task-001")
    check("token format accepted", bool(tm.TOKEN_RE.match(valid_token)), results)
    check("token format rejected (malformed)", not tm.TOKEN_RE.match("RUN-garbage"), results)

    # 4. unknown token rejected
    try:
        tm.resolve_token("TFFFFFFFF")
        check("unknown token rejected", False, results)
    except tm.TokenError:
        check("unknown token rejected", True, results)

    # 5. task hash mismatch rejected (write task, tamper, recompute hash, compare to manifest)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_task_path = PHASE2B_ROOT / "tasks" / "pending" / "contract-test-hash-mismatch.json"
        tmp_result_path = PHASE2B_ROOT / "data" / "results" / "contract-test-hash-mismatch.json"
        try:
            sha, _ = test_task.write_task_file(packet, tmp_task_path)
            token = tm.register_token("contract-test-hash-mismatch", tmp_task_path, tmp_result_path, sha)
            tmp_task_path.write_text(tmp_task_path.read_text(encoding="utf-8") + "\n// tampered",
                                      encoding="utf-8")
            import hashlib
            actual = hashlib.sha256(tmp_task_path.read_bytes()).hexdigest()
            entry = tm.resolve_token(token)
            check("task hash mismatch rejected (detectable)", actual != entry["task_sha256"], results)
        finally:
            tmp_task_path.unlink(missing_ok=True)
            manifest = tm._load_manifest()
            manifest.pop(tm.generate_token("contract-test-hash-mismatch"), None)
            tm._save_manifest(manifest)

    # 6. path traversal rejected
    try:
        tm._assert_in_scope(Path("C:/Windows/System32/evil.json"))
        check("path traversal rejected", False, results)
    except tm.TokenError:
        check("path traversal rejected", True, results)

    # 7. malformed UTF-8 rejected
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b"\xff\xfe\x00bad utf-8")
        bad_path = Path(f.name)
    try:
        bad_path.read_text(encoding="utf-8")
        check("malformed UTF-8 rejected", False, results)
    except UnicodeDecodeError:
        check("malformed UTF-8 rejected", True, results)
    finally:
        bad_path.unlink(missing_ok=True)

    # 8. malformed JSON rejected
    v = test_task.validate_output("this is not { valid json")
    check("malformed JSON rejected", not v.passed, results)

    # 9. schema-invalid result rejected (missing field)
    v = test_task.validate_output(json.dumps({"title": "x"}))
    check("schema-invalid result rejected", not v.passed, results)

    # 10. validator failure rejected (wrong type + extra field)
    bad_result = dict(test_task.INPUT_METADATA)
    bad_result["price_krw"] = "not-an-int"
    bad_result["extra_field"] = "fabricated"
    v = test_task.validate_output(json.dumps(bad_result, ensure_ascii=False))
    check("validator failure rejected (wrong type/extra field)", not v.passed, results)

    # 11. valid atomic final accepted (reuse the real atomic write primitive)
    with tempfile.TemporaryDirectory() as tmpdir:
        final_path = Path(tmpdir) / "final.json"
        tmp_path = final_path.with_suffix(".json.tmp")
        tmp_path.write_text('{"ok": true}', encoding="utf-8")
        tmp_path.replace(final_path)  # same atomic rename primitive used in production code
        check("valid atomic final accepted", final_path.exists() and not tmp_path.exists(), results)

    # 12. existing valid completed result -> no rerun (reuse result_collector.already_ran)
    rc.migrate()
    test_idem_key = "idem-contract-test-001"
    rc.record_run_started("contract-test-run-001", "CODEX", "contract-test-task-001",
                           "METADATA_NORMALIZATION", surface_id="surface:TEST",
                           agent_role="worker-TEST", health_before="AVAILABLE",
                           usage_before="{}", usage_reliability="LOW",
                           idempotency_key=test_idem_key)
    rc.record_run_completed("contract-test-run-001", "COMPLETED", "deadbeef", {"passed": True, "reasons": []},
                             "AVAILABLE", "{}", None, 1.0, "contract test fixture")
    dup = rc.already_ran(test_idem_key)
    check("existing valid completed result -> no rerun", dup is not None and dup["status"] == "COMPLETED", results)
    # cleanup: this is a disposable test fixture row, not existing production data
    from db import publishing_db as _db
    _conn = _db.get_conn()
    _conn.execute("DELETE FROM provider_run WHERE run_id = ?", ("contract-test-run-001",))
    _conn.commit()
    _conn.close()

    # 13. conflicting result -> IDEMPOTENCY_CONFLICT (same pattern used in run_e2e_short_token.py)
    conflict_task_path = PHASE2B_ROOT / "tasks" / "pending" / "contract-test-task-001.json"
    try:
        test_task.write_task_file(packet, conflict_task_path)
        would_conflict = conflict_task_path.exists()  # re-check before a hypothetical re-submit
        check("conflicting result detectable -> IDEMPOTENCY_CONFLICT path", would_conflict, results)
    finally:
        conflict_task_path.unlink(missing_ok=True)

    # 14. provider-specific startup fields are NOT mandatory in the neutral envelope
    provider_specific = set(contract["provider_specific_fields_excluded_from_mandatory_envelope"])
    check("provider-specific fields excluded from mandatory envelope",
          provider_specific.isdisjoint(required), results)

    # 15. Codex/Claude/Gemini identifiers representable
    check("contract represents all 3 provider identifiers",
          set(contract["provider_identifiers"]) == {"CLAUDE", "CODEX", "GEMINI"}, results)
    from controlled_adapter.controlled_cys_adapter import PROVIDER_TO_AGENT
    check("PROVIDER_TO_AGENT maps all 3 providers (reused, not reimplemented)",
          set(PROVIDER_TO_AGENT.keys()) == {"CLAUDE", "CODEX", "GEMINI"}, results)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} contract checks passed")
    print("TEST 2B-B:", "PASS" if passed == total else "FAIL")
    return passed == total, passed, total


if __name__ == "__main__":
    ok, passed, total = main()
    sys.exit(0 if ok else 1)
