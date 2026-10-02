# -*- coding: utf-8 -*-
"""
MINIMAL FIX verification: bypass the npm shim chain entirely (bare "codex" shell script AND
the codex.cmd/.ps1 batch/PowerShell wrappers) by resolving node.exe explicitly and invoking
the actual JS entry point directly: node.exe <codex.js path> <protocol argv>.
This avoids BOTH the FileNotFoundError class (node.exe is a real, directly resolvable native
executable) AND the cmd.exe %*-reparsing risk (no .cmd in the invocation chain at all).
Verified here with a harmless dummy .js echo script -- codex.js itself is never invoked.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh  # noqa: E402

PROTOCOL_LIKE_TEXT = (
    "line one\nline two with <TOKEN> angle brackets\nline three\n"
    "RUN <T1A2B3C4>\nlast line, no trailing newline"
)


def main():
    conn = eh.get_conn()
    run_id = eh.start_run(
        objective="TASK E minimal-fix verification: resolve node.exe explicitly and invoke a "
                   "dummy .js entry point directly, bypassing codex/codex.cmd/codex.ps1 shim "
                   "chain entirely. Dummy only -- codex.js never invoked.",
        actor="claude-session", provider="LOCAL",
        raw_command="python test_node_resolution_fix.py",
        conn=conn,
    )
    print("RUN_ID:", run_id)

    results = {}
    node_path = shutil.which("node")
    results["shutil_which_node"] = node_path
    results["node_is_real_exe"] = bool(node_path and node_path.lower().endswith(".exe"))

    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_js = Path(tmpdir) / "dummy_echo.js"
        dummy_js.write_text(
            "const fs=require('fs');"
            "fs.writeFileSync(process.argv[2], JSON.stringify({received: process.argv[3]}));",
            encoding="utf-8",
        )
        out_marker = Path(tmpdir) / "node_marker.json"

        full_argv = [node_path, str(dummy_js), str(out_marker), PROTOCOL_LIKE_TEXT]
        try:
            proc = subprocess.run(full_argv, shell=False, capture_output=True, text=True, timeout=15)
            results["rc"] = proc.returncode
            results["raised"] = None
            results["stderr"] = proc.stderr.strip()
        except Exception as e:
            results["rc"] = None
            results["raised"] = f"{type(e).__module__}.{type(e).__name__}: {e}"

        results["marker_written"] = out_marker.exists()
        if out_marker.exists():
            received = json.loads(out_marker.read_text(encoding="utf-8"))["received"]
            results["exact_match"] = (received == PROTOCOL_LIKE_TEXT)
            results["newline_count_match"] = (received.count("\n") == PROTOCOL_LIKE_TEXT.count("\n"))
            results["angle_bracket_count_match"] = (
                received.count("<") == PROTOCOL_LIKE_TEXT.count("<")
                and received.count(">") == PROTOCOL_LIKE_TEXT.count(">")
            )

    overall_pass = (
        results["node_is_real_exe"]
        and results.get("raised") is None
        and results.get("rc") == 0
        and results.get("marker_written")
        and results.get("exact_match")
        and results.get("newline_count_match")
        and results.get("angle_bracket_count_match")
    )

    for k, v in results.items():
        print(f"{k}: {v}")
    print("MINIMAL FIX VERIFICATION:", "PASS" if overall_pass else "FAIL")

    eh.record_evidence(
        f"TASK E minimal fix (resolve node.exe + invoke codex.js directly, bypass shim chain) "
        f"verified with dummy .js: {json.dumps(results, ensure_ascii=False, default=str)}",
        "CONFIRMED" if overall_pass else "FAILED",
        run_id=run_id, conn=conn,
    )
    eh.finalize_run(
        run_id, final_status="COMPLETED" if overall_pass else "FAILED",
        validation_result="PASS" if overall_pass else "FAIL",
        conn=conn,
    )
    conn.commit()
    conn.close()
    return run_id, overall_pass


if __name__ == "__main__":
    main()
