# -*- coding: utf-8 -*-
"""Stand-in for the real Codex process during STEP2 transport verification.
Receives the protocol text as argv[1] (one single argument) and writes it verbatim
to a JSON file so the launcher can compare it byte-for-byte against the original.
Never invoked with real Codex involved."""
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "_argv_recorder_output.json"


def main():
    received = sys.argv[1] if len(sys.argv) > 1 else None
    OUT.write_text(
        json.dumps({"argv_len": len(sys.argv), "received_arg1": received}, ensure_ascii=False),
        encoding="utf-8",
    )
    print("RECORDED")


if __name__ == "__main__":
    main()
