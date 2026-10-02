# Copyright (c) tree and fruits. PoC only — PHASE 2B Controlled Adapter.
"""Phase 2A's adapter was 100% read-only. Phase 2B owner §7-8 approves EXACTLY ONE new write
capability on top of it: submit_test_task() / collect_test_result(). No arbitrary shell string
ever reaches subprocess — both functions are fixed Python entry points, same discipline as
Phase 2A's ALLOWED_READONLY_COMMANDS allowlist.

collect_test_result() is pure composition of Phase 2A's existing read-only primitives (it
reuses `_run`/`Phase2AReadOnlyViolation` directly from phase2a's already-audited module rather
than duplicating the allowlist) — phase2a/ itself is not modified, only imported.

submit_test_task() is the ONE write action: `cys send --queued --to <role> "<packet>"`. It is
gated by check_target_policy(), which must return ALLOW before any subprocess is spawned. Any
uncertainty (surface not found, agent mismatch, busy, ambiguous state, DB check failure) is a
DENY — owner §8 is explicit that uncertainty must never be resolved permissively.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PHASE2A_ROOT = Path(__file__).resolve().parent.parent.parent / "phase2a"
sys.path.insert(0, str(PHASE2A_ROOT))
from adapter.cys_readonly_adapter import _run as _readonly_run  # noqa: E402
from adapter.cys_readonly_adapter import Phase2AReadOnlyViolation  # noqa: E402

PHASE2B_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHASE2B_ROOT))
from tasks.test_task import _extract_json_object, write_task_file  # noqa: E402

TASKS_PENDING_DIR = PHASE2B_ROOT / "tasks" / "pending"
RESULTS_DIR = PHASE2B_ROOT / "data" / "results"

DENIED_BY_PHASE2B_TARGET_POLICY = "DENIED_BY_PHASE2B_TARGET_POLICY"

# Pre-announced to master before any surface is created (owner+master safety requirement).
# Deliberately a closed allowlist, not a pattern — a name outside this set is denied even if it
# would otherwise look like a plausible test role.
PHASE2B_ALLOWED_TEST_ROLES = {"worker-4", "worker-5", "worker-6", "worker-8", "worker-10"}

# Defense-in-depth mirror: these must NEVER be accepted as a submit_test_task target, even if a
# future edit accidentally widened PHASE2B_ALLOWED_TEST_ROLES to include one of them.
PRODUCTION_ROLES = {"master", "cso", "worker", "worker-2", "worker-3"}

PROVIDER_TO_AGENT = {"CLAUDE": "claude", "CODEX": "codex", "GEMINI": "gemini"}


@dataclass
class TargetPolicyResult:
    allowed: bool
    reason: str
    surface_ref: str | None = None
    health_snapshot: dict | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deny(reason: str) -> TargetPolicyResult:
    return TargetPolicyResult(allowed=False, reason=f"{DENIED_BY_PHASE2B_TARGET_POLICY}: {reason}")


def _task_exists_and_open(task_id: str) -> bool:
    sys.path.insert(0, str(PHASE2A_ROOT))
    from db import publishing_db as db  # local import: only needed for this one check

    conn = db.get_conn()
    try:
        cur = conn.execute("SELECT status FROM task WHERE task_id = ?", (task_id,))
        row = cur.fetchone()
        if row is None:
            return False
        return row[0] != "COMPLETED"
    finally:
        conn.close()


def check_target_policy(role: str, provider: str, task_id: str) -> TargetPolicyResult:
    """Owner §8, verbatim conditions — ALL must hold, ANY uncertainty denies:
    1. role is a declared PHASE2B test surface (closed allowlist, pre-announced to master)
    2. role is not a production role (master/cso/worker/worker-2/worker-3)
    3. provider is one of CLAUDE/CODEX/GEMINI and matches the surface's actual `agent` field
    4. the surface exists, is alive, not exited, and not currently doing another task
    5. task_id exists in the Phase 2B DB and is not already COMPLETED
    """
    provider_u = provider.upper()

    if role in PRODUCTION_ROLES:
        return _deny(f"role '{role}' is a production role — never a valid test target")
    if role not in PHASE2B_ALLOWED_TEST_ROLES:
        return _deny(f"role '{role}' is not in the pre-announced PHASE2B_ALLOWED_TEST_ROLES set")
    if provider_u not in PROVIDER_TO_AGENT:
        return _deny(f"provider '{provider}' is not one of CLAUDE/CODEX/GEMINI")

    try:
        code, out, err = _readonly_run("status_json")
    except Phase2AReadOnlyViolation as e:
        return _deny(f"could not read cys status to verify target (adapter refused: {e})")
    if code != 0 or not out.strip():
        return _deny(f"cys status --json failed or returned empty (code={code}, err={err!r})")
    try:
        status = json.loads(out)
    except json.JSONDecodeError:
        return _deny("cys status --json returned unparseable output")

    matching = [s for s in status.get("surfaces", []) if s.get("role") == role]
    if len(matching) == 0:
        return _deny(f"no live surface found with role '{role}'")
    if len(matching) > 1:
        return _deny(f"ambiguous: {len(matching)} surfaces found with role '{role}'")
    surface = matching[0]

    if surface.get("exited") is not False:
        return _deny(f"surface for role '{role}' is not confirmed non-exited (exited={surface.get('exited')!r})")
    if surface.get("agent_alive") is not True:
        return _deny(f"surface for role '{role}' is not confirmed alive (agent_alive={surface.get('agent_alive')!r})")

    expected_agent = PROVIDER_TO_AGENT[provider_u]
    if surface.get("agent") != expected_agent:
        return _deny(
            f"agent mismatch: requested provider {provider_u} expects agent="
            f"'{expected_agent}', surface role '{role}' reports agent={surface.get('agent')!r}"
        )

    task_status = surface.get("status")
    if task_status is not None:
        state = task_status.get("state") if isinstance(task_status, dict) else None
        if state != "waiting" and state is not None:
            # Only a surface with no status at all, or an explicit "waiting" state, is treated
            # as free. "working" or any other/unrecognized state is a DENY — uncertainty must
            # not be resolved permissively (owner §8).
            return _deny(f"surface for role '{role}' appears busy (status.state={state!r})")

    if not _task_exists_and_open(task_id):
        return _deny(f"task_id '{task_id}' does not exist in Phase 2B DB or is already COMPLETED")

    health_snapshot = {
        "role": role,
        "agent": surface.get("agent"),
        "queue_depth": surface.get("queue_depth"),
        "queue_paused": surface.get("queue_paused"),
        "idle_secs": surface.get("idle_secs"),
        "usage_source": (surface.get("usage") or {}).get("source"),
        "observed_at": _now(),
    }
    return TargetPolicyResult(allowed=True, reason="target policy satisfied",
                               surface_ref=surface.get("surface_ref"), health_snapshot=health_snapshot)


def submit_test_task(role: str, provider: str, task_id: str, packet: dict) -> dict:
    """The ONE new write capability. Gated by check_target_policy(); on ANY denial, returns
    without ever invoking subprocess. On success, delivers the task packet as an instructed
    message via `cys send --queued` (auto-Return delivery — no send-key race)."""
    policy = check_target_policy(role, provider, task_id)
    if not policy.allowed:
        return {"submitted": False, "reason": policy.reason, "health_before": None}

    instruction = (
        f"[PHASE2B-TASK] task_id={task_id} provider={provider}\n"
        f"{packet['objective']}\n"
        f"INPUT_JSON: {json.dumps(packet['input'], ensure_ascii=False)}\n"
        f"OUTPUT_SCHEMA: {json.dumps(packet['output_schema'], ensure_ascii=False)}\n"
        f"CONSTRAINTS: {json.dumps(packet['constraints'], ensure_ascii=False)}\n"
        f"Reply with ONLY the JSON object — no prose, no code fences."
    )
    proc = subprocess.run(["cys", "send", "--queued", "--to", role, instruction],
                           capture_output=True, text=True, timeout=15.0)
    return {
        "submitted": proc.returncode == 0,
        "reason": "sent" if proc.returncode == 0 else f"cys send failed: {proc.stderr}",
        "surface_ref": policy.surface_ref,
        "health_before": policy.health_snapshot,
        "sent_at": _now(),
    }


def collect_test_result(role: str) -> dict:
    """READ-ONLY composition (reuses Phase 2A's audited `_run('read_screen', ...)` — no new
    write path here). Returns the raw screen text plus whatever JSON object (if any) the
    deterministic extractor could locate in it, for the caller to hand to the real validator.

    ★Retained for observational/debugging use only — NOT the canonical result-collection path
    (screen-scraping was found, this session, to sometimes render MORE completely than what a
    receiving shell actually executed/parsed — see phase2b-bootstrap-submit evidence). The
    canonical path is collect_test_result_file() below."""
    try:
        code, out, err = _readonly_run("read_screen", ["--to", role])
    except Phase2AReadOnlyViolation as e:
        return {"ok": False, "raw_screen": None, "extracted_json": None, "error": str(e)}
    if code != 0:
        return {"ok": False, "raw_screen": None, "extracted_json": None, "error": err}
    extracted = _extract_json_object(out)
    return {"ok": True, "raw_screen": out, "extracted_json": extracted, "observed_at": _now()}


def _check_idempotent_existing_result(task_id: str, expected_task_sha256: str) -> dict:
    """Owner idempotency gate (this round, explicit): a pre-existing final result file is
    NEVER treated as 'already done' on file-existence alone. ALL of the following must
    independently hold, or this returns a CONFLICT (never a silent pass):
      1. a task file exists on disk and its hash matches what the caller is about to submit
      2. the result file is valid UTF-8 and parses as JSON
      3. the existing validate_output() deterministic validator PASSES it
      4. the Phase 2B DB has a COMPLETED provider_run row for this task_id whose output_hash
         matches the result file's own hash
    No automatic delete/overwrite/resubmit ever happens here — this function only classifies."""
    result_path = RESULTS_DIR / f"{task_id}.json"
    task_path = TASKS_PENDING_DIR / f"{task_id}.json"
    if not result_path.exists():
        return {"idempotent": False, "conflict": False, "reason": "no existing result file"}

    if not task_path.exists():
        return {"idempotent": False, "conflict": True,
                "reason": "result file exists but task file is missing — cannot verify identity"}
    on_disk_task_sha = hashlib.sha256(task_path.read_bytes()).hexdigest()
    if on_disk_task_sha != expected_task_sha256:
        return {"idempotent": False, "conflict": True,
                "reason": f"task file hash mismatch: on-disk={on_disk_task_sha} "
                          f"expected={expected_task_sha256}"}

    try:
        raw_bytes = result_path.read_bytes()
        raw_text = raw_bytes.decode("utf-8")
        json.loads(raw_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return {"idempotent": False, "conflict": True,
                "reason": f"existing result file is not valid UTF-8/JSON: {e}"}

    from tasks.test_task import validate_output
    vresult = validate_output(raw_text)
    if not vresult.passed:
        return {"idempotent": False, "conflict": True,
                "reason": f"existing result fails deterministic validator: {vresult.reasons}"}

    result_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    try:
        conn = _db_conn()
        try:
            rows = conn.execute(
                "SELECT run_id, status, output_hash FROM provider_run WHERE task_id = ? "
                "ORDER BY started_at DESC",
                (task_id,),
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        return {"idempotent": False, "conflict": True, "reason": f"could not query DB to cross-check: {e}"}

    matching = [r for r in rows if r[1] == "COMPLETED" and r[2] == result_sha256]
    if not matching:
        return {"idempotent": False, "conflict": True,
                "reason": f"no COMPLETED provider_run row with matching output_hash={result_sha256} "
                          f"(rows on file: {rows})"}

    return {"idempotent": True, "conflict": False,
            "reason": "IDEMPOTENT EXISTING COMPLETED RESULT — DO NOT RESUBMIT",
            "result_sha256": result_sha256, "db_run_id": matching[0][0]}


def _db_conn():
    sys.path.insert(0, str(PHASE2A_ROOT))
    from db import publishing_db as db
    return db.get_conn()


def submit_test_task_file(role: str, provider: str, task_id: str, packet: dict) -> dict:
    """Safe-transport mitigation (canonical path): the task packet itself is NEVER typed into
    the target's PTY — it is written once as UTF-8 JSON to tasks/pending/<task_id>.json
    (ensure_ascii=False, so Hangul/em-dash/etc. are real code points on disk, verified by
    immediate read-back hash in write_task_file()). The only text that reaches `cys send` is a
    short, pure-ASCII, single-line control message referencing that path plus the expected
    result path.

    Transport is DIRECT (non-queued) `cys send` + `cys send-key Return` — `--queued` delivery
    was observed this session to stall indefinitely (291s+, never delivered per the daemon's
    own bookkeeping) even against a confirmed-idle, confirmed-responsive target; direct send
    was reliable for every short single-line ASCII message observed this session. A read-only
    `cys read-screen` immediately after is an OBSERVATIONAL echo check only — it is never used
    to decide task success (that is the exclusive job of the final result file).

    Idempotency: checked BEFORE any subprocess is spawned — see _check_idempotent_existing_result.
    A conflict state halts here; it is never auto-resolved (no delete/overwrite/resubmit).

    Same target-policy gate as submit_test_task() — no relaxation of owner §8."""
    policy = check_target_policy(role, provider, task_id)
    if not policy.allowed:
        return {"submitted": False, "reason": policy.reason, "health_before": None}

    expected_task_sha256 = hashlib.sha256(
        json.dumps(packet, ensure_ascii=False, indent=2).encode("utf-8")
    ).hexdigest()
    idem = _check_idempotent_existing_result(task_id, expected_task_sha256)
    if idem["conflict"]:
        return {"submitted": False, "reason": f"IDEMPOTENCY STATE CONFLICT — STOP: {idem['reason']}",
                "idempotency": idem}
    if idem["idempotent"]:
        return {"submitted": False, "reason": idem["reason"], "idempotency": idem}

    task_path = TASKS_PENDING_DIR / f"{task_id}.json"
    task_sha256, task_bytes = write_task_file(packet, task_path)
    assert task_sha256 == expected_task_sha256, "write_task_file produced unexpected bytes"

    result_path = RESULTS_DIR / f"{task_id}.json"
    result_tmp_path = RESULTS_DIR / f"{task_id}.json.tmp"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Pure ASCII, single line, no embedded task content — this is the whole point.
    instruction = (
        f"[PHASE2B-TASK-FILE] Read the JSON file at {task_path} (UTF-8 encoding). "
        f"Follow its objective/output_schema/constraints fields exactly. "
        f"Write ONLY the resulting output JSON object to {result_tmp_path} using UTF-8 "
        f"encoding with no BOM, then rename that file to {result_path}. "
        f"Do not modify {task_path}. Do not print the JSON to the terminal."
    )
    send_proc = subprocess.run(["cys", "send", "--to", role, instruction],
                                capture_output=True, text=True, timeout=15.0)
    key_proc = subprocess.run(["cys", "send-key", "--to", role, "Return"],
                               capture_output=True, text=True, timeout=15.0)

    echo_observed = None
    try:
        code, screen_out, _ = _readonly_run("read_screen", ["--to", role])
        if code == 0:
            echo_observed = instruction in screen_out
    except Phase2AReadOnlyViolation:
        echo_observed = None  # observational only — absence of this check never blocks anything

    return {
        "submitted": send_proc.returncode == 0 and key_proc.returncode == 0,
        "reason": "sent" if send_proc.returncode == 0 else f"cys send failed: {send_proc.stderr}",
        "surface_ref": policy.surface_ref,
        "health_before": policy.health_snapshot,
        "task_path": str(task_path),
        "task_sha256": task_sha256,
        "task_bytes": task_bytes,
        "expected_result_path": str(result_path),
        "control_screen_echo_observed": echo_observed,  # OBSERVATIONAL ONLY — not a success signal
        "sent_at": _now(),
    }


def collect_test_result_file(task_id: str, timeout_s: float = 60.0, poll_interval_s: float = 1.0) -> dict:
    """Canonical file-based result collection — reads ONLY the final `<task_id>.json`, never the
    `.tmp` file (an in-progress write must never be mistaken for a complete one). Polls
    read-only for the final path to appear; does not touch the `.tmp` file at all (its
    tmp->final rename is the provider's/writer's responsibility, not this function's).

    Atomicity note: relies on the OS-level guarantee of `os.replace()` / Windows
    `MoveFileEx(MOVEFILE_REPLACE_EXISTING)` being atomic for a rename within the SAME volume —
    this holds for tasks/pending and data/results both living under the same
    maf-publishing-poc project tree on one local NTFS volume. It would NOT hold across
    different volumes/network paths."""
    import time as _time
    deadline = _time.time() + timeout_s
    result_path = RESULTS_DIR / f"{task_id}.json"
    while _time.time() < deadline:
        if result_path.exists():
            try:
                raw_bytes = result_path.read_bytes()
                raw_text = raw_bytes.decode("utf-8")
            except (OSError, UnicodeDecodeError) as e:
                # File appeared but isn't fully/validly written yet (or a genuine encoding
                # fault) — keep polling until timeout rather than treating a transient read
                # race as a hard failure.
                _time.sleep(poll_interval_s)
                continue
            import hashlib
            return {
                "ok": True,
                "result_path": str(result_path),
                "raw_text": raw_text,
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "byte_length": len(raw_bytes),
                "observed_at": _now(),
            }
        _time.sleep(poll_interval_s)
    return {"ok": False, "result_path": str(result_path), "raw_text": None,
            "error": f"timeout after {timeout_s}s waiting for {result_path}"}


# ─────────────── Control-plane state machine (this round) ───────────────
CODEX_LOCAL_LOG_PATH = Path.home() / ".codex" / "logs_2.sqlite"


def _codex_submission_exists(task_id: str) -> bool | None:
    """CODEX-ONLY, read-only: queries Codex's own local Rust-internal submission log for a
    Submission record mentioning this task_id — this is the ONLY signal in this whole state
    machine that counts as genuine confirmation the provider actually received a completed
    turn (screen echo and process-alive are both explicitly insufficient, per this round's
    findings). Returns None (never False) if the log file is missing/unreadable — uncertainty
    must halt the state machine, not be resolved as "not submitted".
    ★Scope: only CODEX has this local log in this environment; CLAUDE/GEMINI have no
    equivalent found this session — this function (and the state machine below) is CODEX-only."""
    if not CODEX_LOCAL_LOG_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(CODEX_LOCAL_LOG_PATH))
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM logs WHERE feedback_log_body LIKE ?", (f"%{task_id}%",)
            )
            return cur.fetchone()[0] > 0
        finally:
            conn.close()
    except Exception:
        return None


def _provider_alive(role: str) -> bool | None:
    """Read-only `cys status --json` agent_alive check for role. None on any read failure."""
    try:
        code, out, err = _readonly_run("status_json")
    except Phase2AReadOnlyViolation:
        return None
    if code != 0 or not out.strip():
        return None
    try:
        status = json.loads(out)
    except json.JSONDecodeError:
        return None
    s = None
    for surf in status.get("surfaces", []):
        if surf.get("role") == role and not surf.get("exited"):
            s = surf
            break
    if s is None:
        return None
    return s.get("agent_alive") is True


def _build_wrap_tolerant_pattern(expected: str) -> "re.Pattern":
    """★Hardened this round — the previous "remove ALL whitespace from both sides" approach
    (see git history / prior round's docstring) was found, by direct test, to collapse
    genuinely different strings to the same value whenever a real inter-word space happened to
    be absent in one of them (`"echo hello world"` and `"echo helloworld"` both normalize to
    `"echohelloworld"`) — a real false-positive class, not a theoretical one.

    This replacement is deliberately asymmetric and conservative: a run of one-or-more literal
    SPACE characters in `expected` becomes `\\s+` in the compiled pattern (tolerating a wrap's
    newline+indent at a position that was ALREADY a genuine token boundary — widening or
    narrowing the whitespace there is safe, since some boundary already existed). Every other
    character — including the boundary BETWEEN two characters that had NO space in `expected`
    — is matched as an exact literal (`re.escape`d). No insertion tolerance is ever granted at
    a non-space position, which is exactly what would be required to merge two originally
    separate tokens (the "hello world"/"helloworld" class) — that class is now structurally
    unrepresentable by this pattern, not just avoided by luck.

    Trade-off (accepted per owner explicit instruction — false negatives are tolerable, false
    positives are not): terminal wrap CAN insert its newline+indent in the middle of a word
    that had no original space (empirically observed this session, e.g. "maf-\\n  publishing-"
    from "maf-publishing-poc"). This pattern will NOT match across such a mid-word wrap — that
    produces a safe NO_MATCH, never an incorrect MATCH."""
    parts = []
    prev_was_space = False
    for ch in expected:
        if ch == " ":
            if not prev_was_space:
                parts.append(r"\s+")
            prev_was_space = True
        else:
            parts.append(re.escape(ch))
            prev_was_space = False
    return re.compile("".join(parts), re.DOTALL)


def _pending_input_match(expected: str, observed: str) -> str:
    """Returns exactly one of 'MATCH' / 'NO_MATCH' / 'UNCERTAIN' — never a bare bool, so a
    caller cannot accidentally treat 'could not determine' as either a positive or negative.
    UNCERTAIN is reserved for genuine read/input failures (empty or non-string observed/
    expected) — a well-formed comparison that simply does not find the pattern is NO_MATCH,
    not UNCERTAIN (this deterministic algorithm has no ambiguous middle ground once both
    inputs are valid strings)."""
    if not isinstance(observed, str) or observed == "":
        return "UNCERTAIN"
    if not isinstance(expected, str) or expected == "":
        return "UNCERTAIN"
    pattern = _build_wrap_tolerant_pattern(expected)
    return "MATCH" if pattern.search(observed) else "NO_MATCH"


def _pending_input_visible(role: str, instruction: str) -> str:
    """Read-only screen check — returns 'MATCH' / 'NO_MATCH' / 'UNCERTAIN' (see
    _pending_input_match). ONE input to the recovery-eligibility decision, never sufficient
    alone. Recovery Enter is eligible ONLY on 'MATCH' — both 'NO_MATCH' and 'UNCERTAIN' must
    block recovery (DO NOT ENTER — STOP), per this round's explicit gate semantics."""
    try:
        code, out, err = _readonly_run("read_screen", ["--to", role])
    except Phase2AReadOnlyViolation:
        return "UNCERTAIN"
    if code != 0:
        return "UNCERTAIN"
    return _pending_input_match(instruction, out)


def submit_test_task_state_machine(role: str, provider: str, task_id: str, packet: dict,
                                    submission_check_wait_s: float = 5.0,
                                    result_timeout_s: float = 60.0) -> dict:
    """TASK_READY -> CONTROL_SENT -> PRIMARY_RETURN_SENT -> SUBMISSION_CHECK
       -> [submitted] PROCESSING -> RESULT_FINAL -> VALIDATED -> (caller: DB_COMPLETED)
       -> [not submitted, all 5 recovery preconditions hold] RECOVERY_ENTER_X1 (max once,
          logged as PENDING_INPUT_COMMIT, never as retry) -> SUBMISSION_RECHECK
          -> [submitted] PROCESSING -> ... -> [still not submitted] SUBMISSION_FAILED, STOP.

    CODEX-ONLY (see _codex_submission_exists). Exactly one control-message send, at most one
    recovery Enter, at most one provider execution per call. No automatic retry of anything."""
    trace: list[dict] = []

    def log(state: str, **kw):
        trace.append({"state": state, "at": _now(), **kw})

    log("TASK_READY", task_id=task_id, provider=provider, role=role)

    expected_task_sha256 = hashlib.sha256(
        json.dumps(packet, ensure_ascii=False, indent=2).encode("utf-8")
    ).hexdigest()
    idem = _check_idempotent_existing_result(task_id, expected_task_sha256)
    if idem["conflict"]:
        log("IDEMPOTENCY_CONFLICT", reason=idem["reason"])
        return {"final_state": "IDEMPOTENCY_CONFLICT — STOP", "trace": trace, "idempotency": idem}
    if idem["idempotent"]:
        log("IDEMPOTENT_COMPLETED", reason=idem["reason"])
        return {"final_state": "IDEMPOTENT_COMPLETED — DO NOT SUBMIT", "trace": trace, "idempotency": idem}

    policy = check_target_policy(role, provider, task_id)
    log("TARGET_POLICY", allowed=policy.allowed, reason=policy.reason)
    if not policy.allowed:
        return {"final_state": f"DENIED: {policy.reason}", "trace": trace}

    task_path = TASKS_PENDING_DIR / f"{task_id}.json"
    task_sha256, task_bytes = write_task_file(packet, task_path)
    assert task_sha256 == expected_task_sha256, "write_task_file produced unexpected bytes"

    result_path = RESULTS_DIR / f"{task_id}.json"
    result_tmp_path = RESULTS_DIR / f"{task_id}.json.tmp"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    instruction = (
        f"[PHASE2B-TASK-FILE] Read the JSON file at {task_path} (UTF-8 encoding). "
        f"Follow its objective/output_schema/constraints fields exactly. "
        f"Write ONLY the resulting output JSON object to {result_tmp_path} using UTF-8 "
        f"encoding with no BOM, then rename that file to {result_path}. "
        f"Do not modify {task_path}. Do not print the JSON to the terminal."
    )

    send_proc = subprocess.run(["cys", "send", "--to", role, instruction],
                                capture_output=True, text=True, timeout=15.0)
    log("CONTROL_SENT", rc=send_proc.returncode, stderr=send_proc.stderr)
    control_message_send_count = 1
    if send_proc.returncode != 0:
        return {"final_state": f"CONTROL_SEND_FAILED: {send_proc.stderr}", "trace": trace,
                "control_message_send_count": control_message_send_count}

    key_proc = subprocess.run(["cys", "send-key", "--to", role, "Return"],
                               capture_output=True, text=True, timeout=15.0)
    log("PRIMARY_RETURN_SENT", rc=key_proc.returncode)

    time.sleep(submission_check_wait_s)
    submitted = _codex_submission_exists(task_id)
    log("SUBMISSION_CHECK", submitted=submitted)

    recovery_enter_used = False
    if submitted is not True:
        proc_alive = _provider_alive(role)
        pending_match = _pending_input_visible(role, instruction)  # 'MATCH'/'NO_MATCH'/'UNCERTAIN'
        result_exists = result_path.exists()
        tmp_exists = result_tmp_path.exists()
        # Recovery Enter requires the pending-input signal to be an explicit MATCH — both
        # NO_MATCH and UNCERTAIN block recovery (DO NOT ENTER — STOP), no exceptions.
        eligible = (submitted is False and result_exists is False and tmp_exists is False
                    and proc_alive is True and pending_match == "MATCH")
        log("RECOVERY_ELIGIBILITY", eligible=eligible, submitted=submitted,
            proc_alive=proc_alive, pending_match=pending_match,
            result_exists=result_exists, tmp_exists=tmp_exists)
        if not eligible:
            return {"final_state": "SUBMISSION_UNCERTAIN — STOP (recovery not eligible)",
                    "trace": trace, "submitted": submitted,
                    "control_message_send_count": control_message_send_count}

        recovery_proc = subprocess.run(["cys", "send-key", "--to", role, "Return"],
                                        capture_output=True, text=True, timeout=15.0)
        recovery_enter_used = True
        log("RECOVERY_ENTER_X1", rc=recovery_proc.returncode, classified_as="PENDING_INPUT_COMMIT")

        time.sleep(submission_check_wait_s)
        submitted = _codex_submission_exists(task_id)
        log("SUBMISSION_RECHECK", submitted=submitted)
        if submitted is not True:
            return {"final_state": "SUBMISSION_FAILED — STOP", "trace": trace,
                    "submitted": submitted, "recovery_enter_used": recovery_enter_used,
                    "control_message_send_count": control_message_send_count}

    log("PROCESSING")

    collected = collect_test_result_file(task_id, timeout_s=result_timeout_s, poll_interval_s=2.0)
    if not collected["ok"]:
        log("RESULT_TIMEOUT", error=collected.get("error"))
        return {"final_state": "RESULT_TIMEOUT — STOP", "trace": trace,
                "recovery_enter_used": recovery_enter_used,
                "control_message_send_count": control_message_send_count}
    log("RESULT_FINAL", sha256=collected["sha256"])

    from tasks.test_task import validate_output
    vresult = validate_output(collected["raw_text"])
    log("VALIDATED", passed=vresult.passed, reasons=vresult.reasons)

    return {
        "final_state": "VALIDATED" if vresult.passed else "VALIDATION_FAILED",
        "trace": trace,
        "task_path": str(task_path), "task_sha256": task_sha256,
        "result_path": collected["result_path"], "result_sha256": collected["sha256"],
        "raw_text": collected["raw_text"],
        "validation_passed": vresult.passed, "validation_reasons": vresult.reasons,
        "control_message_send_count": control_message_send_count,
        "recovery_enter_used": recovery_enter_used,
        "surface_ref": policy.surface_ref,
    }
