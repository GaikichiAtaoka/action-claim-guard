"""Small, side-effect-free entry point for action claim verification."""
from __future__ import annotations
from typing import Any
from .engine import validate_response_claims

def check_reply(
    reply: str,
    receipts: list[dict[str, Any]] | None = None,
    *,
    user_message: str = "",
    visible_world_refs: list[dict[str, Any]] | None = None,
    user_message_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check a model reply against already-verified execution receipts."""
    return validate_response_claims(
        user_message=user_message,
        reply=reply,
        retrieval_plan={},
        retrieval_bundle={"model_visible_world_item_refs": visible_world_refs or []},
        capability_validation={},
        executed_actions=receipts or [],
        user_message_refs=user_message_refs,
        call_structured=None,
    )
