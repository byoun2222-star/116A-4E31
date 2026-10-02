"""TEST A — basic workflow: full state traversal MANUSCRIPT_RECEIVED..READY_FOR_PUBLICATION."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import get_db_status, reset_poc_state, run_cli  # noqa: E402

BOOK_ID = "BOOK-POC-001"


def main() -> bool:
    reset_poc_state()
    ok = True

    r1 = run_cli("start", "--book-id", BOOK_ID, "--title", "테스트 가상도서")
    print("start ->", r1)
    if get_db_status(BOOK_ID) != "EDITING":
        print("FAIL: expected DB status EDITING after start, got", get_db_status(BOOK_ID))
        ok = False
    if not r1.get("pending_requests"):
        print("FAIL: expected a pending OWNER_APPROVAL request after start")
        ok = False

    r2 = run_cli("approve", "--book-id", BOOK_ID, "--decision", "approve")
    print("approve ->", r2)
    final_status = get_db_status(BOOK_ID)
    if final_status != "READY_FOR_PUBLICATION":
        print("FAIL: expected final DB status READY_FOR_PUBLICATION, got", final_status)
        ok = False
    outputs = r2.get("outputs", [])
    if not outputs or "READY_FOR_PUBLICATION" not in outputs[0]:
        print("FAIL: expected workflow output to mention READY_FOR_PUBLICATION, got", outputs)
        ok = False
    expected_trace = [
        "MANUSCRIPT_RECEIVED", "EDITING", "OWNER_APPROVAL", "EPUB_BUILD", "EPUB_VALIDATE", "REVIEW",
        "READY_FOR_PUBLICATION",
    ]
    for stage in expected_trace:
        if outputs and stage not in outputs[0]:
            print(f"FAIL: trace missing stage {stage}")
            ok = False

    print("TEST A:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
