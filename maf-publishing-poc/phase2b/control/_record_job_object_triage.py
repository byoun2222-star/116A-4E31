# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

conn = eh.get_conn()
run_id = eh.start_run(
    objective="Job Object breakaway blocker triage (Task A-G): locate error source, inspect "
              "Codex startup/daemon-detach architecture, inspect cys Job Object ownership "
              "(read-only), classify fix safety, attempt dummy reproduction",
    actor="claude-session", provider="LOCAL",
    raw_command="read-only file/help inspection + dummy ctypes reproduction, no surface/Codex execution",
    conn=conn,
)
print("RUN_ID:", run_id)

eh.record_evidence(
    "ERROR SOURCE CONFIRMED: exact string \"host Job Object prevents daemon detachment; start "
    "from a host that allows breakaway\" found embedded (via binary grep) inside the Codex "
    "NATIVE vendor binary itself: "
    r"C:\Users\a\AppData\Local\cys-npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe"
    ". Surrounding embedded strings confirm context: \"cannot launch detached daemon; existing "
    "daemon was not stopped\", \"failed to verify daemon launch capability\", [THIS STRING], "
    "\"failed to terminate suspended launch probe\", \"failed to reap suspended launch probe\", "
    "\"failed to wait for daemon process\", \"failed to verify daemon detachment\". This is "
    "Codex's own shared app-server daemon launch-probe logic: it spawns a suspended/detached "
    "candidate daemon process and verifies it can actually escape the current process's Job "
    "Object before adopting it as the real shared daemon; our surface process tree's Job Object "
    "does not permit that escape.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "codex.js (the npm shim entrypoint, read in full) contains NO daemon/detach logic itself -- "
    "it only resolves and spawn()s the native codex.exe binary with stdio inherit, forwarding "
    "signals. All daemon-launch-probe logic lives inside the native codex.exe binary (compiled "
    "Rust, not source-inspectable on this machine).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "CODEX FOREGROUND/NO-DETACH MODE: CONFIRMED via local codex --help output: a documented "
    "--no-daemon flag exists -- Run without the shared background server, even if it is already "
    "running. This is the officially supported mechanism to avoid the entire daemon-detachment "
    "code path (Task F priority 1). Not yet tested live (no Codex execution performed this "
    "session).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "CYS Job Object ownership: UNVERIFIED -- cys.exe is a closed-source compiled binary (no .rs "
    "source on this machine, confirmed in earlier investigation rounds). cys --help and cys "
    "new-surface --help contain NO job/detach/breakaway/containment-related flags or "
    "documentation. Cannot confirm from local evidence whether cys itself creates a Job Object "
    "for surface process trees, whether breakaway is currently allowed, or whether any "
    "documented switch exists to change this.",
    "UNVERIFIED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "TASK E dummy Job Object reproduction (run2b-bc9851852e1447b8): attempted using raw ctypes "
    "Win32 Job Object APIs (CreateJobObjectW/SetInformationJobObject/AssignProcessToJobObject) "
    "with a harmless dummy child script, no Codex/cys/surface involved. Both the strict (no "
    "breakaway) and permissive (JOB_OBJECT_LIMIT_BREAKAWAY_OK) cases immediately hit "
    "PermissionError: [WinError 5] Access is denied on CREATE_BREAKAWAY_FROM_JOB, before "
    "reaching the intended comparison. Mechanism NOT cleanly reproduced -- inconclusive, "
    "possibly because the current shell process is itself already confined in a restrictive job "
    "object (tangential, unconfirmed support for the broader hypothesis) or due to a privilege "
    "requirement in the ctypes reproduction itself. Not pursued further per owner instruction "
    "(do not force reproduction).",
    "UNVERIFIED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "SAFETY CLASSIFICATION of candidate fixes: "
    "(1) Codex --no-daemon flag = NO SECURITY/CONTAINMENT CHANGE (purely a Codex CLI argument, "
    "changes nothing about cys or OS containment). "
    "(2) CREATE_BREAKAWAY_FROM_JOB on the child spawn inside phase2b_startup_launcher.py = LOCAL "
    "CHILD-ONLY CHANGE (affects only this one spawned process tree, does not alter cys's job "
    "object policy for any other surface). "
    "(3) Modifying cys's own Job Object to add JOB_OBJECT_LIMIT_BREAKAWAY_OK = CYS SURFACE "
    "CONTAINMENT CHANGE (affects ALL surfaces process cleanup/containment guarantees) -- NOT "
    "implemented, requires separate owner approval per instruction, and is deprioritized below "
    "options (1) and (2) per Task F ordering.",
    "CONFIRMED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id, final_status="COMPLETED",
    validation_result="Root cause CONFIRMED (error string located in codex.exe). Priority-1 fix "
                       "(--no-daemon) CONFIRMED available via local --help. CYS job object "
                       "ownership UNVERIFIED (closed source). Dummy OS-level reproduction "
                       "inconclusive (WinError 5, not pursued further).",
    conn=conn,
)
conn.commit()
print("기록 완료")
conn.close()
