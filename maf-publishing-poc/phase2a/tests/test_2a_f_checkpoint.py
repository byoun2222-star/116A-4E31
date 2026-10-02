"""TEST 2A-F — Checkpoint: CYSJavis snapshot + Publishing DB workflow state captured, process
ends (workflow pauses at HITL, which is itself the checkpoint-worthy pause point), resume,
verify the SAME workflow_run/task state is restored (not re-created, not lost)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers2a import PHASE2A_ROOT, reset_poc_state, run_cli  # noqa: E402

sys.path.insert(0, str(PHASE2A_ROOT))
from db import publishing_db as db  # noqa: E402

BOOK_ID = "BOOK-POC-002"


def main() -> bool:
    reset_poc_state()
    ok = True

    r1 = run_cli("start", "--book-id", BOOK_ID, "--title", "TEST 2A-F 도서")
    print("start ->", r1)
    pending_before = r1.get("pending_requests", [])
    if not pending_before:
        print("FAIL: expected a pending OWNER_APPROVAL_PHASE2A request after start")
        ok = False

    conn = db.get_conn()
    try:
        wf_row = conn.execute(
            "SELECT workflow_run_id, status FROM workflow_run WHERE book_id=?", (BOOK_ID,)
        ).fetchone()
    finally:
        conn.close()
    print("workflow_run before resume:", wf_row)
    if wf_row is None:
        print("FAIL: no workflow_run row recorded before resume")
        ok = False

    # "process ends" simulated the same way as Phase 1 TEST C: brand-new CLI invocation with
    # no response supplied, must show the SAME pending request, not a fresh/duplicated one.
    r2 = run_cli("resume", "--book-id", BOOK_ID)
    print("resume ->", r2)
    pending_after = r2.get("pending_requests", [])
    if not pending_after or pending_after[0]["request_id"] != pending_before[0]["request_id"]:
        print(f"FAIL: pending request identity changed across resume: {pending_before} -> {pending_after}")
        ok = False

    conn = db.get_conn()
    try:
        wf_row_after = conn.execute(
            "SELECT workflow_run_id, status FROM workflow_run WHERE book_id=?", (BOOK_ID,)
        ).fetchone()
        wf_count = conn.execute("SELECT COUNT(*) FROM workflow_run WHERE book_id=?", (BOOK_ID,)).fetchone()[0]
    finally:
        conn.close()
    print("workflow_run after resume:", wf_row_after, "| total rows for this book:", wf_count)
    if wf_row != wf_row_after:
        print("FAIL: workflow_run row changed identity/status across resume (should be unchanged, still RUNNING)")
        ok = False
    if wf_count != 1:
        print(f"FAIL: expected exactly 1 workflow_run row for {BOOK_ID}, resume must not duplicate it, got {wf_count}")
        ok = False

    # Finish the flow to prove the recovered checkpoint is genuinely still functional.
    r3 = run_cli("approve", "--book-id", BOOK_ID, "--decision", "approve")
    print("approve ->", r3)
    if db.get_book_status(BOOK_ID) != "PHASE2A_WORKFLOW_COMPLETE":
        print("FAIL: recovered workflow did not reach PHASE2A_WORKFLOW_COMPLETE")
        ok = False

    print("TEST 2A-F:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
