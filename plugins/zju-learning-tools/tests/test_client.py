from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import httpx

from zju_learning_tools.client import ZJUReadClient
from zju_learning_tools.errors import AuthenticationRequired, DownloadRejected, SubmissionStateUnknown, UpstreamChanged, ZJUError


def make_client(handler) -> ZJUReadClient:
    instance = ZJUReadClient.__new__(ZJUReadClient)
    instance.payload = {"account_last4": "1234", "user_id": "42"}
    instance.store = None
    instance.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return instance


class ClientTests(unittest.TestCase):
    def test_json_get_and_write_method_rejection(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            return httpx.Response(200, json={"data": [{"id": 1}]}, request=request)

        client = make_client(handler)
        try:
            self.assertEqual(client.courses("/api/todos"), {"data": [{"id": 1}]})
            with self.assertRaises(ZJUError) as caught:
                client._send("POST", "https://courses.zju.edu.cn/api/topics")
            self.assertEqual(caught.exception.code, "method_rejected")
        finally:
            client.close()

    def test_cross_host_redirect_is_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://evil.example/session"}, request=request)

        client = make_client(handler)
        try:
            with self.assertRaises(ZJUError) as caught:
                client.courses("/api/todos")
            self.assertEqual(caught.exception.code, "network_rejected")
        finally:
            client.close()

    def test_auth_rate_limit_and_contract_drift_are_structured(self) -> None:
        for status, headers, body, expected in (
            (401, {}, b"", AuthenticationRequired),
            (403, {}, b"", AuthenticationRequired),
            (429, {"retry-after": "12"}, b"", ZJUError),
            (200, {"content-type": "text/html"}, b"login", AuthenticationRequired),
            (200, {"content-type": "application/json"}, b"not-json", UpstreamChanged),
        ):
            with self.subTest(status=status, expected=expected):
                def handler(request: httpx.Request, status=status, headers=headers, body=body) -> httpx.Response:
                    return httpx.Response(status, headers=headers, content=body, request=request)

                client = make_client(handler)
                try:
                    with self.assertRaises(expected):
                        client.courses("/api/todos")
                finally:
                    client.close()

    def test_download_is_streamed_hashed_and_versioned(self) -> None:
        body = b"safe fixture bytes"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "application/pdf", "content-length": str(len(body))},
                content=body,
                request=request,
            )

        client = make_client(handler)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                (root / "file.pdf").write_bytes(b"old")
                result = client.download_upload("123", destination_root=str(root), filename="file.pdf", max_bytes=1024)
                self.assertEqual(Path(result["path"]).name, "file-v2.pdf")
                self.assertEqual(Path(result["path"]).read_bytes(), body)
                self.assertEqual(result["size"], len(body))
                self.assertEqual(len(result["sha256"]), 64)
        finally:
            client.close()

    def test_download_rejects_content_length_and_cleans_temp(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-length": "999"}, content=b"x", request=request)

        client = make_client(handler)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                with self.assertRaises(DownloadRejected):
                    client.download_upload("123", destination_root=str(root), filename="file.pdf", max_bytes=8)
                self.assertEqual(list(root.iterdir()), [])
        finally:
            client.close()

    def test_assignment_write_uses_only_fixed_endpoints_and_payloads(self) -> None:
        seen: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path))
            if request.method == "POST" and request.url.path == "/api/uploads":
                payload = json.loads(request.content)
                self.assertEqual(payload["name"], "report.pdf")
                self.assertEqual(payload["size"], 7)
                return httpx.Response(201, json={"id": 123, "upload_url": "https://courses.zju.edu.cn/api/uploads/123/blob"}, request=request)
            if request.method == "PUT" and request.url.path == "/api/uploads/123/blob":
                self.assertIn(b"fixture", request.content)
                return httpx.Response(204, request=request)
            if request.method == "POST" and request.url.path == "/api/course/activities/77/submissions":
                payload = json.loads(request.content)
                self.assertEqual(payload["uploads"], [123])
                self.assertFalse(payload["is_draft"])
                return httpx.Response(201, json={"id": 9}, request=request)
            return httpx.Response(404, request=request)

        client = make_client(handler)
        try:
            reservation = client.reserve_assignment_upload("report.pdf", 7)
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "report.pdf"
                path.write_bytes(b"fixture")
                client.upload_assignment_file(str(reservation["upload_url"]), path)
            client.commit_assignment_submission("77", [str(reservation["id"])], "<p>reviewed</p>")
        finally:
            client.close()
        self.assertEqual(seen, [
            ("POST", "/api/uploads"),
            ("PUT", "/api/uploads/123/blob"),
            ("POST", "/api/course/activities/77/submissions"),
        ])

    def test_assignment_write_timeout_is_unknown_and_not_retried(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("fixture timeout", request=request)

        client = make_client(handler)
        try:
            with self.assertRaises(SubmissionStateUnknown):
                client.reserve_assignment_upload("report.pdf", 7)
        finally:
            client.close()
        self.assertEqual(calls, 1)

    def test_assignment_write_redirect_and_cross_host_upload_are_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(307, headers={"location": "https://courses.zju.edu.cn/api/other"}, request=request)

        client = make_client(handler)
        try:
            with self.assertRaises(SubmissionStateUnknown):
                client.reserve_assignment_upload("report.pdf", 7)
            with self.assertRaises(ZJUError):
                client.upload_assignment_file("https://evil.example/upload", Path(__file__))
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
