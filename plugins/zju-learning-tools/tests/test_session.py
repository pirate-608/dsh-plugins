from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
import httpx

from zju_learning_tools.session import SessionStore


class SessionTests(unittest.TestCase):
    def test_encrypted_atomic_session_contains_no_plain_secrets(self) -> None:
        key = Fernet.generate_key().decode("ascii")
        cookies = httpx.Cookies()
        cookies.set("session", "canary-cookie-secret", domain="courses.zju.edu.cn", path="/")
        cookies.set("wide", "courses-only", domain=".zju.edu.cn", path="/")
        cookies.set("classroom", "cmc-only", domain=".cmc.zju.edu.cn", path="/")
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCALAPPDATA": temporary}), patch(
            "zju_learning_tools.session.keyring.get_password", return_value=key
        ), patch("zju_learning_tools.session.keyring.set_password"):
            store = SessionStore()
            store.save(cookies.jar, account="3200001234", user_id="42", ttl_hours=1)
            target = Path(temporary) / "pirate-608" / "zju-learning-tools" / "session.enc"
            self.assertTrue(target.is_file())
            self.assertNotIn(b"canary-cookie-secret", target.read_bytes())
            self.assertFalse(target.with_suffix(".tmp").exists())
            payload = store.load()
            self.assertEqual(payload["account_last4"], "1234")
            self.assertEqual(payload["user_id"], "42")
            self.assertGreater(datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00")), datetime.now(timezone.utc))
            restored = store.cookies()
            self.assertEqual(restored.get("session", domain="courses.zju.edu.cn", path="/"), "canary-cookie-secret")
            course_cookies = store.cookies("courses")
            classroom_cookies = store.cookies("classroom")
            self.assertEqual(course_cookies.get("wide", domain=".zju.edu.cn", path="/"), "courses-only")
            self.assertEqual(classroom_cookies.get("classroom", domain=".cmc.zju.edu.cn", path="/"), "cmc-only")
            self.assertNotIn("classroom", {cookie.name for cookie in course_cookies.jar})
            self.assertNotIn("wide", {cookie.name for cookie in classroom_cookies.jar})


if __name__ == "__main__":
    unittest.main()
