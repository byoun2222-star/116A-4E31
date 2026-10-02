# -*- coding: utf-8 -*-
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_hash as eh

CONFIG = Path(r"C:\Users\a\.codex\config.toml")
OLD_SHA256 = "e7a59e1af1ac87c9ca7d235db9bab44ee0e720d8350377042ca8bf9e8c8606a8"

new_bytes = CONFIG.read_bytes()
new_sha256 = hashlib.sha256(new_bytes).hexdigest()
new_text = new_bytes.decode("utf-8")

# TOML validity check
toml_valid = False
toml_error = None
model_value = None
try:
    import tomllib
    parsed = tomllib.loads(new_text)
    toml_valid = True
    model_value = parsed.get("model")
except Exception as e:
    toml_error = f"{type(e).__name__}: {e}"

# diff check: compare line-by-line against the known original content (captured before edit)
old_lines = [
    'model = "gpt-6.1-sol"',
    'model_reasoning_effort = "low"',
    'service_tier = "default"',
]
new_lines_head = new_text.splitlines()[:3]
only_model_line_changed = (
    new_lines_head[0] == 'model = "gpt-6-sol"'
    and new_lines_head[1] == old_lines[1]
    and new_lines_head[2] == old_lines[2]
)

print("NEW_SHA256:", new_sha256)
print("TOML_VALID:", toml_valid, toml_error)
print("model value (parsed):", model_value)
print("ONLY_MODEL_LINE_CHANGED:", only_model_line_changed)

conn = eh.get_conn()
run_id = eh.start_run(
    objective="Model config fix: config.toml model gpt-6.1-sol -> gpt-6-sol per OWNER APPROVAL, "
              "config-only change, no Codex execution",
    actor="claude-session", provider="LOCAL",
    raw_command="Edit config.toml line 1 (model value only)",
    conn=conn,
)
print("RUN_ID:", run_id)

eh.record_evidence(
    f"Model config changed in C:\\Users\\a\\.codex\\config.toml. OLD_SHA256={OLD_SHA256} "
    f"NEW_SHA256={new_sha256}. OLD model=gpt-6.1-sol NEW model={model_value}. "
    f"TOML_VALID={toml_valid} ({toml_error}). ONLY_MODEL_LINE_CHANGED={only_model_line_changed} "
    f"(verified against lines 2-3 unchanged: model_reasoning_effort, service_tier).",
    "CONFIRMED" if (toml_valid and model_value == "gpt-6-sol" and only_model_line_changed) else "FAILED",
    evidence_path=str(CONFIG),
    run_id=run_id, conn=conn,
)
eh.finalize_run(
    run_id,
    final_status="COMPLETED" if (toml_valid and model_value == "gpt-6-sol" and only_model_line_changed) else "FAILED",
    output_artifacts=[str(CONFIG)],
    validation_result=f"TOML_VALID={toml_valid}, model={model_value}, only_model_line_changed={only_model_line_changed}",
    conn=conn,
)
conn.commit()
conn.close()
print("기록 완료")
