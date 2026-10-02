# Copyright (c) tree and fruits. PoC only — PHASE 2B short-token control-plane manifest.
"""Local rehearsal module for the TOKEN -> manifest -> task_id -> task.json -> result.json
mapping design. This module does NOT call cys, does NOT touch any AI/provider, and does NOT
modify the Publishing DB schema — it is a self-contained, deterministic PoC-only manifest
sitting entirely under phase2b/control/.

Token format: "T" + sha256(task_id)[:8].upper() — 9 ASCII chars, deterministically derivable
from task_id alone (no registry needed to *generate* it — only to *resolve* it and to detect
collisions before it is accepted into the manifest).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
PHASE2B_ROOT = CONTROL_DIR.parent
MANIFEST_PATH = CONTROL_DIR / "token_manifest.json"

TOKEN_RE = re.compile(r"^T[0-9A-F]{8}$")


class TokenError(Exception):
    """Raised for any STOP condition — never silently resolved permissively."""


def generate_token(task_id: str) -> str:
    return "T" + hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:8].upper()


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _assert_in_scope(path: Path) -> None:
    """Rejects any mapping whose task_path/result_path resolves outside the phase2b/ tree —
    defense against a manifest entry (however it was produced) pointing anywhere else on disk."""
    resolved = path.resolve()
    if PHASE2B_ROOT.resolve() not in resolved.parents and resolved != PHASE2B_ROOT.resolve():
        raise TokenError(f"PATH_OUT_OF_SCOPE: {resolved} is not under {PHASE2B_ROOT.resolve()}")


def register_token(task_id: str, task_path: Path, result_path: Path, task_sha256: str) -> str:
    """Generates the token for task_id and registers it in the manifest. STOPS (raises
    TokenError) on: invalid inputs, path-out-of-scope, or a genuine collision (same token
    already mapped to a DIFFERENT task_id — never silently overwritten)."""
    _assert_in_scope(task_path)
    _assert_in_scope(result_path)

    token = generate_token(task_id)
    if not TOKEN_RE.match(token):
        raise TokenError(f"TOKEN_FORMAT_INVALID (generation itself produced malformed token): {token!r}")

    manifest = _load_manifest()
    existing = manifest.get(token)
    if existing is not None and existing["task_id"] != task_id:
        raise TokenError(
            f"TOKEN_COLLISION_CONFLICT: token {token} already maps to task_id="
            f"{existing['task_id']!r}, cannot also map to {task_id!r}"
        )

    manifest[token] = {
        "task_id": task_id,
        "task_path": str(task_path),
        "result_path": str(result_path),
        "task_sha256": task_sha256,
        "status": "PENDING",
    }
    _save_manifest(manifest)
    return token


def resolve_token(token: str) -> dict:
    """STOPS (raises TokenError) on: invalid format, unknown token, or (defensively) more
    than one manifest entry claiming the same token (should be structurally impossible for a
    dict key, but checked explicitly for a JSON file that could in principle be hand-edited
    or corrupted with duplicate-looking keys after a bad merge)."""
    if not isinstance(token, str) or not TOKEN_RE.match(token):
        raise TokenError(f"TOKEN_FORMAT_INVALID: {token!r}")

    manifest = _load_manifest()
    matches = [(k, v) for k, v in manifest.items() if k == token]
    if len(matches) == 0:
        raise TokenError(f"UNKNOWN_TOKEN: {token!r} not found in manifest")
    if len(matches) > 1:
        raise TokenError(f"AMBIGUOUS_TOKEN: {token!r} appears {len(matches)} times in manifest")

    _, entry = matches[0]
    task_path = Path(entry["task_path"])
    result_path = Path(entry["result_path"])
    _assert_in_scope(task_path)
    _assert_in_scope(result_path)
    return entry
