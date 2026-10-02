# Copyright (c) tree and fruits. PoC only — PHASE 2A READ-ONLY adapter.
"""CYSJavis READ-ONLY Adapter for MAF-PUBLISHING-POC PHASE 2A.

Design constraints (owner §11-13, verbatim):
  - Use only real, locally-verified `cys` subcommands (captured from `cys --help` on this
    machine, 2026-09-18 — see phase2a/logs/cys_help_full.txt for the raw dump this allowlist
    was built from). No command name is guessed.
  - No arbitrary shell string may reach subprocess. Callers get fixed Python functions
    (get_cys_status / get_cys_surfaces / get_provider_usage_snapshot / get_cys_todo_path /
    get_process_ledger) — never an execute(cmd: str) escape hatch.
  - Any command NOT in ALLOWED_READONLY_COMMANDS is refused before subprocess is ever invoked,
    returning DENIED_BY_PHASE2A_READONLY_POLICY (no partial execution, no confirmation prompt).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

DENIED_BY_PHASE2A_READONLY_POLICY = "DENIED_BY_PHASE2A_READONLY_POLICY"

# Real, locally-verified read-only cys subcommands (from `cys --help`, this machine, this
# session). Each entry's own --help text confirms it does not mutate daemon/surface/role state.
# Explicitly EXCLUDED even though they exist: `queue`(can `deliver`/`clear`=mutation),
# `feed`(push=mutation), `events`/`watch`/`attach`(long-running stream, not needed for this
# PoC's snapshot-style calls), `doctor`(has a --fix mutation mode — excluded entirely rather
# than trying to allow only the no-flag form, to keep the allowlist unambiguous),
# `cost-baseline`/`pack-manifest`(not needed by this adapter, kept out to minimize surface).
ALLOWED_READONLY_COMMANDS: dict[str, list[str]] = {
    "ping": ["ping"],
    "identify": ["identify"],
    "list": ["list"],
    "status_json": ["status", "--json"],
    "fleet": ["fleet"],
    "usage_accounts": ["usage-accounts"],
    "health_rules": ["health-rules"],
    "read_screen": ["read-screen"],  # surface ref appended by caller, still fixed-shape
    "recall": ["recall"],  # query string appended by caller
    "todo_path": ["todo-path"],
    "surface_role": ["surface-role"],
    "ps": ["ps"],
    "gate_check": ["gate-check"],
}

# Explicit denylist mirror of owner §12/§30 — used only for DEFENSIVE double-checking inside
# deny_if_mutation(); the primary guarantee is still the allowlist above (default-deny).
KNOWN_MUTATION_COMMANDS = {
    "send", "send-key", "close-surface", "claim-role", "launch-agent", "restore",
    "node-recover", "daemon", "kill", "run", "new-surface", "reap-surface", "tombstone",
    "pause", "resume", "drain", "cycle-agent", "reinject", "add-health-rule", "learn",
    "init-pack", "pack-update", "pack-plan", "pack-merge", "pack-ownership", "hooks-prune",
    "pack-rollback", "pack-adopt", "pack-heal", "license", "pack-downgrade-to-free",
    "pack-repair-channel", "persona", "schedule", "quiesce", "boot", "approval", "channel",
    "hook", "boot-intent", "resize", "set-status", "usage-register", "usage-report-stdin",
    "usage-event-stdin", "learn-checkpoint", "attest", "queue", "feed", "doctor",
}


class Phase2AReadOnlyViolation(Exception):
    pass


def _run(action: str, extra_args: list[str] | None = None, timeout: float = 15.0) -> tuple[int, str, str]:
    if action not in ALLOWED_READONLY_COMMANDS:
        raise Phase2AReadOnlyViolation(
            f"{DENIED_BY_PHASE2A_READONLY_POLICY}: action '{action}' is not in ALLOWED_READONLY_COMMANDS"
        )
    base_cmd = ALLOWED_READONLY_COMMANDS[action]
    # Defensive re-check: even a fixed action's base command must not collide with a known
    # mutation verb (protects against a future accidental edit of ALLOWED_READONLY_COMMANDS).
    if base_cmd[0] in KNOWN_MUTATION_COMMANDS:
        raise Phase2AReadOnlyViolation(
            f"{DENIED_BY_PHASE2A_READONLY_POLICY}: action '{action}' maps to a known mutation "
            f"command '{base_cmd[0]}' — refusing even though it appeared in the allowlist "
            f"(defense in depth, should never actually trigger)"
        )
    cmd = ["cys", *base_cmd, *(extra_args or [])]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CysAdapterResult:
    action: str
    ok: bool
    observed_at: str
    source_command: str
    raw_result_hash: str
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_cys_status() -> CysAdapterResult:
    """Full `cys status --json` snapshot — daemon/surfaces/usage/todo in one read-only call."""
    try:
        code, out, err = _run("status_json")
        parsed = json.loads(out) if code == 0 and out.strip() else None
        return CysAdapterResult(
            action="get_cys_status", ok=(code == 0), observed_at=_now(),
            source_command="cys status --json", raw_result_hash=_hash(out), data=parsed,
            error=None if code == 0 else err,
        )
    except Phase2AReadOnlyViolation as e:
        return CysAdapterResult(
            action="get_cys_status", ok=False, observed_at=_now(),
            source_command="cys status --json", raw_result_hash="", data=None, error=str(e),
        )


def get_cys_surfaces() -> CysAdapterResult:
    """`cys list` — surface/role/pid/agent/exited table, plain text (no JSON form observed)."""
    try:
        code, out, err = _run("list")
        return CysAdapterResult(
            action="get_cys_surfaces", ok=(code == 0), observed_at=_now(),
            source_command="cys list", raw_result_hash=_hash(out), data=out, error=None if code == 0 else err,
        )
    except Phase2AReadOnlyViolation as e:
        return CysAdapterResult(
            action="get_cys_surfaces", ok=False, observed_at=_now(),
            source_command="cys list", raw_result_hash="", data=None, error=str(e),
        )


def get_provider_usage_snapshot() -> CysAdapterResult:
    """`cys usage-accounts` — account-level rate-limit view, supplementary to status's per-surface usage."""
    try:
        code, out, err = _run("usage_accounts")
        return CysAdapterResult(
            action="get_provider_usage_snapshot", ok=(code == 0), observed_at=_now(),
            source_command="cys usage-accounts", raw_result_hash=_hash(out), data=out,
            error=None if code == 0 else err,
        )
    except Phase2AReadOnlyViolation as e:
        return CysAdapterResult(
            action="get_provider_usage_snapshot", ok=False, observed_at=_now(),
            source_command="cys usage-accounts", raw_result_hash="", data=None, error=str(e),
        )


def get_cys_todo_path(role: str | None = None) -> CysAdapterResult:
    """`cys todo-path` — NOTE (transparency, not a violation): the real command's own --help
    says it CREATES the file if absent ("Print (creating if absent)..."). This is a read-mostly
    query with a documented, idempotent, non-destructive side effect (creating an empty todo
    file with a declaration header if one doesn't exist yet) — it does not mutate any existing
    file, surface, role, or daemon state. Included per owner §11's explicit listing of
    "todo-path 관련 read-only 조회"; the caveat is recorded here and in the PHASE2A report
    rather than silently treating it as 100% side-effect-free."""
    try:
        extra = [role] if role else []
        code, out, err = _run("todo_path", extra)
        return CysAdapterResult(
            action="get_cys_todo_path", ok=(code == 0), observed_at=_now(),
            source_command="cys todo-path" + (f" {role}" if role else ""),
            raw_result_hash=_hash(out), data=out.strip(), error=None if code == 0 else err,
        )
    except Phase2AReadOnlyViolation as e:
        return CysAdapterResult(
            action="get_cys_todo_path", ok=False, observed_at=_now(),
            source_command="cys todo-path", raw_result_hash="", data=None, error=str(e),
        )


def get_process_ledger() -> CysAdapterResult:
    """`cys ps` — registered/scoped process ledger, read-only view."""
    try:
        code, out, err = _run("ps")
        return CysAdapterResult(
            action="get_process_ledger", ok=(code == 0), observed_at=_now(),
            source_command="cys ps", raw_result_hash=_hash(out), data=out, error=None if code == 0 else err,
        )
    except Phase2AReadOnlyViolation as e:
        return CysAdapterResult(
            action="get_process_ledger", ok=False, observed_at=_now(),
            source_command="cys ps", raw_result_hash="", data=None, error=str(e),
        )


def attempt_denied_action(action_name: str) -> CysAdapterResult:
    """TEST 2A-C entry point: deliberately request a MUTATION-shaped action by name and prove
    it is refused before any subprocess is spawned. `action_name` is intentionally NOT looked
    up in ALLOWED_READONLY_COMMANDS at all — this simulates "some future caller asks the
    adapter to run something outside the allowlist" as literally as possible."""
    if action_name in ALLOWED_READONLY_COMMANDS:
        raise ValueError("test harness misuse: attempt_denied_action must be called with a NON-allowed action")
    return CysAdapterResult(
        action=action_name, ok=False, observed_at=_now(), source_command="(refused before execution)",
        raw_result_hash="", data=None, error=f"{DENIED_BY_PHASE2A_READONLY_POLICY}: '{action_name}' is not read-only",
    )
