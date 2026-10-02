# -*- coding: utf-8 -*-
"""
TASK D — harmless local reproduction of the Windows subprocess(shell=False) executable
resolution behavior for a "bare-name POSIX shell script + sibling .cmd" pair, exactly
mirroring the real layout found at C:\\Users\\a\\AppData\\Local\\cys-npm\\codex{,.cmd,.ps1}.
Does NOT touch the real codex. No AI/provider/surface involved.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh  # noqa: E402

MARKER = None  # set per-test


def main():
    conn = eh.get_conn()
    run_id = eh.start_run(
        objective="TASK D: reproduce Windows subprocess(shell=False) executable-resolution "
                   "behavior for an extensionless POSIX-shim + sibling .cmd pair (dummy only, "
                   "never touches real codex)",
        actor="claude-session",
        provider="LOCAL",
        raw_command="python test_executable_resolution.py",
        conn=conn,
    )
    print("RUN_ID:", run_id)

    results = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        out_marker = tmp / "marker.json"

        # Mirror the real layout: bare-name POSIX shell script (no extension)
        dummy_sh = tmp / "dummyexe"
        dummy_sh.write_text(
            "#!/bin/sh\necho POSIX_SHIM_RAN\n",
            encoding="utf-8", newline="\n",
        )
        dummy_sh.chmod(0o755)

        # Sibling .cmd wrapper, harmless: just writes a marker file via python, no external calls
        dummy_cmd = tmp / "dummyexe.cmd"
        dummy_cmd.write_text(
            f'@echo off\r\n"{sys.executable}" -c "import json,sys; open(r\'{out_marker}\', \'w\').write(json.dumps({{\'ran\':\'CMD_SHIM\',\'argv\':sys.argv[1:]}}))" %*\r\n',
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["PATH"] = str(tmp) + os.pathsep + env.get("PATH", "")

        # shutil.which resolution in this exact env
        import shutil
        which_result = shutil.which("dummyexe", path=str(tmp) + os.pathsep + os.environ.get("PATH", ""))
        results["shutil_which_dummyexe"] = which_result

        # The actual test: subprocess.run(["dummyexe", "probe-arg"], shell=False) with no extension given
        try:
            proc = subprocess.run(["dummyexe", "probe-arg-with-<angle>-and-\nnewline"],
                                   shell=False, env=env, capture_output=True, text=True, timeout=10)
            results["subprocess_run_rc"] = proc.returncode
            results["subprocess_run_stdout"] = proc.stdout
            results["subprocess_run_stderr"] = proc.stderr
            results["subprocess_run_raised"] = None
        except Exception as e:
            results["subprocess_run_rc"] = None
            results["subprocess_run_raised"] = f"{type(e).__module__}.{type(e).__name__}: {e}"
            results["winerror"] = getattr(e, "winerror", None)

        results["marker_file_written_by_cmd_shim"] = out_marker.exists()
        if out_marker.exists():
            results["marker_content"] = json.loads(out_marker.read_text(encoding="utf-8"))

        # --- MINIMAL FIX candidate: resolve via shutil.which() BEFORE spawning, then pass
        #     the resolved absolute path as argv[0] instead of the bare name. Still
        #     shell=False, still list-argv, protocol text still a single argv element. ---
        out_marker2 = tmp / "marker_fixed.json"
        dummy_cmd2 = tmp / "dummyexe.cmd"  # reuse same .cmd, just point its marker elsewhere
        dummy_cmd2.write_text(
            f'@echo off\r\n"{sys.executable}" -c "import json,sys; open(r\'{out_marker2}\', \'w\').write(json.dumps({{\'ran\':\'CMD_SHIM_VIA_FIX\',\'argv\':sys.argv[1:]}}))" %*\r\n',
            encoding="utf-8",
        )
        resolved = shutil.which("dummyexe", path=str(tmp) + os.pathsep + os.environ.get("PATH", ""))
        results["fix_resolved_path"] = resolved
        try:
            proc2 = subprocess.run([resolved, "probe-arg-with-<angle>-and-\nnewline"],
                                    shell=False, env=env, capture_output=True, text=True, timeout=10)
            results["fix_subprocess_run_rc"] = proc2.returncode
            results["fix_subprocess_run_raised"] = None
        except Exception as e:
            results["fix_subprocess_run_rc"] = None
            results["fix_subprocess_run_raised"] = f"{type(e).__module__}.{type(e).__name__}: {e}"
        results["fix_marker_written"] = out_marker2.exists()
        if out_marker2.exists():
            results["fix_marker_content"] = json.loads(out_marker2.read_text(encoding="utf-8"))
            # confirm the protocol-text-like arg survived intact (multiline + angle brackets)
            fixed_arg = results["fix_marker_content"]["argv"][0]
            results["fix_arg_exact_match"] = (fixed_arg == "probe-arg-with-<angle>-and-\nnewline")

    for k, v in results.items():
        print(f"{k}: {v}")

    # Which executable actually ran (if any)?
    if results.get("subprocess_run_raised"):
        conclusion = "FAILED: subprocess.run(shell=False) raised an exception resolving the bare name"
        root_cause_confirmed = True
    elif results.get("marker_file_written_by_cmd_shim"):
        conclusion = "SUCCEEDED: resolved to the .cmd sibling (PATHEXT-style resolution occurred)"
        root_cause_confirmed = False  # would mean executable-resolution is NOT the failure mode
    else:
        conclusion = "SUCCEEDED but ran the bare POSIX shim directly (unexpected on native Windows)"
        root_cause_confirmed = False

    fix_pass = (
        results.get("fix_subprocess_run_raised") is None
        and results.get("fix_marker_written") is True
        and results.get("fix_arg_exact_match") is True
    )
    results["FIX_VERIFICATION"] = "PASS" if fix_pass else "FAIL"

    print("CONCLUSION:", conclusion)
    print("FIX_VERIFICATION:", results["FIX_VERIFICATION"])

    eh.record_evidence(
        f"TASK D dummy executable-resolution reproduction: {json.dumps(results, ensure_ascii=False, default=str)}. "
        f"Conclusion: {conclusion}",
        "CONFIRMED",
        run_id=run_id,
        conn=conn,
    )
    eh.finalize_run(
        run_id, final_status="COMPLETED",
        validation_result=conclusion,
        conn=conn,
    )
    conn.commit()
    conn.close()
    return run_id, results, conclusion


if __name__ == "__main__":
    main()
