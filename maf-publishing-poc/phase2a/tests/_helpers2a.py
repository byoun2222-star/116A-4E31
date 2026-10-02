"""Shared helpers for PHASE 2A tests."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PHASE2A_ROOT = Path(__file__).resolve().parent.parent
PYTHON = PHASE2A_ROOT.parent / "venv" / "Scripts" / "python.exe"
WORKFLOW = PHASE2A_ROOT / "workflow" / "workflow2a.py"
CHECKPOINT_DIR = PHASE2A_ROOT / "data" / "checkpoints"
DB_PATH = PHASE2A_ROOT / "data" / "publishing_poc.db"

sys.path.insert(0, str(PHASE2A_ROOT))


def reset_poc_state() -> None:
    if CHECKPOINT_DIR.exists():
        shutil.rmtree(CHECKPOINT_DIR)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            p.unlink()


def run_cli(*args: str, timeout: float = 60.0) -> dict:
    proc = subprocess.run(
        [str(PYTHON), str(WORKFLOW), *args], cwd=str(PHASE2A_ROOT.parent),
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"CLI failed (exit {proc.returncode}):\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
    text = proc.stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        matches = re.findall(r"\{.*\}", text, re.DOTALL)
        if matches:
            return json.loads(matches[-1])
        raise


def cys_list_raw() -> str:
    proc = subprocess.run(["cys", "list"], capture_output=True, text=True, timeout=15)
    return proc.stdout


def cys_status_json() -> dict:
    proc = subprocess.run(["cys", "status", "--json"], capture_output=True, text=True, timeout=15)
    return json.loads(proc.stdout)
