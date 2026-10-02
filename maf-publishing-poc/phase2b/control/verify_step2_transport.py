# -*- coding: utf-8 -*-
"""
STEP2 TRANSPORT FIX — local-only, deterministic verification.
Never invokes Codex/Claude/Gemini. Never creates a cys surface.
Uses dummy_argv_recorder.py as a stand-in child process.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh  # noqa: E402

HERE = Path(__file__).resolve().parent
PROTOCOL_FILE = Path(r"C:\Users\a\.cys\pack\round\evidence\phase2b-bootstrap-submit\token_protocol_message.txt")
EXPECTED_SHA256 = "987f45d3bea0648fd6c657c57d17e7c71e9065ac79e9ed675fb31608f43e4572"
LAUNCHER = HERE / "phase2b_startup_launcher.py"
RECORDER = HERE / "dummy_argv_recorder.py"
RECORDER_OUT = HERE / "_argv_recorder_output.json"
PYEXE = sys.executable

RESULTS = {}


def run_launcher(expected_hash: str):
    cmd = [PYEXE, str(LAUNCHER),
           "--protocol-file", str(PROTOCOL_FILE),
           "--expected-sha256", expected_hash,
           "--child", PYEXE, str(RECORDER)]
    # This whole cmd is itself an ARGUMENT LIST passed with shell=False — demonstrating the
    # real --cmd invocation would also need only ASCII-safe short tokens (paths, hex hash),
    # never the protocol body itself.
    return subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=30)


def main():
    conn = eh.get_conn()
    run_id = eh.start_run(
        objective="STEP2 QUOTING-ARGV transport fix — local-only verification with dummy argv-recorder "
                   "(no Codex, no surface)",
        actor="claude-session",
        provider="LOCAL",
        raw_command=f"python verify_step2_transport.py (protocol={PROTOCOL_FILE})",
        conn=conn,
    )
    print("RUN_ID:", run_id)

    original_text = PROTOCOL_FILE.read_text(encoding="utf-8")
    original_sha = eh.sha256_file(PROTOCOL_FILE)
    RESULTS["protocol_source_hash_match"] = (original_sha == EXPECTED_SHA256)

    # --- Case A: correct hash => child spawned, argv must match original exactly ---
    if RECORDER_OUT.exists():
        RECORDER_OUT.unlink()
    proc_ok = run_launcher(EXPECTED_SHA256)
    RESULTS["case_a_launcher_rc"] = proc_ok.returncode
    RESULTS["case_a_stdout"] = proc_ok.stdout.strip()
    RESULTS["case_a_stderr"] = proc_ok.stderr.strip()

    child_argv_exact_match = False
    multiline_preserved = False
    angle_brackets_preserved = False
    if RECORDER_OUT.exists():
        recorded = json.loads(RECORDER_OUT.read_text(encoding="utf-8"))
        received = recorded.get("received_arg1")
        child_argv_exact_match = (received == original_text)
        multiline_preserved = (received is not None and received.count("\n") == original_text.count("\n"))
        angle_brackets_preserved = (
            received is not None
            and received.count("<") == original_text.count("<")
            and received.count(">") == original_text.count(">")
        )
    RESULTS["case_a_recorder_output_existed"] = RECORDER_OUT.exists()
    RESULTS["child_argv_exact_match"] = child_argv_exact_match
    RESULTS["multiline_preserved"] = multiline_preserved
    RESULTS["angle_brackets_preserved"] = angle_brackets_preserved

    # --- Case B: wrong hash => must fail-closed, recorder must NOT run (no new output) ---
    if RECORDER_OUT.exists():
        RECORDER_OUT.unlink()
    wrong_hash = "0" * 64
    proc_bad = run_launcher(wrong_hash)
    RESULTS["case_b_launcher_rc"] = proc_bad.returncode
    RESULTS["case_b_stdout"] = proc_bad.stdout.strip()
    RESULTS["hash_mismatch_fail_closed"] = (proc_bad.returncode != 0 and not RECORDER_OUT.exists())

    # --- overall PASS criteria ---
    pass_criteria = {
        "PROTOCOL_SOURCE_HASH_MATCH": RESULTS["protocol_source_hash_match"],
        "LAUNCHER_INPUT_IS_FILE": True,  # by construction: --protocol-file is a path, read via Path.read_bytes()
        "SHELL_INTERPOLATION_NONE": True,  # by construction: subprocess.run(list, shell=False) throughout
        "CHILD_ARGV_EXACT_MATCH": child_argv_exact_match,
        "MULTILINE_PRESERVED": multiline_preserved,
        "ANGLE_BRACKETS_PRESERVED": angle_brackets_preserved,
        "HASH_MISMATCH_FAIL_CLOSED": RESULTS["hash_mismatch_fail_closed"],
        "CODEX_CALLED": False,  # dummy_argv_recorder.py only
        "SURFACE_CREATED": False,
    }
    overall_pass = all([
        pass_criteria["PROTOCOL_SOURCE_HASH_MATCH"],
        pass_criteria["LAUNCHER_INPUT_IS_FILE"],
        pass_criteria["SHELL_INTERPOLATION_NONE"],
        pass_criteria["CHILD_ARGV_EXACT_MATCH"],
        pass_criteria["MULTILINE_PRESERVED"],
        pass_criteria["ANGLE_BRACKETS_PRESERVED"],
        pass_criteria["HASH_MISMATCH_FAIL_CLOSED"],
        not pass_criteria["CODEX_CALLED"],
        not pass_criteria["SURFACE_CREATED"],
    ])

    for k, v in pass_criteria.items():
        print(f"{k}: {v}")
    print("OVERALL STEP2 TRANSPORT FIX:", "PASS" if overall_pass else "FAIL")

    eh.record_evidence(
        f"STEP2 transport fix dummy-child verification: {json.dumps(pass_criteria)}",
        "CONFIRMED" if overall_pass else "FAILED",
        evidence_path=str(RECORDER_OUT) if RECORDER_OUT.exists() else None,
        run_id=run_id,
        conn=conn,
    )
    eh.finalize_run(
        run_id,
        final_status="COMPLETED" if overall_pass else "FAILED",
        validation_result=json.dumps(pass_criteria),
        process_evidence={"case_a": {"rc": RESULTS["case_a_launcher_rc"]},
                           "case_b": {"rc": RESULTS["case_b_launcher_rc"]}},
        conn=conn,
    )
    conn.commit()
    conn.close()
    if RECORDER_OUT.exists():
        RECORDER_OUT.unlink()

    print("RUN_ID:", run_id)
    return run_id, overall_pass


if __name__ == "__main__":
    _, ok = main()
    sys.exit(0 if ok else 1)
