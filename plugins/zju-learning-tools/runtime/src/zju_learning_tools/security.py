from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import os
from pathlib import Path, PureWindowsPath
import re
from typing import Any
import unicodedata
from urllib.parse import urlparse

from .constants import ALLOWED_HOSTS
from .errors import DownloadRejected, SubmissionRejected, ZJUError

SECRET_KEY_PARTS = (
    "password", "passwd", "cookie", "authorization", "bearer", "csrf", "ticket",
    "execution", "rsapwd", "token", "secret",
)
ANSWER_KEY_PARTS = (
    "answer", "correct", "solution", "subject_result", "is_right", "right_option",
)
TIME_KEY_PARTS = ("time", "date", "deadline", "created_at", "updated_at", "start", "end")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def html_to_text(value: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return " ".join(re.sub(r"<[^>]*>", " ", value).split())
    return " ".join(parser.parts)


def is_allowed_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() in ALLOWED_HOSTS


def require_allowed_url(value: str) -> str:
    if not is_allowed_url(value):
        raise ZJUError("network_rejected", "A URL outside the exact ZJU HTTPS allowlist was rejected.")
    if urlparse(value).username or urlparse(value).password:
        raise ZJUError("network_rejected", "URLs containing embedded credentials are rejected.")
    return value


def _normalize_time(value: str) -> str:
    candidate = value.strip().replace("/", "-")
    if not candidate or candidate.lower() in {"null", "none"}:
        return value
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return f"{candidate}T00:00:00+08:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", candidate):
        return candidate.replace(" ", "T") + "+08:00"
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except ValueError:
        return value


def sanitize_data(value: Any, *, key: str = "") -> Any:
    lowered = key.lower().replace("-", "_")
    if any(part in lowered for part in SECRET_KEY_PARTS):
        return "[REDACTED]"
    if any(part in lowered for part in ANSWER_KEY_PARTS):
        return "[REMOVED]"
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for raw_key, item in value.items():
            item_key = str(raw_key)
            normalized = item_key.lower().replace("-", "_")
            if any(part in normalized for part in ANSWER_KEY_PARTS):
                continue
            if any(part in normalized for part in SECRET_KEY_PARTS):
                continue
            clean[item_key] = sanitize_data(item, key=item_key)
        return clean
    if isinstance(value, list):
        return [sanitize_data(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [sanitize_data(item, key=key) for item in value]
    if isinstance(value, (int, float)) and lowered.endswith(("id", "_id")):
        return str(value)
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            return value if is_allowed_url(value) else "[URL REMOVED]"
        if "<" in value and ">" in value:
            value = html_to_text(value)
        if any(part in lowered for part in TIME_KEY_PARTS):
            value = _normalize_time(value)
        return value[:100_000]
    return value


def safe_remote_filename(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    if not value or CONTROL_RE.search(value) or any(unicodedata.category(character) in {"Cc", "Cf"} for character in value):
        raise DownloadRejected("The remote filename is empty or contains a control character.")
    if value.startswith(("\\\\", "//")) or PureWindowsPath(value).is_absolute():
        raise DownloadRejected("Absolute and UNC remote filenames are rejected.")
    if ":" in value or "/" in value or "\\" in value or value in {".", ".."}:
        raise DownloadRejected("The remote filename contains a path, drive, ADS, or traversal component.")
    if value != value.rstrip(" ."):
        raise DownloadRejected("Remote filenames ending in a space or period are rejected on Windows.")
    name = value
    reserved_stem = name.split(".", 1)[0].rstrip(" .").upper()
    if not name or reserved_stem in WINDOWS_RESERVED:
        raise DownloadRejected("The remote filename is a reserved Windows name.")
    return name[:240]


def safe_destination(root: str, filename: str) -> tuple[Path, Path]:
    root_path = Path(root).expanduser()
    if not root_path.is_absolute() or not root_path.is_dir():
        raise DownloadRejected("The destination root must be an existing absolute directory.")
    if str(root_path).startswith(("\\\\", "//")):
        raise DownloadRejected("UNC destination roots are rejected.")
    unresolved_root = root_path.absolute()
    resolved_root = root_path.resolve(strict=True)
    for checked_root in (unresolved_root, resolved_root):
        current = Path(checked_root.anchor)
        for part in checked_root.parts[1:]:
            current = current / part
            try:
                stats = current.lstat()
                attrs = getattr(stats, "st_file_attributes", 0)
            except (AttributeError, OSError):
                continue
            if current.is_symlink() or attrs & 0x400:
                raise DownloadRejected("The destination root contains a symbolic link or reparse point.")
    clean_name = safe_remote_filename(filename)
    candidate = resolved_root / clean_name
    index = 2
    while candidate.exists():
        candidate = resolved_root / f"{Path(clean_name).stem}-v{index}{Path(clean_name).suffix}"
        index += 1
    if os.path.commonpath([str(resolved_root), str(candidate.resolve(strict=False))]) != str(resolved_root):
        raise DownloadRejected("The resolved destination escaped the selected root.")
    return resolved_root, candidate


def _reject_reparse_components(path: Path, *, label: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            stats = current.lstat()
        except OSError as exc:
            raise SubmissionRejected(f"The {label} could not be inspected safely.") from exc
        attrs = getattr(stats, "st_file_attributes", 0)
        if current.is_symlink() or attrs & 0x400:
            raise SubmissionRejected(f"The {label} contains a symbolic link or reparse point.")


def safe_upload_root(value: str) -> Path:
    root = Path(value).expanduser()
    if not root.is_absolute() or not root.is_dir() or str(root).startswith(("\\\\", "//")):
        raise SubmissionRejected("Each approved upload root must be an existing absolute local directory.")
    _reject_reparse_components(root.absolute(), label="approved upload root")
    resolved = root.resolve(strict=True)
    _reject_reparse_components(resolved, label="approved upload root")
    return resolved


def safe_submission_file(value: str, approved_roots: list[str]) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() or not candidate.is_file() or str(candidate).startswith(("\\\\", "//")):
        raise SubmissionRejected("Each submission path must name one existing absolute local file.")
    _reject_reparse_components(candidate.absolute(), label="submission file path")
    resolved = candidate.resolve(strict=True)
    _reject_reparse_components(resolved, label="submission file path")
    safe_remote_filename(resolved.name)
    attrs = getattr(resolved.stat(), "st_file_attributes", 0)
    if attrs & 0x2:
        raise SubmissionRejected("Hidden files cannot be submitted through the plugin.")
    roots = [safe_upload_root(root) for root in approved_roots]
    if not roots:
        raise SubmissionRejected("No approved upload root is configured.", code="write_capability_disabled")
    within_root = False
    for root in roots:
        try:
            if os.path.commonpath([str(root), str(resolved)]) == str(root):
                within_root = True
                break
        except ValueError:
            continue
    if not within_root:
        raise SubmissionRejected("The file is outside the user-approved upload roots.")
    return resolved
