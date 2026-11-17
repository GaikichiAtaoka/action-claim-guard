"""Synthetic, isolated contract tests (no private conversation data)."""
from __future__ import annotations
import json
import unittest
from action_claim_guard import check_reply

class ClaimGuardTests(unittest.TestCase):
    def check(self, reply, receipts=None, **kwargs):
        return check_reply(reply, receipts or [], **kwargs)

    def test_plain_chat_passes(self):
        self.assertEqual(self.check("こんにちは。今日はいい日ですね。")["status"], "pass")

    def test_unsaved_file_blocked(self):
        self.assertEqual(self.check("ファイルに保存しました。")["status"], "blocked")

    def test_saved_file_matching_receipt(self):
        self.assertEqual(self.check("ファイルに保存しました。", [{"action":"file.write", "ok":True}])["status"], "pass")

    def test_search_receipt_does_not_prove_save(self):
        self.assertEqual(self.check("ファイルに保存しました。", [{"action":"network.search", "ok":True}])["status"], "blocked")

    def test_memory_claim_rejects_file_write_receipt(self):
        self.assertEqual(self.check("メモリに保存しました。", [{"action":"file.write","ok":True}])["status"], "blocked")

    def test_file_claim_rejects_memory_store_receipt(self):
        self.assertEqual(self.check("ファイルに保存しました。", [{"action":"memory.store","ok":True}])["status"], "blocked")

    def test_script_claim_rejects_file_write(self):
        self.assertEqual(self.check("スクリプトを実行しました。", [{"action":"file.write","ok":True}])["status"], "blocked")

    def test_failed_save_not_counted(self):
        self.assertEqual(self.check("ファイルに保存しました。", [{"action":"file.write", "ok":False, "status":"failed"}])["status"], "blocked")

    def test_memory_store_matches(self):
        self.assertEqual(self.check("メモリに保存しました。", [{"action":"memory.store", "ok":True}])["status"], "pass")

    def test_script_without_receipt(self):
        self.assertEqual(self.check("スクリプトを実行しました。")["status"], "blocked")

    def test_script_with_matching_receipt(self):
        self.assertEqual(self.check("スクリプトを実行しました。", [{"action":"script.run", "ok":True}])["status"], "pass")

    def test_web_search_without_receipt(self):
        self.assertEqual(self.check("ネットで検索しました。最新情報です。")["status"], "blocked")

    def test_web_search_matching_receipt(self):
        self.assertEqual(self.check("ネットで検索しました。", [{"action":"network.search","query":"demo","ok":True}])["status"], "pass")

    def test_future_search_intent(self):
        self.assertEqual(self.check("必要ならネットで検索してみようと思います。")["status"], "pass")

    def test_conditional_search(self):
        self.assertEqual(self.check("検索した方がいいと思います。")["status"], "pass")

    def test_quoted_report(self):
        self.assertEqual(self.check("『検索しました』という表現について話しましょう。")["status"], "pass")

    def test_found_record_without_receipt(self):
        self.assertEqual(self.check("記録にありました。")["status"], "blocked")

    def test_record_found_with_count(self):
        self.assertEqual(self.check("記録にありました。", [{"action":"memory.recall","ok":True,"match_count":2}])["status"], "pass")

    def test_image_without_receipt(self):
        self.assertEqual(self.check("画像を確認しました。")["status"], "blocked")

    def test_image_with_receipt(self):
        self.assertEqual(self.check("画像を確認しました。", [{"action":"attachment.image.interpreted","ok":True}])["status"], "pass")

    def test_world_inspection_needs_proof(self):
        self.assertEqual(self.check("WORLD全件検査しました。")["status"], "blocked")

    def test_world_inspection_verified(self):
        self.assertEqual(self.check("WORLD全件検査しました。", [{"action":"world.inspect","inspection_id":"synthetic","mutation_count":0,"ok":True}])["status"], "pass")

    def test_schedule_with_proactive(self):
        self.assertEqual(self.check("リマインダーを登録しました。", [{"action":"proactive.create","ok":True}])["status"], "pass")

    def test_schedule_without_receipt(self):
        self.assertEqual(self.check("リマインダーを登録しました。")["status"], "blocked")

    def test_neutral_user_said_no_ref(self):
        self.assertEqual(self.check("ユーザーが言ったことを覚えています。")["status"], "blocked")

    def test_neutral_user_said_with_ref(self):
        self.assertEqual(self.check("ユーザーが言ったことを覚えています。", user_message_refs=[{"id":"synthetic"}])["status"], "pass")

    def test_support_edges_for_successful_save(self):
        result=self.check("ファイルに保存しました。",[{"action":"file.write","ok":True,"action_id":"demo"}])
        self.assertTrue(any("demo" in row.get("action_ids",[]) for row in result["support_edges"]))

    def test_contradictory_receipt_explicit_failure_wins(self):
        self.assertEqual(self.check("ファイルに保存しました.", [{"action":"file.write","ok":False,"status":"completed"}])["status"], "blocked")

    def test_contradictory_status_failure_wins(self):
        self.assertEqual(self.check("ファイルに保存しました.", [{"action":"file.write","ok":True,"status":"failed"}])["status"], "blocked")

    def test_search_specific_wrong_query(self):
        self.assertFalse(__import__("action_claim_guard.engine",fromlist=["_query_receipt_matches"])._query_receipt_matches(
            "大阪の天気", [{"action":"network.search","query":"東京の天気","ok":True}]))

    def test_search_generic_single_receipt(self):
        self.assertTrue(__import__("action_claim_guard.engine",fromlist=["_query_receipt_matches"])._query_receipt_matches(
            "", [{"action":"network.search","query":"東京の天気","ok":True}]))

    def test_input_immutability(self):
        receipts=[{"action":"file.write","ok":True}]
        before=json.dumps(receipts)
        self.check("ファイルに保存しました。",receipts)
        self.assertEqual(json.dumps(receipts),before)

if __name__=="__main__":
    unittest.main()
