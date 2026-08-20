from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "everything_search.py"
SPEC = importlib.util.spec_from_file_location("everything_search", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def completed(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    return subprocess.CompletedProcess(["es.exe"], returncode, stdout, stderr)


class EverythingSearchTests(unittest.TestCase):
    def test_control_queries_are_rejected(self) -> None:
        for query in ("-exit", "/quit", "about:config"):
            with self.subTest(query=query):
                with self.assertRaisesRegex(module.EverythingSearchError, "blocked"):
                    module.validate_query(query)

    def test_empty_and_control_character_queries_are_rejected(self) -> None:
        with self.assertRaises(module.EverythingSearchError):
            module.validate_query("  ")
        with self.assertRaises(module.EverythingSearchError):
            module.validate_query("hello\nworld")

    def test_scope_must_be_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(module.validate_scope(temp), str(Path(temp).resolve()))
            with self.assertRaisesRegex(module.EverythingSearchError, "not an existing directory"):
                module.validate_scope(str(Path(temp) / "missing"))

    def test_filter_arguments_are_allowlisted(self) -> None:
        args = argparse.Namespace(
            timeout_ms=5000,
            instance="dev",
            path=r"D:\projects",
            kind="file",
            regex=True,
            case_sensitive=True,
            whole_word=True,
            match_path=True,
            diacritics=True,
        )
        self.assertEqual(
            module.build_filter_arguments(args),
            [
                "-timeout", "5000", "-instance", "dev", "-path", r"D:\projects", "/a-d",
                "-regex", "-case", "-whole-word", "-match-path", "-diacritics",
            ],
        )

    def test_search_normalizes_json_and_bounds_results(self) -> None:
        raw = json.dumps(
            [
                {
                    "name": "guide.pdf",
                    "path": r"D:\Docs",
                    "extension": "pdf",
                    "size": 42,
                    "date_created": "2026-08-13T10:00:00",
                    "date_modified": "2026-08-13T11:00:00",
                    "attributes": 32,
                },
                {"name": "Archive", "path": r"D:\Docs", "attributes": 16},
            ]
        ).encode()
        args = argparse.Namespace(
            query="guide | archive",
            path=None,
            kind="any",
            regex=False,
            case_sensitive=False,
            whole_word=False,
            match_path=False,
            diacritics=False,
            instance=None,
            timeout_ms=5000,
            max_results=25,
            offset=10,
            sort="date-modified",
            order="descending",
        )
        with mock.patch.object(module, "_run_es", return_value=completed(stdout=raw)) as runner:
            payload = module.search(args)
        command = runner.call_args.args[0]
        self.assertIn("-max-results", command)
        self.assertIn("25", command)
        self.assertIn("date-modified-descending", command)
        self.assertEqual(payload["returned"], 2)
        self.assertEqual(payload["results"][0]["full_path"], str(Path(r"D:\Docs") / "guide.pdf"))
        self.assertEqual(payload["results"][1]["kind"], "directory")

    def test_search_maps_missing_ipc_error(self) -> None:
        args = argparse.Namespace(
            query="report",
            path=None,
            kind="any",
            regex=False,
            case_sensitive=False,
            whole_word=False,
            match_path=False,
            diacritics=False,
            instance=None,
            timeout_ms=5000,
            max_results=10,
            offset=0,
            sort=None,
            order=None,
        )
        with mock.patch.object(module, "_run_es", return_value=completed(8, stderr=b"IPC not found")):
            with self.assertRaisesRegex(module.EverythingSearchError, "Start the Everything") as caught:
                module.search(args)
        self.assertEqual(caught.exception.exit_code, 8)

    def test_count_parses_integer(self) -> None:
        args = argparse.Namespace(
            query="ext:py",
            path=None,
            kind="file",
            regex=False,
            case_sensitive=False,
            whole_word=False,
            match_path=False,
            diacritics=False,
            instance=None,
            timeout_ms=5000,
        )
        with mock.patch.object(module, "_run_es", return_value=completed(stdout=b"123\r\n")):
            payload = module.count(args)
        self.assertEqual(payload["count"], 123)

    def test_doctor_reports_ipc_not_ready_without_starting_everything(self) -> None:
        responses = [completed(stdout=b"1.1.0.37\r\n"), completed(8, stderr=b"IPC not found")]
        with (
            mock.patch.object(module, "find_es", return_value=Path("es.exe")),
            mock.patch.object(module, "find_everything_application", return_value=Path("Everything.exe")),
            mock.patch.object(module, "_run_es", side_effect=responses),
        ):
            payload = module.doctor(argparse.Namespace(timeout_ms=5000))
        self.assertFalse(payload["everything_ipc_ready"])
        self.assertIn("Start the Everything", payload["diagnostic"])


if __name__ == "__main__":
    unittest.main()
