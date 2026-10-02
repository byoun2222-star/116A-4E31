# -*- coding: utf-8 -*-
"""
STEP2 transport fix — local launcher design.

Intended real --cmd string (ASCII-safe, short, no newlines/angle-brackets, never carries the
protocol body):
    <python> phase2b_startup_launcher.py --protocol-file "<path>" --expected-sha256 <hash> --child <real-child-exe>

The launcher itself:
  1. Verifies the protocol file's SHA-256 against the expected hash BEFORE doing anything else.
     Mismatch => fail-closed: do not decode, do not spawn, exit nonzero.
  2. Decodes the file strictly as UTF-8. Decode failure => fail-closed.
  3. Spawns the child via subprocess with an ARGUMENT LIST (shell=False), so the protocol text
     is handed to CreateProcess as one already-delimited argv element — no shell ever re-parses
     it, so '<' '>' and newlines are not reinterpreted as redirection/line breaks.

In this verification phase the child is dummy_argv_recorder.py, never Codex.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


class LaunchAbort(Exception):
    pass


def verify_and_read_protocol(protocol_file: Path, expected_sha256: str) -> str:
    if not protocol_file.exists():
        raise LaunchAbort(f"protocol file not found: {protocol_file}")
    raw = protocol_file.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise LaunchAbort(f"PROTOCOL HASH MISMATCH: expected={expected_sha256} actual={actual} — fail-closed, child NOT spawned")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as e:
        raise LaunchAbort(f"UTF-8 decode failed: {e} — fail-closed, child NOT spawned")
    return text


def spawn_child_captured(child_argv_prefix, protocol_text: str) -> subprocess.CompletedProcess:
    """Verification-mode spawn: used only against dummy_argv_recorder.py (short-lived,
    exits immediately). Captures output and bounds runtime with a timeout. This is the
    exact call shape already validated by run2b-2891635096a3415b — unchanged."""
    full_argv = list(child_argv_prefix) + [protocol_text]
    return subprocess.run(full_argv, capture_output=True, text=True, shell=False, timeout=30)


def spawn_child_live(child_argv_prefix, protocol_text: str) -> int:
    """Live-mode spawn: used for a real long-lived interactive child (e.g. Codex). No capture
    (stdio inherited from the PTY so the TUI renders and reads input normally), no timeout
    (the child is meant to keep running as the surface's foreground process). Same list-argv,
    shell=False transport as the validated verification-mode path — only I/O handling differs."""
    full_argv = list(child_argv_prefix) + [protocol_text]
    proc = subprocess.run(full_argv, shell=False)
    return proc.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol-file", required=True)
    ap.add_argument("--expected-sha256", required=True)
    ap.add_argument("--live", action="store_true",
                     help="spawn with inherited stdio and no timeout (real interactive child, e.g. Codex)")
    # --child MUST be the last option on the command line: nargs=REMAINDER takes every
    # following token literally (no "looks like an option" classification), so a child
    # argv prefix containing its own flags (e.g. "node.exe codex.js --no-daemon") is not
    # truncated the way plain nargs="+" would truncate it at the first "--..." token.
    ap.add_argument("--child", nargs=argparse.REMAINDER, required=True, help="child executable argv prefix (must be the last option)")
    args = ap.parse_args()
    if not args.child:
        raise LaunchAbort("--child requires at least one token")

    protocol_text = verify_and_read_protocol(Path(args.protocol_file), args.expected_sha256)

    if args.live:
        rc = spawn_child_live(args.child, protocol_text)
        if rc != 0:
            raise LaunchAbort(f"live child exited nonzero: {rc}")
        print("LAUNCHER OK (live mode), child exited 0")
    else:
        proc = spawn_child_captured(args.child, protocol_text)
        if proc.returncode != 0:
            raise LaunchAbort(f"child exited nonzero: {proc.returncode} stderr={proc.stderr}")
        print("LAUNCHER OK, child stdout:", proc.stdout.strip())


if __name__ == "__main__":
    try:
        main()
    except LaunchAbort as e:
        print("LAUNCH ABORTED (fail-closed):", e)
        sys.exit(1)
