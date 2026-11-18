#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Runnable local-agent integration: execute -> collect receipt -> guard -> display.

All data is fabricated. The only file write occurs in a temporary directory.
No real LLM or external services are required for this example.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from action_claim_guard import check_reply

SIMULATED_MODEL_REPLY = "ファイルに保存しました。"


def execute_file_write(target: Path, content: str) -> dict[str, Any]:
    """Trusted executor constructs a receipt AFTER a real attempted operation.

    Never ask the model to invent its own successful operation receipt.
    An application should attach its own authenticated turn/action IDs.
    """
    try:
        target.write_text(content, encoding="utf-8")
    except OSError:
        return {
            "action": "file.write",
            "ok": False,
            "status": "failed",
            "action_id": "synthetic-save-attempt-01",
        }
    return {
        "action": "file.write",
        "ok": True,
        "status": "completed",
        "action_id": "synthetic-save-attempt-01",
    }


def verify_before_display(
    candidate_reply: str, trusted_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return both the check and a conservative final user-visible message."""
    outcome = check_reply(reply=candidate_reply, receipts=trusted_receipts)
    if outcome["status"] == "pass":
        visible_reply = candidate_reply
    else:
        # The original claim must NOT reach the user unqualified.
        visible_reply = "ファイルへの保存は確認できていません。"
    return {
        "status": outcome["status"],
        "candidate_reply": candidate_reply,
        "visible_reply": visible_reply,
        "receipt_count": len(trusted_receipts),
        "guard_result": outcome,
    }


def run_demo(*, skip_write: bool = False) -> dict[str, Any]:
    """Use a temporary workspace; real integrations replace this tool adapter."""
    with tempfile.TemporaryDirectory(prefix="action-claim-guard-example-") as work:
        target = Path(work) / "sample_note.txt"
        receipts = [] if skip_write else [
            execute_file_write(target, "This is wholly synthetic demonstration text.\n")
        ]
        result = verify_before_display(SIMULATED_MODEL_REPLY, receipts)
        result["write_completed"] = target.is_file()
        # No example file survives the TemporaryDirectory cleanup.
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-write", action="store_true",
        help="Demonstrate a fabricated model completion claim without execution.",
    )
    args = parser.parse_args(argv)
    result = run_demo(skip_write=args.skip_write)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Blocked is an EXPECTED demonstration result for --skip-write.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
