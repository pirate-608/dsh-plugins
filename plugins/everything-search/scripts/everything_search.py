#!/usr/bin/env python3
"""Safe JSON wrapper around voidtools ES for read-only local file search."""

from __future__ import annotations

import argparse
import json
import locale
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


MAX_RESULTS_LIMIT = 1000
DEFAULT_RESULTS_LIMIT = 100
DEFAULT_TIMEOUT_MS = 5000
DIRECTORY_ATTRIBUTE = 0x10
SORT_FIELDS = (
    "name",
    "path",
    "size",
    "extension",
    "date-created",
    "date-modified",
    "date-accessed",
    "attributes",
    "run-count",
    "date-recently-changed",
    "date-run",
)
ERROR_MESSAGES = {
    1: "ES failed to register its window class.",
    2: "ES failed to create its listening window.",
    3: "ES ran out of memory.",
    4: "ES expected a value for one of its command-line options.",
    5: "ES failed to create an export file.",
    6: "ES received an unknown option.",
    7: "ES could not send the query to Everything IPC.",
    8: "Everything IPC was not found. Start the Everything desktop application, then retry.",
    9: "No results were found.",
}


class EverythingSearchError(RuntimeError):
    """An actionable ES discovery, validation, or execution failure."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _candidate_paths() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("EVERYTHING_ES_PATH")
    if explicit:
        candidates.append(Path(explicit).expanduser())

    found = shutil.which("es.exe") or shutil.which("es")
    if found:
        candidates.append(Path(found))

    local_app_data = os.environ.get("LOCALAPPDATA")
    user_profile = os.environ.get("USERPROFILE")
    if local_app_data:
        candidates.extend(
            [
                Path(local_app_data) / "Microsoft" / "WindowsApps" / "es.exe",
                Path(local_app_data) / "Everything" / "es.exe",
            ]
        )
    if user_profile:
        candidates.append(Path(user_profile) / ".local" / "bin" / "es.exe")
    candidates.extend(
        [
            Path(r"C:\Program Files\Everything\es.exe"),
            Path(r"C:\Program Files (x86)\Everything\es.exe"),
        ]
    )
    return candidates


def find_es() -> Path:
    if os.name != "nt":
        raise EverythingSearchError("Everything Search is supported only on Windows.")
    seen: set[str] = set()
    for candidate in _candidate_paths():
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate.resolve()
    raise EverythingSearchError(
        "es.exe was not found. Install the Everything Command Line Interface and place es.exe "
        "on PATH, or set EVERYTHING_ES_PATH to its full path."
    )


def find_everything_application() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\Everything\Everything.exe"),
        Path(r"C:\Program Files (x86)\Everything\Everything.exe"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Everything" / "Everything.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _decode(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8-sig", locale.getpreferredencoding(False), "utf-16"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _run_es(arguments: Sequence[str], *, timeout_ms: int) -> subprocess.CompletedProcess[bytes]:
    es_path = find_es()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(
            [str(es_path), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=(timeout_ms / 1000) + 5,
            check=False,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise EverythingSearchError(
            f"ES did not finish within {timeout_ms + 5000} milliseconds.", exit_code=124
        ) from exc
    except OSError as exc:
        raise EverythingSearchError(f"Unable to start ES: {exc}") from exc


def _failure(result: subprocess.CompletedProcess[bytes]) -> EverythingSearchError:
    output = (_decode(result.stderr) or _decode(result.stdout)).strip()
    message = ERROR_MESSAGES.get(result.returncode, f"ES failed with exit code {result.returncode}.")
    if output and output.lower() not in message.lower():
        message = f"{message} ES output: {output}"
    return EverythingSearchError(message, exit_code=result.returncode or 2)


def validate_query(query: str) -> str:
    query = query.strip()
    if not query:
        raise EverythingSearchError("A non-empty search query is required.")
    if len(query) > 4096:
        raise EverythingSearchError("The search query is longer than the 4096-character safety limit.")
    lowered = query.lower()
    if query.startswith(("-", "/")) or lowered.startswith("about:"):
        raise EverythingSearchError(
            "Queries beginning with '-', '/', or 'about:' are blocked because Everything treats "
            "some of them as commands. Express the request with filename terms or search functions instead."
        )
    if any(character in query for character in ("\x00", "\r", "\n")):
        raise EverythingSearchError("The search query contains a prohibited control character.")
    return query


def validate_scope(path: str | None) -> str | None:
    if not path:
        return None
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise EverythingSearchError(f"Search scope is not an existing directory: {resolved}")
    return str(resolved)


def _validate_common(max_results: int, offset: int, timeout_ms: int, instance: str | None) -> None:
    if not 1 <= max_results <= MAX_RESULTS_LIMIT:
        raise EverythingSearchError(f"--max-results must be between 1 and {MAX_RESULTS_LIMIT}.")
    if offset < 0:
        raise EverythingSearchError("--offset cannot be negative.")
    if not 100 <= timeout_ms <= 60_000:
        raise EverythingSearchError("--timeout-ms must be between 100 and 60000.")
    if instance and (len(instance) > 128 or any(c in instance for c in "\x00\r\n")):
        raise EverythingSearchError("--instance is invalid or longer than 128 characters.")


def build_filter_arguments(args: argparse.Namespace) -> list[str]:
    arguments: list[str] = ["-timeout", str(args.timeout_ms)]
    if args.instance:
        arguments.extend(["-instance", args.instance])
    if args.path:
        arguments.extend(["-path", args.path])
    if args.kind == "file":
        arguments.append("/a-d")
    elif args.kind == "directory":
        arguments.append("/ad")
    if args.regex:
        arguments.append("-regex")
    if args.case_sensitive:
        arguments.append("-case")
    if args.whole_word:
        arguments.append("-whole-word")
    if args.match_path:
        arguments.append("-match-path")
    if args.diacritics:
        arguments.append("-diacritics")
    return arguments


def _normalize_result(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item.get("name") or item.get("filename") or "")
    parent = str(item.get("path") or "")
    full_path = str(Path(parent) / name) if parent and name else name or parent
    attributes = item.get("attributes")
    try:
        attributes_number = int(attributes) if attributes is not None else None
    except (TypeError, ValueError):
        attributes_number = None
    is_directory = bool(attributes_number is not None and attributes_number & DIRECTORY_ATTRIBUTE)
    return {
        "name": name,
        "path": parent,
        "full_path": full_path,
        "kind": "directory" if is_directory else "file",
        "extension": item.get("extension") or "",
        "size": item.get("size"),
        "date_created": item.get("date_created"),
        "date_modified": item.get("date_modified"),
        "attributes": attributes_number,
    }


def search(args: argparse.Namespace) -> dict[str, Any]:
    args.query = validate_query(args.query)
    args.path = validate_scope(args.path)
    _validate_common(args.max_results, args.offset, args.timeout_ms, args.instance)
    if args.order and not args.sort:
        raise EverythingSearchError("--order requires --sort.")

    command = build_filter_arguments(args)
    command.extend(
        [
            "-json",
            "-name",
            "-path-column",
            "-extension",
            "-size",
            "-date-created",
            "-date-modified",
            "-attributes",
            "-date-format",
            "1",
            "-offset",
            str(args.offset),
            "-max-results",
            str(args.max_results),
        ]
    )
    if args.sort:
        sort_value = args.sort if not args.order else f"{args.sort}-{args.order}"
        command.extend(["-sort", sort_value])
    command.append(args.query)

    result = _run_es(command, timeout_ms=args.timeout_ms)
    if result.returncode != 0:
        raise _failure(result)
    raw = _decode(result.stdout).strip() or "[]"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EverythingSearchError(f"ES returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise EverythingSearchError("ES returned an unexpected JSON document instead of a result list.")
    normalized = [_normalize_result(item) for item in parsed if isinstance(item, dict)]
    return {
        "query": args.query,
        "scope": args.path,
        "kind": args.kind,
        "offset": args.offset,
        "limit": args.max_results,
        "returned": len(normalized),
        "results": normalized,
    }


def count(args: argparse.Namespace) -> dict[str, Any]:
    args.query = validate_query(args.query)
    args.path = validate_scope(args.path)
    _validate_common(1, 0, args.timeout_ms, args.instance)
    command = build_filter_arguments(args)
    command.extend(["-get-result-count", args.query])
    result = _run_es(command, timeout_ms=args.timeout_ms)
    if result.returncode != 0:
        raise _failure(result)
    raw = _decode(result.stdout).strip()
    try:
        result_count = int(raw)
    except ValueError as exc:
        raise EverythingSearchError(f"ES returned an invalid result count: {raw!r}") from exc
    return {"query": args.query, "scope": args.path, "kind": args.kind, "count": result_count}


def doctor(args: argparse.Namespace) -> dict[str, Any]:
    _validate_common(1, 0, args.timeout_ms, None)
    es_path = find_es()
    es_version_result = _run_es(["-version"], timeout_ms=args.timeout_ms)
    if es_version_result.returncode != 0:
        raise _failure(es_version_result)
    everything_result = _run_es(["-get-everything-version"], timeout_ms=args.timeout_ms)
    everything_ready = everything_result.returncode == 0
    return {
        "ok": everything_ready,
        "platform": sys.platform,
        "es_path": str(es_path),
        "es_version": _decode(es_version_result.stdout).strip(),
        "everything_ipc_ready": everything_ready,
        "everything_version": _decode(everything_result.stdout).strip() if everything_ready else None,
        "everything_application": str(find_everything_application() or "") or None,
        "diagnostic": None if everything_ready else str(_failure(everything_result)),
    }


def _add_filters(parser: argparse.ArgumentParser, *, include_paging: bool) -> None:
    parser.add_argument("--query", required=True, help="Everything search expression")
    parser.add_argument("--path", help="existing directory used as the search scope")
    parser.add_argument("--kind", choices=("any", "file", "directory"), default="any")
    parser.add_argument("--regex", action="store_true")
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--whole-word", action="store_true")
    parser.add_argument("--match-path", action="store_true")
    parser.add_argument("--diacritics", action="store_true")
    parser.add_argument("--instance", help="named Everything instance")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    if include_paging:
        parser.add_argument("--max-results", type=int, default=DEFAULT_RESULTS_LIMIT)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--sort", choices=SORT_FIELDS)
        parser.add_argument("--order", choices=("ascending", "descending"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor_parser = subparsers.add_parser("doctor", help="diagnose ES and Everything IPC")
    doctor_parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    search_parser = subparsers.add_parser("search", help="return bounded JSON search results")
    _add_filters(search_parser, include_paging=True)
    count_parser = subparsers.add_parser("count", help="count matching indexed paths")
    _add_filters(count_parser, include_paging=False)
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    try:
        if args.command == "doctor":
            payload = doctor(args)
        elif args.command == "search":
            payload = search(args)
        else:
            payload = count(args)
    except EverythingSearchError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "exit_code": exc.exit_code}, ensure_ascii=False))
        return exc.exit_code
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
