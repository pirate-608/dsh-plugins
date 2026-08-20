from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PLUGIN_ROOT / "scripts" / "prepare_renpy_asset.py"
INSPECT_PATH = PLUGIN_ROOT / "scripts" / "inspect_renpy_project.py"
SPEC = importlib.util.spec_from_file_location("prepare_renpy_asset", SCRIPT_PATH)
assert SPEC and SPEC.loader
asset_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(asset_module)


class AssetWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "game").mkdir()
        (self.root / "game" / "gui.rpy").write_text("init python:\n    gui.init(1280, 720)\n", encoding="utf-8")
        self.incoming = self.root / ".renpy-assets" / "incoming"
        self.incoming.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_rgb(self, name: str, size: tuple[int, int] = (800, 800)) -> Path:
        path = self.incoming / name
        Image.new("RGB", size, (20, 40, 60)).save(path)
        return path

    def make_sprite(self, name: str, box: tuple[int, int, int, int]) -> Path:
        path = self.incoming / name
        image = Image.new("RGBA", (500, 900), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle(box, fill=(220, 100, 80, 255))
        image.save(path)
        return path

    def prepare(self, **overrides):
        values = {
            "project": self.root,
            "input_path": self.make_rgb("input.png"),
            "role": "background",
            "name": "BG Classroom-Day",
        }
        values.update(overrides)
        return asset_module.prepare_asset(**values)

    def test_rejects_input_outside_project(self) -> None:
        outside = self.root.parent / "outside-renpy-test.png"
        Image.new("RGB", (10, 10)).save(outside)
        self.addCleanup(outside.unlink, missing_ok=True)
        with self.assertRaisesRegex(asset_module.AssetPreparationError, "inside the project"):
            self.prepare(input_path=outside)

    def test_background_is_named_cropped_hashed_and_manifested(self) -> None:
        entry = self.prepare(prompt="empty classroom at dawn")
        output = self.root / entry["output"]
        self.assertEqual(entry["renpy_name"], "bg classroom day")
        self.assertEqual(output.name, "bg_classroom_day.png")
        with Image.open(output) as image:
            self.assertEqual(image.size, (1280, 720))
        self.assertEqual(entry["sha256"], asset_module._sha256(output))
        manifest = json.loads((self.root / ".renpy-assets" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["assets"][0]["prompt"], "empty classroom at dawn")

    def test_existing_asset_gets_safe_versioned_sibling(self) -> None:
        source = self.make_rgb("repeat.png")
        first = self.prepare(input_path=source, name="bg station")
        second = self.prepare(input_path=source, name="bg station")
        self.assertEqual(Path(first["output"]).name, "bg_station.png")
        self.assertEqual(Path(second["output"]).name, "bg_station_v2.png")
        self.assertNotEqual(first["id"], second["id"])

    def test_cli_accepts_project_relative_input(self) -> None:
        source = self.make_rgb("cli.png", (640, 480))
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--project",
                str(self.root),
                "--input",
                source.relative_to(self.root).as_posix(),
                "--role",
                "cg",
                "--name",
                "cg opening",
                "--prompt",
                "opening illustration",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        entry = json.loads(result.stdout)
        self.assertEqual(entry["output"], "game/images/cg_opening.png")
        self.assertEqual(entry["prompt"], "opening illustration")

    def test_sprite_without_alpha_is_rejected(self) -> None:
        with self.assertRaisesRegex(asset_module.AssetPreparationError, "no alpha channel"):
            self.prepare(
                input_path=self.make_rgb("opaque.png"),
                role="sprite",
                name="eileen neutral",
                character="eileen",
            )

    def test_neutral_establishes_canvas_and_variant_reuses_baseline(self) -> None:
        neutral = self.prepare(
            input_path=self.make_sprite("neutral.png", (120, 80, 380, 880)),
            role="sprite",
            name="eileen neutral",
            character="eileen",
        )
        happy = self.prepare(
            input_path=self.make_sprite("happy.png", (170, 150, 350, 850)),
            role="sprite",
            name="eileen happy",
            character="eileen",
            references=[self.root / neutral["output"]],
        )
        self.assertEqual(neutral["canvas"], happy["canvas"])
        self.assertEqual((neutral["width"], neutral["height"]), (happy["width"], happy["height"]))
        for entry in (neutral, happy):
            with Image.open(self.root / entry["output"]) as image:
                self.assertIn("A", image.getbands())
                self.assertEqual(image.getchannel("A").getbbox()[3], 720)

    def test_variant_before_neutral_is_rejected(self) -> None:
        with self.assertRaisesRegex(asset_module.AssetPreparationError, "neutral sprite"):
            self.prepare(
                input_path=self.make_sprite("happy-first.png", (100, 100, 400, 850)),
                role="sprite",
                name="eileen happy",
                character="eileen",
            )

    def test_atomic_json_failure_preserves_original_and_cleans_temp(self) -> None:
        target = self.root / ".renpy-assets" / "atomic.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"old": true}\n', encoding="utf-8")
        with mock.patch.object(asset_module.os, "replace", side_effect=OSError("locked")):
            with self.assertRaisesRegex(OSError, "locked"):
                asset_module._atomic_write_json(target, {"new": True})
        self.assertEqual(target.read_text(encoding="utf-8"), '{"old": true}\n')
        self.assertEqual(list(target.parent.glob(".atomic.json.*.tmp")), [])

    def test_project_audit_warns_for_unconfigured_cjk_font(self) -> None:
        (self.root / "game" / "script.rpy").write_text('label start:\n    "你好，世界"\n', encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(INSPECT_PATH), str(self.root)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertIn("CJK text locations: 1", result.stdout)
        self.assertIn("no bundled or configured font", result.stdout)

    def test_end_to_end_sample_asset_set_and_branching_scene(self) -> None:
        for index, location in enumerate(("classroom day", "station night", "rooftop sunset")):
            self.prepare(
                input_path=self.make_rgb(f"background-{index}.png", (900 + index * 50, 600)),
                role="background",
                name=f"bg {location}",
                prompt=f"visual novel background: {location}",
            )

        expressions = ("neutral", "happy", "sad", "surprised", "angry")
        for character_index, character in enumerate(("eileen", "lucy")):
            neutral_output = None
            for expression_index, expression in enumerate(expressions):
                entry = self.prepare(
                    input_path=self.make_sprite(
                        f"{character}-{expression}.png",
                        (100 + expression_index * 5, 70, 390 - expression_index * 3, 870),
                    ),
                    role="sprite",
                    name=f"{character} {expression}",
                    character=character,
                    prompt=f"{character} expression: {expression}",
                    references=[neutral_output] if neutral_output else [],
                )
                if expression == "neutral":
                    neutral_output = self.root / entry["output"]

        (self.root / "game" / "script.rpy").write_text(
            """label start:
    scene bg classroom day
    menu:
        \"Take the station route\":
            jump station_route
        \"Take the rooftop route\":
            jump rooftop_route

label station_route:
    scene bg station night
    show eileen happy
    return

label rooftop_route:
    scene bg rooftop sunset
    show lucy surprised
    return
""",
            encoding="utf-8",
        )
        manifest = json.loads((self.root / ".renpy-assets" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["assets"]), 13)
        self.assertEqual(len({item["output"] for item in manifest["assets"]}), 13)
        audit = subprocess.run(
            [sys.executable, str(INSPECT_PATH), str(self.root)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertIn("start (game", audit.stdout)
        self.assertIn("station_route", audit.stdout)
        self.assertIn("rooftop_route", audit.stdout)


if __name__ == "__main__":
    unittest.main()
