"""Run a claim check on synthetic/local JSON input; no automatic logging."""
from __future__ import annotations
import argparse
import json
import sys
from .api import check_reply

def main() -> int:
    parser = argparse.ArgumentParser(description="Verify assistant execution claims against receipts")
    parser.add_argument("--input", default="-", help="JSON file, or - for standard input")
    args = parser.parse_args()
    try:
        if args.input == "-":
            payload = json.load(sys.stdin)
        else:
            with open(args.input, "r", encoding="utf-8") as stream:
                payload = json.load(stream)
        if not isinstance(payload, dict) or not isinstance(payload.get("reply"), str):
            raise ValueError("Input must be a JSON object with reply string")
        receipts = payload.get("receipts", [])
        if not isinstance(receipts, list) or any(not isinstance(x, dict) for x in receipts):
            raise ValueError("receipts must be a list of objects")
        result = check_reply(payload["reply"], receipts, user_message=str(payload.get("user_message") or ""))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "pass" else 2
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
