"""MEDIA.md compliance helpers.

Provides:

* ``MEDIA_INVARIANTS`` — the structured form of MEDIA.md's "four invariants",
  used by the ``get_media_invariants`` Tier 1 tool so agents can consume the
  rules without parsing markdown.
* ``probe_image`` — minimal PNG/JPEG header reader returning width/height and
  alpha-channel presence. No external dependencies.
* ``compliance_warnings_for_alias`` — given an image name, asset path, and
  resolved project root, return a list of human-readable warnings about the
  asset's deviation from MEDIA.md's invariants. Used by ``add_image_alias`` to
  surface dimension/alpha drift without rejecting the write.

The probe deliberately stays in the standard library: a hard dependency on
Pillow would be a sledgehammer for "read 24 bytes of header info."
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

# MEDIA.md §"Four invariants" + §"Quick lookup table" condensed into a JSON
# shape that's cheap to consume from a tool response.
DEFAULT_SCREEN_WIDTH = 1920
DEFAULT_SCREEN_HEIGHT = 1080

MEDIA_INVARIANTS: dict = {
    "image": {
        "background": {
            "format": ["png", "jpg"],
            "exact_size": [DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT],
            "alpha_required": False,
            "tag_hint": "first token `bg` (e.g. `bg cafe`)",
        },
        "sprite": {
            "format": ["png"],
            "height": DEFAULT_SCREEN_HEIGHT,
            "alpha_required": True,
            "no_painted_background": True,
            "tag_hint": "first token is the character variable (e.g. `eileen happy`)",
        },
        "cg": {
            "format": ["png"],
            "exact_size": [DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT],
            "alpha_required": False,
            "tag_hint": "first token `cg` (e.g. `cg lighthouse_climb`)",
        },
        "ui": {
            "format": ["png"],
            "alpha_required": True,
            "directory_hint": "game/gui/",
        },
    },
    "audio": {
        "music": {"format": ["ogg"], "duration_seconds": [30, 180]},
        "voice": {"format": ["ogg", "mp3"]},
        "sfx": {"format": ["ogg", "wav"], "duration_seconds": [0.3, 3]},
        "ambience": {"format": ["ogg"], "duration_seconds": [60, 300]},
    },
    "naming": {
        "filename_underscore_means_space": True,
        "avoid_hyphens_in_image_filenames": True,
        "avoid_in_filenames": [":", ";", "\""],
    },
    "directories": {
        "backgrounds_sprites_cgs": "game/images/",
        "audio": "game/audio/",
        "ui": "game/gui/",
    },
    "doc": "MEDIA.md (full prose; this dict is the machine-readable summary)",
}


# ---------- header probes -------------------------------------------------------


@dataclass(frozen=True)
class ImageProbe:
    """What we learn from reading the first ~30 bytes of an image file.

    ``has_alpha`` is True when the format declares per-pixel transparency:
    PNG color types 4 (gray+alpha) or 6 (RGBA), or any GIF/WebP/JPG that
    we can't introspect cheaply (in those cases the field is None — we
    err toward "don't warn" rather than risk false positives).
    """

    width: int | None
    height: int | None
    format: str  # "png" | "jpg" | "jpeg" | "webp" | "gif" | "unknown"
    has_alpha: bool | None


def probe_image(path: Path) -> ImageProbe:
    """Read the file's header and return its dimensions + alpha presence.

    Only PNG and JPEG headers are decoded — those are the only formats
    MEDIA.md considers "in scope" for VN art. Other formats return
    ``unknown`` width/height and ``None`` alpha so we never produce
    false-positive warnings.
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(32)
    except OSError:
        return ImageProbe(None, None, "unknown", None)

    # PNG: 8-byte signature, then IHDR (width, height, bit-depth, color-type).
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            width, height = struct.unpack(">II", head[16:24])
            color_type = head[25]
            # Color types: 0=gray, 2=RGB, 3=palette, 4=gray+alpha, 6=RGBA.
            # Type 3 (palette) can carry transparency through the tRNS
            # chunk, but reading that chunk requires walking past IHDR;
            # mark it None to avoid false positives on indexed images.
            if color_type in (4, 6):
                has_alpha: bool | None = True
            elif color_type in (0, 2):
                has_alpha = False
            else:
                has_alpha = None
            return ImageProbe(width, height, "png", has_alpha)
        except struct.error:
            return ImageProbe(None, None, "png", None)

    # JPEG: starts with SOI 0xFFD8, then a series of segments. To find
    # dimensions cheaply we re-open and walk to the SOFn (Start-of-Frame)
    # marker. JPEG never has alpha.
    if head[:2] == b"\xff\xd8":
        return ImageProbe(*_read_jpeg_dimensions(path), "jpg", False)

    # WebP / GIF / other: return what we have.
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ImageProbe(None, None, "webp", None)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        try:
            width, height = struct.unpack("<HH", head[6:10])
            return ImageProbe(width, height, "gif", None)
        except struct.error:
            return ImageProbe(None, None, "gif", None)

    return ImageProbe(None, None, "unknown", None)


def _read_jpeg_dimensions(path: Path) -> tuple[int | None, int | None]:
    """Walk JPEG segments until we hit a SOFn marker, then read W×H.

    Returns (None, None) on any unexpected byte pattern. JPEG dimensions
    require walking past variable-length APPn segments, so we can't
    decode them from a 32-byte head buffer.
    """
    try:
        with path.open("rb") as fh:
            if fh.read(2) != b"\xff\xd8":
                return None, None
            while True:
                byte = fh.read(1)
                if not byte:
                    return None, None
                if byte != b"\xff":
                    # Misaligned — bail out rather than guess.
                    return None, None
                # Marker byte; skip any 0xFF padding.
                marker = fh.read(1)
                while marker == b"\xff":
                    marker = fh.read(1)
                if not marker:
                    return None, None
                m = marker[0]
                # Standalone markers carry no payload; skip.
                if m in (0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9):
                    continue
                length_bytes = fh.read(2)
                if len(length_bytes) < 2:
                    return None, None
                length = struct.unpack(">H", length_bytes)[0]
                # Start-of-Frame markers (SOF0..SOF15 except DHT/JPG/DAC).
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    payload = fh.read(length - 2)
                    if len(payload) < 5:
                        return None, None
                    height = struct.unpack(">H", payload[1:3])[0]
                    width = struct.unpack(">H", payload[3:5])[0]
                    return width, height
                fh.seek(length - 2, 1)
    except OSError:
        return None, None


# ---------- inference + warning emission ---------------------------------------


_BG_TAG_RE = re.compile(r"^\s*bg(\s|$)")
_CG_TAG_RE = re.compile(r"^\s*cg(\s|$)")


def infer_image_role(image_name: str) -> str:
    """Guess whether an image is a background, CG, or sprite from its name.

    Heuristic mirrors MEDIA.md §"Naming conventions": tag `bg` -> background,
    `cg` -> cinematic, anything else -> sprite. The agent can override by
    passing ``role`` explicitly to ``compliance_warnings_for_alias``.
    """
    if _BG_TAG_RE.match(image_name):
        return "background"
    if _CG_TAG_RE.match(image_name):
        return "cg"
    return "sprite"


def compliance_warnings_for_alias(
    *,
    image_name: str,
    asset_rel: str,
    project_root: Path,
    screen_size: tuple[int, int] = (DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT),
    role: str | None = None,
) -> list[str]:
    """Return MEDIA.md-shaped warnings for an `image <name> = "<asset>"` pair.

    Empty list means the asset matches the invariants. Each warning is a
    short, agent-actionable sentence. Never raises — a missing or
    unreadable file simply produces no warnings (the existence check
    lives in the caller).
    """
    asset_path = project_root / "game" / asset_rel
    if not asset_path.is_file():
        return []
    role = role or infer_image_role(image_name)
    probe = probe_image(asset_path)
    warnings: list[str] = []

    expected_format = {"background": ("png", "jpg"), "sprite": ("png",), "cg": ("png",)}
    allowed = expected_format.get(role, ("png", "jpg"))
    if probe.format not in allowed and probe.format != "unknown":
        warnings.append(
            f"{role}: format `{probe.format}` not in MEDIA.md's allowed list "
            f"{list(allowed)} for {role}s"
        )

    sw, sh = screen_size
    if role == "background" or role == "cg":
        if probe.width is not None and probe.height is not None:
            if (probe.width, probe.height) != (sw, sh):
                warnings.append(
                    f"{role}: dimensions {probe.width}x{probe.height} do not "
                    f"match screen size {sw}x{sh} (MEDIA.md §Backgrounds)"
                )
    elif role == "sprite":
        if probe.height is not None and probe.height != sh:
            warnings.append(
                f"sprite: height {probe.height} != screen height {sh} "
                f"(MEDIA.md §Sprites: sprites are 1080 tall on transparent canvas)"
            )
        if probe.format == "png" and probe.has_alpha is False:
            warnings.append(
                "sprite: PNG has no alpha channel — sprites must sit on "
                "transparency or you'll see a rectangle behind the character. "
                "Run a background-removal pass before registering."
            )

    return warnings


__all__ = [
    "MEDIA_INVARIANTS",
    "DEFAULT_SCREEN_WIDTH",
    "DEFAULT_SCREEN_HEIGHT",
    "ImageProbe",
    "compliance_warnings_for_alias",
    "infer_image_role",
    "probe_image",
]
