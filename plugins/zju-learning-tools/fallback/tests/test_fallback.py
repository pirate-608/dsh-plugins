from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from zju_tronclass_fallback import cli


class FallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"LOCALAPPDATA": self.temporary.name})
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def test_read_operations_use_fixed_cli_arguments(self) -> None:
        seen: list[list[str]] = []

        def fake(arguments: list[str], *, interactive: bool = False) -> str:
            seen.append(arguments)
            return "fixture"

        with patch.object(cli, "_invoke_tcc", side_effect=fake):
            self.assertTrue(cli._read("todo")["ok"])
            self.assertTrue(cli._read("courses")["ok"])
            self.assertTrue(cli._read("activities", course_id="12")["ok"])
            self.assertTrue(cli._read("activity", activity_id="34")["ok"])
            self.assertTrue(cli._read("assignments", course_id="12")["ok"])
        flattened = [argument for invocation in seen for argument in invocation]
        for forbidden in ("submit", "--api-url", "--username", "password", "glob"):
            self.assertNotIn(forbidden, flattened)

    def test_destination_is_scoped_versioned_and_rejects_unsafe_names(self) -> None:
        root = Path(self.temporary.name).resolve()
        first = root / "notes.pdf"
        first.write_bytes(b"old")
        self.assertEqual(cli._safe_destination(str(root), "notes.pdf"), root / "notes-v2.pdf")
        for filename in ("../escape", "C:\\escape.txt", "name:stream", "CON"):
            with self.assertRaises(ValueError):
                cli._safe_destination(str(root), filename)

    def test_config_contains_no_password_and_status_masks_account(self) -> None:
        key = Fernet.generate_key()
        with patch.object(cli.keyring, "get_password", return_value=key.decode("ascii")):
            cli._save_config({
                "session": {"username": "3123456789", "auth_provider": "zju", "save_credentials": False},
                "api": {"api_url": "zju"},
            })
            raw = cli._config_path().read_bytes()
            self.assertNotIn(b"3123456789", raw)
            self.assertNotIn(b"password", raw.lower())
            status = cli._status()
        self.assertEqual(status["data"]["account_last4"], "6789")
        self.assertNotIn("3123456789", json.dumps(status))

    def test_parser_does_not_expose_remote_writes_or_raw_cli_args(self) -> None:
        help_text = cli.build_parser().format_help().lower()
        for forbidden in ("submit", "quiz", "rollcall", "raw", "url", "command"):
            self.assertNotIn(forbidden, help_text)

    def test_session_cache_is_encrypted_and_restored(self) -> None:
        key = Fernet.generate_key()
        cache = Path(self.temporary.name) / "plain-cache"
        cache.mkdir()
        (cache / "cache.dat").write_bytes(b"session-cookie-canary")
        with patch.object(cli.keyring, "get_password", return_value=key.decode("ascii")):
            cli._save_cache(cache)
            encrypted = cli._session_path().read_bytes()
            self.assertNotIn(b"session-cookie-canary", encrypted)
            restored = Path(self.temporary.name) / "restored"
            restored.mkdir()
            cli._restore_cache(restored)
        self.assertEqual((restored / "cache.dat").read_bytes(), b"session-cookie-canary")

    def test_output_redacts_secrets_and_non_zju_urls(self) -> None:
        cleaned = cli._safe_text("<b>course</b> token=secret-canary https://evil.example/x https://courses.zju.edu.cn/course/1")
        self.assertNotIn("secret-canary", cleaned)
        self.assertNotIn("evil.example", cleaned)
        self.assertNotIn("<b>", cleaned)
        self.assertIn("https://courses.zju.edu.cn/course/1", cleaned)


if __name__ == "__main__":
    unittest.main()
