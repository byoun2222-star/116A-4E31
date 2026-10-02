# PHASE2B-PROVIDER-CONTRACT-V1

Provider-neutral execution contract for Phase 2B. Extracted **read-only** from the already
verified Codex success path — nothing in the existing implementation was changed to produce
this document.

Authoritative runs this contract was derived from:
- `run2b-98c6b20ac93d4003` — Identity-Preserving Codex Startup (ESTABLISHED)
- `run2b-d7f7a04578394cc7` — Short-Token Real E2E (PASS)

## 1. Source classification (PROVIDER_NEUTRAL vs CODEX_SPECIFIC)

Classified from actual code, not assumption.

| File / component | Classification | Basis |
|---|---|---|
| `phase2b/control/token_manifest.py` | **PROVIDER_NEUTRAL** | Pure task_id/hash/path logic — no provider branching anywhere in the source |
| `phase2b/tasks/test_task.py` | **PROVIDER_NEUTRAL** | Schema/validator operate on plain text/JSON, no provider awareness |
| `phase2b/collector/result_collector.py` | **PROVIDER_NEUTRAL** | `provider` is stored as an opaque string column, never branched on |
| `phase2b/workflow/run_baseline.py` | **PROVIDER_NEUTRAL** | `--provider` arg accepts CLAUDE/CODEX/GEMINI equally, identical flow for all three |
| `controlled_cys_adapter.py: PROVIDER_TO_AGENT` | **PROVIDER_NEUTRAL** | Explicit 3-way map `{CLAUDE:claude, CODEX:codex, GEMINI:gemini}` |
| `controlled_cys_adapter.py: check_target_policy()` | **PROVIDER_NEUTRAL** | Generic role/provider/task checks, no Codex-only branch |
| `controlled_cys_adapter.py: collect_test_result_file()` | **PROVIDER_NEUTRAL** | Pure file I/O, provider-agnostic |
| `controlled_cys_adapter.py: _codex_submission_exists()` / `CODEX_LOCAL_LOG_PATH` | **CODEX_SPECIFIC** | Docstring itself states "★Scope: only CODEX has this local log" |
| `phase2b_startup_launcher.py` (hash-verify / UTF-8 / shell=False / fail-closed mechanism) | **PROVIDER_NEUTRAL (reusable pattern)** | The transport-safety mechanism itself does not depend on Codex |
| `phase2b_startup_launcher.py` (actual `--child` values used) | **CODEX_SPECIFIC** | node.exe + codex.js + `--no-daemon` are today's Codex-specific invocation |
| `~/.codex/config.toml` (`model = "gpt-6-sol"`) | **CODEX_SPECIFIC** | Codex's own config file |
| Codex TUI vim-mode / Enter-submit behavior | **CODEX_SPECIFIC** | Found only in the Codex vendor binary's embedded strings |
| Protocol V1 **instruction text/ACK wording** | **PROVIDER_NEUTRAL** | The instructions themselves (read manifest, verify hash, write result) name no provider |
| Protocol V1 **delivery mechanism to Codex** (argv via node.exe/codex.js) | **CODEX_SPECIFIC** | How the text reaches the provider's process, not what it says |

## 2. The Contract

See `provider_execution_contract.json` (machine-readable, same sections) for the authoritative
field list. Summary:

- **Task Envelope** — `task_id, provider, objective, input, output_schema, constraints,
  validation_rules, result_path` (plus `workflow_run_id`/`book_id`/`relevant_file_paths`/
  `owner_instruction_reference` from the existing `build_task_packet` shape). `provider` is not
  a mandatory field of the envelope itself — it is carried alongside it.
- **Control Contract** — terminal payload is exactly `RUN <TOKEN>`; the token is never the task
  body; token → manifest → task file mapping is deterministic (`T` + first 8 uppercase hex of
  SHA-256(task_id)).
- **Data Contract** — canonical task/result = UTF-8 JSON file; screen/PTY content is never
  canonical data.
- **Result Contract** — provider writes only the result JSON to the assigned path; `.tmp` →
  atomic final; no human reconstruction.
- **Validation Contract** — UTF-8 → JSON parse → schema → task-specific validator → SHA-256,
  deterministic, never AI-self-graded.
- **Completion Contract** — COMPLETED requires valid final result + validator PASS + DB/hash
  consistency, never the provider's own claim alone.
- **Retry Contract** — `MAX_AUTOMATIC_RETRY=0`; a retry is never conflated with a legitimate
  recovery/input-commit action.
- **Idempotency Contract** — a valid completed result blocks resubmission; a genuine identity/
  hash conflict reports `IDEMPOTENCY_CONFLICT — STOP`.

## 3. Codex Adapter / Codex Startup Profile (isolated, not part of the neutral contract)

The following remain Codex-specific and MUST NOT be required of Claude/Gemini adapters:
`node.exe` + `codex.js` direct invocation, `--no-daemon`, the current `gpt-6-sol` model setting,
the Codex Protocol V1 *installation* mechanism (argv injection at startup), Codex TUI
shortcut/key behavior (vim-mode, Enter semantics), and the Codex-only submission-log check
(`_codex_submission_exists`). A Claude or Gemini adapter satisfies the same neutral contract
through its own startup mechanics — it is not expected to imitate Codex's.

## 4. DB provenance gap (analysis only, no schema change, no existing row modified)

The short-token E2E's successful `provider_run` row (`run-e2e-tfbab618c`) has empty
`agent_role`/`surface_id` columns. Root cause (confirmed by reading source, not guessed):

- **`phase2b/collector/result_collector.py: record_run_started()`** is the **intended canonical
  writer** for Phase 2B — it already accepts and stores `surface_id`, `agent_role`,
  `idempotency_key`, `health_before/after`, `usage_before/after`. `run_baseline.py` uses exactly
  this function.
- The E2E script in this session used the simpler, generic **`phase2a/db/publishing_db.py:
  record_provider_run()`** instead, which has no `surface_id`/`agent_role`/`idempotency_key`
  parameters at all — hence the gap.
- The `provider_run` table **already has** the needed columns (added by
  `result_collector.migrate()` as additive `ALTER TABLE`, already applied) — **no schema
  migration is required**.
- **Minimal fix for future runs (proposed, not implemented this round):** route any future
  provider-run recording (Codex, Claude, or Gemini) through
  `result_collector.record_run_started()` / `record_run_completed()` instead of calling
  `publishing_db.record_provider_run()` directly, so `run_id → task_id → surface_id → agent_role
  → idempotency_key → result hash` forms one deterministic provenance chain for every future
  run. The existing `run-e2e-tfbab618c` COMPLETED row is left untouched.

## 5. Deterministic contract tests

`phase2b/tests/test_2b_b_provider_contract.py` — no AI/provider calls, reuses
`test_task.validate_output`/`token_manifest`/`collect_test_result_file`/`check_target_policy`
rather than duplicating their logic. See that file for the 15 cases.

## 6. Regression protection

Before/after this contract-extraction work, the following were re-hashed/re-checked and found
**unchanged**: Protocol V1 file SHA-256, `~/.codex/config.toml` model value, Phase2B allowlist
set, `phase2b_startup_launcher.py` file hash, `token_manifest.generate_token()` formula, and the
`run2b-d7f7a04578394cc7` COMPLETED evidence in the Publishing DB. No Codex process was
re-executed to verify this — all checks are static/file/DB reads.
