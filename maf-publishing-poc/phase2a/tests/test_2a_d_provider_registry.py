"""TEST 2A-D — Provider Registry: CLAUDE/CODEX/GEMINI all register; only observed health/usage
recorded; unobserved values are UNKNOWN, never fabricated."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers2a import PHASE2A_ROOT, reset_poc_state, run_cli  # noqa: E402

sys.path.insert(0, str(PHASE2A_ROOT))
from db import publishing_db as db  # noqa: E402

BOOK_ID = "BOOK-POC-002"


def main() -> bool:
    reset_poc_state()
    ok = True

    run_cli("start", "--book-id", BOOK_ID, "--title", "TEST 2A-D 도서")

    providers = {p["provider_id"]: p for p in db.get_all_providers()}
    print("registered providers:", list(providers.keys()))

    for expected in ("CLAUDE", "CODEX", "GEMINI"):
        if expected not in providers:
            print(f"FAIL: {expected} not registered")
            ok = False

    claude = providers.get("CLAUDE", {})
    if claude.get("health") != "AVAILABLE" or "statusline" not in (claude.get("usage_source") or ""):
        print(f"FAIL: unexpected CLAUDE record: {claude}")
        ok = False
    else:
        print("CLAUDE: health=AVAILABLE, usage_source=statusline (hook-verified) — OK")

    codex = providers.get("CODEX", {})
    if "heuristic" not in (codex.get("usage_source") or "") or "LOW" not in (codex.get("confidence_reliability") or ""):
        print(f"FAIL: CODEX confidence should be explicitly LOW/heuristic, got: {codex}")
        ok = False
    else:
        print("CODEX: usage_source=rollout:heuristic:stale, confidence=LOW — OK (not upgraded to a nicer label)")

    gemini = providers.get("GEMINI", {})
    if gemini.get("health") != "UNKNOWN" or gemini.get("usage_value") is not None:
        print(f"FAIL: GEMINI should be health=UNKNOWN with no fabricated usage_value, got: {gemini}")
        ok = False
    else:
        print("GEMINI: health=UNKNOWN, usage_value=None (not observable, not guessed) — OK")

    print("TEST 2A-D:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
