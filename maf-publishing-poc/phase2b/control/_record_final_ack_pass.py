# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

conn = eh.get_conn()
run_id = "run2b-98c6b20ac93d4003"

eh.record_evidence(
    "surface:220 created successfully: role=worker-6, agent=codex, exited=False, agent_alive=True, "
    "seat=occupied, alt_screen=true. CRITICALLY, cys status --json shows a populated 'usage' field "
    "(ctx_tokens=17437, ctx_window=258400, session_file path under ~/.codex/sessions/...) -- real "
    "token consumption, meaning Codex's model API call actually SUCCEEDED this time (surface:219 "
    "never had a usage field populated at any point, consistent with its immediate 400 error before "
    "any tokens were consumed).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "ACK EXACT MATCH CONFIRMED via cys read-screen on surface:220: screen shows "
    "'SHORT TOKEN PROTOCOL: UNDERSTOOD' followed by 'RUN TOKEN EXECUTED: NO' (timestamped 1:49 PM), "
    "exactly matching the two required lines verbatim. The TUI returned to its ready prompt "
    "('Ask Co[dex]...') afterward, and the status bar shows the new model active (GPT-6-... visible, "
    "truncated).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "PROTOCOL DELIVERY ESTABLISHED via OS process-table evidence (strongest evidence class): "
    "Get-CimInstance Win32_Process on PID 47752 (node.exe, grandchild of the surface's PowerShell "
    "host PID 29004 -> launcher python.exe PID 41832) shows the FULL CommandLine: "
    "'node.exe codex.js --no-daemon \"[PHASE2B-SHORT-TOKEN-PROTOCOL-V1] ... SHORT TOKEN PROTOCOL: "
    "UNDERSTOOD\\nRUN TOKEN EXECUTED: NO\"' -- the entire Protocol V1 text (multiline, <TOKEN> angle "
    "brackets intact) as a single argv element. No WinError 2, no Job Object/breakaway error "
    "anywhere in the screen or process evidence.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "TARGET POLICY (live, surface alive): check_target_policy('worker-6','CODEX', "
    "'phase2b-nonexistent-probe-task') -- role/production/provider-agent-match/surface-alive/"
    "surface-not-busy gates ALL passed; denied only at the final DB task-existence gate (expected, "
    "no task created). TARGET POLICY: NOT FULLY EVALUABLE WITHOUT TASK -- EXPECTED GATE.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "surface:219 confirmed UNTOUCHED throughout this entire retest: exited=False, agent_alive=True, "
    "no input/send/send-key/close/reap/kill issued to it at any point during this run. Fully "
    "isolated from the worker-6 test as required.",
    "CONFIRMED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id,
    final_status="COMPLETED",
    process_evidence={
        "surface_ref": "surface:220",
        "pid_chain": {"powershell_host": 29004, "launcher_python": 41832, "node_codex": 47752},
        "ack_text": "SHORT TOKEN PROTOCOL: UNDERSTOOD\nRUN TOKEN EXECUTED: NO",
        "usage": {"ctx_tokens": 17437, "ctx_window": 258400},
        "surface_219_untouched": True,
    },
    validation_result="PASS -- all required evidence confirmed: role/agent/model/alive/no-daemon/"
                       "protocol-hash/protocol-delivery/ack-exact-match all CONFIRMED by direct "
                       "evidence (screen + OS process table + cys status usage field).",
    conn=conn,
)
conn.commit()
print("기록 완료, run_id:", run_id)
conn.close()
