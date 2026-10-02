"""TEST 2A-H — Cost Guard: a mock task claims requires_paid_api=true; workflow must halt with
BLOCKED_BY_COST_POLICY and never reach OWNER_APPROVAL/FINALIZE."""
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

    r = run_cli("start", "--book-id", BOOK_ID, "--title", "TEST 2A-H 도서", "--requires-paid-api")
    print("start (requires_paid_api=True) ->", r)

    status = db.get_book_status(BOOK_ID)
    print("DB status:", status)
    if status != "BLOCKED_BY_COST_POLICY":
        print(f"FAIL: expected BLOCKED_BY_COST_POLICY, got {status!r}")
        ok = False

    outputs = r.get("outputs", [])
    if not outputs or "BLOCKED_BY_COST_POLICY" not in outputs[0]:
        print(f"FAIL: expected terminal output to mention BLOCKED_BY_COST_POLICY, got {outputs}")
        ok = False

    if r.get("pending_requests"):
        print("FAIL: workflow must not have reached the OWNER_APPROVAL HITL gate at all")
        ok = False

    conn = db.get_conn()
    try:
        appr_count = conn.execute("SELECT COUNT(*) FROM approval WHERE book_id=?", (BOOK_ID,)).fetchone()[0]
    finally:
        conn.close()
    if appr_count != 0:
        print(f"FAIL: no approval row should have been created (cost guard halts BEFORE owner_approval), got {appr_count}")
        ok = False
    else:
        print("confirmed: 0 approval rows created — cost guard halted strictly before OWNER_APPROVAL")

    print("TEST 2A-H:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
