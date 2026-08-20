from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from zju_learning_tools.errors import DownloadRejected, SubmissionRejected
from zju_learning_tools.security import (
    html_to_text,
    is_allowed_url,
    safe_destination,
    safe_remote_filename,
    safe_submission_file,
    sanitize_data,
)
from zju_learning_tools.responses import failure


class SecurityTests(unittest.TestCase):
    def test_html_answer_secret_url_and_id_sanitization(self) -> None:
        payload = {
            "id": 123,
            "description": "<p>Hello <b>student</b></p>",
            "correct_answers": ["A"],
            "Cookie": "canary-cookie",
            "official_url": "https://courses.zju.edu.cn/course/123",
            "evil_url": "https://example.com/steal",
            "start_time": "2026-08-13 09:30:00",
        }
        clean = sanitize_data(payload)
        self.assertEqual(clean["id"], "123")
        self.assertEqual(clean["description"], "Hello student")
        self.assertNotIn("correct_answers", clean)
        self.assertNotIn("Cookie", clean)
        self.assertEqual(clean["official_url"], "https://courses.zju.edu.cn/course/123")
        self.assertEqual(clean["evil_url"], "[URL REMOVED]")
        self.assertEqual(clean["start_time"], "2026-08-13T09:30:00+08:00")

    def test_allowlist_is_exact_https(self) -> None:
        self.assertTrue(is_allowed_url("https://courses.zju.edu.cn/api/todos"))
        self.assertFalse(is_allowed_url("http://courses.zju.edu.cn/api/todos"))
        self.assertFalse(is_allowed_url("https://courses.zju.edu.cn.example.com/"))

    def test_remote_filename_rejections(self) -> None:
        for value in ("../a.pdf", r"C:\a.pdf", r"\\server\share.pdf", "a:b.pdf", "CON.txt", "CON .txt", "a\n.pdf", "safe\u202Efdp.exe"):
            with self.subTest(value=value):
                with self.assertRaises(DownloadRejected):
                    safe_remote_filename(value)
        self.assertEqual(safe_remote_filename("lecture 01.pdf"), "lecture 01.pdf")

    def test_destination_is_scoped_and_versioned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "lecture.pdf").write_bytes(b"old")
            resolved_root, target = safe_destination(str(root), "lecture.pdf")
            self.assertEqual(resolved_root, root)
            self.assertEqual(target.name, "lecture-v2.pdf")
            self.assertEqual(os.path.commonpath([str(root), str(target)]), str(root))

    def test_unexpected_exception_does_not_leak_secret_canary(self) -> None:
        payload = failure(RuntimeError("password=canary-password Cookie=canary-cookie"))
        rendered = str(payload)
        self.assertNotIn("canary-password", rendered)
        self.assertNotIn("canary-cookie", rendered)

    def test_submission_file_must_stay_in_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            approved = base / "approved"
            approved.mkdir()
            inside = approved / "work.zip"
            inside.write_bytes(b"fixture")
            outside = base / "private.txt"
            outside.write_text("secret", encoding="utf-8")
            self.assertEqual(safe_submission_file(str(inside), [str(approved)]), inside)
            with self.assertRaises(SubmissionRejected):
                safe_submission_file(str(outside), [str(approved)])


if __name__ == "__main__":
    unittest.main()
