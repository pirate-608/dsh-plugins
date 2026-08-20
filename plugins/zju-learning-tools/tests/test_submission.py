from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zju_learning_tools.errors import SubmissionRejected, SubmissionStateUnknown, UpstreamChanged
from zju_learning_tools.submission import SubmissionManager


class FakeClient:
    def __init__(self) -> None:
        self.payload = {"account_last4": "1234", "user_id": "42"}
        self.assignment = {
            "id": 77,
            "title": "Reviewed report",
            "type": "homework",
            "course_id": 9,
            "end_time": "2099-08-20T12:00:00+08:00",
            "updated_at": "2026-08-13T00:00:00Z",
        }
        self.history: dict[str, object] = {"list": []}
        self.writes: list[str] = []
        self.upload_ids: list[str] = []
        self.fail_upload = False
        self.submitted_comment_html = ""

    def assignment_snapshot(self, activity_id: str) -> dict[str, object]:
        return {"assignment": dict(self.assignment), "submission_history": self.history}

    def reserve_assignment_upload(self, filename: str, size: int) -> dict[str, object]:
        self.writes.append("reserve")
        upload_id = str(100 + len(self.upload_ids))
        self.upload_ids.append(upload_id)
        return {"id": upload_id, "upload_url": f"https://courses.zju.edu.cn/api/uploads/{upload_id}", "request_id": "reserve-request"}

    def upload_assignment_file(self, upload_url: str, file_path: Path) -> dict[str, object]:
        self.writes.append("upload")
        if self.fail_upload:
            raise SubmissionStateUnknown("fixture unknown")
        return {"request_id": "upload-request"}

    def commit_assignment_submission(self, activity_id: str, upload_ids: list[str], comment_html: str) -> dict[str, object]:
        self.writes.append("commit")
        self.submitted_comment_html = comment_html
        self.history = {"list": [{"id": 1, "uploads": [{"id": int(value)} for value in upload_ids]}]}
        return {"request_id": "commit-request"}


class SubmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"LOCALAPPDATA": self.temporary.name})
        self.environment.start()
        self.root = Path(self.temporary.name) / "reviewed"
        self.root.mkdir()
        self.file = self.root / "report.pdf"
        self.file.write_bytes(b"reviewed fixture")
        self.manager = SubmissionManager()
        self.manager.policy.enable([str(self.root)])
        self.client = FakeClient()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def test_prepare_is_read_only_and_commit_is_verified_once(self) -> None:
        preview = self.manager.prepare(self.client, "77", [str(self.file)], "final version")
        self.assertEqual(self.client.writes, [])
        self.assertEqual(preview["files"][0]["sha256"], "ce9a85bb5c5d562b77484cc44e2e9fd032a39c75223137ff944905a2aed5224b")
        result = self.manager.commit(self.client, str(preview["approval_id"]))
        self.assertEqual(result["status"], "committed")
        self.assertTrue(result["verified"])
        self.assertEqual(self.client.writes, ["reserve", "upload", "commit"])
        with self.assertRaises(SubmissionRejected) as caught:
            self.manager.commit(self.client, str(preview["approval_id"]))
        self.assertEqual(caught.exception.code, "approval_invalid")

    def test_file_mutation_and_revision_change_are_rejected_before_write(self) -> None:
        preview = self.manager.prepare(self.client, "77", [str(self.file)])
        self.file.write_bytes(b"changed after preview")
        with self.assertRaises(SubmissionRejected) as caught:
            self.manager.commit(self.client, str(preview["approval_id"]))
        self.assertEqual(caught.exception.code, "approval_payload_changed")
        self.assertEqual(self.client.writes, [])

        self.file.write_bytes(b"reviewed fixture")
        preview = self.manager.prepare(self.client, "77", [str(self.file)], "new")
        self.client.assignment["updated_at"] = "2026-08-13T01:00:00Z"
        with self.assertRaises(SubmissionRejected) as caught:
            self.manager.commit(self.client, str(preview["approval_id"]))
        self.assertEqual(caught.exception.code, "approval_revision_changed")
        self.assertEqual(self.client.writes, [])

    def test_expired_or_wrong_account_approval_is_rejected(self) -> None:
        preview = self.manager.prepare(self.client, "77", [str(self.file)])
        approval_id = str(preview["approval_id"])
        self.manager._approvals[approval_id] = replace(
            self.manager._approvals[approval_id],
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        with self.assertRaises(SubmissionRejected) as caught:
            self.manager.commit(self.client, approval_id)
        self.assertEqual(caught.exception.code, "approval_expired")

        preview = self.manager.prepare(self.client, "77", [str(self.file)], "account")
        self.client.payload["account_last4"] = "9999"
        with self.assertRaises(SubmissionRejected) as caught:
            self.manager.commit(self.client, str(preview["approval_id"]))
        self.assertEqual(caught.exception.code, "approval_account_changed")

    def test_unknown_write_blocks_identical_retry(self) -> None:
        preview = self.manager.prepare(self.client, "77", [str(self.file)], "uncertain")
        self.client.fail_upload = True
        with self.assertRaises(SubmissionStateUnknown):
            self.manager.commit(self.client, str(preview["approval_id"]))
        self.assertEqual(self.client.writes, ["reserve", "upload"])
        with self.assertRaises(SubmissionRejected) as caught:
            self.manager.prepare(self.client, "77", [str(self.file)], "uncertain")
        self.assertEqual(caught.exception.code, "duplicate_submission_blocked")

    def test_comment_is_html_escaped_and_ledger_contains_no_content(self) -> None:
        preview = self.manager.prepare(self.client, "77", [str(self.file)], '<b>reviewed & final</b>')
        result = self.manager.commit(self.client, str(preview["approval_id"]))
        self.assertEqual(result["status"], "committed")
        self.assertIn("&lt;b&gt;reviewed &amp; final&lt;/b&gt;", self.client.submitted_comment_html)
        self.assertNotIn("<b>", self.client.submitted_comment_html)
        ledger = (Path(self.temporary.name) / "pirate-608" / "zju-learning-tools" / "submission-ledger.json").read_text(encoding="utf-8")
        self.assertNotIn("reviewed & final", ledger)
        self.assertNotIn(str(self.file), ledger)
        self.assertNotIn("report.pdf", ledger)

    def test_expired_homework_is_rejected_before_write(self) -> None:
        self.client.assignment["end_time"] = "2020-01-01T00:00:00+08:00"
        with self.assertRaises(SubmissionRejected):
            self.manager.prepare(self.client, "77", [str(self.file)])
        self.assertEqual(self.client.writes, [])

    def test_unknown_deadline_format_fails_closed(self) -> None:
        self.client.assignment["end_time"] = "sometime later"
        with self.assertRaises(UpstreamChanged) as caught:
            self.manager.prepare(self.client, "77", [str(self.file)])
        self.assertEqual(getattr(caught.exception, "code", None), "upstream_changed")
        self.assertEqual(self.client.writes, [])

    def test_disabled_outside_root_and_non_homework_are_rejected(self) -> None:
        self.manager.policy.disable()
        with self.assertRaises(SubmissionRejected) as caught:
            self.manager.prepare(self.client, "77", [str(self.file)])
        self.assertEqual(caught.exception.code, "write_capability_disabled")

        self.manager.policy.enable([str(self.root)])
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        with self.assertRaises(SubmissionRejected):
            self.manager.prepare(self.client, "77", [str(outside)])

        self.client.assignment["type"] = "exam"
        with self.assertRaises(SubmissionRejected):
            self.manager.prepare(self.client, "77", [str(self.file)])


if __name__ == "__main__":
    unittest.main()
