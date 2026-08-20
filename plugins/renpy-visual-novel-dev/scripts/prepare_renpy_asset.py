#!/usr/bin/env python3
"""Normalize a generated image and register reproducible Ren'Py asset metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


DEFAULT_SCREEN_SIZE = (1920, 1080)
MANIFEST_SCHEMA_VERSION = 1
VALID_ROLES = {"background", "cg", "sprite", "ui"}
VALID_STATUSES = {"draft", "approved"}


class AssetPreparationError(ValueError):
    """Raised when an asset cannot be prepared without violating project rules."""


def _resolve_inside(path: Path, root: Path, *, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise AssetPreparationError(f"{label} must be inside the project: {resolved}")
    return resolved


def _safe_slug(value: str, *, label: str) -> str:
    normalized = value.strip().lower().replace("'", "")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise AssetPreparationError(f"{label} must contain an ASCII letter or digit")
    return normalized


def normalize_image_name(value: str) -> tuple[str, str]:
    """Return a Ren'Py space-delimited name and a safe underscore filename stem."""
    stem = _safe_slug(value, label="name")
    return stem.replace("_", " "), stem


def _versioned_path(path: Path) -> Path:
    if not path.exists():
        return path
    for version in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}_v{version}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise AssetPreparationError(f"unable to allocate a versioned filename for {path.name}")


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _screen_size(project: Path) -> tuple[int, int]:
    patterns = (
        re.compile(r"gui\.init\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)"),
        re.compile(r"config\.screen_width\s*=\s*(\d+).*?config\.screen_height\s*=\s*(\d+)", re.S),
    )
    for relative in ("game/gui.rpy", "game/options.rpy"):
        path = project / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return int(match.group(1)), int(match.group(2))
    return DEFAULT_SCREEN_SIZE


def _has_alpha(image: Image.Image) -> bool:
    return "A" in image.getbands() or "transparency" in image.info


def _copy_source(project: Path, input_path: Path, stem: str, *, replace: bool) -> Path:
    source_dir = project / ".renpy-assets" / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    suffix = input_path.suffix.lower() or ".png"
    target = source_dir / f"{stem}_source{suffix}"
    if not replace:
        target = _versioned_path(target)
    if input_path != target:
        shutil.copy2(input_path, target)
    return target


def _transparent_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise AssetPreparationError("sprite contains no visible pixels after transparency processing")
    return bbox


def _fit_sprite_subject(
    subject: Image.Image,
    *,
    canvas_width: int,
    canvas_height: int,
    subject_width: int,
    subject_height: int,
    baseline: int,
) -> Image.Image:
    scale = min(subject_width / subject.width, subject_height / subject.height)
    width = max(1, round(subject.width * scale))
    height = max(1, round(subject.height * scale))
    resized = subject.resize((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    x = (canvas_width - width) // 2
    y = baseline - height
    if x < 0 or y < 0 or x + width > canvas_width or y + height > canvas_height:
        raise AssetPreparationError("sprite cannot fit the character's canonical canvas")
    canvas.alpha_composite(resized, (x, y))
    return canvas


def _prepare_sprite(
    image: Image.Image,
    project: Path,
    character: str,
    expression: str,
    screen_size: tuple[int, int],
    *,
    replace: bool,
) -> tuple[Image.Image, dict[str, int]]:
    if not _has_alpha(image):
        raise AssetPreparationError("sprite input has no alpha channel; remove its background first")
    rgba = image.convert("RGBA")
    subject = rgba.crop(_transparent_bbox(rgba))
    character_slug = _safe_slug(character, label="character")
    profile_path = project / ".renpy-assets" / "characters" / f"{character_slug}.json"
    screen_width, screen_height = screen_size

    if not profile_path.exists():
        if expression != "neutral":
            raise AssetPreparationError("prepare a neutral sprite before expression variants")
        max_subject_height = max(1, round(screen_height * 0.94))
        max_subject_width = max(1, screen_width - 64)
        scale = min(max_subject_height / subject.height, max_subject_width / subject.width)
        subject_width = max(1, round(subject.width * scale))
        subject_height = max(1, round(subject.height * scale))
        canvas_width = min(screen_width, max(subject_width + 64, round(screen_width * 0.5)))
        profile = {
            "canvas_width": canvas_width,
            "canvas_height": screen_height,
            "subject_width": subject_width,
            "subject_height": subject_height,
            "baseline": screen_height,
        }
        _atomic_write_json(profile_path, {"schema_version": 1, "character": character_slug, **profile})
    else:
        profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
        profile = {key: int(profile_data[key]) for key in (
            "canvas_width", "canvas_height", "subject_width", "subject_height", "baseline"
        )}
        if profile["canvas_height"] != screen_height:
            raise AssetPreparationError("character profile screen height no longer matches the project")
        if expression == "neutral" and not replace:
            raise AssetPreparationError("neutral sprite already defines this character profile; use --replace intentionally")

    prepared = _fit_sprite_subject(subject, **profile)
    return prepared, profile


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": MANIFEST_SCHEMA_VERSION, "assets": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION or not isinstance(data.get("assets"), list):
        raise AssetPreparationError("unsupported or malformed .renpy-assets/manifest.json")
    return data


def prepare_asset(
    *,
    project: Path,
    input_path: Path,
    role: str,
    name: str,
    character: str | None = None,
    replace: bool = False,
    prompt: str = "",
    references: list[Path] | None = None,
    generator: str = "external-or-user-provided",
    status: str = "draft",
) -> dict[str, Any]:
    project = project.resolve()
    if not (project / "game").is_dir():
        raise AssetPreparationError(f"not a Ren'Py project (missing game/): {project}")
    if role not in VALID_ROLES:
        raise AssetPreparationError(f"unsupported role: {role}")
    if status not in VALID_STATUSES:
        raise AssetPreparationError(f"unsupported status: {status}")
    if not input_path.is_absolute():
        input_path = project / input_path
    input_path = _resolve_inside(input_path, project, label="input")
    if not input_path.is_file():
        raise AssetPreparationError(f"input file does not exist: {input_path}")

    renpy_name, stem = normalize_image_name(name)
    reference_paths = []
    for path in references or []:
        if not path.is_absolute():
            path = project / path
        reference_paths.append(_resolve_inside(path, project, label="reference"))
    for reference in reference_paths:
        if not reference.is_file():
            raise AssetPreparationError(f"reference file does not exist: {reference}")

    source_path = _copy_source(project, input_path, stem, replace=replace)
    screen_size = _screen_size(project)
    output_dir = project / "game" / ("gui" if role == "ui" else "images")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{stem}.png"
    if output_path.exists() and not replace:
        output_path = _versioned_path(output_path)

    with Image.open(source_path) as opened:
        image = ImageOps.exif_transpose(opened)
        profile: dict[str, int] | None = None
        expression: str | None = None
        if role in {"background", "cg"}:
            prepared = ImageOps.fit(image.convert("RGB"), screen_size, method=Image.Resampling.LANCZOS)
        elif role == "ui":
            if not _has_alpha(image):
                raise AssetPreparationError("UI input has no alpha channel")
            prepared = image.convert("RGBA")
        else:
            if not character:
                raise AssetPreparationError("--character is required for sprites")
            character_slug = _safe_slug(character, label="character")
            tokens = renpy_name.split()
            if len(tokens) < 2 or tokens[0] != character_slug:
                raise AssetPreparationError("sprite name must start with the character id and include an expression")
            expression = " ".join(tokens[1:])
            prepared, profile = _prepare_sprite(
                image, project, character_slug, expression, screen_size, replace=replace
            )
        prepared.save(output_path, format="PNG", optimize=True)

    output_relative = output_path.relative_to(project).as_posix()
    source_relative = source_path.relative_to(project).as_posix()
    final_sha = _sha256(output_path)
    with Image.open(output_path) as final_image:
        width, height = final_image.size
        has_alpha = _has_alpha(final_image)

    entry: dict[str, Any] = {
        "id": f"{output_path.stem}-{final_sha[:12]}",
        "role": role,
        "renpy_name": renpy_name,
        "source": source_relative,
        "output": output_relative,
        "prompt": prompt,
        "reference_assets": [path.relative_to(project).as_posix() for path in reference_paths],
        "generator": generator,
        "width": width,
        "height": height,
        "has_alpha": has_alpha,
        "sha256": final_sha,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
    }
    if role == "sprite":
        entry.update({"character": _safe_slug(character or "", label="character"), "expression": expression})
        entry["canvas"] = profile

    manifest_path = project / ".renpy-assets" / "manifest.json"
    manifest = _load_manifest(manifest_path)
    if replace:
        manifest["assets"] = [item for item in manifest["assets"] if item.get("output") != output_relative]
    manifest["assets"].append(entry)
    _atomic_write_json(manifest_path, manifest)
    return entry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path, help="Ren'Py project root")
    parser.add_argument("--input", required=True, type=Path, help="project-internal source image")
    parser.add_argument("--role", required=True, choices=sorted(VALID_ROLES))
    parser.add_argument("--name", required=True, help="Ren'Py image name, such as 'bg classroom day'")
    parser.add_argument("--character", help="character id; required for sprites")
    parser.add_argument("--replace", action="store_true", help="replace the unversioned target intentionally")
    parser.add_argument("--prompt", default="", help="final image-generation prompt for provenance")
    parser.add_argument("--reference", action="append", default=[], type=Path, help="project-internal reference asset")
    parser.add_argument("--generator", default="external-or-user-provided")
    parser.add_argument("--status", choices=sorted(VALID_STATUSES), default="draft")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args()
    try:
        entry = prepare_asset(
            project=args.project,
            input_path=args.input,
            role=args.role,
            name=args.name,
            character=args.character,
            replace=args.replace,
            prompt=args.prompt,
            references=args.reference,
            generator=args.generator,
            status=args.status,
        )
    except (AssetPreparationError, OSError, json.JSONDecodeError) as exc:
        print(f"prepare-renpy-asset: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
