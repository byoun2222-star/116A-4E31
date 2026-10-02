# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

conn = eh.get_conn()
run_id = eh.start_run(
    objective="Claude adapter discovery & local validation against PHASE2B-PROVIDER-CONTRACT-V1 "
              "(FROZEN). Read-only discovery + local deterministic tests only, zero AI/provider calls.",
    actor="claude-session", provider="LOCAL",
    raw_command="read-only agents.json/CLI inspection + test_2b_c_claude_adapter_discovery.py",
    conn=conn,
)
print("RUN_ID:", run_id)

eh.record_evidence(
    "Claude CLI discovered: path=/c/Users/a/.local/bin/claude, version=2.1.287 (Claude Code). "
    "No Claude process was executed -- `claude --version` is a local metadata query, not a live "
    "agent invocation.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "CYS native Claude agent config (~/.cys/pack/agents.json -> 'claude'): cmd='claude "
    "--dangerously-skip-permissions' (no --model flag -- model selection is NOT mandatory, unlike "
    "Codex's config.toml). env.CLAUDE_CONFIG_DIR isolates auth per cys account. ready_marker='-' "
    "(the prompt glyph) gates when launch-agent injects its directive. inject_delay_secs=10. "
    "approval_patterns already auto-handle tool-permission/trust-prompt dialogs. first_run_gates "
    "already handles theme/login/OAuth/folder-trust/disclaimer (login/OAuth explicitly human_only, "
    "a known pre-existing constraint, not newly discovered here).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "STARTUP MECHANISM confirmed structurally different from Codex: Claude's existing native "
    "launch-agent flow is spawn -> wait for ready_marker on screen -> INJECT directive text via "
    "the existing send+send-key mechanism (PTY post-boot text injection) -- NOT a startup-argv "
    "delivery like Codex's node.exe/codex.js/Protocol-V1-as-argv design. This means NO new custom "
    "launcher script is needed for Claude (unlike phase2b_startup_launcher.py which was built from "
    "scratch for Codex) -- the existing cys launch-agent mechanism already satisfies the delivery "
    "need.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "AUTH MODE: OAuth/subscription-based, credentials stored in a config-dir-keyed "
    ".credentials.json (Windows) -- confirmed via agents.json's own documented notes field, not "
    "inferred. No API-key or model-name field required anywhere in the Claude agent definition.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "CLAUDE STARTUP PROFILE V1 (proposed, NOT implemented, NOT sent to any Claude process): "
    "CYS -> `cys launch-agent --role <role> --agent claude` (existing native mechanism, reused "
    "as-is) -> wait for ready_marker '-' (existing) -> inject Protocol V1's TEXT SEMANTICS "
    "(same meaning: install short-token protocol, require exact 2-line ACK) via the existing "
    "send+send-key injection path, NOT via startup argv. The original Codex Protocol V1 file "
    "itself is NOT modified -- Claude would receive the same semantic content through its own "
    "already-proven delivery channel. RUN <TOKEN> control-plane send is unchanged/provider-generic "
    "(plain cys send/send-key, already confirmed provider-agnostic from Codex's working path).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "CONTRACT COMPATIBILITY classification for Claude (local evidence, no guessing): RUN <TOKEN> "
    "= SUPPORTED (generic cys send, provider-agnostic). manifest lookup/task SHA verification/"
    "canonical JSON task read/UTF-8/result .tmp->final/JSON-only result/deterministic validator/"
    "idempotency/retry=0 = SUPPORTED (all providers read the same file-based mechanisms; nothing "
    "in these is Codex-specific). target policy = SUPPORTED (check_target_policy is already "
    "provider-generic, verified live with provider=CLAUDE this round). completion/DB provenance = "
    "SUPPORTED via result_collector.record_run_started (verified live with provider=CLAUDE, full "
    "surface_id/agent_role stored). Protocol *delivery mechanism* = CLAUDE-SPECIFIC ADAPTER "
    "REQUIRED (ready_marker+inject, not startup argv) -- this is the only adapter-level difference "
    "needed; the contract's semantic content is unchanged.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "PROVENANCE PATH for future Claude runs: result_collector.record_run_started()/"
    "record_run_completed(), same as the fix already proposed for Codex in run2b-048f11bf5ab64d0b "
    "-- verified live this round (dry fixture row with provider=CLAUDE correctly stored surface_id/"
    "agent_role, then cleaned up; zero residue confirmed in provider_run table). NO DB schema "
    "change required (columns already exist from prior additive ALTER TABLE).",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "FUTURE TEST ROLE CANDIDATE: worker-4. Already allowlisted, no live surface (surface:219=worker-10, "
    "surface:220=worker-6, both preserved/occupied), thematically consistent (worker-4 was RUN-1's "
    "original CLAUDE role, COMPLETED cleanly, no incident history), no allowlist change required. "
    "worker-5 (incident history) and worker-8 (prior Codex use) considered and not selected.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Local deterministic tests (test_2b_c_claude_adapter_discovery.py): 15/15 PASS, zero AI/"
    "provider calls. Covers: provider=CLAUDE contract representation, CLAUDE->claude agent "
    "mapping, provider-generic target-policy denial (production role, unlisted role), task/token "
    "compatibility (no provider field baked into envelope), provenance writer path, Claude startup "
    "profile structural validation, zero Codex-specific marker leakage into Claude's config, "
    "frozen contract hash unchanged (142dabae.../f3b7be00...). Test fixture row cleaned up, zero "
    "residue confirmed.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Regression re-check (no Codex/Claude execution): Protocol V1 sha256 unchanged (987f45d3...), "
    "config.toml model unchanged (gpt-6-sol), allowlist unchanged ({worker-4,5,6,8,10}), "
    "surface:219/220 both still alive and untouched (exited=False, agent_alive=True).",
    "CONFIRMED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id, final_status="COMPLETED",
    output_artifacts=[str(Path(__file__).resolve().parent.parent / "tests" / "test_2b_c_claude_adapter_discovery.py")],
    validation_result="15/15 local tests PASS; Claude's existing native CYS integration fully "
                       "satisfies the frozen provider-neutral contract except for the protocol "
                       "delivery mechanism (adapter-level difference only, proposed not "
                       "implemented); zero AI provider calls; contract/baseline unchanged; "
                       "surface:219/220 untouched.",
    db_changes={"tables_created": [], "existing_tables_modified": [],
                "note": "one test fixture row created and deleted; no production data touched"},
    conn=conn,
)
conn.commit()
print("기록 완료")
conn.close()
