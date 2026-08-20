from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from zju_learning_tools.auth import Authenticator


class AuthenticationTests(unittest.TestCase):
    def test_mock_cas_redirect_chain_and_encrypted_password(self) -> None:
        requests: list[tuple[str, str, bytes]] = []
        login_page = b'<html><input name="execution" value="exec-canary"></html>'

        def handler(request: httpx.Request) -> httpx.Response:
            body = request.content
            requests.append((request.method, str(request.url), body))
            host = request.url.host
            path = request.url.path
            if host == "courses.zju.edu.cn" and path == "/user/index":
                return httpx.Response(
                    302,
                    headers={"location": "https://identity.zju.edu.cn/auth/realms/zju/protocol/cas/login?service=https%3A%2F%2Fcourses.zju.edu.cn%2Fuser%2Findex"},
                    request=request,
                )
            if host == "identity.zju.edu.cn" and request.method == "GET":
                return httpx.Response(200, content=login_page, headers={"content-type": "text/html"}, request=request)
            if host == "zjuam.zju.edu.cn" and path == "/cas/v2/getPubKey":
                return httpx.Response(200, json={"exponent": "1", "modulus": "f" * 256}, request=request)
            if host == "identity.zju.edu.cn" and request.method == "POST":
                return httpx.Response(302, headers={"location": "https://courses.zju.edu.cn/landing"}, request=request)
            if host == "courses.zju.edu.cn" and path == "/landing":
                return httpx.Response(200, content=b'<span id="userId" value="42"></span>', request=request)
            if host == "courses.zju.edu.cn" and path == "/api/activities/is-locked":
                return httpx.Response(200, json={"locked": False}, request=request)
            if host == "tgmedia.cmc.zju.edu.cn":
                return httpx.Response(200, content=b"ok", request=request)
            return httpx.Response(404, request=request)

        authenticator = Authenticator()
        authenticator.client.close()
        authenticator.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        with patch("zju_learning_tools.auth.SessionStore.save") as save:
            try:
                result = authenticator.login("3200001234", "canary-password")
            finally:
                authenticator.close()
        self.assertEqual(result["account_last4"], "1234")
        save.assert_called_once()
        transcript = b"\n".join(body for _, _, body in requests)
        self.assertNotIn(b"canary-password", transcript)
        self.assertFalse(any("canary-password" in url for _, url, _ in requests))
        methods = [method for method, _, _ in requests]
        self.assertEqual(methods.count("POST"), 1)


if __name__ == "__main__":
    unittest.main()
