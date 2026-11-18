# Action Claim Guard を自分のAIエージェントへ組み込む

このガイドは「実際にツールを実行した証拠（receipt）をどこで作り、AIの回答をいつチェックするか」を説明します。[examples/agent_integration.py](../examples/agent_integration.py) には、実ファイルの一時保存から回答の検証までを通す**実行可能な例**があります。

Action Claim Guardは操作そのものを実行せず、既存のAIの回答を自動で書き換えて公開することもしません。利用側のアプリが**表示直前に検証し、表示する回答を決める**ためのPythonライブラリです。

## 1. まず架空データで試す

Python 3.11以上で、リポジトリのルートから次を実行します。

~~~bash
python -m pip install -e .
python -m unittest discover -s tests -v
action-claim-guard --input examples/synthetic_input.json
python examples/agent_integration.py
python examples/agent_integration.py --skip-write
~~~

通常の例では、一時ディレクトリへ本当にファイルを書き、その成功receiptを受けて `pass` になります。`--skip-write` では操作をせず、モデルが「ファイルに保存しました」と言っても `blocked` になり、安全な代替文を表示します。

一時ディレクトリは実行後に自動削除されます。サンプルはOllama、クラウドAPI、モデル重み、実ユーザーの情報を必要としません。

## 2. エージェントの処理に挟む場所

標準的な流れは次の順番です。

1. AIが行動を要求する。
2. 信頼できる**アプリ側の実行器**がファイル保存や検索を実行する。
3. 実行器が、結果に基づく `action`、`ok`、`status`、`action_id` 等のreceiptを生成する。モデルに成功証拠を作文させない。
4. AIがユーザーに見せる回答案（candidate reply）を作る。
5. **表示前**に `check_reply(candidate_reply, receipts)` を実行する。
6. `pass` の場合だけ元の回答案を採用する。`blocked` の場合は未実施であることを明示するか、正しい実行証拠を加えて回答を再生成する。

~~~python
from action_claim_guard import check_reply

candidate = "ファイルに保存しました。"
# このreceiptは「実行器が成功を確認した後」に生成したものとする。
receipts = [
    {"action": "file.write", "ok": True,
     "status": "completed", "action_id": "synthetic-001"}
]
result = check_reply(reply=candidate, receipts=receipts)
if result["status"] == "pass":
    visible_reply = candidate
else:
    visible_reply = "ファイルへの保存は確認できていません。"
print(visible_reply)
~~~

実際にファイルを保存する手順、失敗時のreceipt、表示までの一連のコードは[サンプル本体](../examples/agent_integration.py)を参照してください。例は `file.write` ですが、検索やスケジュール等も該当する規則の範囲で扱います。

## 3. Receipt の作り方

receiptは**AIが書いた文章とは独立して**生成してください。

~~~json
{"action":"file.write","ok":true,"status":"completed","action_id":"synthetic-001"}
~~~

- `action`：実行器が実行した操作の種類（`file.write`、`network.search` 等）。
- `ok`：本当に成功したときだけ `true`。失敗なら `false`。
- `status`：`completed`、`failed` などの機械的な実行結果。
- `action_id`：その実行を追跡する識別子。作成・保存するのは利用側の責任。
- このサンプルには固定の架空IDを使っています。実運用では各操作で新しく生成し、turn ID、対象ファイル・検索クエリ等と紐付けてください。

例えば、`network.search` の成功を渡しても「ファイルに保存した」証拠にはならず、`file.write` が `ok:false` なら保存完了の主張は `blocked` となります。

重要：ライブラリはreceiptの偽造耐性、同一ターンへの結び付け、保存先の一致、時刻の新しさを完全には保証しません。**実行器側で**実行結果を検証し、モデルが作った文字列をreceiptとして受け入れないでください。

## 4. 元の回答を表示してよいか

`check_reply` は `status`、検出された主張、関連する根拠、条件次第で `replacement_reply` を返します。

- `pass`：対応するルールで矛盾が検出されなかった状態。**回答全体が真実という保証ではありません**。
- `blocked`：このルールセットで検出可能な未裏付けの完了宣言などがある状態。そのまま表示せず、未実施であることを伝えるか、正しい実行結果を使って再生成します。
- `replacement_reply`：一部で提供される参考の言い換え候補。採用するかはアプリ側で判断します。

すべての行動や日本語表現を検出する仕組みではありません。特に引用、否定、将来の予定、複雑な言い換えでは誤検出・見逃しの可能性があります。

## 5. 自分のアプリへの移植チェック

- 候補回答を**ユーザーへ返す前**に検証しているか。
- 直近の実行結果と対象操作の種類が一致するか。
- receiptに前の会話ターンの実行が混ざっていないか。
- 「何も実行していない」場合は空配列を渡し、虚偽の成功を作っていないか。
- 検証失敗時でも元の完了宣言がチャット・通知・音声へ先に流れていないか。
- 実際のAPIキー、会話ログ、ファイル内容をサンプルやGitHubへ出していないか。

## ライセンス

[PolyForm Noncommercial License 1.0.0](../LICENSE) に従う非商用利用向けです。商用利用には[別途の書面許諾](../COMMERCIAL-LICENSING.md)が必要です。公開サンプルは架空データだけを使用しています。
