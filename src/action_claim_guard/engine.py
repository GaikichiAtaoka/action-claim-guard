#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic claim/receipt consistency checks for assistant replies.

Critical claims are extracted without an LLM and matched to typed receipts.
An optional structured model pass may add non-critical classifications, but a
model failure never disables the deterministic guard.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from .claim_patterns import critical_action_claims

CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "claims": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim_type": {
                        "type": "string",
                        "enum": [
                            "world_empty", "world_present", "world_inspected",
                            "action_completed", "action_scheduled", "action_cancelled",
                            "action_not_completed", "record_available", "record_unavailable", "other",
                        ],
                    },
                    "subject": {"type": "string", "maxLength": 400},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["claim_type", "subject", "confidence"],
            },
        }
    },
    "required": ["claims"],
}


def _extract_claims(
    user_message: str,
    reply: str,
    call_structured: Callable[[list[dict[str, str]], dict[str, Any], dict[str, Any] | None], str],
) -> list[dict[str, Any]]:
    messages = [
        {
            "role": "system",
            "content": (
                "Extract only externally checkable claims from the assistant reply. Return JSON only. "
                "Do not infer hidden intent. Classify whether the reply says WORLD has no records, has records, was inspected, "
                "or whether an action/registration/cancellation completed. Ignore politeness and opinions."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"user_message": user_message, "assistant_reply": reply}, ensure_ascii=False),
        },
    ]
    raw = call_structured(messages, CLAIM_SCHEMA, {
        "temperature": 0.0, "num_predict": 260, "_request_timeout": 120,
    })
    parsed = json.loads(raw)
    return list(parsed.get("claims") or [])


def _successful(row: dict[str, Any]) -> bool:
    # Contradictory receipts must fail closed.
    status = str(row.get("status") or "").lower()
    if (row.get("ok") is False or row.get("operation_succeeded") is False
            or status in {"failed", "failure", "error", "cancelled", "canceled", "rejected"}):
        return False
    return bool(row.get("ok") is True or row.get("operation_succeeded") is True
                or status in {"ok", "success", "completed", "integrated"})


def _action_name(row: dict[str, Any]) -> str:
    return str(row.get("action") or row.get("capability") or row.get("operation") or "")


def _action_receipts(kind: str, receipts: list[dict[str, Any]], subject: str = "") -> list[dict[str, Any]]:
    """Match operation claims by operation kind, not arbitrary successful tools.

    A successful search is never evidence that a file was saved.
    The caller is responsible for the authenticity and correlation of receipts.
    """
    successful = [row for row in receipts if _successful(row)]
    def action_is(row: dict[str, Any], prefixes: tuple[str, ...], suffixes: tuple[str, ...]) -> bool:
        value = _action_name(row).strip().lower()
        return any(value == x or value.startswith(x + ".") for x in prefixes) and any(value.endswith(s) for s in suffixes)
    if kind == "world_inspected":
        return [row for row in successful if _action_name(row) == "world.inspect"
                and row.get("inspection_id") and int(row.get("mutation_count") or 0) == 0]
    if kind in {"schedule_completed", "action_scheduled"}:
        return [row for row in successful if _action_name(row) in {"proactive.create", "proactive.update", "schedule.create", "schedule.update", "reminder.create"}]
    if kind in {"action_cancelled", "schedule_cancelled"}:
        return [row for row in successful if _action_name(row) in {"proactive.cancel", "policy.clear", "schedule.cancel", "reminder.cancel"}]
    subject_value = str(subject or "")
    target = ()
    if re.search(r"記憶|メモリ", subject_value):
        target = ("memory",)
    elif "WORLD" in subject_value.upper():
        target = ("world",)
    elif re.search(r"設定ファイル|構成ファイル|システム設定", subject_value):
        target = ("settings","config","configuration","file")
    elif re.search(r"データベース|ＤＢ|DB", subject_value, re.I):
        target = ("db","database")
    elif re.search(r"ファイル", subject_value):
        target = ("file",)
    elif re.search(r"スクリプト|コマンド|プログラム|ツール", subject_value):
        target = ("script","command","program","tool","capability")
    if kind in {"save_completed", "action_completed"}:
        prefixes = ("world","memory","file","storage","db","database","configuration","config","settings","record")
        return [row for row in successful if action_is(row,
                target or prefixes, (".save",".write",".store",".insert",".record",".create",".put",".update",".set"))]
    if kind == "execution_completed":
        prefixes = ("world","memory","file","storage","db","database","configuration","config","settings","record","command","script","program","capability","tool")
        return [row for row in successful if action_is(row,
                target or prefixes, (".execute",".run",".update",".delete",".remove",".clear",".change",".write",".save",".set",".modify"))]
    if kind == "retrieval_checked":
        return [row for row in successful if _action_name(row) in {
            "logs.search", "logs.record.read", "network.search", "network.fetch",
            "memory.recall", "memory.inspect", "memory.chronology", "memory.day",
            "memory.hub", "file.read", "web.fetch", "web.search"}]
    if kind == "retrieval_found":
        return [row for row in successful if _action_name(row) in {
            "logs.search", "logs.record.read", "memory.recall", "memory.inspect",
            "memory.chronology", "memory.day", "memory.hub",
        } and int(row.get("candidate_count") or row.get("match_count") or 0) > 0]
    if kind == "image_checked":
        return [row for row in successful if _action_name(row) == "attachment.image.interpreted"]
    return []


def _receipt_matches_claim(claim_type: str, receipts: list[dict[str, Any]], subject: str = "") -> bool:
    return bool(_action_receipts(claim_type, receipts, subject))


def _normalized_query(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _query_receipt_matches(query: str, receipts: list[dict[str, Any]]) -> bool:
    successful_searches = [
        row for row in receipts
        if _action_name(row) == "network.search" and _successful(row)
    ]
    wanted = _normalized_query(query)
    if not wanted:
        return bool(successful_searches)

    for row in successful_searches:
        actual = _normalized_query(
            row.get("query") or (row.get("input") or {}).get("query")
        )
        if actual and (actual == wanted or actual in wanted or wanted in actual):
            return True

    # If a query was explicitly extracted, a different query is not evidence.
    # A generic search claim may use the unique successful search receipt.
    return len(successful_searches) == 1 and not any(
        _normalized_query(row.get("query") or (row.get("input") or {}).get("query"))
        for row in successful_searches
    )


def _verified_reuse_receipts(receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A reuse receipt supports reuse and facts, never a current search claim."""
    return [row for row in receipts if _action_name(row) == "research.evidence.reuse"
            and _successful(row) and row.get("evidence_id")]


CLAUSE_BOUNDARY_RE = re.compile(
    r"(?:[。！？!?\n]|(?:ので|から|けど|けれど|のに|ものの|だが|ですが|が)[、\s]|(?:ので|から|けど|けれど|のに|ものの|だが|ですが)[。\n])"
)

FOLLOWING_NON_COMPLETION_RE = re.compile(
    r"^(?:り|りして|方(?:が|は)?(?:いい|良い|おすすめ|適切)|ほう(?:が|は)?(?:いい|良い)|場合|とき|時|なら|としても|としてもいい|らいい|はず|わけ|つもり|こと(?:が|も)?ある)",
    re.I,
)

LOCAL_POTENTIAL_RE = re.compile(
    r"(?:すること(?:が|も)?(?:できる|可能|でき)|できる|できそう|可能な|可能だ|拾ってくること(?:が|も)?できる|参照できる|使える|扱える)",
    re.I,
)

LOCAL_INTENT_FUTURE_RE = re.compile(
    r"(?:しよう|したい|してみよう|してみる(?:ね|よ|予定|つもり|ところ|と思い)|する予定|するつもり|してみます)",
    re.I,
)

LOCAL_NEGATIVE_RE = re.compile(
    r"(?:しない|していな|しなかっ|できな|できていな|未完了|未実行|せず)",
    re.I,
)

LOCAL_CITATION_RE = re.compile(
    r"(?:と言|という|と述べ|と主張|について|に関して|条件|機能|話題|発火|トリガー|誤認|混同)",
    re.I,
)


def _find_clause_bounds(reply: str, start: int, end: int) -> tuple[int, int]:
    """Find the local clause boundaries around [start, end]."""
    prefix = reply[:start]
    boundaries = list(CLAUSE_BOUNDARY_RE.finditer(prefix))
    clause_start = boundaries[-1].end() if boundaries else 0

    suffix = reply[end:]
    boundary = CLAUSE_BOUNDARY_RE.search(suffix)
    clause_end = end + boundary.start() if boundary else len(reply)
    return clause_start, clause_end


def _is_non_completion_context(reply: str, start: int, end: int) -> bool:
    """Return True if the match occurs in a conditional, potential, future, or explanatory clause."""
    # 1. Check direct following suffix (e.g. 検索した + 方がいい / 場合 / なら / り)
    following = reply[end:min(len(reply), end + 30)].strip()
    if FOLLOWING_NON_COMPLETION_RE.search(following):
        return True

    # 2. Extract the local clause surrounding this predicate
    c_start, c_end = _find_clause_bounds(reply, start, end)
    local_clause = reply[c_start:c_end].strip()

    # 3. Check for local potential (e.g. 検索することができる)
    if LOCAL_POTENTIAL_RE.search(local_clause):
        return True

    # 4. Check for local intent / future (e.g. 検索してみよう)
    if LOCAL_INTENT_FUTURE_RE.search(local_clause):
        return True

    # 5. Check for local negative (e.g. 検索していません)
    if LOCAL_NEGATIVE_RE.search(local_clause):
        return True

    # 6. Check for local citation / topic discussion (e.g. 検索機能について)
    if LOCAL_CITATION_RE.search(local_clause):
        return True

    return False


def _repair_unsupported_execution_wording(reply: str, *, has_verified_reuse: bool) -> tuple[str, list[dict[str, Any]]]:
    """Remove only an unsupported current execution assertion and retain its facts."""
    repairs: list[dict[str, Any]] = []
    patterns = [
        (
            re.compile(
                r"(?P<sentence>[^。！？\n]{0,220}?(?:ネット|Web|ウェブ|インターネット)?(?:で|を)?"
                r"(?:検索(?:を)?(?:いたしました|完了しました|試みました|してみました|してみたら|しました|したよ|してみた)|"
                r"調べましたよ|調べました|調べたよ|"
                r"(?:公式サイト|公式ページ|参照先ページ|Webページ)[^。！？\n]{0,24}(?:確認しました|見ました|読みました))[、。！？]?)",
                re.I,
            ),
            "取得済みの検証済み情報に基づいてお答えします。" if has_verified_reuse else "手元で確認できる範囲でお答えします。",
            "searched_current_turn",
        ),
        (
            re.compile(
                r"(?P<sentence>[^。！？\n]{0,220}?"
                r"(?:過去ログ|会話ログ|記録|ログ|検索結果|記憶)"
                r"[^。！？\n]{0,55}?"
                r"(?:確認しました|確認してみた|読みました|調べました|"
                r"参照しました|辿って確認しました|辿り直しました|見つけました|"
                r"にありました|がありました|ありました)[、。！？]?)",
                re.I,
            ),
            "手元で確認できる範囲でお答えします。",
            "retrieval_checked",
        ),
        (
            re.compile(
                r"(?P<sentence>[^。！？\n]{0,220}?(?:WORLD|メモリ|記憶|ファイル|ストレージ|設定ファイル)[^。！？\n]{0,24}(?:保存しました|保存を完了しました|記録しました|登録しました)[、。！？]?)",
                re.I,
            ),
            "（現時点での保存は行っていません）",
            "save_completed",
        ),
        (
            re.compile(
                r"(?P<sentence>[^。！？\n]{0,220}?(?:設定ファイル|構成ファイル|システム設定)[^。！？\n]{0,24}(?:更新しました|変更しました|上書きしました)[、。！？]?)",
                re.I,
            ),
            "（現時点での設定変更は行っていません）",
            "execution_completed",
        ),
    ]

    repaired = reply
    for pattern, replacement, claim_type in patterns:
        def replace(match: re.Match[str]) -> str:
            surface = match.group("sentence")
            repairs.append({
                "claim_type": claim_type, "surface": surface,
                "repair": "execution_wording_replaced_factual_content_preserved",
                "replacement": replacement,
            })
            return replacement
        repaired = pattern.sub(replace, repaired)

    return repaired, repairs


def _deterministic_claim_rows(reply: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    mapping = {
        "save_completed": "action_completed",
        "execution_completed": "action_completed",
        "schedule_completed": "action_scheduled",
        "world_inspected": "world_inspected",
        "world_empty": "world_empty",
        "user_said": "user_said",
    }
    for row in critical_action_claims(reply):
        surface = str(row.get("surface") or "")
        position = reply.find(surface)
        if position >= 0 and _is_non_completion_context(reply, position, position + len(surface)):
            continue
        rows.append({
            "claim_type": mapping.get(str(row.get("claim_type") or ""), str(row.get("claim_type") or "other")),
            "deterministic_type": row.get("claim_type"),
            "subject": surface,
            "confidence": 1.0,
            "source": "deterministic",
        })
    # WORLD presence statements without honorific/action wording.
    for m in re.finditer(r"WORLD.{0,18}(?:項目|記録|内容).{0,10}(?:ある|存在|入って)", reply, re.I):
        if not _is_non_completion_context(reply, m.start(), m.end()):
            rows.append({"claim_type": "world_present", "subject": "WORLD records present", "confidence": 1.0, "source": "deterministic"})
            break
    for m in re.finditer(
        r"(?:過去ログ|会話ログ|記録|検索結果|ログ|記憶)"
        r"[^。！？\n]{0,45}?"
        r"(?:確認しました|確認してみた|読みました|調べました|検索しました|"
        r"辿って確認しました|辿り直しました|見つけました|にありました|がありました|"
        r"ありました)",
        reply,
    ):
        # The quotation preceding "というお話、ちゃんと記録にありました"
        # describes the TOPIC, not a quoted claim about search execution.
        # Preserve the existing conditional/citation guard for all other cases.
        positive_found_claim = bool(re.fullmatch(
            r"(?:記録|ログ|検索結果)(?:に|が)ありました", m.group(0)
        ))
        if positive_found_claim or not _is_non_completion_context(reply, m.start(), m.end()):
            rows.append({
                "claim_type": ("retrieval_found" if positive_found_claim
                               else "retrieval_checked"),
                "subject": m.group(0),
                "confidence": 1.0, "source": "deterministic",
            })
            break
    for m in re.finditer(r"(?:公式サイト|公式ページ|参照先ページ|Webページ).{0,24}(?:確認しました|見ました|読みました)", reply, re.I):
        if not _is_non_completion_context(reply, m.start(), m.end()):
            rows.append({"claim_type": "retrieval_checked", "subject": "current source inspection", "confidence": 1.0, "source": "deterministic"})
            break
    for m in re.finditer(
        r"(?:ネット|Web|ウェブ|インターネット)?(?:で|を)?(?:検索(?:を)?(?:いたしました|完了しました|試みました|してみました|してみたら|しました|したよ|してみた)|調べましたよ|調べました|調べたよ)",
        reply,
    ):
        if not _is_non_completion_context(reply, m.start(), m.end()):
            quoted = re.search(r"[「『`\"]([^」』`\"]{2,200})[」』`\"](?:.{0,20}(?:検索|query|クエリ))?", reply, re.I)
            rows.append({
                "claim_type": "search_executed", "subject": "network search execution",
                "query": quoted.group(1).strip() if quoted else "", "confidence": 1.0, "source": "deterministic",
            })
            break
    for m in re.finditer(r"画像.{0,18}(?:確認しました|見ました|読みました|読めました)", reply):
        if not _is_non_completion_context(reply, m.start(), m.end()):
            rows.append({"claim_type": "image_checked", "subject": "image inspection", "confidence": 1.0, "source": "deterministic"})
            break
    for m in re.finditer(
        r"((?:(?:これから|順次|後で|その都度|しばらく)[^。！？!?]{0,80})?"
        r"(?:検査|検索|調査|確認|報告|通知)[^。！？!?]{0,18}"
        r"(?:開始します|着手します|進めます|していきます|報告します|知らせます))",
        reply,
    ):
        if not _is_non_completion_context(reply, m.start(), m.end()):
            rows.append({
                "claim_type": "action_scheduled", "deterministic_type": "schedule_completed",
                "subject": m.group(1), "confidence": 1.0, "source": "deterministic",
            })
            break
    return rows


def _matching_receipts(claim: dict[str, Any], receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the concrete machine receipts that support a typed claim.

    This deliberately records observable support, not hidden model attention.
    """
    kind = str(claim.get("claim_type") or "")
    successful = [row for row in receipts if _successful(row)]
    if kind == "world_inspected":
        return [row for row in successful if _action_name(row) == "world.inspect"
                and row.get("inspection_id") and int(row.get("mutation_count") or 0) == 0]
    if kind == "search_executed":
        query = str(claim.get("query") or "")
        return [row for row in successful if _action_name(row) == "network.search"
                and _query_receipt_matches(query, [row])]
    if kind in {"retrieval_checked", "retrieval_found"}:
        allowed = {
            "logs.search", "logs.record.read", "network.search", "network.fetch",
            "historical.action.read", "memory.recall", "memory.inspect",
            "memory.chronology", "memory.day", "memory.hub",
        }
        if kind == "retrieval_found":
            allowed &= {"logs.search", "logs.record.read", "memory.recall",
                        "memory.inspect", "memory.chronology", "memory.day", "memory.hub"}
            return [
                row for row in successful if _action_name(row) in allowed
                and int(row.get("candidate_count") or row.get("match_count") or 0) > 0
            ]
        return [row for row in successful if _action_name(row) in allowed]
    if kind == "image_checked":
        return [row for row in successful if _action_name(row) == "attachment.image.interpreted"]
    if kind in {"action_completed", "action_scheduled", "action_cancelled"}:
        deterministic_type = str(claim.get("deterministic_type") or kind)
        return _action_receipts(deterministic_type, successful, str(claim.get("subject") or ""))
    if kind == "user_said":
        return []
    return []


def validate_response_claims(
    *,
    user_message: str,
    reply: str,
    retrieval_plan: dict[str, Any],
    retrieval_bundle: dict[str, Any],
    capability_validation: dict[str, Any],
    executed_actions: list[dict[str, Any]],
    call_structured: Callable[[list[dict[str, str]], dict[str, Any], dict[str, Any] | None], str] | None = None,
    mutation_receipts: list[dict[str, Any]] | None = None,
    user_message_refs: list[dict[str, Any]] | None = None,
    evidence_facts: list[dict[str, Any]] | None = None,
    historical_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    visible_world_refs = list(
        retrieval_bundle.get("model_visible_world_item_refs")
        or retrieval_bundle.get("world_item_refs")
        or []
    )
    receipts = [row for row in (executed_actions or []) if isinstance(row, dict)]
    receipts.extend(row for row in (mutation_receipts or []) if isinstance(row, dict))
    receipts.extend(row for row in (historical_actions or []) if isinstance(row, dict))
    deterministic = _deterministic_claim_rows(reply)
    result: dict[str, Any] = {
        "status": "pass",
        "claims": list(deterministic),
        "deterministic_claims": list(deterministic),
        "model_claims": [],
        "model_check_status": "not_requested",
        "violations": [],
        "world_item_count": len(visible_world_refs),
        "world_item_ids": [str(row.get("world_id") or "") for row in visible_world_refs],
        "executed_action_count": len(receipts),
        "receipt_actions": [_action_name(row) for row in receipts if _action_name(row)],
        "rewritten": False,
        "replacement_reply": "",
        "support_edges": [],
        "claim_support_matrix": {
            "searched_current_turn": {"required_action": "network.search", "supported": False},
            "fetched_current_turn": {"required_action": "network.fetch", "supported": False},
            "reused_verified_evidence": {"required_action": "research.evidence.reuse", "supported": False},
            "retrieved_log_record": {"required_action": "logs.record.read", "supported": False},
            "factual_claim_supported": {"authority": "valid_evidence_support_edge", "supported": False},
        },
    }
    result["claim_support_matrix"]["searched_current_turn"]["supported"] = any(
        _action_name(row) == "network.search" and _successful(row) for row in receipts)
    result["claim_support_matrix"]["fetched_current_turn"]["supported"] = any(
        _action_name(row) == "network.fetch" and _successful(row) for row in receipts)
    reuse_receipts = _verified_reuse_receipts(receipts)
    result["claim_support_matrix"]["reused_verified_evidence"].update({
        "supported": bool(reuse_receipts),
        "action_ids": [str(row.get("audit_id") or row.get("action_id") or "") for row in reuse_receipts],
        "evidence_ids": [str(row.get("evidence_id") or "") for row in reuse_receipts],
    })
    result["claim_support_matrix"]["retrieved_log_record"]["supported"] = any(
        _action_name(row) == "logs.record.read" and _successful(row) for row in receipts)

    if call_structured is not None:
        try:
            model_claims = _extract_claims(user_message, reply, call_structured)
            result["model_claims"] = model_claims
            result["model_check_status"] = "completed"
            # The LLM pass may add claims, never remove deterministic ones.
            for row in model_claims:
                candidate = dict(row)
                candidate["source"] = "structured_model"
                if not any(
                    existing.get("claim_type") == candidate.get("claim_type")
                    and existing.get("subject") == candidate.get("subject")
                    for existing in result["claims"]
                ):
                    result["claims"].append(candidate)
        except Exception as exc:
            result["model_check_status"] = "failed_non_authoritative"
            result["model_check_error"] = str(exc)

    world_count = int(result["world_item_count"])
    # Only deterministic extraction can block a response.  Structured-model
    # classifications remain advisory telemetry and may never invent a
    # blocking claim.
    for claim in result["deterministic_claims"]:
        claim_id = f"claim_{len(result['support_edges']) + 1:03d}"
        claim["claim_id"] = claim_id
        kind = str(claim.get("claim_type") or "other")
        confidence = float(claim.get("confidence") or 0.0)
        if confidence < 0.55:
            continue
        if kind == "world_empty" and world_count > 0:
            result["violations"].append({
                "type": "world_empty_contradicts_model_visible_retrieval",
                "world_item_count": world_count,
                "world_item_ids": result["world_item_ids"],
            })
        elif kind == "world_inspected" and not _receipt_matches_claim("world_inspected", receipts):
            result["violations"].append({"type": "world_inspection_claim_without_completed_receipt"})
        elif kind in {"action_completed", "action_scheduled", "action_cancelled"}:
            deterministic_type = str(claim.get("deterministic_type") or kind)
            match_type = {
                "schedule_completed": "schedule_completed",
                "action_scheduled": "schedule_completed",
                "action_cancelled": "action_cancelled",
            }.get(deterministic_type, deterministic_type if deterministic_type in {"save_completed", "execution_completed"} else kind)
            if not _receipt_matches_claim(match_type, receipts, str(claim.get("subject") or "")):
                result["violations"].append({
                    "type": "action_claim_without_matching_receipt",
                    "claim_type": kind,
                    "subject": claim.get("subject"),
                })
        elif kind in {"retrieval_checked", "retrieval_found", "image_checked"} and not _receipt_matches_claim(kind, receipts):
            result["violations"].append({"type": f"{kind}_claim_without_matching_evidence", "subject": claim.get("subject")})
        elif kind == "search_executed" and not _query_receipt_matches(str(claim.get("query") or ""), receipts):
            result["violations"].append({
                "type": "search_claim_without_matching_query_receipt",
                "subject": claim.get("subject"), "query": claim.get("query"),
            })
        elif kind == "user_said" and not (user_message_refs or []):
            result["violations"].append({"type": "user_statement_claim_without_message_ref"})

        supporting = _matching_receipts(claim, receipts)
        result["support_edges"].append({
            "claim_id": claim_id,
            "claim_type": kind,
            "subject": claim.get("subject"),
            "query": claim.get("query", ""),
            "supported": bool(supporting) or kind in {"world_present"},
            "action_ids": [str(row.get("audit_id") or row.get("action_id") or "")
                           for row in supporting if row.get("audit_id") or row.get("action_id")],
            "actions": [_action_name(row) for row in supporting if _action_name(row)],
            "evidence_ids": [str(row.get("evidence_id") or "")
                             for row in supporting if row.get("evidence_id")],
            "receipt_count": len(supporting),
        })

    for fact in evidence_facts or []:
        field = str(fact.get("field") or "")
        value = str(fact.get("value") or "")
        if field == "birthdate" and re.search(r"(?:誕生日|生年月日)", user_message):
            try:
                year, month, day = value.split("-")
                alternatives = (value, f"{int(year)}年{int(month)}月{int(day)}日")
            except ValueError:
                alternatives = (value,)
            if value and not any(item in reply for item in alternatives):
                result["violations"].append({"type": "verified_fact_field_omitted", "field": field, "value": value})
        if field == "age_on_reference_date" and re.search(r"(?:年齢|何歳)", user_message):
            if value and not re.search(rf"(?<!\d){re.escape(value)}\s*歳", reply):
                result["violations"].append({"type": "verified_fact_field_omitted", "field": field, "value": value})

    if not result["violations"]:
        result["image_inspection_supported"] = _receipt_matches_claim("image_checked", receipts)
        return result

    result["status"] = "blocked"
    result["rewritten"] = True
    types = {str(row.get("type") or "") for row in result["violations"]}
    repaired, repairs = _repair_unsupported_execution_wording(
        reply, has_verified_reuse=bool(reuse_receipts),
    )
    if repairs and repaired.strip() and repaired != reply:
        result["replacement_reply"] = repaired
        result["repair_mode"] = "partial_claim_repair"
        result["repairs"] = repairs
        result["internal_diagnostic_user_visible"] = False
        return result

    if "world_empty_contradicts_model_visible_retrieval" in types:
        result["replacement_reply"] = "手元に確認できる記録があるので、そちらを踏まえてお答えしますね。"
    elif "world_inspection_claim_without_completed_receipt" in types:
        result["replacement_reply"] = "まだ手元の確認は完了していませんが、今の時点での知識としてお答えしますね。"
    elif "user_statement_claim_without_message_ref" in types:
        result["replacement_reply"] = "直前の発言として確認できていないため、確実な事実としての断定は控えますね。"
    else:
        result["replacement_reply"] = "まだ実際の操作や確認は完了していませんが、手元でわかる範囲からお答えしますね。"
    return result


__all__ = ["validate_response_claims"]
