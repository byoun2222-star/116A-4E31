# -*- coding: utf-8 -*-
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

PROTOCOL_PATH = Path(r"C:\Users\a\.cys\pack\round\evidence\phase2b-bootstrap-submit\token_protocol_message.txt")
protocol_sha256 = hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest()

conn = eh.get_conn()
run_id = "run2b-a4b528cb1d3f4518"

eh.record_evidence(
    "surface:221 created via `cys launch-agent --role worker-4 --agent claude --cwd "
    "<MAF-PUBLISHING-POC>` (existing native CYS mechanism, no custom launcher). "
    "cys status --json: role=worker-4, agent=claude, agent_alive=true, exited=false, "
    "usage.source=statusline (real Claude session, session_file under ~/.cys/claude/projects/...).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "launch-agent's OWN default CYSJavis directive injection (separate from this Phase2B test) "
    "was observed completing first: screen showed 'running UserPromptSubmit hooks... 0/2' then "
    "'OK -- 각성 완료 · 브리프 대기' (awakening complete, waiting for brief), idle_secs returning "
    "to nonzero (16s) before this test's own payload was sent -- confirms CLAUDE READY state was "
    "correctly waited for rather than racing an in-flight CYSJavis boot sequence.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    f"PROTOCOL INSTALL PAYLOAD: reused the EXISTING Codex Protocol V1 file verbatim (same "
    f"semantics required by owner), sha256={protocol_sha256} (identical to the Codex baseline "
    f"hash -- no new artifact needed since content is unchanged, only the delivery CHANNEL "
    f"differs). Delivered via the Claude-native PTY injection path confirmed in discovery "
    f"(run2b-83573a3ad72b4d1b): `cys send --surface surface:221 <full text>` (Python subprocess "
    f"list-argv, not bash, to avoid quoting risk) + `cys send-key --surface surface:221 Return`, "
    f"EXACTLY ONCE. NOT delivered via Codex's startup-argv method -- no custom launcher was used.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "ACK EXACT MATCH CONFIRMED via cys read-screen: screen shows "
    "'SHORT TOKEN PROTOCOL: UNDERSTOOD' followed by 'RUN TOKEN EXECUTED: NO' "
    "(bullet-prefixed chat message, 'Brewed for 13s · done 2:25 PM' timestamp line separate from "
    "the ACK text itself), then returned to idle ready prompt. No task was executed -- Claude "
    "followed the protocol's explicit 'Do NOT execute any task now' instruction.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "TARGET POLICY (live, surface alive): check_target_policy('worker-4','CLAUDE', "
    "'phase2b-nonexistent-probe-task') -- role/production/provider-agent-match/surface-alive/"
    "surface-not-busy gates ALL passed; denied only at the final DB task-existence gate (expected, "
    "no task created). TARGET POLICY: NOT FULLY EVALUABLE WITHOUT TASK -- EXPECTED GATE.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Isolation confirmed: surface:219 (exited=False, agent_alive=True) and surface:220 "
    "(exited=False, agent_alive=True) both untouched throughout this entire Claude validation -- "
    "no input/send/send-key/close/reap/kill issued to either. Frozen contract hashes and Codex "
    "baseline (Protocol V1 hash, model=gpt-6-sol, allowlist) re-verified unchanged.",
    "CONFIRMED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id,
    final_status="COMPLETED",
    process_evidence={
        "surface_ref": "surface:221",
        "ack_text": "SHORT TOKEN PROTOCOL: UNDERSTOOD\nRUN TOKEN EXECUTED: NO",
        "protocol_payload_sha256": protocol_sha256,
        "surface_219_untouched": True,
        "surface_220_untouched": True,
    },
    validation_result="PASS -- role/agent/claude-alive/ready/protocol-delivery/ack-exact-match "
                       "all CONFIRMED by direct screen evidence; no task executed; no RUN TOKEN "
                       "sent; input count = 1 (single send + single send-key).",
    conn=conn,
)
conn.commit()
print("기록 완료, protocol_sha256:", protocol_sha256)
conn.close()
