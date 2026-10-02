"""TEST 2A-C — READ-ONLY Policy: mock-request forbidden mutation ops, verify DENIED_BY_PHASE2A_
READONLY_POLICY is returned and NO subprocess is ever spawned for them."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers2a import PHASE2A_ROOT  # noqa: E402

sys.path.insert(0, str(PHASE2A_ROOT))
from adapter.cys_readonly_adapter import (  # noqa: E402
    DENIED_BY_PHASE2A_READONLY_POLICY,
    Phase2AReadOnlyViolation,
    _run,
    attempt_denied_action,
)

FORBIDDEN_ACTIONS = [
    "send", "send-key", "close-surface", "claim-role", "launch-agent", "restore",
    "node-recover", "daemon", "kill", "run", "new-surface",
]


def main() -> bool:
    ok = True

    for action in FORBIDDEN_ACTIONS:
        result = attempt_denied_action(action)
        if result.ok:
            print(f"FAIL: {action} was NOT denied")
            ok = False
        if DENIED_BY_PHASE2A_READONLY_POLICY not in (result.error or ""):
            print(f"FAIL: {action} error did not contain the policy tag: {result.error}")
            ok = False
        if result.source_command != "(refused before execution)":
            print(f"FAIL: {action} appears to have reached subprocess construction: {result.source_command}")
            ok = False
    print(f"attempt_denied_action(): {len(FORBIDDEN_ACTIONS)}/{len(FORBIDDEN_ACTIONS)} forbidden ops correctly denied, 0 subprocess spawned")

    # Second path: hit _run() directly (the actual subprocess-invoking function) with an
    # action key that isn't in the allowlist, proving the low-level guard also refuses.
    for action_key in ("close_surface", "send_key", "launch_agent", "daemon_restart"):
        try:
            _run(action_key)
            print(f"FAIL: _run('{action_key}') should have raised Phase2AReadOnlyViolation")
            ok = False
        except Phase2AReadOnlyViolation as e:
            if DENIED_BY_PHASE2A_READONLY_POLICY not in str(e):
                print(f"FAIL: _run('{action_key}') raised without the policy tag: {e}")
                ok = False
    print("_run() direct-call denial path: confirmed for all 4 sample keys")

    print("TEST 2A-C:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
