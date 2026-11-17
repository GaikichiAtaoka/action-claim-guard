# Action Claim Guard

Receipt-grounded checks for **claims that an AI assistant has taken an action**.

An assistant can write "I saved the file" or "I searched the web" without a
matching tool execution. This package checks a bounded set of **Japanese**
execution-claim patterns against the caller's typed, successful receipts,
and returns a structured decision (pass or blocked), evidence links,
and optional safer replacement wording.

## Status and scope

- **v0.1 alpha**, extracted from a larger private local-agent project into a
  separately testable package with a new Git history.
- Source-available under **PolyForm Noncommercial License 1.0.0**.
  Commercial use requires a separate written license. **Not OSI open source.**
- Local-first and **no runtime dependencies**. No network calls, model
  downloads, telemetry, or persistent conversation storage in the package.
- The included Japanese rules cover common file/memory saves, searches,
  inspections, schedule changes, action cancellation, and related claims.
- Optional caller-supplied structured-LLM classification exists in the lower
  level validate_response_claims API, but its results **do not block** replies.
  Deterministic extracted claims are authoritative for this library's verdict.

## Quick start

Python 3.11+:

    python -m pip install .
    python -m unittest discover -s tests -v
    action-claim-guard --input examples/synthetic_input.json

Python API:

    from action_claim_guard import check_reply

    result = check_reply(
        reply="ファイルに保存しました。",
        receipts=[{"action": "network.search", "ok": True}],
    )
    assert result["status"] == "blocked"

    result = check_reply(
        reply="ファイルに保存しました。",
        receipts=[{"action": "file.write", "ok": True, "action_id": "demo-1"}],
    )
    assert result["status"] == "pass"

The CLI accepts a JSON file containing reply, optional user_message,
and a receipts array. It prints JSON. Exit codes: 0 pass, 2 blocked, 1 invalid.

## Receipt contract

Supply receipts ONLY from a trusted execution layer; never from arbitrary
model-generated text. Each record must be a dict with action (or capability
or operation) and ok: true / operation_succeeded: true / recognized
successful status. Optional action_id or audit_id adds provenance.

For save/modify claims, a **matching action category** is required. For
example, a successful web search does NOT validate a file-save claim.
A world.inspect receipt needs inspection_id and mutation_count: 0.
A current web-search assertion needs a network.search receipt.

The detailed API allows visible_world_refs, user_message_refs and an
optional lower-level model classifier. It never executes actions.

## What the result means

pass means **no mismatch was detected by these rules**, not that all the
reply's facts are true. blocked means a supported rule found a mismatch.
replacement_reply is optional, generated through conservative templates;
the caller decides what to display.

The rules are heuristic, particularly for Japanese negation, future intention,
quoted speech, and paraphrases. They are not a semantic truth detector.
They can have false positives and false negatives. Receipts may also have
their own authenticity, correlation, staleness, or data-quality problems.
**Production integrations must validate and bind receipts to the correct turn
and action independently.**

Do not silently replace evidence-free claims with unverified factual
statements. For high-stakes use, display a generic truthful fallback or
request a new model response with explicit evidence constraints.

## Privacy and provenance

The released files are source-only, with wholly synthetic examples/tests.
No private conversation transcripts, identities, memory database, state,
credentials, recordings, prompts, or original project Git history are
bundled. CLI output may contain the caller's input text; handle that output
as private data if the input contains private information.

## Commercial licensing

See COMMERCIAL-LICENSING.md.
