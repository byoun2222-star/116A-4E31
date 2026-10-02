"""TEST 2A-G — Provider Router MOCK: no real provider is ever contacted. Injects synthetic
health scenarios and verifies selection follows health, not a hard-coded provider preference."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers2a import PHASE2A_ROOT  # noqa: E402

sys.path.insert(0, str(PHASE2A_ROOT))
from router.provider_router import ProviderHealth, ProviderState, route  # noqa: E402


def main() -> bool:
    ok = True

    # Scenario 1: Claude RATE_LIMITED, Codex/Gemini AVAILABLE -> must NOT pick Claude.
    states1 = [
        ProviderState("CLAUDE", ProviderHealth.RATE_LIMITED),
        ProviderState("CODEX", ProviderHealth.AVAILABLE),
        ProviderState("GEMINI", ProviderHealth.AVAILABLE),
    ]
    d1 = route(states1)
    print("scenario1 (Claude rate-limited):", d1)
    if d1.selected_provider != "CODEX":
        print(f"FAIL: expected CODEX (first routable in stable order), got {d1.selected_provider}")
        ok = False
    if "CLAUDE" not in d1.excluded:
        print("FAIL: CLAUDE should be listed as excluded (rate-limited)")
        ok = False

    # Scenario 2: Claude AVAILABLE, Codex RATE_LIMITED, Gemini AVAILABLE -> must pick Claude
    # (not because Claude is "better", but because it's first in stable order among routable).
    states2 = [
        ProviderState("CLAUDE", ProviderHealth.AVAILABLE),
        ProviderState("CODEX", ProviderHealth.RATE_LIMITED),
        ProviderState("GEMINI", ProviderHealth.AVAILABLE),
    ]
    d2 = route(states2)
    print("scenario2 (Codex rate-limited):", d2)
    if d2.selected_provider != "CLAUDE":
        print(f"FAIL: expected CLAUDE, got {d2.selected_provider}")
        ok = False

    # Scenario 3: everything unavailable/unknown -> no selection, honest "none routable".
    states3 = [
        ProviderState("CLAUDE", ProviderHealth.RATE_LIMITED),
        ProviderState("CODEX", ProviderHealth.UNAVAILABLE),
        ProviderState("GEMINI", ProviderHealth.UNKNOWN),
    ]
    d3 = route(states3)
    print("scenario3 (all down/unknown):", d3)
    if d3.selected_provider is not None:
        print(f"FAIL: expected no selection when nothing is routable, got {d3.selected_provider}")
        ok = False

    # Scenario 4: UNKNOWN must not be treated as usable (owner §5 explicit).
    states4 = [
        ProviderState("CLAUDE", ProviderHealth.UNKNOWN),
        ProviderState("CODEX", ProviderHealth.UNKNOWN),
        ProviderState("GEMINI", ProviderHealth.DEGRADED),
    ]
    d4 = route(states4)
    print("scenario4 (Claude/Codex UNKNOWN, Gemini DEGRADED):", d4)
    if d4.selected_provider != "GEMINI":
        print(f"FAIL: expected GEMINI (only routable one, DEGRADED still counts as usable), got {d4.selected_provider}")
        ok = False

    print("TEST 2A-G:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
