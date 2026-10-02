# Copyright (c) tree and fruits. PoC only — PHASE 2B fixed test task + deterministic validator.
"""The ONE test task all three providers receive, verbatim (owner §9-10).

Objective: read a virtual book's metadata JSON and return it normalized to a fixed schema.
Deliberately measurable, not creative — a human/deterministic script can grade the output
without judgment calls, so provider comparison is objective (owner §10).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

TASK_TYPE = "METADATA_NORMALIZATION"

INPUT_METADATA = {
    "title": "스펄전의 시편 묵상 (PoC 가상도서)",
    "subtitle": "PHASE 2B 시험용 가상 메타데이터 — 실제 출판물 아님",
    "author": "Charles H. Spurgeon (PoC placeholder)",
    "price": "18000",
    "language": "ko",
    "publication_status": "draft",
}

OUTPUT_SCHEMA_REQUIRED_FIELDS = {
    "title": str,
    "subtitle": str,
    "author": str,
    "price_krw": int,          # input "price" is a string -> must be normalized to int
    "language_code": str,      # input "language" -> renamed key, must stay "ko"
    "status": str,             # input "publication_status" -> renamed key, must stay "draft"
}

FORBIDDEN_OUTPUT_FIELDS = {"price", "publication_status", "language", "isbn", "notes", "comment"}

# The Task Packet echoes OUTPUT_SCHEMA verbatim as a JSON object (see build_task_packet below)
# so a provider's terminal transcript will show it TWICE before the real answer appears: once
# as our own instruction, once (hopefully) as the correctly-filled answer. Both are syntactically
# valid JSON objects with the same keys, so brace-balance scanning alone can't tell them apart.
# This is the literal echo shape (all values are type NAMES, never real data) — any extracted
# object identical to this is unambiguously our own instruction, not a provider's answer, for
# every provider equally (the exclusion is on the shared packet content, not provider-specific).
_SCHEMA_ECHO = {k: v.__name__ for k, v in OUTPUT_SCHEMA_REQUIRED_FIELDS.items()}

# The Task Packet ALSO echoes the raw INPUT_METADATA verbatim (as `INPUT_JSON: {...}` in the
# instruction text sent to the provider) — a second echo shape that appears on screen before the
# real answer, for the same structural reason as _SCHEMA_ECHO above. Both echoes must be
# excluded, or whichever one is still visible when we poll gets mistaken for the answer.
_KNOWN_ECHOES = (_SCHEMA_ECHO, dict(INPUT_METADATA))

OBJECTIVE = (
    "Read the INPUT metadata JSON for a virtual test book and return ONLY a JSON object "
    "normalized to the OUTPUT_SCHEMA below. Do not add, invent, or omit any information. "
    "Do not add commentary, markdown fences, or any text other than the JSON object itself."
)

CONSTRAINTS = [
    "Output must be a single valid JSON object, nothing else (no prose, no code fences).",
    "price (string) must become price_krw (integer), stripping any non-digit characters.",
    "language must be renamed to language_code, value unchanged.",
    "publication_status must be renamed to status, value unchanged.",
    "title/subtitle/author must be copied verbatim, unchanged.",
    "Do not include the old field names (price/language/publication_status) in the output.",
    "Do not fabricate any field not derivable from the input (no isbn, no notes, no comment).",
]


def build_task_packet(task_id: str, workflow_run_id: str, book_id: str) -> dict:
    """Owner §17 minimal Task Packet — no conversational history, no prior provider's output."""
    return {
        "task_id": task_id,
        "workflow_run_id": workflow_run_id,
        "book_id": book_id,
        "task_type": TASK_TYPE,
        "objective": OBJECTIVE,
        "input": INPUT_METADATA,
        "output_schema": _SCHEMA_ECHO,
        "constraints": CONSTRAINTS,
        "validation_rules": "see phase2b/tasks/test_task.py:validate_output() — deterministic, not AI-graded",
        "relevant_file_paths": [],  # none needed — self-contained task (owner §9 "외부자료 불필요")
        "owner_instruction_reference": "PHASE2B §9-10, task packet §17",
    }


@dataclass
class ValidationResult:
    passed: bool
    reasons: list[str]

    def to_dict(self) -> dict:
        return {"passed": self.passed, "reasons": self.reasons}


def _find_balanced_json_objects(raw_text: str) -> list[dict]:
    """Scan for every top-level {...} span via balanced-brace counting (not a naive greedy
    regex) and return the ones that actually parse as JSON, in the order they appear.

    Why this matters (found empirically in PHASE 2B RUN-1, worker-4/Claude): a `cys
    read-screen` capture of a real agent surface still shows the ECHOED task instruction above
    the answer, and that instruction itself contains a JSON object
    (`OUTPUT_SCHEMA: {"title": "str", ...}`, from build_task_packet()). A greedy
    `re.search(r"\\{.*\\}", ..., re.DOTALL)` matches from THAT first '{' all the way to the
    LAST '}' on screen (the real answer's closing brace), swallowing unrelated text in between
    and producing unparseable garbage — this is a screen-capture artifact of always having our
    own prompt visible, not a provider error. Balanced-brace scanning finds each self-contained
    object independently; the real answer is picked by the caller as the LAST one that parses,
    since it is always the most recently produced content."""
    objects: list[dict] = []
    depth = 0
    start = None
    for i, ch in enumerate(raw_text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = raw_text[start:i + 1]
                    try:
                        objects.append(json.loads(candidate))
                    except json.JSONDecodeError:
                        pass
                    start = None
    return objects


def _extract_json_object(raw_text: str) -> dict | None:
    """Providers may wrap JSON in prose/code fences despite instructions — the validator itself
    must not be lenient about SCORING that, but we do need to locate the JSON to grade it.
    Extraction leniency is not the same as validation leniency: if extra prose surrounds the
    JSON, that is recorded as a validation finding (see validate_output), not silently ignored.

    Preference order: a fenced code block's JSON (most explicit signal of "this is my answer"),
    else the LAST balanced top-level JSON object found anywhere in the text (the real answer is
    always the most recent thing on screen; any earlier '{...}' is our own echoed instruction)."""
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            if parsed not in _KNOWN_ECHOES:
                return parsed
        except json.JSONDecodeError:
            pass
    objects = [o for o in _find_balanced_json_objects(raw_text) if o not in _KNOWN_ECHOES]
    return objects[-1] if objects else None


def validate_output(raw_output_text: str) -> ValidationResult:
    """Deterministic, non-AI validator (owner §10 explicit: "AI가 자기 결과를 합격 처리하지
    않는다"). Every check below is a plain Python comparison — no LLM call, no judgment call."""
    reasons: list[str] = []

    is_pure_json = raw_output_text.strip().startswith("{") and raw_output_text.strip().endswith("}")
    if not is_pure_json:
        reasons.append("output was not a bare JSON object (contained surrounding prose/fences)")

    parsed = _extract_json_object(raw_output_text)
    if parsed is None:
        reasons.append("could not parse any JSON object from the output at all")
        return ValidationResult(passed=False, reasons=reasons)

    for field, expected_type in OUTPUT_SCHEMA_REQUIRED_FIELDS.items():
        if field not in parsed:
            reasons.append(f"missing required field '{field}'")
        elif not isinstance(parsed[field], expected_type):
            reasons.append(f"field '{field}' has wrong type: expected {expected_type.__name__}, "
                            f"got {type(parsed[field]).__name__}")

    for forbidden in FORBIDDEN_OUTPUT_FIELDS:
        if forbidden in parsed:
            reasons.append(f"forbidden field '{forbidden}' present in output (old key name or fabricated)")

    if parsed.get("title") != INPUT_METADATA["title"]:
        reasons.append("title was not preserved verbatim")
    if parsed.get("subtitle") != INPUT_METADATA["subtitle"]:
        reasons.append("subtitle was not preserved verbatim")
    if parsed.get("author") != INPUT_METADATA["author"]:
        reasons.append("author was not preserved verbatim")
    if "price_krw" in parsed and parsed["price_krw"] != int(INPUT_METADATA["price"]):
        reasons.append(f"price_krw={parsed.get('price_krw')} does not match expected {int(INPUT_METADATA['price'])}")
    if "language_code" in parsed and parsed["language_code"] != INPUT_METADATA["language"]:
        reasons.append("language_code does not match input language")
    if "status" in parsed and parsed["status"] != INPUT_METADATA["publication_status"]:
        reasons.append("status does not match input publication_status")

    extra_fields = set(parsed.keys()) - set(OUTPUT_SCHEMA_REQUIRED_FIELDS.keys())
    if extra_fields:
        reasons.append(f"extra/fabricated fields present: {sorted(extra_fields)}")

    # A "hard fail" reason (missing/wrong-type/forbidden/mismatched-value/extra-field) fails the
    # task. The "not pure JSON" finding is recorded but does NOT alone fail validation (a
    # provider that wraps correct JSON in a code fence still produced a materially correct
    # answer) — this distinction is itself deterministic and stated up front, not adjudicated
    # per-provider after the fact.
    hard_fail = any(r for r in reasons if not r.startswith("output was not a bare JSON"))
    return ValidationResult(passed=not hard_fail, reasons=reasons)


def write_task_file(packet: dict, path: str | Path) -> tuple[str, int]:
    """File-based transport (Phase 2B safe-transport mitigation): writes the canonical task
    packet as UTF-8 JSON, ensure_ascii=False so non-ASCII punctuation/Hangul is stored as real
    code points rather than \\uXXXX escapes. Returns (sha256_of_bytes_on_disk, byte_length) —
    computed by reading the file straight back, never from the in-memory string, so the hash is
    what a reader will actually see on disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(packet, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8", newline="\n")
    written = path.read_bytes()
    import hashlib
    return hashlib.sha256(written).hexdigest(), len(written)


def validate_output_file(path: str | Path) -> ValidationResult:
    """Thin file-based wrapper — reads the result file as UTF-8 text and hands it to the
    existing validate_output() unchanged. Validation semantics are not re-implemented here."""
    path = Path(path)
    raw_text = path.read_text(encoding="utf-8")
    return validate_output(raw_text)
