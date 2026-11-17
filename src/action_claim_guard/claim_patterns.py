#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Japanese-language high-impact action claim patterns.

Input text is not retained by this module. Pattern extraction is heuristic.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def critical_action_claims(text: str) -> list[dict[str, str]]:
    """Extract deterministic high-impact claims from Japanese output."""
    value = _norm(text)
    claims: list[dict[str, str]] = []
    patterns = [
        ("save_completed", r"(?:WORLD|メモリ|記憶|ファイル|ストレージ|永続データ|データベース|DB|設定ファイル)(?:[をへに]|への)?(?:保存|記録|登録)(?:し|をし|が)?(?:ました|た|済み|完了)"),
        ("execution_completed", r"(?:(?:設定ファイル|構成ファイル|システム設定|実設定)(?:[をへに]|の)?(?:更新|変更|上書き)(?:し|をし|が)?(?:ました|た|済み|完了)|(?:ファイル|データ|レコード|項目|アカウント)(?:[を]|の)?(?:削除|消去|解除)(?:し|をし|が)?(?:ました|た|済み|完了)|(?:コマンド|capability|ツール|tool|スクリプト|プログラム|Web検索|ネット検索|ログ検索|ログ取得)(?:[を]|の)?(?:実行|処理)(?:し|をし|が)?(?:ました|た|済み|完了))"),
        ("schedule_completed", r"(?:予定|スケジュール|リマインダー?|通知)(?:[をへに]|への)?(?:登録|設定)(?:し|をし)?(?:ました|た|済み|完了)"),
        ("world_inspected", r"WORLD(?:全件|全項目)?.{0,12}(?:検査|チェック)(?:し|をし)?(?:ました|た|完了)"),
        ("world_empty", r"WORLD.{0,12}(?:何もない|空です|0件|存在しない|ありません)"),
        ("user_said", r"(?:ユーザー|利用者)(?:が|は).{0,28}(?:言った|話した|指摘した|頼んだ|希望した)"),
    ]
    for claim_type, pattern in patterns:
        for match in re.finditer(pattern, value, re.I):
            claims.append({"claim_type": claim_type, "surface": match.group(0)})
    return claims


__all__ = ["critical_action_claims"]
