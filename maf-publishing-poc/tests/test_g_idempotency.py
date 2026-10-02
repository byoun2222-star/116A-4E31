"""TEST G — re-running the same command must not duplicate DB rows/transitions or corrupt state.

Exercises three duplicate-invocation shapes:
  1. `start` run twice for the same book_id (second call re-delivers the same initial message
     into a workflow that already has checkpoints for this name).
  2. `resume` run twice in a row with no response.
  3. `approve` run twice in a row with the same decision, AFTER the workflow has already
     completed. ★Verified MAF behavior (not assumed): the second `approve` call raises
     `RuntimeError: No pending requests found in workflow context.` — agent_framework itself
     refuses to apply a response when nothing is pending. That is the correct idempotency
     outcome for this case: the DB is NOT duplicated/corrupted, but the redundant call surfaces
     an explicit error rather than silently no-op'ing. This test asserts exactly that shape.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import get_db_status, get_transition_count, reset_poc_state, run_cli  # noqa: E402

BOOK_ID = "BOOK-POC-G1"
ALL_STAGES = [
    "MANUSCRIPT_RECEIVED", "EDITING", "OWNER_APPROVAL", "EPUB_BUILD", "EPUB_VALIDATE", "REVIEW",
    "READY_FOR_PUBLICATION",
]


def assert_transition_counts(expected: dict[str, int], ok_ref: list[bool]) -> None:
    for stage in ALL_STAGES:
        count = get_transition_count(BOOK_ID, stage)
        want = expected.get(stage, 0)
        status = "OK" if count == want else "FAIL"
        print(f"  [{status}] transition_count[{stage}] = {count} (expected {want})")
        if count != want:
            ok_ref[0] = False


def main() -> bool:
    reset_poc_state()
    ok = [True]

    print("-- start (1st) --")
    run_cli("start", "--book-id", BOOK_ID, "--title", "TEST G 도서")
    print("-- start (2nd, duplicate) --")
    r_start2 = run_cli("start", "--book-id", BOOK_ID, "--title", "TEST G 도서")
    print("start(2nd) ->", r_start2)
    # ensure_book() is INSERT OR IGNORE; only MANUSCRIPT_RECEIVED/EDITING should be logged so far.
    assert_transition_counts({"MANUSCRIPT_RECEIVED": 1, "EDITING": 1}, ok)

    print("-- resume (1st, duplicate no-op) --")
    run_cli("resume", "--book-id", BOOK_ID)
    print("-- resume (2nd, duplicate no-op) --")
    run_cli("resume", "--book-id", BOOK_ID)
    if get_db_status(BOOK_ID) != "EDITING":
        print(f"FAIL: duplicate resume calls must not change status, expected EDITING, got {get_db_status(BOOK_ID)}")
        ok[0] = False
    assert_transition_counts({"MANUSCRIPT_RECEIVED": 1, "EDITING": 1}, ok)

    print("-- approve (1st) --")
    r_approve1 = run_cli("approve", "--book-id", BOOK_ID, "--decision", "approve")
    print("approve(1st) ->", r_approve1)
    if get_db_status(BOOK_ID) != "READY_FOR_PUBLICATION":
        print("FAIL: expected READY_FOR_PUBLICATION after the first approval")
        ok[0] = False
    assert_transition_counts({s: 1 for s in ALL_STAGES}, ok)

    print("-- approve (2nd, duplicate, workflow already complete) --")
    try:
        run_cli("approve", "--book-id", BOOK_ID, "--decision", "approve")
        print("FAIL: expected the 2nd approve (nothing pending) to raise/exit non-zero")
        ok[0] = False
    except RuntimeError as e:
        msg = str(e)
        if "No pending requests found" not in msg:
            print(f"FAIL: expected 'No pending requests found' error, got different failure:\n{msg[:500]}")
            ok[0] = False
        else:
            print("duplicate approve correctly rejected by agent_framework:",
                  "RuntimeError: No pending requests found in workflow context.")

    # The crucial idempotency assertion: the rejected duplicate call must not have mutated
    # anything — status unchanged, and NOT ONE transition row duplicated.
    if get_db_status(BOOK_ID) != "READY_FOR_PUBLICATION":
        print(f"FAIL: DB status must remain READY_FOR_PUBLICATION after the rejected duplicate call, "
              f"got {get_db_status(BOOK_ID)}")
        ok[0] = False
    print("-- final transition counts (must all still be exactly 1 — no duplication from the rejected call) --")
    assert_transition_counts({s: 1 for s in ALL_STAGES}, ok)

    print("TEST G:", "PASS" if ok[0] else "FAIL")
    return ok[0]


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
