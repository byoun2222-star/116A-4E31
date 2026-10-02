# -*- coding: utf-8 -*-
"""
TASK E — harmless, local-only reproduction of the Windows Job Object breakaway mechanism
referenced by the embedded codex.exe string "host Job Object prevents daemon detachment;
start from a host that allows breakaway". Uses only a dummy child process and raw Win32
Job Object APIs via ctypes. Never touches Codex, cys, or any surface.
"""
import ctypes
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh  # noqa: E402

kernel32 = ctypes.windll.kernel32

JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_SUSPENDED = 0x00000004


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def make_job(allow_breakaway: bool):
    hjob = kernel32.CreateJobObjectW(None, None)
    if not hjob:
        raise OSError("CreateJobObjectW failed")
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    if allow_breakaway:
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_BREAKAWAY_OK
    ok = kernel32.SetInformationJobObject(
        hjob, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
    )
    if not ok:
        raise OSError(f"SetInformationJobObject failed: {ctypes.get_last_error()}")
    return hjob


def spawn_in_job(hjob, try_breakaway: bool, dummy_child_path, marker_path):
    creationflags = CREATE_SUSPENDED | (CREATE_BREAKAWAY_FROM_JOB if try_breakaway else 0)
    proc = subprocess.Popen(
        [sys.executable, str(dummy_child_path), str(marker_path)],
        creationflags=creationflags,
    )
    hproc = int(proc._handle)
    assigned = kernel32.AssignProcessToJobObject(hjob, hproc)
    assign_error = None if assigned else ctypes.get_last_error()
    kernel32.ResumeThread(int(proc._handle_thread) if hasattr(proc, "_handle_thread") else 0)
    # Python's Popen doesn't expose the suspended thread handle directly when using
    # CREATE_SUSPENDED via creationflags alone on some versions; fall back: if the process
    # wasn't actually suspended (older Python), it already ran. We just wait briefly.
    time.sleep(1.5)
    proc.poll()
    return proc, assigned, assign_error


def main():
    conn = eh.get_conn()
    run_id = eh.start_run(
        objective="TASK E: dummy-only reproduction of Windows Job Object breakaway restriction "
                   "(no Codex/cys/surface involved) to confirm the mechanism behind the embedded "
                   "codex.exe string 'host Job Object prevents daemon detachment'",
        actor="claude-session", provider="LOCAL",
        raw_command="python test_job_object_breakaway.py",
        conn=conn,
    )
    print("RUN_ID:", run_id)
    results = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_child = Path(tmpdir) / "dummy_child.py"
        dummy_child.write_text(
            "import sys, time\n"
            "open(sys.argv[1], 'w').write('alive')\n"
            "time.sleep(2)\n",
            encoding="utf-8",
        )

        # Case 1: job WITHOUT breakaway-ok, child tries CREATE_BREAKAWAY_FROM_JOB -> should FAIL
        marker1 = Path(tmpdir) / "marker1.txt"
        try:
            hjob_strict = make_job(allow_breakaway=False)
            try:
                proc = subprocess.Popen(
                    [sys.executable, str(dummy_child), str(marker1)],
                    creationflags=CREATE_BREAKAWAY_FROM_JOB,
                )
                proc.wait(timeout=5)
                results["case1_rc"] = proc.returncode
                results["case1_raised"] = None
            except OSError as e:
                results["case1_rc"] = None
                results["case1_raised"] = f"{type(e).__name__}: {e} (winerror={getattr(e,'winerror',None)})"
        finally:
            kernel32.CloseHandle(hjob_strict)
        results["case1_marker_written"] = marker1.exists()

        # Case 2: job WITH JOB_OBJECT_LIMIT_BREAKAWAY_OK, same breakaway attempt -> should SUCCEED
        marker2 = Path(tmpdir) / "marker2.txt"
        try:
            hjob_permissive = make_job(allow_breakaway=True)
            try:
                proc2 = subprocess.Popen(
                    [sys.executable, str(dummy_child), str(marker2)],
                    creationflags=CREATE_BREAKAWAY_FROM_JOB,
                )
                proc2.wait(timeout=5)
                results["case2_rc"] = proc2.returncode
                results["case2_raised"] = None
            except OSError as e:
                results["case2_rc"] = None
                results["case2_raised"] = f"{type(e).__name__}: {e} (winerror={getattr(e,'winerror',None)})"
        finally:
            kernel32.CloseHandle(hjob_permissive)
        results["case2_marker_written"] = marker2.exists()

    reproduced = (
        results.get("case1_raised") is not None or not results.get("case1_marker_written")
    ) and (
        results.get("case2_raised") is None and results.get("case2_marker_written")
    )
    results["MECHANISM_REPRODUCED"] = reproduced

    for k, v in results.items():
        print(f"{k}: {v}")
    print("MECHANISM_REPRODUCED:", reproduced)

    eh.record_evidence(
        f"TASK E dummy Job Object breakaway reproduction: {json.dumps(results, ensure_ascii=False, default=str)}",
        "CONFIRMED" if reproduced else "UNVERIFIED",
        run_id=run_id, conn=conn,
    )
    eh.finalize_run(run_id, final_status="COMPLETED",
                     validation_result=json.dumps(results, ensure_ascii=False, default=str), conn=conn)
    conn.commit()
    conn.close()
    return run_id, reproduced


if __name__ == "__main__":
    main()
