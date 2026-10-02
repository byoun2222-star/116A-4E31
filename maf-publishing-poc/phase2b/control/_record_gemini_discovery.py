# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

conn = eh.get_conn()
run_id = eh.start_run(
    objective="Gemini (Antigravity/agy) adapter discovery & local validation against "
              "PHASE2B-PROVIDER-CONTRACT-V1 (FROZEN). Read-only discovery + local deterministic "
              "tests only, zero AI/provider calls.",
    actor="claude-session", provider="LOCAL",
    raw_command="read-only agents.json/CLI --help inspection + test_2b_d_gemini_adapter_discovery.py",
    conn=conn,
)
print("RUN_ID:", run_id)

eh.record_evidence(
    "CRITICAL DISCOVERY: the 'gemini' key in CYS agents.json is NOT the original Gemini CLI -- "
    "it is 'Antigravity CLI (agy)'. agents.json's own notes field states the original Gemini CLI "
    "was discontinued for consumer tiers (free/AI Pro/Ultra) on 2026-06-18 and migrated "
    "(measured 2026-06-13); the key name 'gemini' is retained only for role/orchestration "
    "compatibility (reviewer-gemini, orchestra check, boot PLAN contract), not because the "
    "underlying CLI is still Gemini-branded.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "GEMINI CLI (agy.exe) discovered: path=C:\\Users\\a\\AppData\\Local\\agy\\bin\\agy.exe "
    "(confirmed via `which agy` matching agents.json exactly), version=1.2.3 (via `agy --version`, "
    "a local metadata query, not a live invocation). `agy --help` confirms --model is an OPTIONAL "
    "CLI flag (not mandatory, not set in agents.json's cmd -- same pattern as Claude, unlike "
    "Codex's mandatory config.toml model). Also discovered agy natively supports "
    "--prompt/--prompt-interactive (an argv-based initial-prompt mechanism similar to Codex's "
    "[PROMPT] positional arg) -- but this is NOT what the existing CYS agents.json config uses.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "CYS native Gemini agent config (agents.json -> 'gemini'): cmd='<agy.exe path> "
    "--dangerously-skip-permissions' (no --model). ready_marker='? for shortcuts' "
    "(different glyph from both Codex and Claude). inject_delay_secs=12. approval_patterns has "
    "one 'approve' pattern (Approve|Allow|Yes, proceed). NO first_run_gates block exists "
    "(unlike Claude's detailed gates[] structure) -- login is documented as human-only (Google "
    "OAuth, first-boot screen guidance) but without a structured/automated gate corpus.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "AUTH MODE: Google OAuth, explicitly human-only per agents.json notes (same category as "
    "Claude's OAuth constraint). No API-key-based auth found. No local CLI-specific config/cache "
    "directory discovered separate from the Antigravity IDE's own Electron app data "
    "(AppData/Roaming/Antigravity) -- the CLI's own auth storage was not located this round "
    "(searched ~/.antigravity-ide, AppData/Local/agy, AppData/Roaming for agy-named dirs; found "
    "none beyond the IDE's unrelated app_storage.json/Cache/etc).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "STARTUP MECHANISM: per owner instruction C (prefer existing native integration over copying "
    "Codex/Claude), the EXISTING CYS config uses the SAME PTY-injection pattern as Claude "
    "(ready_marker + inject_delay_secs), NOT argv-based delivery -- even though agy.exe itself "
    "natively supports an argv prompt mechanism (--prompt-interactive), CYS's current config does "
    "not use it. PROTOCOL INSTALL DESIGN (proposed, NOT sent to any Gemini/agy process): reuse "
    "the identical Protocol V1 file content (same semantics, same hash) delivered via the "
    "existing ready_marker-gated send+send-key path, mirroring the Claude adapter exactly -- no "
    "new artifact needed.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "CONTRACT COMPATIBILITY for Gemini (local evidence, no guessing): RUN <TOKEN>/manifest "
    "lookup/task SHA/path scope/canonical JSON read/UTF-8/.tmp->final/JSON-only result/"
    "deterministic validation/idempotency/retry=0/target policy/DB provenance = all SUPPORTED "
    "(verified live this round: check_target_policy and record_run_started both called with "
    "provider=GEMINI successfully, full provenance stored, fixture cleaned up). Protocol "
    "*delivery mechanism* = GEMINI-SPECIFIC ADAPTER REQUIRED (ready_marker='? for shortcuts' + "
    "PTY injection, distinct glyph/timing from Claude but same category of mechanism).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "PROVENANCE PATH: result_collector.record_run_started()/record_run_completed(), identical "
    "design to Codex/Claude. Verified live with provider=GEMINI this round (dry fixture row "
    "correctly stored surface_id/agent_role, then cleaned up, zero residue). NO DB schema change "
    "required.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "CURRENT ALLOWLIST (re-read from source, not assumed): {worker-4, worker-5, worker-6, "
    "worker-8, worker-10}. Live occupancy: worker-4=surface:221(claude), worker-6=surface:220"
    "(codex), worker-10=surface:219(codex) -- all preserved evidence surfaces, excluded as "
    "candidates. worker-5: 0 provider_run DB rows but carries the surface:54 incident narrative "
    "from the original Phase2B checkpoint. worker-8: 4 CLEAN COMPLETED Codex provider_run rows "
    "(no incident), no live surface. FUTURE TEST ROLE CANDIDATE: worker-8 -- already allowlisted, "
    "no live surface, clean (non-incident) history, no allowlist change required. worker-5 "
    "considered and not selected due to its incident association.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Local deterministic tests (test_2b_d_gemini_adapter_discovery.py): 16/16 PASS, zero AI/"
    "provider calls. Covers: provider=GEMINI contract representation, GEMINI->gemini agent "
    "mapping, provider-generic target-policy denial, task/token compatibility, provenance writer "
    "compatibility, Gemini startup profile structure (including absence of first_run_gates vs "
    "Claude), zero Codex-specific marker leakage, frozen contract hash unchanged. Test fixture "
    "cleaned up, zero residue confirmed.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Regression re-check (no Codex/Claude/Gemini execution): Protocol V1 sha256 unchanged "
    "(987f45d3...), config.toml model unchanged (gpt-6-sol), allowlist unchanged, surface:219/"
    "220/221 all still alive and untouched (exited=False, agent_alive=True for all three).",
    "CONFIRMED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id, final_status="COMPLETED",
    output_artifacts=[str(Path(__file__).resolve().parent.parent / "tests" / "test_2b_d_gemini_adapter_discovery.py")],
    validation_result="16/16 local tests PASS; Gemini(agy)'s existing native CYS integration "
                       "fully satisfies the frozen provider-neutral contract except for the "
                       "protocol delivery mechanism (adapter-level difference only, proposed not "
                       "implemented); zero AI provider calls; contract/baseline unchanged; "
                       "surface:219/220/221 untouched. Key finding: 'gemini' role now runs "
                       "Antigravity CLI (agy), not the original Gemini CLI (discontinued for "
                       "consumer tiers 2026-06-18).",
    db_changes={"tables_created": [], "existing_tables_modified": [],
                "note": "one test fixture row created and deleted; no production data touched"},
    conn=conn,
)
conn.commit()
print("기록 완료")
conn.close()
