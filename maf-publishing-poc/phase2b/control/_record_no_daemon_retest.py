# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

conn = eh.get_conn()
run_id = "run2b-57d497ebf49d4c43"

eh.record_evidence(
    "surface:219 created successfully (role=worker-10, agent=codex). cys status --json snapshot: "
    "agent_alive=true, exited=false, seat=occupied, alt_screen=true, line_count=194, PID=23820. "
    "Surface remained alive long enough to read its screen and inspect its OS process tree "
    "(unlike run2b-c30db2faa87c444b and run2b-f6cb01319e02447f, both of which died before this "
    "point was reached).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "JOB OBJECT ERROR DID NOT RECUR: cys read-screen on surface:219 shows no 'Job Object' / "
    "'breakaway' / 'daemon detachment' text anywhere -- the --no-daemon flag confirmed to avoid "
    "the shared app-server daemon launch-probe code path that caused run2b-f6cb01319e02447f's "
    "failure.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "PROTOCOL DELIVERY ESTABLISHED via TWO INDEPENDENT evidence sources: "
    "(1) cys read-screen on surface:219 shows the Protocol V1 text rendered verbatim inside "
    "Codex's TUI (items 6-10 and the closing 'Reply with EXACTLY these two lines' instruction "
    "visible on screen). "
    "(2) OS-level process inspection (Get-CimInstance Win32_Process on PID 34904, the node.exe "
    "child of the launcher's python.exe PID 13612, itself a child of the surface's PowerShell "
    "host PID 23820) shows the FULL CommandLine: "
    "'node.exe codex.js --no-daemon \"[PHASE2B-SHORT-TOKEN-PROTOCOL-V1] ... SHORT TOKEN "
    "PROTOCOL: UNDERSTOOD\\nRUN TOKEN EXECUTED: NO\"' -- the entire Protocol V1 text (including "
    "literal multiline structure and <TOKEN> angle brackets) present as a single argv element "
    "at the actual OS process-table level, the strongest class of evidence available. This is "
    "the first time in this investigation that PROTOCOL DELIVERY has been established by "
    "process-level evidence rather than only inferred from screen text.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "ACK NOT ACHIEVED: Codex did not reply with the expected ACK. Instead, surface:219's screen "
    "shows Codex's own API call failed immediately after receiving the protocol as its initial "
    "prompt: {\"type\":\"error\",\"status\":400,\"error\":{\"type\":\"invalid_request_error\","
    "\"message\":\"The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT "
    "account.\"}}. This is a Codex account/model-configuration issue, unrelated to the launcher, "
    "node.exe/codex.js invocation, quoting/argv transport, or Job Object/daemon mechanics -- all "
    "of which are now confirmed working correctly up to this point. The TUI remained alive and "
    "interactive afterward ('Ask Codex to do anything' prompt visible), but no ACK text was "
    "ever produced.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "TARGET POLICY (live, surface alive): check_target_policy('worker-10','CODEX', "
    "'phase2b-nonexistent-probe-task') evaluated against the real live surface -- role/"
    "production/provider-agent-match/surface-alive/surface-not-busy gates ALL passed; denied "
    "only at the final DB task-existence gate ('task_id ... does not exist in Phase 2B DB or is "
    "already COMPLETED'), exactly the expected/deliberate denial per owner instruction (no task "
    "created). TARGET POLICY: NOT FULLY EVALUABLE WITHOUT TASK -- EXPECTED GATE.",
    "CONFIRMED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id,
    final_status="FAILED",
    stop_reason="Launcher/node.exe/codex.js/--no-daemon chain fully succeeded (Job Object error "
                "did not recur; protocol delivery confirmed at both screen and OS process-table "
                "level) but Codex itself returned a 400 invalid_request_error for its configured "
                "model ('gpt-6.1-sol' unsupported for this ChatGPT account), so no ACK was ever "
                "produced. ACK EXACT MATCH criterion not met -> overall startup PASS not granted "
                "per owner's strict all-or-nothing rule. No second surface created, no retry, no "
                "live fix attempted.",
    process_evidence={
        "surface_ref": "surface:219",
        "pid_chain": {"powershell_host": 23820, "launcher_python": 13612, "node_codex": 34904},
        "status_snapshot": {"role": "worker-10", "agent": "codex", "agent_alive": True,
                             "exited": False, "seat": "occupied", "line_count": 194},
        "codex_error": {"type": "error", "status": 400,
                         "error": {"type": "invalid_request_error",
                                   "message": "The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account."}},
    },
    validation_result="PARTIAL: ROLE/AGENT/ALIVE/NO-DAEMON/PROTOCOL-HASH/PROTOCOL-DELIVERY all CONFIRMED; "
                       "ACK EXACT MATCH = NOT ACHIEVED (Codex model-config error, unrelated to transport/launcher)",
    conn=conn,
)
conn.commit()
print("기록 완료, run_id:", run_id)
conn.close()
