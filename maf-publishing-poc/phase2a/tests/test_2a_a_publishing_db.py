"""TEST 2A-A — Publishing DB: create PoC DB, register BOOK-POC-002, verify Workflow/Task/
Approval/File Version records."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers2a import PHASE2A_ROOT, reset_poc_state  # noqa: E402

sys.path.insert(0, str(PHASE2A_ROOT))
from db import publishing_db as db  # noqa: E402

BOOK_ID = "BOOK-POC-002"


def main() -> bool:
    reset_poc_state()
    ok = True

    db.ensure_book(BOOK_ID, "PHASE2A DB 시험 도서", actor="test")
    if db.get_book_status(BOOK_ID) != "MANUSCRIPT_RECEIVED":
        print("FAIL: book not created with MANUSCRIPT_RECEIVED status")
        ok = False

    wf_id = f"run-{BOOK_ID}"
    db.create_workflow_run(wf_id, BOOK_ID, "test-workflow", actor="test")

    task_id = f"task-{BOOK_ID}-001"
    db.create_task(task_id, wf_id, BOOK_ID, "EDIT", actor="test", assigned_provider="CLAUDE")
    db.set_task_status(task_id, "IN_PROGRESS", actor="test")

    approval_id = db.record_approval_request(BOOK_ID, "TEST_ACTION", requested_by="test")
    db.record_approval_decision(approval_id, "owner", "APPROVED", evidence="test")

    db.record_file_version(f"file-{BOOK_ID}-001", BOOK_ID, "manuscript", "poc://fake.docx", "v1",
                            "deadbeef" * 8, "test", task_id)

    db.record_checkpoint_reference(f"ckpt-{BOOK_ID}-001", wf_id, "fake-maf-checkpoint-id", "test note")

    # Verify each entity round-trips
    conn = db.get_conn()
    try:
        checks = {
            "workflow_run": "SELECT COUNT(*) FROM workflow_run WHERE workflow_run_id=?",
            "task": "SELECT COUNT(*) FROM task WHERE task_id=?",
            "approval": "SELECT COUNT(*) FROM approval WHERE approval_id=?",
            "file_version": "SELECT COUNT(*) FROM file_version WHERE book_id=?",
            "checkpoint_reference": "SELECT COUNT(*) FROM checkpoint_reference WHERE workflow_run_id=?",
        }
        ids = {"workflow_run": wf_id, "task": task_id, "approval": approval_id,
               "file_version": BOOK_ID, "checkpoint_reference": wf_id}
        for entity, query in checks.items():
            count = conn.execute(query, (ids[entity],)).fetchone()[0]
            print(f"  {entity}: {count} row(s)")
            if count < 1:
                print(f"FAIL: expected at least 1 {entity} row")
                ok = False

        event_count = conn.execute("SELECT COUNT(*) FROM system_event").fetchone()[0]
        print(f"  system_event (audit log): {event_count} row(s)")
        if event_count < 5:
            print("FAIL: expected system_event audit rows for each state change made above")
            ok = False
    finally:
        conn.close()

    print("TEST 2A-A:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
