"""TEST C — HITL persistence: stopping and restarting the process while a workflow is
paused at OWNER_APPROVAL must NOT lose or auto-advance the pending approval gate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import get_db_status, reset_poc_state, run_cli  # noqa: E402

BOOK_ID = "BOOK-POC-003"


def main() -> bool:
    reset_poc_state()
    ok = True

    r1 = run_cli("start", "--book-id", BOOK_ID, "--title", "TEST C 도서")
    print("start ->", r1)
    if get_db_status(BOOK_ID) != "EDITING":
        print("FAIL: expected DB status EDITING after start")
        ok = False
    if not r1.get("pending_requests"):
        print("FAIL: expected pending OWNER_APPROVAL request after start")
        ok = False

    # Simulate "process ended, new process started later" by simply invoking `resume` in a
    # brand-new subprocess WITHOUT supplying any response. The approval gate must still be
    # pending afterwards — resume must not silently approve/skip it.
    r2 = run_cli("resume", "--book-id", BOOK_ID)
    print("resume (no response given) ->", r2)

    if get_db_status(BOOK_ID) != "EDITING":
        print("FAIL: DB status must remain EDITING (not advanced past OWNER_APPROVAL) after a "
              f"no-response resume, got {get_db_status(BOOK_ID)}")
        ok = False

    pending = r2.get("pending_requests", [])
    if not pending or pending[0].get("request_id") != f"approval-{BOOK_ID}":
        print("FAIL: expected the SAME pending approval-{} request to still be reported after resume, got {}"
              .format(BOOK_ID, pending))
        ok = False

    # Now actually approve, to confirm the gate is still genuinely functional afterwards
    # (not stuck/corrupted by the earlier no-op resume).
    r3 = run_cli("approve", "--book-id", BOOK_ID, "--decision", "approve")
    print("approve (after persisted pending) ->", r3)
    if get_db_status(BOOK_ID) != "READY_FOR_PUBLICATION":
        print("FAIL: expected workflow to still be resumable and reach READY_FOR_PUBLICATION")
        ok = False

    print("TEST C:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
