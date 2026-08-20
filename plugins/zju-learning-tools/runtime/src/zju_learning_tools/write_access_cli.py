from __future__ import annotations

import argparse
import json
import sys

from .errors import ZJUError
from .write_policy import WritePolicy


def _print(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="User-owned assignment-submission capability for ZJU Learning Tools")
    parser.add_argument("command", choices=("enable", "status", "disable"))
    parser.add_argument("--root", action="append", default=[], help="Existing absolute directory containing reviewed submission files")
    args = parser.parse_args()
    policy = WritePolicy()
    try:
        if args.command == "status":
            _print({"ok": True, **policy.status(include_roots=True)})
            return 0
        if not sys.stdin.isatty():
            _print({"ok": False, "error": {"code": "interactive_required", "message": "Changing assignment-submit access requires a terminal owned by the user."}})
            return 2
        if args.command == "disable":
            confirmation = input("Type DISABLE to turn off assignment submission: ").strip()
            if confirmation != "DISABLE":
                _print({"ok": False, "error": {"code": "cancelled", "message": "No policy change was made."}})
                return 1
            policy.disable()
            _print({"ok": True, **policy.status(include_roots=True)})
            return 0
        if not args.root:
            _print({"ok": False, "error": {"code": "root_required", "message": "Pass at least one existing absolute directory with -Root."}})
            return 2
        print("This permits one-time, separately confirmed final homework submissions from the listed roots.")
        print("It does not permit exams, quizzes, questionnaires, attendance, discussion posting, batch jobs, or automatic retries.")
        confirmation = input("Type ENABLE ASSIGNMENT SUBMISSION to continue: ").strip()
        if confirmation != "ENABLE ASSIGNMENT SUBMISSION":
            _print({"ok": False, "error": {"code": "cancelled", "message": "No policy change was made."}})
            return 1
        payload = policy.enable(args.root)
        _print({"ok": True, **payload})
        return 0
    except ZJUError as exc:
        _print({"ok": False, "error": {"code": exc.code, "message": exc.safe_message}})
        return 1
    except Exception:
        _print({"ok": False, "error": {"code": "write_policy_error", "message": "The local write policy could not be changed safely."}})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
