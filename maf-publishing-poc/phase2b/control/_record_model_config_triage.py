# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

conn = eh.get_conn()
run_id = eh.start_run(
    objective="Codex model configuration triage (Task A-F): protect surface:219 (read-only, no "
              "input), trace exact source of gpt-6.1-sol config, check locally-cached supported "
              "models for this ChatGPT account WITHOUT any provider call",
    actor="claude-session", provider="LOCAL",
    raw_command="read-only config/cache inspection, no surface/Codex execution, no input to surface:219",
    conn=conn,
)
print("RUN_ID:", run_id)

eh.record_evidence(
    "surface:219 PROTECTED (read-only check only, no input/send-key/close/kill): "
    "cys status --json re-confirms agent_alive=true, exited=false, seat=occupied, "
    "line_count grew from 194 to 341 between checks (something still rendering/idle-looping on "
    "screen) but NO input was sent by this investigation.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "MODEL CONFIG SOURCE CONFIRMED: C:\\Users\\a\\.codex\\config.toml, FIRST LINE: "
    'model = "gpt-6.1-sol". No environment variable sets this (env | grep -i model/codex -> no '
    "matches). No startup argument from phase2b_startup_launcher.py specifies a model (launcher "
    "never passes -c model=... or --model). No per-project override in config.toml's "
    "[projects.'c:\\users\\a\\install-jarvis\\maf-publishing-poc'] section (only trust_level is "
    "set there). cys itself has no model-related flags anywhere in `cys --help`. This is a "
    "GLOBAL, machine-wide Codex CLI default, unrelated to this test's launcher/surface.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "CHATGPT-ACCOUNT SUPPORTED MODEL EVIDENCE (local cache, zero provider calls made by this "
    "investigation): C:\\Users\\a\\.codex\\models_cache.json, fetched_at=2026-10-02T04:28:32Z "
    "(same day, ~9 hours before the failing live test -- fresh), client_version=0.157.0, "
    "identity hash present (this account). Lists exactly 9 models, ALL with supported_in_api=true: "
    "gpt-6-astra(priority 2, visibility list), gpt-6-sol(3, list), gpt-6-luna(4, list), "
    "gpt-reserve(4, hide), gpt-5.6-sol(5, list), gpt-5.6-terra(8, list), gpt-5.6-luna(9, list), "
    "gpt-5.5(13, list), codex-auto-review(43, hide). 'gpt-6.1-sol' (the configured model) is "
    "ABSENT from this list entirely -- directly explaining the 400 invalid_request_error observed "
    "in run2b-57d497ebf49d4c43. None of the 9 entries has is_default/default explicitly set to "
    "true (all null) -- no single model is flagged by Codex's own cache as THE default/"
    "recommended choice.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "Per owner instruction E, this triage used ONLY evidence local to the current installation/"
    "account (config.toml + models_cache.json fetched today for this identity) -- it did NOT use "
    "any prior codex-cli version's observed models or any other surface's configuration as "
    "evidence of current support.",
    "CONFIRMED", run_id=run_id, conn=conn,
)
eh.record_evidence(
    "SUPPORTED REPLACEMENT determination: since no model in the confirmed local cache is marked "
    "is_default/default=true, there is no single confirmed correct replacement -- picking one "
    "among the 9 valid slugs (e.g. by lowest priority number) would be a guess, not a confirmed "
    "fact, and the owner explicitly prohibited auto-selecting a model name. Reported as "
    "SUPPORTED REPLACEMENT: UNVERIFIED per the owner's own stop condition, with the full "
    "confirmed candidate pool preserved as supporting (not prescriptive) evidence.",
    "UNVERIFIED", run_id=run_id, conn=conn,
)

eh.finalize_run(
    run_id, final_status="COMPLETED",
    validation_result="MODEL CONFIG SOURCE and CHATGPT-ACCOUNT SUPPORTED MODEL EVIDENCE both "
                       "CONFIRMED from local, same-day, zero-provider-call evidence. Specific "
                       "SUPPORTED REPLACEMENT left UNVERIFIED (no explicit default flag in cache; "
                       "owner prohibited guessing a model name). No config changed.",
    conn=conn,
)
conn.commit()
print("기록 완료, run_id:", run_id)
conn.close()
