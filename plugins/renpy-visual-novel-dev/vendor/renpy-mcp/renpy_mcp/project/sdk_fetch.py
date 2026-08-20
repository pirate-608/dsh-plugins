"""Download and extract a Ren'Py SDK into a local cache.

The SDK is the largest install-friction this server has. README §Install
tells users to clone the repo and run `gui/launch.sh` to fetch it, but
MCP-only setups (Claude Code with `pip install`, hermes-agent with the
config snippet) don't have that. This module is the agent-friendly
equivalent: a stdlib-only fetch + extract that mirrors the 200 MB
tar.bz2 from renpy.org into ``$XDG_CACHE_HOME/renpy-mcp/sdk-<version>``.

Idempotent — if the destination already has a `renpy.sh`, the function
returns the existing path without re-downloading.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DOWNLOAD_INDEX = "https://www.renpy.org/dl/"
DEFAULT_VERSION = "8.6.0"
# Pin a known-good version when --fetch-sdk runs without a network probe;
# bump this in lockstep with the release notes when the SDK changes shape.

_VERSION_HREF_RE = re.compile(r'href="(\d+\.\d+\.\d+)/"')


class SDKFetchError(Exception):
    """Raised when the fetch process can't complete (network, IO, layout)."""


@dataclass(frozen=True)
class FetchResult:
    sdk_path: Path
    version: str
    cached: bool  # False == we just downloaded it; True == reuse


def default_cache_dir() -> Path:
    """Return the persistent SDK cache root.

    Honors `$RENPY_MCP_SDK_CACHE` first (lets users override without
    fighting `$XDG_CACHE_HOME`), then falls back to the standard
    `$XDG_CACHE_HOME/renpy-mcp/` (or `~/.cache/renpy-mcp/`).
    """
    override = os.environ.get("RENPY_MCP_SDK_CACHE")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "renpy-mcp"


def cached_sdk(cache_dir: Path | None = None) -> Path | None:
    """Return the most-recently-installed cached SDK, or None.

    Picks the highest-version directory under ``cache_dir`` whose
    ``renpy.sh`` exists. Used by ``__main__`` to fall back to the
    cache when ``--sdk`` and ``$RENPY_SDK`` are both unset.
    """
    cache_dir = cache_dir or default_cache_dir()
    if not cache_dir.is_dir():
        return None
    candidates: list[tuple[tuple[int, int, int], Path]] = []
    for child in cache_dir.iterdir():
        if not child.is_dir() or not child.name.startswith("sdk-"):
            continue
        version = child.name.removeprefix("sdk-")
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
        if not m:
            continue
        if not (child / "renpy.sh").is_file():
            continue
        candidates.append(((int(m.group(1)), int(m.group(2)), int(m.group(3))), child))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def latest_version() -> str:
    """Probe https://www.renpy.org/dl/ for the highest 8.x release.

    Falls back to ``DEFAULT_VERSION`` on network errors so callers in
    air-gapped contexts still get a usable answer (they can override
    via the explicit `version` argument anyway).
    """
    try:
        with urllib.request.urlopen(DOWNLOAD_INDEX, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        log.warning("could not probe %s for latest version: %s", DOWNLOAD_INDEX, exc)
        return DEFAULT_VERSION
    versions = sorted(
        {tuple(int(p) for p in v.split(".")) for v in _VERSION_HREF_RE.findall(html)},
        reverse=True,
    )
    if not versions:
        return DEFAULT_VERSION
    # Stick to the 8.x line — 7.x is the legacy fork.
    eight_x = [v for v in versions if v[0] == 8]
    pick = eight_x[0] if eight_x else versions[0]
    return ".".join(str(p) for p in pick)


def fetch_sdk(
    version: str | None = None,
    *,
    cache_dir: Path | None = None,
    progress: bool = True,
) -> FetchResult:
    """Download (or reuse) a Ren'Py SDK and return its path.

    On a fresh machine: pulls ``renpy-<version>-sdk.tar.bz2`` from
    renpy.org, extracts it under ``cache_dir``, and returns
    ``<cache_dir>/sdk-<version>``. On a warm machine: returns the
    existing path immediately.
    """
    cache_dir = cache_dir or default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    resolved_version = version or latest_version()

    target = cache_dir / f"sdk-{resolved_version}"
    if (target / "renpy.sh").is_file():
        return FetchResult(sdk_path=target, version=resolved_version, cached=True)

    archive_url = (
        f"{DOWNLOAD_INDEX}{resolved_version}/renpy-{resolved_version}-sdk.tar.bz2"
    )
    if progress:
        log.info("downloading Ren'Py SDK %s from %s", resolved_version, archive_url)
    try:
        with tempfile.TemporaryDirectory(prefix="renpy-mcp-fetch-") as tmpdir:
            tmp = Path(tmpdir)
            archive_path = tmp / f"renpy-{resolved_version}-sdk.tar.bz2"
            _download(archive_url, archive_path)
            extract_root = tmp / "extract"
            extract_root.mkdir()
            _safe_extract(archive_path, extract_root)
            extracted = _locate_sdk_root(extract_root)
            if extracted is None:
                raise SDKFetchError(
                    f"archive at {archive_url} did not contain a renpy.sh "
                    "(unexpected layout)"
                )
            # Atomic-ish rename; if the target somehow appeared during
            # extraction (parallel fetches), back off to it.
            if (target / "renpy.sh").is_file():
                return FetchResult(sdk_path=target, version=resolved_version, cached=True)
            shutil.move(str(extracted), str(target))
    except (urllib.error.URLError, OSError, tarfile.TarError) as exc:
        raise SDKFetchError(f"fetch failed: {exc}") from exc

    return FetchResult(sdk_path=target, version=resolved_version, cached=False)


# ---------- helpers -------------------------------------------------------------


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as resp:
        with dest.open("wb") as fh:
            shutil.copyfileobj(resp, fh)


def _safe_extract(archive: Path, into: Path) -> None:
    """Extract `archive` into `into`, refusing path-traversal entries.

    Standard `tar.extractall` is unsafe against malicious archives. We
    trust renpy.org but still gate paths so a single misbehaving release
    can't write outside the extract root.
    """
    with tarfile.open(archive, "r:bz2") as tf:
        for member in tf.getmembers():
            target = (into / member.name).resolve()
            if not str(target).startswith(str(into.resolve()) + os.sep) and target != into.resolve():
                raise SDKFetchError(f"refusing path-traversal entry: {member.name!r}")
        tf.extractall(into)


def _locate_sdk_root(extract_root: Path) -> Path | None:
    """Return the directory containing renpy.sh (typically `renpy-X.Y.Z-sdk/`)."""
    direct = extract_root / "renpy.sh"
    if direct.is_file():
        return extract_root
    for child in extract_root.iterdir():
        if child.is_dir() and (child / "renpy.sh").is_file():
            return child
    return None


__all__ = [
    "DEFAULT_VERSION",
    "FetchResult",
    "SDKFetchError",
    "cached_sdk",
    "default_cache_dir",
    "fetch_sdk",
    "latest_version",
]
