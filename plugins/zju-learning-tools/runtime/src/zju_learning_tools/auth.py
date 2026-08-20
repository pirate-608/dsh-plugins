from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse

import httpx

from .constants import ALLOWED_HOSTS, AUTH_HOSTS, COURSES_HOST, MAX_REDIRECTS, USER_AGENT
from .errors import ZJUError
from .session import SessionStore

try:
    from lazy_core.LoginRSA import RSAKeyPython, encrypted_string_python
except ImportError as exc:  # pragma: no cover - startup wiring error
    raise RuntimeError("The pinned LAZY RSA compatibility module is unavailable.") from exc


class _LoginFields(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        if values.get("name"):
            self.fields[values["name"]] = values.get("value", "")


class Authenticator:
    def __init__(self) -> None:
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
            follow_redirects=False,
            timeout=30.0,
            trust_env=False,
        )

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        current_method = method.upper()
        current_url = url
        current_kwargs = dict(kwargs)
        for _ in range(MAX_REDIRECTS + 1):
            parsed = urlparse(current_url)
            if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
                raise ZJUError("auth_flow_changed", "ZJU authentication redirected outside the approved HTTPS hosts.")
            response = self.client.request(current_method, current_url, **current_kwargs)
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if not location:
                raise ZJUError("auth_flow_changed", "ZJU authentication returned a redirect without a destination.")
            current_url = urljoin(str(response.url), location)
            if response.status_code == 303 or (response.status_code in {301, 302} and current_method == "POST"):
                current_method = "GET"
                current_kwargs = {}
        raise ZJUError("auth_flow_changed", "ZJU authentication exceeded the safe redirect limit.")

    def login(self, account: str, password: str) -> dict[str, str | None]:
        account = account.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", account):
            raise ZJUError("invalid_account", "The ZJU account identifier has an unexpected format.")
        entry = self._request("GET", "https://courses.zju.edu.cn/user/index#/")
        login_host = (entry.url.host or "").lower()
        if login_host not in AUTH_HOSTS:
            if entry.status_code == 200 and entry.url.host == COURSES_HOST:
                return self._persist_authenticated(account, entry.text)
            raise ZJUError("auth_flow_changed", "The expected ZJU CAS login page was not reached.")

        fields_parser = _LoginFields()
        fields_parser.feed(entry.text)
        execution = fields_parser.fields.get("execution")
        if not execution:
            raise ZJUError("auth_flow_changed", "The CAS login form changed or requires interactive verification.")

        pubkey = self._request("GET", "https://zjuam.zju.edu.cn/cas/v2/getPubKey")
        try:
            key_data = pubkey.json()
            exponent = str(key_data["exponent"])
            modulus = str(key_data["modulus"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ZJUError("auth_flow_changed", "The ZJU RSA public-key response changed.") from exc
        rsa_key = RSAKeyPython(public_exponent_hex=exponent, modulus_hex=modulus)
        encrypted = encrypted_string_python(rsa_key, password[::-1])
        form = {
            key: value
            for key, value in fields_parser.fields.items()
            if key.lower() not in {"username", "password", "authcode"}
        }
        form.update({
            "username": account,
            "password": encrypted,
            "authcode": "",
            "execution": execution,
            "_eventId": "submit",
        })
        result = self._request("POST", str(entry.url), data=form)
        if result.status_code >= 400:
            raise ZJUError("login_failed", "ZJU authentication failed; verify the account or complete required verification in the official site.")
        validation = self._request("GET", "https://courses.zju.edu.cn/api/activities/is-locked")
        if validation.status_code != 200 or validation.url.host != COURSES_HOST:
            raise ZJUError("login_failed", "ZJU authentication did not produce a valid course-system session.")

        # Best-effort classroom bootstrap. Failure does not invalidate Courses access.
        try:
            self._request(
                "GET",
                "https://tgmedia.cmc.zju.edu.cn/index.php?r=auth/login&auType=cmc&tenant_code=112&forward=https%3A%2F%2Fclassroom.zju.edu.cn%2F",
            )
        except ZJUError:
            pass
        return self._persist_authenticated(account, result.text)

    def _persist_authenticated(self, account: str, html: str) -> dict[str, str | None]:
        match = re.search(r'id=["\']userId["\'][^>]*value=["\']([^"\']+)', html, re.IGNORECASE)
        user_id = match.group(1) if match else None
        SessionStore().save(self.client.cookies.jar, account=account, user_id=user_id)
        return {"account_last4": account[-4:], "user_id": user_id}
