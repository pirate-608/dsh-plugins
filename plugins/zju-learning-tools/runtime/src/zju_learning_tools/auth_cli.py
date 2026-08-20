from __future__ import annotations

import argparse
import getpass
import json
import sys

from .auth import Authenticator
from .errors import ZJUError
from .session import SessionStore


def _print(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="User-owned local authentication for ZJU Learning Tools")
    parser.add_argument("command", choices=("login", "status", "logout"))
    args = parser.parse_args()
    store = SessionStore()
    if args.command == "status":
        try:
            _print(store.status())
            return 0
        except Exception:
            _print({"ok": False, "error": {"code": "session_error", "message": "The protected session status could not be read."}})
            return 1
    if args.command == "logout":
        try:
            store.clear()
            _print({"ok": True, "authenticated": False})
            return 0
        except Exception:
            _print({"ok": False, "error": {"code": "session_error", "message": "The protected session could not be fully cleared."}})
            return 1
    if not sys.stdin.isatty():
        _print({"ok": False, "error": "Login requires an interactive terminal owned by the user."})
        return 2
    account = input("ZJU account: ").strip()
    password = getpass.getpass("ZJU password (not stored): ")
    authenticator = Authenticator()
    try:
        result = authenticator.login(account, password)
    except ZJUError as exc:
        _print({"ok": False, "error": {"code": exc.code, "message": exc.safe_message}})
        return 1
    except Exception:
        _print({"ok": False, "error": {"code": "login_error", "message": "Local ZJU authentication failed without exposing sensitive diagnostics."}})
        return 1
    finally:
        password = ""
        authenticator.close()
    _print({"ok": True, "authenticated": True, **result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
