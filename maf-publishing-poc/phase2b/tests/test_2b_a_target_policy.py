# Copyright (c) tree and fruits. PoC only.
"""TEST 2B-A — Controlled Write Gate: denied targets must be refused BEFORE any subprocess is
spawned; only a genuinely allowed target may pass. This test exercises the denial paths that
don't require a live PHASE2B test surface to exist yet (production-role targets, bad providers,
nonexistent roles, nonexistent/already-completed task_ids) — the ALLOW path is exercised
separately in TEST 2B-B/C/D once each real worker-4/5/6 surface actually exists."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from controlled_adapter.controlled_cys_adapter import (  # noqa: E402
    DENIED_BY_PHASE2B_TARGET_POLICY, check_target_policy,
)


def expect_denied(role: str, provider: str, task_id: str, label: str) -> bool:
    result = check_target_policy(role, provider, task_id)
    ok = (not result.allowed) and result.reason.startswith(DENIED_BY_PHASE2B_TARGET_POLICY)
    print(f"[{label}] allowed={result.allowed} reason={result.reason}")
    if not ok:
        print(f"FAIL: {label} should have been denied")
    return ok


def main() -> bool:
    ok = True
    ok &= expect_denied("master", "CLAUDE", "phase2b-task-run1-claude", "production role master")
    ok &= expect_denied("cso", "CLAUDE", "phase2b-task-run1-claude", "production role cso")
    ok &= expect_denied("worker", "CLAUDE", "phase2b-task-run1-claude", "production role worker")
    ok &= expect_denied("worker-2", "CLAUDE", "phase2b-task-run1-claude", "production role worker-2")
    ok &= expect_denied("worker-3", "CODEX", "phase2b-task-run2-codex", "production role worker-3 (native-handoff surface)")
    ok &= expect_denied("worker-4", "OPENAI", "phase2b-task-run1-claude", "bad provider name")
    ok &= expect_denied("worker-9", "CLAUDE", "phase2b-task-run1-claude", "role not in pre-announced allowlist")
    ok &= expect_denied("worker-4", "CLAUDE", "phase2b-task-does-not-exist", "nonexistent task_id")
    # worker-4 legitimately allowlisted but surface does not exist yet at this point in the
    # test run (created later, sequentially, per master's one-at-a-time safety instruction) ->
    # must still deny (uncertainty = deny), not silently skip the surface-existence check.
    ok &= expect_denied("worker-4", "CLAUDE", "phase2b-task-run1-claude", "allowlisted role but no live surface yet")
    print("TEST 2B-A:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
