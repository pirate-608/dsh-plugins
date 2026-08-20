from __future__ import annotations

from datetime import datetime, timedelta, timezone
import getpass
import json
import os
from pathlib import Path
from typing import Any, Iterable
import subprocess

from cryptography.fernet import Fernet, InvalidToken
import httpx
import keyring

from .constants import KEYRING_SERVICE, KEYRING_SESSION_KEY, session_path, state_dir
from .errors import AuthenticationRequired, ZJUError


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def harden_private_file(path: Path) -> None:
    if os.name != "nt":
        return
    domain = os.environ.get("USERDOMAIN", "").strip()
    username = os.environ.get("USERNAME", "").strip() or getpass.getuser()
    principal = f"{domain}\\{username}" if domain else username
    try:
        result = subprocess.run(
            ["icacls.exe", str(path), "/inheritance:r", "/grant:r", f"{principal}:(F)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ZJUError("session_storage_failed", "Windows could not secure a private ZJU state file.") from exc
    if result.returncode != 0:
        raise ZJUError("session_storage_failed", "Windows could not restrict access to a private ZJU state file.")


class SessionStore:
    @staticmethod
    def _cookie_service(domain: str) -> str:
        normalized = domain.lstrip(".").lower()
        if normalized.endswith("cmc.zju.edu.cn") or normalized == "classroom.zju.edu.cn":
            return "classroom"
        if normalized in {"zjuam.zju.edu.cn", "identity.zju.edu.cn"}:
            return "auth"
        return "courses"

    @staticmethod
    def _harden_acl(path: Path) -> None:
        harden_private_file(path)

    def _key(self, *, create: bool) -> bytes:
        encoded = keyring.get_password(KEYRING_SERVICE, KEYRING_SESSION_KEY)
        if encoded:
            try:
                return encoded.encode("ascii")
            except UnicodeEncodeError as exc:
                raise ZJUError("session_corrupt", "The protected session key is invalid.") from exc
        if not create:
            raise AuthenticationRequired()
        key = Fernet.generate_key()
        keyring.set_password(KEYRING_SERVICE, KEYRING_SESSION_KEY, key.decode("ascii"))
        return key

    def save(
        self,
        cookies: Iterable[httpx.Cookie],
        *,
        account: str,
        user_id: str | None,
        ttl_hours: int = 12,
    ) -> None:
        now = datetime.now(timezone.utc)
        payload = {
            "schema_version": 1,
            "account_last4": account[-4:],
            "user_id": str(user_id) if user_id else None,
            "created_at": _rfc3339(now),
            "expires_at": _rfc3339(now + timedelta(hours=ttl_hours)),
            "cookies": [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path or "/",
                    "secure": bool(cookie.secure),
                    "expires": cookie.expires,
                    "service": self._cookie_service(cookie.domain or ""),
                }
                for cookie in cookies
            ],
        }
        target = session_path()
        state_dir().mkdir(parents=True, exist_ok=True)
        encrypted = Fernet(self._key(create=True)).encrypt(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        temporary = target.with_suffix(".tmp")
        with temporary.open("wb") as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        try:
            self._harden_acl(target)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def load(self, *, allow_expired: bool = False) -> dict[str, Any]:
        target = session_path()
        if not target.is_file():
            raise AuthenticationRequired()
        try:
            decrypted = Fernet(self._key(create=False)).decrypt(target.read_bytes())
            payload = json.loads(decrypted.decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
            raise ZJUError("session_corrupt", "The encrypted ZJU session is unreadable; log out and sign in again.") from exc
        if payload.get("schema_version") != 1 or not isinstance(payload.get("cookies"), list):
            raise ZJUError("session_corrupt", "The encrypted ZJU session has an unsupported format.")
        if not allow_expired:
            expires = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
            if expires <= datetime.now(timezone.utc):
                raise AuthenticationRequired("The local ZJU session expired; run the authentication script again.")
        return payload

    def cookies(self, service: str | None = None) -> httpx.Cookies:
        payload = self.load()
        jar = httpx.Cookies()
        for item in payload["cookies"]:
            if not isinstance(item, dict):
                continue
            item_service = str(item.get("service") or self._cookie_service(str(item.get("domain", ""))))
            if service is not None and item_service != service:
                continue
            jar.set(
                str(item.get("name", "")),
                str(item.get("value", "")),
                domain=str(item.get("domain", "")) or None,
                path=str(item.get("path", "/")),
            )
        return jar

    def status(self) -> dict[str, Any]:
        try:
            payload = self.load()
        except AuthenticationRequired as exc:
            return {"authenticated": False, "reason": exc.safe_message}
        return {
            "authenticated": True,
            "account_last4": payload.get("account_last4"),
            "created_at": payload.get("created_at"),
            "expires_at": payload.get("expires_at"),
        }

    def clear(self) -> None:
        target = session_path()
        if target.exists():
            target.unlink()
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_SESSION_KEY)
        except keyring.errors.PasswordDeleteError:
            pass
