"""TEST 2A-B — CYSJavis READ-ONLY Adapter: query real state, verify surfaces/pid/role unchanged
before vs after."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers2a import PHASE2A_ROOT, cys_list_raw  # noqa: E402

sys.path.insert(0, str(PHASE2A_ROOT))
from adapter.cys_readonly_adapter import get_cys_status, get_cys_surfaces, get_provider_usage_snapshot  # noqa: E402


def parse_surfaces(list_output: str) -> dict[str, tuple[str, str, str]]:
    """surface_ref -> (role, pid, exited)"""
    out = {}
    for line in list_output.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ref = parts[0]
        role = parts[1].replace("role=", "")
        pid = parts[2].replace("pid=", "")
        exited = parts[3].replace("exited=", "") if len(parts) > 3 else "?"
        out[ref] = (role, pid, exited)
    return out


def main() -> bool:
    ok = True

    before = cys_list_raw()
    before_parsed = parse_surfaces(before)
    print("before:", before_parsed)

    r_status = get_cys_status()
    r_surfaces = get_cys_surfaces()
    r_usage = get_provider_usage_snapshot()

    if not r_status.ok:
        print("FAIL: get_cys_status() failed:", r_status.error)
        ok = False
    if not r_surfaces.ok:
        print("FAIL: get_cys_surfaces() failed:", r_surfaces.error)
        ok = False
    if not r_usage.ok:
        print("FAIL: get_provider_usage_snapshot() failed:", r_usage.error)
        ok = False

    if r_status.data:
        n_surfaces = len(r_status.data.get("surfaces", []))
        print(f"adapter reports {n_surfaces} surfaces via get_cys_status()")
        if n_surfaces != len(before_parsed):
            print(f"FAIL: surface count mismatch, cys list={len(before_parsed)} vs status.surfaces={n_surfaces}")
            ok = False

    after = cys_list_raw()
    after_parsed = parse_surfaces(after)
    print("after:", after_parsed)

    if before_parsed != after_parsed:
        print("FAIL: surface/role/pid/exited changed after adapter calls!")
        print("  before:", before_parsed)
        print("  after: ", after_parsed)
        ok = False
    else:
        print("surfaces/role/pid/exited: IDENTICAL before vs after adapter read-only calls")

    print("TEST 2A-B:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
