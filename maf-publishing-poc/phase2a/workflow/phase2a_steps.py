# Copyright (c) tree and fruits. PoC only — PHASE 2A workflow executors.
"""PHASE 2A workflow: SYNC_CYS_STATE -> REGISTER_PROVIDERS -> ROUTER_DECISION -> COST_GUARD
-> OWNER_APPROVAL(HITL) -> FINALIZE

No agent_framework.openai/.anthropic/.foundry/.gemini/.ollama/.bedrock/.mistral import anywhere
in this file (PHASE 2A §3 hard rule, same as Phase 1). No `cys` mutation command is ever
constructed here — all CYSJavis contact goes through phase2a/adapter/cys_readonly_adapter.py's
fixed functions.

NOTE (same as Phase 1, confirmed again here): do NOT use `from __future__ import annotations`
in a file that defines @handler/@response_handler — PEP 563 deferred annotations break
agent_framework's runtime WorkflowContext[...] introspection (documented in PHASE1 report §4).
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Never

from agent_framework import Executor, WorkflowContext, handler, response_handler

PHASE2A_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHASE2A_ROOT))

from adapter.cys_readonly_adapter import (  # noqa: E402
    get_cys_status,
    get_cys_surfaces,
    get_provider_usage_snapshot,
)
from db import publishing_db as db  # noqa: E402
from router.provider_router import ProviderHealth, ProviderState, route  # noqa: E402


@dataclass
class Phase2AMessage:
    book_id: str
    title: str
    workflow_run_id: str
    # TEST 2A-G hook: if set, overrides real observed health with an injected mock scenario
    # {"CLAUDE": "RATE_LIMITED", "CODEX": "AVAILABLE", "GEMINI": "AVAILABLE"} — pure mock input,
    # never derived from a real provider call.
    mock_provider_health: dict[str, str] | None = None
    # TEST 2A-H hook: simulate a task that would require a paid API path.
    requires_paid_api: bool = False
    trace: list[str] = field(default_factory=list)
    router_decision: str | None = None


@dataclass
class ApprovalRequest:
    book_id: str
    action: str = "OWNER_APPROVAL_PHASE2A"


@dataclass
class ApprovalResponse:
    approved: bool
    approved_by: str = "owner"


class SyncCysStateExecutor(Executor):
    """TEST 2A-E core: MAF Function Executor -> READ-ONLY Adapter -> CYSJavis. Zero mutation."""

    def __init__(self) -> None:
        super().__init__(id="sync_cys_state")

    @handler
    async def run(self, message: Phase2AMessage, ctx: WorkflowContext[Phase2AMessage]) -> None:
        status_result = get_cys_status()
        surfaces_result = get_cys_surfaces()
        usage_result = get_provider_usage_snapshot()

        conn = db.get_conn()
        try:
            db.log_event(
                conn, actor="sync_cys_state", action="cys_state.synced", previous_state=None,
                new_state="synced", reason=(
                    f"status_ok={status_result.ok} surfaces_ok={surfaces_result.ok} "
                    f"usage_ok={usage_result.ok} status_hash={status_result.raw_result_hash[:16]} "
                    f"surfaces_hash={surfaces_result.raw_result_hash[:16]}"
                ),
                source="sync_cys_state_executor", workflow_run_id=message.workflow_run_id,
                entity_type="cys_state", entity_id="snapshot",
            )
            conn.commit()
        finally:
            conn.close()

        message.trace.append("SYNC_CYS_STATE")
        await ctx.send_message(message)


class RegisterProvidersExecutor(Executor):
    """TEST 2A-D: populate the PROVIDER registry using ONLY what was actually observed by
    SyncCysStateExecutor moments ago (re-reads the same adapter calls' fresh result rather than
    a cached/assumed value). Claude/Codex are populated from real `cys status --json` /
    `cys usage-accounts` data; Gemini is recorded UNKNOWN when no surface/usage-accounts line
    exists for it (never fabricated)."""

    def __init__(self) -> None:
        super().__init__(id="register_providers")

    @handler
    async def run(self, message: Phase2AMessage, ctx: WorkflowContext[Phase2AMessage]) -> None:
        status_result = get_cys_status()
        usage_result = get_provider_usage_snapshot()
        status_data = status_result.data or {}
        surfaces = status_data.get("surfaces", [])
        usage_text = usage_result.data or ""

        claude_surface = next((s for s in surfaces if s.get("agent") == "claude"), None)
        codex_surface = next((s for s in surfaces if s.get("agent") == "codex"), None)
        gemini_surface = next((s for s in surfaces if s.get("agent") in ("gemini", "agy")), None)

        def rate5h(surface: dict | None) -> float | None:
            if not surface:
                return None
            for r in (surface.get("usage") or {}).get("rate", []) or []:
                if r.get("label") == "5h":
                    return r.get("used_pct")
            return None

        # Claude: cys status --json usage.source is "statusline" -> official hook telemetry.
        db.upsert_provider(
            "CLAUDE", "Claude", "AVAILABLE" if claude_surface else "UNKNOWN",
            usage_source=(claude_surface or {}).get("usage", {}).get("source"),
            usage_value=str(rate5h(claude_surface)), confidence_reliability="HIGH (hook-verified statusline)",
            stale=False, error_signal=None, actor="register_providers",
        )
        # Codex: cys status --json usage.source is literally "rollout:heuristic:stale" —
        # recorded exactly as the daemon itself labels it, not upgraded to a nicer confidence.
        codex_usage_source = (codex_surface or {}).get("usage", {}).get("source")
        db.upsert_provider(
            "CODEX", "ChatGPT Codex", "AVAILABLE" if codex_surface else "UNKNOWN",
            usage_source=codex_usage_source, usage_value=str(rate5h(codex_surface)),
            confidence_reliability=("LOW (self-labeled heuristic:stale)" if codex_usage_source and "heuristic" in codex_usage_source else "UNKNOWN"),
            stale=bool(codex_usage_source and "stale" in codex_usage_source), error_signal=None,
            actor="register_providers",
        )
        # Gemini: no surface, no usage-accounts line -> UNKNOWN, not assumed AVAILABLE or 0%.
        db.upsert_provider(
            "GEMINI", "Gemini", "UNKNOWN" if not gemini_surface else "AVAILABLE",
            usage_source=None, usage_value=None, confidence_reliability="UNKNOWN",
            stale=True, error_signal=("no gemini surface and no usage-accounts line observed"
                                        if not gemini_surface else None),
            actor="register_providers",
        )

        message.trace.append("REGISTER_PROVIDERS")
        await ctx.send_message(message)


class RouterDecisionExecutor(Executor):
    """TEST 2A-G: pure decision, no dispatch. Uses message.mock_provider_health when supplied
    (test harness), otherwise reads the just-registered PROVIDER table's real observed health."""

    def __init__(self) -> None:
        super().__init__(id="router_decision")

    @handler
    async def run(self, message: Phase2AMessage, ctx: WorkflowContext[Phase2AMessage]) -> None:
        if message.mock_provider_health:
            states = [
                ProviderState(name=name, health=ProviderHealth(health))
                for name, health in message.mock_provider_health.items()
            ]
        else:
            rows = db.get_all_providers()
            states = [
                ProviderState(name=r["provider_id"], health=ProviderHealth(r["health"]))
                for r in rows
            ]
        decision = route(states)
        message.router_decision = decision.selected_provider or "NONE_ROUTABLE"

        conn = db.get_conn()
        try:
            db.log_event(
                conn, actor="router_decision", action="router.decision", previous_state=None,
                new_state=message.router_decision,
                reason=f"{decision.reason} | candidates={decision.candidates_considered} | excluded={decision.excluded}",
                source="router_decision_executor", workflow_run_id=message.workflow_run_id,
                entity_type="router", entity_id=message.workflow_run_id,
            )
            conn.commit()
        finally:
            conn.close()

        message.trace.append(f"ROUTER_DECISION={message.router_decision}")
        await ctx.send_message(message)


class CostGuardExecutor(Executor):
    """TEST 2A-H: if the incoming task claims it needs a paid API, halt HERE — do not forward
    to OWNER_APPROVAL. No real cost-incurring call is ever made regardless of this flag; the
    flag only simulates "a future real executor reported that it would need one"."""

    def __init__(self) -> None:
        super().__init__(id="cost_guard")

    @handler
    async def run(self, message: Phase2AMessage, ctx: WorkflowContext[Phase2AMessage, str]) -> None:
        if message.requires_paid_api:
            db.set_book_status(message.book_id, "BLOCKED_BY_COST_POLICY", actor="cost_guard")
            await ctx.yield_output(f"{message.book_id}: BLOCKED_BY_COST_POLICY (halted, no paid API call made)")
            return
        message.trace.append("COST_GUARD_PASSED")
        await ctx.send_message(message)


class OwnerApprovalExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="owner_approval_2a")

    @handler
    async def run(self, message: Phase2AMessage, ctx: WorkflowContext[Phase2AMessage]) -> None:
        db.record_approval_request(message.book_id, "OWNER_APPROVAL_PHASE2A", requested_by="workflow")
        ctx.set_state("pending_message", message)
        await ctx.request_info(
            ApprovalRequest(book_id=message.book_id), ApprovalResponse,
            request_id=f"approval2a-{message.book_id}",
        )

    @response_handler
    async def on_approval(
        self, original_request: ApprovalRequest, response: ApprovalResponse, ctx: WorkflowContext[Phase2AMessage],
    ) -> None:
        message: Phase2AMessage = ctx.get_state("pending_message")
        approval_id = f"appr-{message.book_id}-OWNER_APPROVAL_PHASE2A"
        if response.approved:
            db.record_approval_decision(approval_id, response.approved_by, "APPROVED", evidence="TEST harness")
            message.trace.append("OWNER_APPROVAL")
            await ctx.send_message(message)
        else:
            db.record_approval_decision(approval_id, response.approved_by, "REJECTED", evidence="TEST harness")
            db.set_book_status(message.book_id, "OWNER_APPROVAL_REJECTED", actor="owner_approval_2a")


class FinalizeExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="finalize")

    @handler
    async def run(self, message: Phase2AMessage, ctx: WorkflowContext[Never, str]) -> None:
        db.set_book_status(message.book_id, "PHASE2A_WORKFLOW_COMPLETE", actor="finalize")
        message.trace.append("FINALIZE")
        await ctx.yield_output(f"{message.book_id}: PHASE2A_WORKFLOW_COMPLETE | trace={message.trace}")
