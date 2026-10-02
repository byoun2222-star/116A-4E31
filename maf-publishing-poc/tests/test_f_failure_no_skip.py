"""TEST F — when an executor fails, the workflow must NOT silently advance to the next stage.

Two distinct failure shapes are exercised:
  1. An executor RAISES (EDITING) — simulates a crash/exception inside a step.
  2. An executor determines failure WITHOUT raising (EPUB_VALIDATE) — simulates a mock
     validator that ran fine but concluded "invalid", and must stop the chain itself by
     not calling ctx.send_message().
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import get_db_status, reset_poc_state, run_cli  # noqa: E402


def check_raise_failure() -> bool:
    """EDITING raises -> DB must show EDITING_FAILED, never OWNER_APPROVAL/EPUB_BUILD/... ."""
    book_id = "BOOK-POC-F1"
    reset_poc_state()
    ok = True
    try:
        run_cli("start", "--book-id", book_id, "--title", "TEST F1 도서", "--fail-at", "EDITING")
        print("FAIL: expected the CLI process to exit non-zero (unhandled RuntimeError) for --fail-at EDITING")
        ok = False
    except RuntimeError as e:
        print("start raised as expected:", str(e).splitlines()[-1][:200])

    status = get_db_status(book_id)
    print("DB status after EDITING failure:", status)
    if status != "EDITING_FAILED":
        print(f"FAIL: expected DB status EDITING_FAILED, got {status!r}")
        ok = False
    forbidden = {"OWNER_APPROVAL", "EPUB_BUILD", "EPUB_VALIDATE", "REVIEW", "READY_FOR_PUBLICATION"}
    if status in forbidden:
        print(f"FAIL: workflow incorrectly advanced to {status} after a failure")
        ok = False
    return ok


def check_explicit_validate_failure() -> bool:
    """EPUB_VALIDATE decides FAIL without raising -> DB must show EPUB_VALIDATE_FAILED,
    never REVIEW/READY_FOR_PUBLICATION."""
    book_id = "BOOK-POC-F2"
    reset_poc_state()
    ok = True

    run_cli("start", "--book-id", book_id, "--title", "TEST F2 도서", "--fail-at", "EPUB_VALIDATE")
    r2 = run_cli("approve", "--book-id", book_id, "--decision", "approve")
    print("approve (fail_at=EPUB_VALIDATE) ->", r2)

    status = get_db_status(book_id)
    print("DB status after EPUB_VALIDATE failure:", status)
    if status != "EPUB_VALIDATE_FAILED":
        print(f"FAIL: expected DB status EPUB_VALIDATE_FAILED, got {status!r}")
        ok = False
    if status in ("REVIEW", "READY_FOR_PUBLICATION"):
        print(f"FAIL: workflow incorrectly advanced to {status} after EPUB_VALIDATE failure")
        ok = False
    outputs = r2.get("outputs", [])
    if not outputs or "EPUB_VALIDATE_FAILED" not in outputs[0]:
        print(f"FAIL: expected terminal output to report EPUB_VALIDATE_FAILED, got {outputs}")
        ok = False
    return ok


def main() -> bool:
    ok1 = check_raise_failure()
    ok2 = check_explicit_validate_failure()
    ok = ok1 and ok2
    print("TEST F:", "PASS" if ok else "FAIL", f"(raise-failure={ok1}, explicit-failure={ok2})")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
