# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

conn = eh.get_conn()
run_id = "run2b-ea813726dde34ae4"

eh.record_evidence(
    "surface:222 created via `cys launch-agent --role worker-8 --agent gemini --cwd "
    "<MAF-PUBLISHING-POC>` (existing native CYS mechanism, no custom launcher). "
    "cys status --json: role=worker-8, agent=gemini, agent_alive=true, exited=false, "
    "idle_secs=23 at check time.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "cys read-screen on surface:222 shows the actual booted CLI banner: 'Antigravity CLI 1', an "
    "already-authenticated account identifier ('broughdeepshikha@...'), model line "
    "'Gemini 3.8 Flash', cwd '~/install-jarvis/...', and the ready_marker '? for shortcuts' "
    "visible at the bottom exactly as declared in agents.json. NO OAuth/trust/permission gate "
    "appeared at any point -- the session reached its interactive prompt directly, meaning "
    "authentication was already established from a prior login (persisted auth state), not "
    "created or approved by this investigation.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Per owner instruction (STOP on any human-judgment gate): no such gate was encountered, so "
    "no stop/report-to-owner branch was triggered -- this is reported as an observed fact "
    "(gate absent), not an assumption.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Protocol V1 file re-hashed: sha256=987f45d3bea0648fd6c657c57d17e7c71e9065ac79e9ed675fb31608"
    "f43e4572 -- UNCHANGED from the Codex/Claude baseline. NOT sent to surface:222 this round "
    "(explicitly out of scope per owner's closing line reserving actual task E2E / protocol "
    "install+ACK for a separate future step).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "PTY delivery path applicability assessed structurally (not executed): surface:222 presents "
    "a standard interactive text prompt ('>') identical in category to Claude's prompt -- the "
    "same `cys send`/`cys send-key` mechanism already proven for Codex (surface:220) and Claude "
    "(surface:221) is structurally applicable here too (same CYS surface/PTY primitives, no "
    "Gemini/agy-specific blocker observed in the banner or prompt state). This is an assessment "
    "of compatibility, not a live transmission test.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Isolation confirmed: surface:219/220/221 (exited=False, agent_alive=True for all three) "
    "untouched throughout. Frozen contract, Protocol V1, allowlist ({worker-4,5,6,8,10}), DB "
    "schema all re-verified unchanged. No automatic retry, no second surface, no daemon restart.",
    "CONFIRMED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id,
    final_status="COMPLETED",
    process_evidence={
        "surface_ref": "surface:222",
        "cli_banner": "Antigravity CLI 1, model=Gemini 3.8 Flash, already authenticated",
        "ready_marker_observed": "? for shortcuts",
        "oauth_or_trust_gate_encountered": False,
        "protocol_sent": False,
        "surfaces_untouched": ["surface:219", "surface:220", "surface:221"],
    },
    validation_result="Startup validation PASS: role/agent/alive/ready all CONFIRMED by direct "
                       "screen+status evidence. No auth/trust gate encountered (already logged "
                       "in). Protocol V1 hash unchanged and NOT transmitted this round (reserved "
                       "for a separate future step per owner scope).",
    conn=conn,
)
conn.commit()
print("기록 완료")
conn.close()
