"""Synthetic agent integration: receipts originate from executor only."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from examples.agent_integration import (
    SIMULATED_MODEL_REPLY,
    execute_file_write,
    run_demo,
    verify_before_display,
)


class ClaimGuardIntegrationTests(unittest.TestCase):
    def test_successful_write_yields_matching_receipt(self):
        with tempfile.TemporaryDirectory() as work:
            target = Path(work) / "test_note.txt"
            receipt = execute_file_write(target, "synthetic text\n")
            self.assertTrue(receipt["ok"])
            self.assertEqual(target.read_text(), "synthetic text\n")
            outcome = verify_before_display(SIMULATED_MODEL_REPLY, [receipt])
            self.assertEqual(outcome["status"], "pass")
            self.assertEqual(outcome["visible_reply"], SIMULATED_MODEL_REPLY)

    def test_unexecuted_action_claim_is_not_displayed(self):
        outcome = verify_before_display(SIMULATED_MODEL_REPLY, [])
        self.assertEqual(outcome["status"], "blocked")
        self.assertNotEqual(outcome["visible_reply"], SIMULATED_MODEL_REPLY)

    def test_wrong_kind_of_success_does_not_support_save(self):
        outcome = verify_before_display(
            SIMULATED_MODEL_REPLY, [{"action": "network.search", "ok": True}]
        )
        self.assertEqual(outcome["status"], "blocked")

    def test_failed_receipt_blocks_completion_claim(self):
        outcome = verify_before_display(
            SIMULATED_MODEL_REPLY,
            [{"action": "file.write", "ok": False, "status": "failed"}],
        )
        self.assertEqual(outcome["status"], "blocked")

    def test_no_write_mode_is_isolated(self):
        result = run_demo(skip_write=True)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["write_completed"])

    def test_default_demo_uses_temporary_file(self):
        result = run_demo()
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["write_completed"])


if __name__ == "__main__":
    unittest.main()
