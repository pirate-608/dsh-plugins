from __future__ import annotations

from pathlib import Path
import os

PLUGIN_NAME = "zju-learning-tools"
USER_AGENT = "ZJU-Learning-Tools/0.3.0 (local DSH plugin; gated assignment submission)"

COURSES_HOST = "courses.zju.edu.cn"
AUTH_HOSTS = frozenset({"zjuam.zju.edu.cn", "identity.zju.edu.cn"})
CLASSROOM_HOSTS = frozenset({
    "classroom.zju.edu.cn",
    "tgmedia.cmc.zju.edu.cn",
    "yjapi.cmc.zju.edu.cn",
})
ALLOWED_HOSTS = frozenset({COURSES_HOST, *AUTH_HOSTS, *CLASSROOM_HOSTS})
READ_METHODS = frozenset({"GET", "HEAD"})
ASSIGNMENT_WRITE_METHODS = frozenset({"POST", "PUT"})

DEFAULT_FILE_LIMIT = 250 * 1024 * 1024
MAX_FILE_LIMIT = 250 * 1024 * 1024
MAX_BATCH_FILES = 50
MAX_BATCH_BYTES = 1024 * 1024 * 1024
REQUEST_INTERVAL_SECONDS = 0.55
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 8
MAX_SUBMISSION_FILES = 10
MAX_SUBMISSION_FILE_BYTES = 100 * 1024 * 1024
MAX_SUBMISSION_BYTES = 250 * 1024 * 1024
MAX_SUBMISSION_COMMENT_CHARS = 5000
APPROVAL_TTL_SECONDS = 120

KEYRING_SERVICE = "pirate-608.zju-learning-tools"
KEYRING_SESSION_KEY = "session-encryption-key"


def state_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / "pirate-608" / PLUGIN_NAME


def session_path() -> Path:
    return state_dir() / "session.enc"


def write_policy_path() -> Path:
    return state_dir() / "write-policy.json"


def submission_ledger_path() -> Path:
    return state_dir() / "submission-ledger.json"


def submission_lock_path() -> Path:
    return state_dir() / "submission.lock"
