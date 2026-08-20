from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from .constants import write_policy_path
from .errors import SubmissionRejected
from .security import safe_upload_root
from .session import harden_private_file


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WritePolicy:
    schema_version = 1

    def load(self) -> dict[str, Any]:
        target = write_policy_path()
        if not target.is_file():
            return {"schema_version": self.schema_version, "assignment_submission_enabled": False, "approved_roots": []}
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SubmissionRejected("The local write policy is unreadable; disable it and configure it again.", code="write_policy_invalid") from exc
        if payload.get("schema_version") != self.schema_version or not isinstance(payload.get("approved_roots"), list):
            raise SubmissionRejected("The local write policy has an unsupported format.", code="write_policy_invalid")
        return payload

    def require_enabled(self) -> list[str]:
        payload = self.load()
        if payload.get("assignment_submission_enabled") is not True:
            raise SubmissionRejected("Assignment submission is disabled. The user must enable it from a local interactive PowerShell.", code="write_capability_disabled")
        roots = [str(safe_upload_root(str(root))) for root in payload.get("approved_roots", [])]
        if not roots:
            raise SubmissionRejected("Assignment submission has no approved upload root.", code="write_capability_disabled")
        return roots

    def enable(self, roots: list[str]) -> dict[str, Any]:
        normalized = sorted({str(safe_upload_root(root)) for root in roots}, key=str.casefold)
        if not normalized:
            raise SubmissionRejected("At least one approved upload root is required.")
        payload = {
            "schema_version": self.schema_version,
            "assignment_submission_enabled": True,
            "approved_roots": normalized,
            "updated_at": _now(),
        }
        self._save(payload)
        return payload

    def disable(self) -> None:
        write_policy_path().unlink(missing_ok=True)

    def status(self, *, include_roots: bool = False) -> dict[str, Any]:
        payload = self.load()
        roots = payload.get("approved_roots", [])
        result = {
            "assignment_submission_enabled": payload.get("assignment_submission_enabled") is True,
            "approved_root_count": len(roots),
            "updated_at": payload.get("updated_at"),
        }
        if include_roots:
            result["approved_roots"] = roots
        return result

    def _save(self, payload: dict[str, Any]) -> None:
        target = write_policy_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        try:
            harden_private_file(target)
        except Exception:
            target.unlink(missing_ok=True)
            raise
