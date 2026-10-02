"""TEST 2A-I — Owner Approval: a task is created; it must not execute (reach FINALIZE) before
approval; approval-pending state survives a checkpoint/resume cycle; no real external
publication action is ever taken (this is enforced by construction — FinalizeExecutor only
writes to the PoC DB, never to any external system)."""
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

    r1 = run_cli("start", "--book-id", BOOK_ID, "--title", "TEST 2A-I 도서")
    print("start ->", r1)
    if db.get_book_status(BOOK_ID) not in ("MANUSCRIPT_RECEIVED", None):
        # book status is only changed by book-level transitions; PHASE2A workflow doesn't
        # advance book.status until FINALIZE, so it must still read MANUSCRIPT_RECEIVED here.
        print(f"FAIL: workflow must not execute (finalize) before approval, status={db.get_book_status(BOOK_ID)}")
        ok = False
    if not r1.get("pending_requests"):
        print("FAIL: expected a pending owner-approval request")
        ok = False

    # checkpoint/resume cycle (no response) — approval-pending must survive.
    r2 = run_cli("resume", "--book-id", BOOK_ID)
    print("resume (no decision) ->", r2)
    if not r2.get("pending_requests"):
        print("FAIL: approval-pending state was lost across a resume with no response")
        ok = False
    if db.get_book_status(BOOK_ID) not in ("MANUSCRIPT_RECEIVED", None):
        print("FAIL: workflow incorrectly advanced past approval during a no-op resume")
        ok = False

    # now actually approve, confirm real completion of the (still entirely local/mock) flow.
    r3 = run_cli("approve", "--book-id", BOOK_ID, "--decision", "approve")
    print("approve ->", r3)
    if db.get_book_status(BOOK_ID) != "PHASE2A_WORKFLOW_COMPLETE":
        print("FAIL: approved workflow did not reach PHASE2A_WORKFLOW_COMPLETE")
        ok = False

    print("TEST 2A-I:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
