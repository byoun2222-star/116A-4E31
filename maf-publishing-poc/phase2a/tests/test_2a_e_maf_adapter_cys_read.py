"""TEST 2A-E — MAF -> Function Executor -> Adapter -> CYSJavis READ. Full workflow start
(which runs SyncCysStateExecutor as a real MAF step), structured result flows into workflow
events + Publishing DB's system_event log, and CYSJavis has zero mutations."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers2a import PHASE2A_ROOT, cys_list_raw, reset_poc_state, run_cli  # noqa: E402

sys.path.insert(0, str(PHASE2A_ROOT))
from db import publishing_db as db  # noqa: E402

BOOK_ID = "BOOK-POC-002"


def main() -> bool:
    reset_poc_state()
    ok = True

    before = cys_list_raw()

    r = run_cli("start", "--book-id", BOOK_ID, "--title", "TEST 2A-E 도서")
    print("workflow start ->", r)

    after = cys_list_raw()
    if before != after:
        print("FAIL: cys list output changed after MAF workflow ran SyncCysStateExecutor")
        print("before:", before)
        print("after:", after)
        ok = False
    else:
        print("cys list output byte-identical before/after MAF->Adapter->CYSJavis read step")

    events = db.get_events_for("cys_state", "snapshot")
    print(f"system_event rows for cys_state.synced: {len(events)}")
    if not events:
        print("FAIL: expected at least one cys_state.synced audit event in Publishing DB")
        ok = False
    else:
        ev = events[0]
        if "status_ok=True" not in ev["reason"] or "surfaces_ok=True" not in ev["reason"]:
            print(f"FAIL: expected the sync event to record ok=True results, got: {ev}")
            ok = False
        else:
            print("audit event content:", ev["reason"][:150])

    print("TEST 2A-E:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
