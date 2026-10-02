# Copyright (c) tree and fruits. PoC only.
"""Mock step executors for the MAF-PUBLISHING-POC workflow.

MANUSCRIPT_RECEIVED -> EDITING -> OWNER_APPROVAL -> EPUB_BUILD -> EPUB_VALIDATE -> REVIEW -> READY_FOR_PUBLICATION

★ZERO-INCREMENTAL-COST / no-Agent rule: nothing in this file imports agent_framework's
Agent / model-client surface (no agent_framework.openai, .anthropic, .foundry, .gemini, ...).
Every step below is a plain Python function wrapped by Executor/FunctionExecutor — no LLM call,
no API key, no network call of any kind. CYSJavis is NOT called yet (mock only, per task §4).

NOTE: deliberately NOT using `from __future__ import annotations` — agent_framework's
@handler/@response_handler decorators inspect real runtime type objects (get_origin() on
the actual WorkflowContext[...] generic alias); PEP 563 deferred (string) annotations make
those checks fail with "must be annotated as WorkflowContext... got WorkflowContext[X]"
(confirmed by direct reproduction while building this PoC).
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Literal

from typing_extensions import Never

from agent_framework import Executor, WorkflowContext, handler, response_handler

from . import db_writer as db

Stage = Literal[
    "MANUSCRIPT_RECEIVED",
    "EDITING",
    "OWNER_APPROVAL",
    "EPUB_BUILD",
    "EPUB_VALIDATE",
    "REVIEW",
    "READY_FOR_PUBLICATION",
]


@dataclass
class BookMessage:
    book_id: str
    title: str
    # TEST F hook: name of a stage that should simulate a hard failure (e.g. "EPUB_VALIDATE").
    fail_at: str | None = None
    # TEST B hook: artificial delay (seconds) inside EDITING so a real process-kill has a window.
    editing_delay_seconds: float = 0.0
    trace: list[str] = field(default_factory=list)


@dataclass
class ApprovalRequest:
    book_id: str
    action: str = "OWNER_APPROVAL"


@dataclass
class ApprovalResponse:
    approved: bool
    approved_by: str = "owner"


class ManuscriptReceivedExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="manuscript_received")

    @handler
    async def run(self, message: BookMessage, ctx: WorkflowContext[BookMessage]) -> None:
        db.ensure_book(message.book_id, message.title)
        db.set_status(message.book_id, "MANUSCRIPT_RECEIVED", actor="manuscript_received")
        message.trace.append("MANUSCRIPT_RECEIVED")
        await ctx.send_message(message)


class EditingExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="editing")

    @handler
    async def run(self, message: BookMessage, ctx: WorkflowContext[BookMessage]) -> None:
        if message.editing_delay_seconds > 0:
            # Deliberately slow, real wall-clock sleep so TEST B can kill -9 the OS process
            # while this coroutine is mid-flight, before send_message() is ever reached —
            # i.e. before this superstep completes and a new checkpoint would be written.
            await asyncio.sleep(message.editing_delay_seconds)
        if message.fail_at == "EDITING":
            db.set_status(message.book_id, "EDITING_FAILED", actor="editing")
            raise RuntimeError("TEST F: simulated EDITING failure — must not advance to OWNER_APPROVAL")
        db.set_status(message.book_id, "EDITING", actor="editing")
        message.trace.append("EDITING")
        await ctx.send_message(message)


class OwnerApprovalExecutor(Executor):
    """HITL gate. Pauses the workflow via ctx.request_info() until an ApprovalResponse arrives."""

    def __init__(self) -> None:
        super().__init__(id="owner_approval")

    @handler
    async def run(self, message: BookMessage, ctx: WorkflowContext[BookMessage]) -> None:
        db.record_approval_request(message.book_id, "OWNER_APPROVAL", requested_by="workflow")
        # Stash the in-flight message on shared workflow state so the response_handler (which
        # only receives the ApprovalRequest + ApprovalResponse, not our BookMessage) can recover it.
        ctx.set_state("pending_book_message", message)
        # Deterministic request_id (not a random UUID) so the CLI can address this exact
        # pending request across separate process invocations (start -> [kill] -> approve).
        await ctx.request_info(
            ApprovalRequest(book_id=message.book_id), ApprovalResponse, request_id=f"approval-{message.book_id}"
        )

    @response_handler
    async def on_approval(
        self,
        original_request: ApprovalRequest,
        response: ApprovalResponse,
        ctx: WorkflowContext[BookMessage],
    ) -> None:
        message: BookMessage = ctx.get_state("pending_book_message")
        approval_id = f"appr-{message.book_id}-OWNER_APPROVAL"
        if response.approved:
            db.record_approval_decision(approval_id, response.approved_by, "APPROVED", evidence="TEST harness")
            db.set_status(message.book_id, "OWNER_APPROVAL", actor="owner_approval")
            message.trace.append("OWNER_APPROVAL")
            await ctx.send_message(message)
        else:
            db.record_approval_decision(approval_id, response.approved_by, "REJECTED", evidence="TEST harness")
            db.set_status(message.book_id, "OWNER_APPROVAL_REJECTED", actor="owner_approval")
            # Rejected: workflow ends here on purpose. No send_message() -> no advance to EPUB_BUILD.


class EpubBuildExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="epub_build")

    @handler
    async def run(self, message: BookMessage, ctx: WorkflowContext[BookMessage]) -> None:
        if message.fail_at == "EPUB_BUILD":
            db.set_status(message.book_id, "EPUB_BUILD_FAILED", actor="epub_build")
            raise RuntimeError("TEST F: simulated EPUB_BUILD failure — must not advance to EPUB_VALIDATE")
        # mock only: no real InDesign/epub tooling invoked in Phase 1.
        fake_epub_path = f"mock://{message.book_id}.epub"
        db.upsert_production(message.book_id, epub_status="BUILT", current_file=fake_epub_path)
        db.set_status(message.book_id, "EPUB_BUILD", actor="epub_build")
        message.trace.append("EPUB_BUILD")
        await ctx.send_message(message)


class EpubValidateExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="epub_validate")

    @handler
    async def run(self, message: BookMessage, ctx: WorkflowContext[BookMessage, str]) -> None:
        if message.fail_at == "EPUB_VALIDATE":
            # Explicit validation-failure branch (distinct from an exception): the mock validator
            # itself determined the epub is invalid. Must NOT call send_message -> REVIEW never runs.
            db.set_status(message.book_id, "EPUB_VALIDATE_FAILED", actor="epub_validate")
            await ctx.yield_output(f"{message.book_id}: EPUB_VALIDATE_FAILED (stopped, did not advance to REVIEW)")
            return
        db.upsert_production(message.book_id, epub_status="VALID")
        db.set_status(message.book_id, "EPUB_VALIDATE", actor="epub_validate")
        message.trace.append("EPUB_VALIDATE")
        await ctx.send_message(message)


class ReviewExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="review")

    @handler
    async def run(self, message: BookMessage, ctx: WorkflowContext[BookMessage]) -> None:
        if message.fail_at == "REVIEW":
            db.set_status(message.book_id, "REVIEW_FAILED", actor="review")
            raise RuntimeError("TEST F: simulated REVIEW failure — must not advance to READY_FOR_PUBLICATION")
        db.set_status(message.book_id, "REVIEW", actor="review")
        message.trace.append("REVIEW")
        await ctx.send_message(message)


class ReadyForPublicationExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="ready_for_publication")

    @handler
    async def run(self, message: BookMessage, ctx: WorkflowContext[Never, str]) -> None:
        db.set_status(message.book_id, "READY_FOR_PUBLICATION", actor="ready_for_publication")
        message.trace.append("READY_FOR_PUBLICATION")
        await ctx.yield_output(f"{message.book_id}: READY_FOR_PUBLICATION | trace={message.trace}")
