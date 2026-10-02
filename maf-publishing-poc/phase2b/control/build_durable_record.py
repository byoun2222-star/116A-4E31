# -*- coding: utf-8 -*-
"""
Executes the Durable Project Record minimum implementation build itself as a recorded run
(OWNER APPROVAL item 7: the build is the first entry in its own system). No AI calls.
"""
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh  # noqa: E402
import generate_project_state as gps  # noqa: E402
import test_durable_record_local as tests  # noqa: E402

THIS_FILE = Path(__file__).resolve()
NEW_FILES = [
    THIS_FILE.parent / "evidence_hash.py",
    THIS_FILE.parent / "generate_project_state.py",
    THIS_FILE.parent / "test_durable_record_local.py",
    THIS_FILE,
]


def main():
    conn = eh.get_conn()
    run_id = eh.start_run(
        objective="Build Durable Project Record minimum implementation "
                   "(PROJECT_STATE.json + phase2b_run_record + evidence_ledger + evidence_hash.py) "
                   "per OWNER APPROVAL 2026-10-02",
        actor="claude-session",
        provider="LOCAL",
        raw_command="python build_durable_record.py",
        conn=conn,
    )
    print("BUILD RUN_ID:", run_id)

    try:
        eh.ensure_schema(conn)
        eh.record_evidence("phase2b_run_record and evidence_ledger tables created (CREATE TABLE IF NOT EXISTS)",
                            "CONFIRMED", run_id=run_id, conn=conn)

        test_run_id = tests.main()
        eh.record_evidence(f"deterministic local test suite passed (10 categories, internal test run_id={test_run_id})",
                            "CONFIRMED", run_id=run_id, conn=conn)

        state = gps.write_state()
        eh.record_evidence("PROJECT_STATE.json generated from primary sources",
                            "CONFIRMED", evidence_path=str(gps.OUT_PATH), run_id=run_id, conn=conn)

        eh.finalize_run(
            run_id, final_status="COMPLETED",
            output_artifacts=[str(p) for p in NEW_FILES] + [str(gps.OUT_PATH)],
            validation_result="10/10 deterministic checks passed; Publishing DB pre-existing rows unchanged",
            db_changes={"tables_created": ["phase2b_run_record", "evidence_ledger"],
                        "existing_tables_modified": []},
            conn=conn,
        )
        print("BUILD STATUS: COMPLETED")
    except Exception as e:
        eh.record_evidence(f"build failed: {e}", "FAILED", run_id=run_id, conn=conn)
        eh.finalize_run(run_id, final_status="FAILED", stop_reason=str(e), conn=conn)
        traceback.print_exc()
        print("BUILD STATUS: FAILED")
        sys.exit(1)
    finally:
        conn.commit()

    # ---- final report values ----
    report = {
        "run_id": run_id,
        "files_created": [str(p) for p in NEW_FILES],
        "project_state_path": str(gps.OUT_PATH),
        "project_state": state,
    }
    conn2 = eh.get_conn()
    report["evidence_ledger_count"] = conn2.execute("SELECT COUNT(*) FROM evidence_ledger").fetchone()[0]
    report["run_record_count"] = conn2.execute("SELECT COUNT(*) FROM phase2b_run_record").fetchone()[0]
    conn2.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
