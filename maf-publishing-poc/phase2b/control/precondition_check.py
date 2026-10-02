# -*- coding: utf-8 -*-
"""STEP 1 — Phase 2B precondition batch check. Pure deterministic, no AI analysis.
Runs all checks once, prints a single structured result."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

CHECKPOINT = Path(r"C:\Users\a\.cys\pack\round\WORKER_PHASE2B_CHECKPOINT_20260918.md")
PROTOCOL_V1 = Path(r"C:\Users\a\.cys\pack\round\evidence\phase2b-bootstrap-submit\token_protocol_message.txt")
EXPECTED_PROTOCOL_SHA256 = "987f45d3bea0648fd6c657c57d17e7c71e9065ac79e9ed675fb31608f43e4572"
TOKEN_MANIFEST_PY = Path(__file__).resolve().parent / "token_manifest.py"
TOKEN_MANIFEST_JSON = Path(__file__).resolve().parent / "token_manifest.json"

PRODUCTION_ROLES = {"master", "cso", "worker", "worker-1", "worker-2", "worker-3"}
PHASE2B_KNOWN_ROLES = {"worker-4", "worker-5", "worker-6", "worker-8"}

result = {}

# 1. authoritative checkpoint exists + hash
if CHECKPOINT.exists():
    data = CHECKPOINT.read_bytes()
    result["checkpoint_exists"] = True
    result["checkpoint_sha256"] = hashlib.sha256(data).hexdigest()
else:
    result["checkpoint_exists"] = False
    result["checkpoint_sha256"] = None

# 2. Protocol V1 original exists
result["protocol_v1_exists"] = PROTOCOL_V1.exists()

# 3. Protocol V1 sha256 exact match
if PROTOCOL_V1.exists():
    proto_bytes = PROTOCOL_V1.read_bytes()
    actual_hash = hashlib.sha256(proto_bytes).hexdigest()
    result["protocol_v1_sha256_actual"] = actual_hash
    result["protocol_v1_sha256_match"] = (actual_hash == EXPECTED_PROTOCOL_SHA256)
else:
    result["protocol_v1_sha256_actual"] = None
    result["protocol_v1_sha256_match"] = False

# 4. token_manifest.py exists
result["token_manifest_py_exists"] = TOKEN_MANIFEST_PY.exists()

# 5. token_manifest.json exists
result["token_manifest_json_exists"] = TOKEN_MANIFEST_JSON.exists()

# 6. current CYS surfaces/roles
try:
    proc = subprocess.run(["cys", "status", "--json"], capture_output=True, text=True, timeout=15.0)
    result["cys_status_rc"] = proc.returncode
    if proc.returncode == 0 and proc.stdout.strip():
        status = json.loads(proc.stdout)
        surfaces = status.get("surfaces", [])
        result["current_roles"] = sorted(set(s.get("role") for s in surfaces if s.get("role")))
        result["daemon_ok"] = True
    else:
        result["current_roles"] = []
        result["daemon_ok"] = False
except Exception as e:
    result["cys_status_rc"] = None
    result["current_roles"] = []
    result["daemon_ok"] = False
    result["cys_status_error"] = str(e)

# 7. pick one unused fresh worker role name
existing = set(result.get("current_roles", []))
fresh_role = None
for i in range(10, 100):
    candidate = f"worker-{i}"
    if candidate not in existing and candidate not in PRODUCTION_ROLES:
        fresh_role = candidate
        break
result["fresh_role_candidate"] = fresh_role

# 8. confirm no production/Phase2B surfaces will be touched (informational — this script changes nothing)
result["existing_roles_untouched"] = True  # this script performs no writes

# 9. target-policy current state (read phase2b allowlist constant, read-only)
try:
    adapter_path = Path(__file__).resolve().parent.parent / "controlled_adapter" / "controlled_cys_adapter.py"
    adapter_src = adapter_path.read_text(encoding="utf-8")
    result["target_policy_file_exists"] = True
    result["target_policy_allowlist_literal_present"] = "PHASE2B_ALLOWED_TEST_ROLES" in adapter_src
except Exception as e:
    result["target_policy_file_exists"] = False
    result["target_policy_allowlist_literal_present"] = False

# 10. daemon normal
result["daemon_normal"] = result.get("daemon_ok", False)

# ---- overall verdict ----
required = [
    result["checkpoint_exists"],
    result["protocol_v1_exists"],
    result["protocol_v1_sha256_match"],
    result["token_manifest_py_exists"],
    result["token_manifest_json_exists"],
    result["daemon_normal"],
    result["fresh_role_candidate"] is not None,
]
result["PRECONDITION"] = "PASS" if all(required) else "FAIL"

print(json.dumps(result, ensure_ascii=False, indent=2))
