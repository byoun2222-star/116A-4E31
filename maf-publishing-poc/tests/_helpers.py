"""Shared test helpers — subprocess-based (real CLI invocations, real OS processes).

Using subprocess (not in-process function calls) is deliberate: TEST B needs a real,
externally-killable OS process to prove crash/restart recovery actually works, not just
that a Python exception was caught. The other tests reuse the same harness for consistency.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
WORKFLOW = ROOT / "workflow.py"
CHECKPOINT_DIR = ROOT / "checkpoints"
DB_PATH = ROOT / "publishing_poc.sqlite3"


def reset_poc_state() -> None:
    """Wipe checkpoints + DB for a clean test run. PoC-only paths, never touches anything
    outside maf-publishing-poc/."""
    if CHECKPOINT_DIR.exists():
        shutil.rmtree(CHECKPOINT_DIR)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            p.unlink()


def run_cli(*args: str, timeout: float = 60.0) -> dict:
    proc = subprocess.run(
        [str(PYTHON), str(WORKFLOW), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"CLI failed (exit {proc.returncode}):\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "{}") \
            if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        # multiple JSON blocks or stray stderr warnings mixed into stdout — take the last valid JSON object
        text = proc.stdout.strip()
        # find the last top-level {...} block
        depth = 0
        start = None
        candidates = []
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    candidates.append(text[start : i + 1])
        if not candidates:
            raise
        return json.loads(candidates[-1])


def get_db_status(book_id: str) -> str | None:
    sys.path.insert(0, str(ROOT))
    from executors import db_writer as db  # noqa: E402

    return db.get_status(book_id)


def get_transition_count(book_id: str, status: str) -> int:
    sys.path.insert(0, str(ROOT))
    from executors import db_writer as db  # noqa: E402

    return db.get_transition_count(book_id, status)
