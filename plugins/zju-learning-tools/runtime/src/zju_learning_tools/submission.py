from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
import threading
from typing import Any, Iterator

from .client import ZJUReadClient
from .constants import (
    APPROVAL_TTL_SECONDS,
    MAX_SUBMISSION_BYTES,
    MAX_SUBMISSION_COMMENT_CHARS,
    MAX_SUBMISSION_FILE_BYTES,
    MAX_SUBMISSION_FILES,
    submission_ledger_path,
    submission_lock_path,
)
from .errors import SubmissionRejected, SubmissionStateUnknown, UpstreamChanged
from .security import safe_submission_file
from .session import harden_private_file
from .write_policy import WritePolicy


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dict_value(payload: Any, keys: tuple[str, ...]) -> Any:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    for container in ("activity", "data", "course_activity"):
        nested = payload.get(container)
        if isinstance(nested, dict):
            value = _dict_value(nested, keys)
            if value not in (None, ""):
                return value
    return None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().replace("/", "-").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed.astimezone(timezone.utc)


def _history_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("list", "submissions", "items", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _history_items(value)
            if nested:
                return nested
    return []


def _upload_ids_from_history(payload: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in {"uploads", "attachments", "files"}:
                for item in value if isinstance(value, list) else []:
                    if isinstance(item, dict) and str(item.get("id", "")).isdigit():
                        found.add(str(item["id"]))
            else:
                found.update(_upload_ids_from_history(value))
    elif isinstance(payload, list):
        for item in payload:
            found.update(_upload_ids_from_history(item))
    return found


def _assignment_view(activity_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    assignment = snapshot.get("assignment")
    if not isinstance(assignment, dict):
        raise UpstreamChanged("The assignment detail response was not an object.")
    returned_id = _dict_value(assignment, ("id", "activity_id"))
    if returned_id is not None and str(returned_id) != str(activity_id):
        raise UpstreamChanged("The assignment detail response returned a different activity ID.")
    kind_value = _dict_value(assignment, ("type", "activity_type", "activity_type_name", "category"))
    kind = str(kind_value or "").strip().lower()
    forbidden = ("exam", "quiz", "test", "classroom", "questionnaire", "rollcall", "考试", "测验", "测试", "问卷", "签到")
    allowed = ("homework", "assignment", "作业")
    if any(word in kind for word in forbidden) or not any(word in kind for word in allowed):
        raise SubmissionRejected("Only ordinary homework activities are eligible; exams, quizzes, classroom exercises, questionnaires, and roll calls are permanently excluded.")
    title = str(_dict_value(assignment, ("title", "name")) or "").strip()
    if not title:
        raise UpstreamChanged("The assignment detail response did not include a title.")
    status = str(_dict_value(assignment, ("status", "activity_status")) or "").lower()
    if status in {"closed", "locked", "expired", "ended"}:
        raise SubmissionRejected("The assignment is closed or locked on the campus service.")
    is_open = _dict_value(assignment, ("is_open", "can_submit", "submission_available"))
    if is_open is False:
        raise SubmissionRejected("The assignment currently does not accept submissions.")
    deadline_raw = _dict_value(assignment, ("end_time", "due_at", "deadline", "end_at", "end_date"))
    deadline = _parse_time(deadline_raw)
    if deadline_raw not in (None, "") and deadline is None:
        raise UpstreamChanged("The assignment deadline used an unknown format; submission was stopped.")
    if deadline is not None and deadline <= _now():
        raise SubmissionRejected("The authoritative assignment deadline has passed.")
    history = snapshot.get("submission_history")
    attempts = _history_items(history)
    revision_fields = {
        "activity_id": str(activity_id),
        "title": title,
        "kind": kind,
        "status": status,
        "deadline": str(deadline_raw or ""),
        "updated_at": str(_dict_value(assignment, ("updated_at", "modified_at")) or ""),
        "attempts": [
            {
                "id": str(item.get("id", "")),
                "created_at": str(item.get("created_at", item.get("submitted_at", ""))),
                "status": str(item.get("status", "")),
            }
            for item in attempts
        ],
    }
    return {
        "activity_id": str(activity_id),
        "title": title,
        "kind": kind,
        "course_id": str(_dict_value(assignment, ("course_id",)) or ""),
        "instructor": _dict_value(assignment, ("instructor", "instructors", "teacher", "teachers")),
        "deadline": _rfc3339(deadline) if deadline else None,
        "deadline_raw": str(deadline_raw or ""),
        "official_url": _dict_value(assignment, ("url", "official_url")),
        "attempt_count": len(attempts),
        "revision": _canonical_hash(revision_fields),
    }


def _comment_html(comment: str) -> str:
    if not comment:
        return ""
    return f'<p><span style="font-size: 14px;">{escape(comment, quote=True)}</span><br></p>'


@dataclass(frozen=True)
class Approval:
    approval_id: str
    expires_at: datetime
    account_last4: str
    user_id: str
    assignment: dict[str, Any]
    files: tuple[dict[str, Any], ...]
    comment: str
    comment_html: str
    payload_sha256: str
    fingerprint: str


class SubmissionLedger:
    schema_version = 1
    _lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        target = submission_ledger_path()
        if not target.is_file():
            return {"schema_version": self.schema_version, "records": {}}
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SubmissionRejected("The local submission ledger is unreadable; do not submit until it is reviewed.", code="submission_ledger_invalid") from exc
        if payload.get("schema_version") != self.schema_version or not isinstance(payload.get("records"), dict):
            raise SubmissionRejected("The local submission ledger has an unsupported format.", code="submission_ledger_invalid")
        return payload

    def require_new(self, fingerprint: str) -> None:
        with self._lock:
            record = self._load()["records"].get(fingerprint)
        if isinstance(record, dict) and record.get("status") in {"in_progress", "unknown", "committed"}:
            raise SubmissionRejected("An identical submission is already in progress, completed, or awaiting manual verification. Check the official page; the plugin will not send it again.", code="duplicate_submission_blocked")

    def mark(self, approval: Approval, status: str, **fields: Any) -> None:
        with self._lock:
            payload = self._load()
            records: dict[str, Any] = payload["records"]
            records[approval.fingerprint] = {
                "status": status,
                "activity_hash": sha256(approval.assignment["activity_id"].encode("utf-8")).hexdigest(),
                "payload_sha256": approval.payload_sha256,
                "approval_hash": sha256(approval.approval_id.encode("utf-8")).hexdigest(),
                "updated_at": _rfc3339(_now()),
                **fields,
            }
            if len(records) > 100:
                oldest = sorted(records, key=lambda key: str(records[key].get("updated_at", "")))[: len(records) - 100]
                for key in oldest:
                    records.pop(key, None)
            self._save(payload)

    @staticmethod
    def _save(payload: dict[str, Any]) -> None:
        target = submission_ledger_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        harden_private_file(target)


@contextmanager
def _process_mutex() -> Iterator[None]:
    target = submission_lock_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = target.open("a+b")
    if target.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise SubmissionRejected("Another assignment commit is already running. Wait for it to finish; do not start a second submission.", code="submission_busy") from exc
    try:
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class SubmissionManager:
    def __init__(self) -> None:
        self._approvals: dict[str, Approval] = {}
        self._approvals_lock = threading.Lock()
        self.ledger = SubmissionLedger()
        self.policy = WritePolicy()

    def _files(self, file_paths: list[str], approved_roots: list[str]) -> tuple[dict[str, Any], ...]:
        if not file_paths or len(file_paths) > MAX_SUBMISSION_FILES:
            raise SubmissionRejected(f"Select between 1 and {MAX_SUBMISSION_FILES} explicit files for one assignment.")
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        total = 0
        for raw_path in file_paths:
            path = safe_submission_file(raw_path, approved_roots)
            identity = os.path.normcase(str(path))
            if identity in seen:
                raise SubmissionRejected("The same file was selected more than once.")
            seen.add(identity)
            before = path.stat()
            if before.st_size < 1 or before.st_size > MAX_SUBMISSION_FILE_BYTES:
                raise SubmissionRejected("Each submission file must be non-empty and no larger than 100 MiB.")
            digest = _file_digest(path)
            after = path.stat()
            stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
            if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
                raise SubmissionRejected("A selected file changed while it was being inspected. Wait for local writes to finish, then prepare again.", code="submission_file_unstable")
            total += after.st_size
            if total > MAX_SUBMISSION_BYTES:
                raise SubmissionRejected("The selected submission exceeds the 250 MiB aggregate limit.")
            records.append({
                "path": str(path),
                "name": path.name,
                "size": after.st_size,
                "mtime_ns": after.st_mtime_ns,
                "sha256": digest,
            })
        return tuple(records)

    @staticmethod
    def _payload(account_last4: str, user_id: str, assignment: dict[str, Any], files: tuple[dict[str, Any], ...], comment: str) -> dict[str, Any]:
        return {
            "account_last4": account_last4,
            "user_id_hash": sha256(user_id.encode("utf-8")).hexdigest(),
            "activity_id": assignment["activity_id"],
            "assignment_revision": assignment["revision"],
            "files": [{key: item[key] for key in ("name", "size", "mtime_ns", "sha256")} for item in files],
            "comment": comment,
        }

    def prepare(self, client: ZJUReadClient, activity_id: str, file_paths: list[str], comment: str = "") -> dict[str, Any]:
        if not str(activity_id).isdigit():
            raise SubmissionRejected("The activity ID must be the opaque numeric ID returned by assignment tools.")
        if not isinstance(comment, str) or len(comment) > MAX_SUBMISSION_COMMENT_CHARS or "\x00" in comment:
            raise SubmissionRejected("The optional submission comment must be plain text no longer than 5000 characters.")
        approved_roots = self.policy.require_enabled()
        user_id = str(client.payload.get("user_id") or "")
        account_last4 = str(client.payload.get("account_last4") or "")
        if not user_id or not account_last4:
            raise SubmissionRejected("The authenticated session lacks the account identity required for a verifiable submission.")
        assignment = _assignment_view(str(activity_id), client.assignment_snapshot(str(activity_id)))
        files = self._files(file_paths, approved_roots)
        payload = self._payload(account_last4, user_id, assignment, files, comment)
        payload_sha256 = _canonical_hash(payload)
        fingerprint = _canonical_hash({"account": account_last4, "payload_sha256": payload_sha256})
        self.ledger.require_new(fingerprint)
        approval_id = secrets.token_urlsafe(24)
        approval = Approval(
            approval_id=approval_id,
            expires_at=_now() + timedelta(seconds=APPROVAL_TTL_SECONDS),
            account_last4=account_last4,
            user_id=user_id,
            assignment=assignment,
            files=files,
            comment=comment,
            comment_html=_comment_html(comment),
            payload_sha256=payload_sha256,
            fingerprint=fingerprint,
        )
        with self._approvals_lock:
            self._approvals = {key: value for key, value in self._approvals.items() if value.expires_at > _now()}
            self._approvals[approval_id] = approval
        return {
            "approval_id": approval_id,
            "expires_at": _rfc3339(approval.expires_at),
            "account_last4": account_last4,
            "assignment": {key: value for key, value in assignment.items() if key != "revision"},
            "assignment_revision": assignment["revision"],
            "files": [{key: item[key] for key in ("path", "name", "size", "sha256")} for item in files],
            "comment_preview": comment,
            "payload_sha256": payload_sha256,
            "irreversible": True,
            "requires_new_user_confirmation": True,
        }

    def _consume(self, approval_id: str) -> Approval:
        with self._approvals_lock:
            approval = self._approvals.pop(approval_id, None)
        if approval is None:
            raise SubmissionRejected("The approval is missing, expired, already used, or belongs to another MCP process.", code="approval_invalid")
        if approval.expires_at <= _now():
            raise SubmissionRejected("The approval expired. Prepare the submission again and review the new preview.", code="approval_expired")
        return approval

    def commit(self, client: ZJUReadClient, approval_id: str) -> dict[str, Any]:
        with _process_mutex():
            approval = self._consume(approval_id)
            approved_roots = self.policy.require_enabled()
            if str(client.payload.get("user_id") or "") != approval.user_id or str(client.payload.get("account_last4") or "") != approval.account_last4:
                raise SubmissionRejected("The authenticated account changed after preparation. Prepare again with the intended account.", code="approval_account_changed")
            files = self._files([str(item["path"]) for item in approval.files], approved_roots)
            payload = self._payload(approval.account_last4, approval.user_id, approval.assignment, files, approval.comment)
            if _canonical_hash(payload) != approval.payload_sha256:
                raise SubmissionRejected("A selected file or comment changed after preparation. Prepare again and review the new hashes.", code="approval_payload_changed")
            current_assignment = _assignment_view(approval.assignment["activity_id"], client.assignment_snapshot(approval.assignment["activity_id"]))
            if current_assignment["revision"] != approval.assignment["revision"]:
                raise SubmissionRejected("The assignment state, deadline, or submission history changed after preparation. Prepare again.", code="approval_revision_changed")
            self.ledger.require_new(approval.fingerprint)
            self.ledger.mark(approval, "in_progress")
            writes_started = False
            upload_ids: list[str] = []
            request_ids: list[str] = []
            try:
                for expected in approval.files:
                    path = Path(str(expected["path"]))
                    writes_started = True
                    reservation = client.reserve_assignment_upload(path.name, int(expected["size"]))
                    upload_ids.append(str(reservation["id"]))
                    if reservation.get("request_id"):
                        request_ids.append(str(reservation["request_id"]))
                    uploaded = client.upload_assignment_file(str(reservation["upload_url"]), path)
                    if uploaded.get("request_id"):
                        request_ids.append(str(uploaded["request_id"]))
                    after = self._files([str(path)], approved_roots)[0]
                    if after["sha256"] != expected["sha256"] or after["size"] != expected["size"]:
                        raise SubmissionStateUnknown("A file changed while it was uploading. The reserved upload may be incomplete; do not submit or retry automatically.")
                submitted = client.commit_assignment_submission(approval.assignment["activity_id"], upload_ids, approval.comment_html)
                if submitted.get("request_id"):
                    request_ids.append(str(submitted["request_id"]))
                verified_snapshot = client.assignment_snapshot(approval.assignment["activity_id"])
                observed = _upload_ids_from_history(verified_snapshot.get("submission_history"))
                if not set(upload_ids).issubset(observed):
                    raise SubmissionStateUnknown("The final write returned but the new upload IDs were not visible in submission history. Check the official page; do not retry automatically.")
                self.ledger.mark(approval, "committed", upload_count=len(upload_ids))
                return {
                    "status": "committed",
                    "verified": True,
                    "activity_id": approval.assignment["activity_id"],
                    "assignment_title": approval.assignment["title"],
                    "upload_ids": upload_ids,
                    "files": [{key: item[key] for key in ("name", "size", "sha256")} for item in approval.files],
                    "payload_sha256": approval.payload_sha256,
                    "request_ids": request_ids,
                    "submitted_at": _rfc3339(_now()),
                }
            except Exception as exc:
                if writes_started:
                    self.ledger.mark(approval, "unknown", upload_count=len(upload_ids))
                    if isinstance(exc, SubmissionStateUnknown):
                        raise
                    raise SubmissionStateUnknown("A write sequence stopped after remote mutation began. Check the official assignment page and any uploaded resources; do not retry automatically.") from exc
                self.ledger.mark(approval, "failed")
                raise


submission_manager = SubmissionManager()
