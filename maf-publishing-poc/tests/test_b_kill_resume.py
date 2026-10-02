"""TEST B — kill -9 mid-EDITING, restart, verify exact checkpoint-based recovery.

Real OS process is launched (subprocess.Popen), given a real wall-clock window while the
EDITING executor is asyncio.sleep()-ing (i.e. BEFORE it reaches ctx.send_message(), so no new
checkpoint has been written for "EDITING done" yet), then force-killed (SIGKILL /
proc.kill() -> Windows TerminateProcess). A fresh process is then started with `resume` and
must complete the workflow correctly with no missing/duplicated stages.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import PYTHON, ROOT, WORKFLOW, get_db_status, get_transition_count, reset_poc_state, run_cli  # noqa: E402

BOOK_ID = "BOOK-POC-002"
EDITING_DELAY = 6.0  # seconds — long enough to reliably kill the process mid-sleep
KILL_AFTER = 2.0  # seconds — kill well before EDITING_DELAY elapses


def main() -> bool:
    reset_poc_state()
    ok = True

    proc = subprocess.Popen(
        [
            str(PYTHON), str(WORKFLOW), "start",
            "--book-id", BOOK_ID, "--title", "TEST B 도서",
            "--editing-delay", str(EDITING_DELAY),
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(KILL_AFTER)
    still_running_before_kill = proc.poll() is None
    proc.kill()  # SIGKILL-equivalent (Windows TerminateProcess) — no graceful shutdown chance
    proc.wait(timeout=10)

    print(f"process was still running before kill: {still_running_before_kill} (must be True for a valid test)")
    if not still_running_before_kill:
        print("FAIL: process had already finished before we tried to kill it — "
              "test window too short / delay too short, not a valid TEST B run")
        ok = False

    status_after_kill = get_db_status(BOOK_ID)
    print("DB status immediately after kill:", status_after_kill)
    if status_after_kill not in ("MANUSCRIPT_RECEIVED", None):
        # None would mean ensure_book() itself never ran, which would also be wrong for this timing,
        # but the important assertion is that it must NOT already show EDITING (that would mean the
        # kill landed too late, after send_message() already advanced the superstep).
        print(f"FAIL: expected DB status MANUSCRIPT_RECEIVED right after kill (EDITING must not have "
              f"completed yet), got {status_after_kill!r}")
        ok = False

    # Fresh process, resumes from the last real checkpoint (before EDITING completed).
    r_resume = run_cli("resume", "--book-id", BOOK_ID)
    print("resume ->", r_resume)

    if get_db_status(BOOK_ID) != "EDITING":
        print(f"FAIL: expected resume to complete EDITING and reach the OWNER_APPROVAL gate "
              f"(DB status EDITING), got {get_db_status(BOOK_ID)}")
        ok = False

    if not r_resume.get("pending_requests"):
        print("FAIL: expected resume to reach the pending OWNER_APPROVAL request")
        ok = False

    # EDITING must have been logged exactly once (the killed attempt logged nothing, since it
    # died before send_message(); the resumed attempt re-ran EDITING from the last checkpoint
    # and completed it exactly once) — this is also a partial idempotency check for the kill path.
    editing_count = get_transition_count(BOOK_ID, "EDITING")
    print("EDITING transition log count:", editing_count)
    if editing_count != 1:
        print(f"FAIL: expected exactly 1 EDITING transition logged, got {editing_count}")
        ok = False

    # Finish the flow to confirm the recovered workflow is fully healthy end-to-end.
    r_approve = run_cli("approve", "--book-id", BOOK_ID, "--decision", "approve")
    print("approve ->", r_approve)
    if get_db_status(BOOK_ID) != "READY_FOR_PUBLICATION":
        print("FAIL: recovered workflow did not reach READY_FOR_PUBLICATION after approval")
        ok = False

    print("TEST B:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
