from __future__ import annotations

from pathlib import Path
import unittest

from zju_learning_tools.constants import ASSIGNMENT_WRITE_METHODS, READ_METHODS
from zju_learning_tools.server import mcp


class StaticBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_surface_contains_only_transactional_assignment_writes(self) -> None:
        tools = await mcp.list_tools()
        names = {tool.name for tool in tools}
        self.assertEqual(len(names), 25)
        self.assertIn("zju_download_resource", names)
        self.assertEqual(
            {name for name in names if "submission" in name},
            {"zju_prepare_assignment_submission", "zju_commit_assignment_submission"},
        )
        for forbidden in ("exam_submit", "quiz_submit", "answer", "signin", "sign_in", "post_discussion", "delete", "remove", "complete"):
            self.assertFalse(any(forbidden in name for name in names), (forbidden, sorted(names)))

    async def test_tool_schemas_do_not_accept_urls_or_credentials(self) -> None:
        tools = await mcp.list_tools()
        by_name = {tool.name: tool for tool in tools}
        serialized = "\n".join(str(tool.inputSchema).lower() for tool in tools)
        for forbidden in ("password", "cookie", "authorization", "raw_url", "endpoint"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(READ_METHODS, frozenset({"GET", "HEAD"}))
        self.assertEqual(ASSIGNMENT_WRITE_METHODS, frozenset({"POST", "PUT"}))
        prepare = by_name["zju_prepare_assignment_submission"].annotations
        commit = by_name["zju_commit_assignment_submission"].annotations
        self.assertTrue(prepare.readOnlyHint)
        self.assertFalse(commit.readOnlyHint)
        self.assertTrue(commit.destructiveHint)
        self.assertFalse(commit.idempotentHint)

    async def test_tools_are_partitioned_across_task_specific_skills(self) -> None:
        plugin_root = Path(__file__).resolve().parents[1]
        skills_root = plugin_root / "skills"
        expected_skills = {
            "zju-auth-session",
            "zju-course-planning",
            "zju-assignment-grades",
            "zju-assignment-submission",
            "zju-resource-downloads",
            "zju-assessments-discussions",
            "zju-zhiyun-classroom",
            "zju-tronclass-fallback",
        }
        actual_skills = {path.parent.name for path in skills_root.glob("*/SKILL.md")}
        self.assertEqual(actual_skills, expected_skills)
        self.assertFalse((skills_root / "zju-learning" / "SKILL.md").exists())

        tools = await mcp.list_tools()
        routed: dict[str, list[str]] = {}
        for skill_name in expected_skills:
            body = (skills_root / skill_name / "SKILL.md").read_text(encoding="utf-8")
            for tool in tools:
                if f"`{tool.name}`" in body:
                    routed.setdefault(tool.name, []).append(skill_name)

        self.assertEqual(set(routed), {tool.name for tool in tools})
        self.assertTrue(all(len(owners) == 1 for owners in routed.values()), routed)

    async def test_fallback_surface_excludes_remote_writes_and_arbitrary_cli(self) -> None:
        plugin_root = Path(__file__).resolve().parents[1]
        script = (plugin_root / "scripts" / "zju-fallback.ps1").read_text(encoding="utf-8").lower()
        runtime = (plugin_root / "fallback" / "src" / "zju_tronclass_fallback" / "cli.py").read_text(encoding="utf-8").lower()
        self.assertNotIn('"submit"', script)
        self.assertNotIn('"raw"', script)
        self.assertNotIn('"url"', script)
        self.assertNotIn("valuefromremainingarguments", script)
        self.assertNotIn('["homework", "submit"', runtime)
        self.assertIn('"tronclass-cli==0.2.8"', (plugin_root / "fallback" / "pyproject.toml").read_text(encoding="utf-8"))

    async def test_skill_prompts_name_their_skill(self) -> None:
        skills_root = Path(__file__).resolve().parents[1] / "skills"
        for skill_file in skills_root.glob("*/SKILL.md"):
            skill_name = skill_file.parent.name
            yaml_text = (skill_file.parent / "agents" / "openai.yaml").read_text(encoding="utf-8")
            self.assertIn(f"${skill_name}", yaml_text)


if __name__ == "__main__":
    unittest.main()
