# Copyright (c) tree and fruits. PoC only — PHASE 2B DB bootstrap.
"""Creates BOOK-POC-002, one workflow_run, and the 3 forced-baseline tasks (owner §14:
RUN-1->CLAUDE, RUN-2->CODEX, RUN-3->GEMINI). Idempotent (INSERT OR IGNORE throughout) — safe
to re-run after a restart without duplicating rows."""
import sys
import uuid
from pathlib import Path

PHASE2A_ROOT = Path(__file__).resolve().parent.parent.parent / "phase2a"
sys.path.insert(0, str(PHASE2A_ROOT))
from db import publishing_db as db  # noqa: E402

BOOK_ID = "BOOK-POC-002"
WORKFLOW_RUN_ID = "phase2b-wfrun-001"
WORKFLOW_NAME = "maf-publishing-poc-phase2b"

BASELINE_TASKS = [
    ("phase2b-task-run1-claude", "CLAUDE"),
    ("phase2b-task-run2-codex", "CODEX"),
    ("phase2b-task-run3-gemini", "GEMINI"),
]


def main() -> None:
    db.ensure_book(BOOK_ID, "PHASE 2B 시험용 가상도서 (METADATA_NORMALIZATION 시험)", actor="phase2b_setup")
    db.create_workflow_run(WORKFLOW_RUN_ID, BOOK_ID, WORKFLOW_NAME, actor="phase2b_setup")
    for task_id, provider in BASELINE_TASKS:
        db.create_task(task_id, WORKFLOW_RUN_ID, BOOK_ID, "METADATA_NORMALIZATION",
                        actor="phase2b_setup", assigned_provider=provider)
    for task_id, provider in BASELINE_TASKS:
        cur_status = None
        conn = db.get_conn()
        try:
            row = conn.execute("SELECT status FROM task WHERE task_id=?", (task_id,)).fetchone()
            cur_status = row[0] if row else None
        finally:
            conn.close()
        print(f"task {task_id} ({provider}) status={cur_status}")
    print("BOOK_ID:", BOOK_ID)
    print("WORKFLOW_RUN_ID:", WORKFLOW_RUN_ID)


if __name__ == "__main__":
    main()
