"""
SolidWorks VBA 宏生成防护层。

本模块用于稳定对接 GPT / Kimi / Claude 等多模型场景：
- 按模型族选择提示词策略。
- 对模型输出做 VBA 合法性校验。
- 解析失败时自动重试，并追加更强格式约束。
- 多次失败后按关键词使用本地模板兜底。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional


DEFAULT_TIMEOUT_SECONDS = 30
MAX_RETRIES = 2


def _configure_stdio_utf8() -> None:
    """在 Windows 旧代码页下尽量使用 UTF-8 输出中文提示。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_stdio_utf8()

CORE_OBJECT_PATTERNS = (r"\bSldWorks\.SldWorks\b", r"\bSldWorks\b", r"\bswApp\b")
MODELDOC_PATTERNS = (r"\bModelDoc2\b", r"\bswModel\b")
SUB_PATTERN = r"\bSub\s+\w+\s*\("
END_SUB_PATTERN = r"\bEnd\s+Sub\b"

GPT_PROMPT = """你是 SolidWorks VBA 自动化工程师。请只输出可执行的 VBA 宏代码。"""

STRICT_FORMAT_PROMPT = """你是 SolidWorks VBA 自动化工程师。
必须遵守以下格式：
1. 只输出一个完整 VBA 代码块，不要 Markdown，不要解释。
2. 必须包含 `Sub main()` 与 `End Sub`。
3. 必须声明并初始化 `SldWorks.SldWorks` 与 `ModelDoc2` 核心对象。
4. 所有长度单位使用米，毫米必须显式除以 1000#。
5. 禁止输出 JSON、自然语言说明、伪代码或省略号。
"""

RETRY_PROMPT_SUFFIX = """
上一轮输出未通过自动校验。请严格修正：
- 只输出 VBA 源码。
- 必须包含 SldWorks / ModelDoc2 / Sub main() / End Sub。
- 不要包含 Markdown 围栏、解释文字、JSON 或占位符。
"""


VBA_TEMPLATES: Dict[str, str] = {
    "cube": r'''
Option Explicit

Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2

Sub main()
    Set swApp = Application.SldWorks
    Set swModel = swApp.NewPart
    If swModel Is Nothing Then
        MsgBox "无法新建零件文档"
        Exit Sub
    End If

    swModel.Extension.SelectByID2 "Front Plane", "PLANE", 0#, 0#, 0#, False, 0, Nothing, 0
    swModel.SketchManager.InsertSketch True
    swModel.SketchManager.CreateCenterRectangle 0#, 0#, 0#, 0.025, 0.025, 0#
    swModel.SketchManager.InsertSketch True
    swModel.FeatureManager.FeatureExtrusion3 True, False, True, 0, 0, 0.05, 0#, False, False, False, False, 0#, 0#, False, False, False, False, True, False, True, 0, 0#, False
    swModel.ForceRebuild3 False
End Sub
'''.strip(),
    "cylinder": r'''
Option Explicit

Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2

Sub main()
    Set swApp = Application.SldWorks
    Set swModel = swApp.NewPart
    If swModel Is Nothing Then
        MsgBox "无法新建零件文档"
        Exit Sub
    End If

    swModel.Extension.SelectByID2 "Front Plane", "PLANE", 0#, 0#, 0#, False, 0, Nothing, 0
    swModel.SketchManager.InsertSketch True
    swModel.SketchManager.CreateCircleByRadius 0#, 0#, 0#, 0.025
    swModel.SketchManager.InsertSketch True
    swModel.FeatureManager.FeatureExtrusion3 True, False, True, 0, 0, 0.05, 0#, False, False, False, False, 0#, 0#, False, False, False, False, True, False, True, 0, 0#, False
    swModel.ForceRebuild3 False
End Sub
'''.strip(),
    "extrude": r'''
Option Explicit

Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2

Sub main()
    Set swApp = Application.SldWorks
    Set swModel = swApp.NewPart
    If swModel Is Nothing Then
        MsgBox "无法新建零件文档"
        Exit Sub
    End If

    swModel.Extension.SelectByID2 "Front Plane", "PLANE", 0#, 0#, 0#, False, 0, Nothing, 0
    swModel.SketchManager.InsertSketch True
    swModel.SketchManager.CreateCornerRectangle -0.03, -0.02, 0#, 0.03, 0.02, 0#
    swModel.SketchManager.InsertSketch True
    swModel.FeatureManager.FeatureExtrusion3 True, False, True, 0, 0, 0.01, 0#, False, False, False, False, 0#, 0#, False, False, False, False, True, False, True, 0, 0#, False
    swModel.ForceRebuild3 False
End Sub
'''.strip(),
    "sketch": r'''
Option Explicit

Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2

Sub main()
    Set swApp = Application.SldWorks
    Set swModel = swApp.NewPart
    If swModel Is Nothing Then
        MsgBox "无法新建零件文档"
        Exit Sub
    End If

    swModel.Extension.SelectByID2 "Front Plane", "PLANE", 0#, 0#, 0#, False, 0, Nothing, 0
    swModel.SketchManager.InsertSketch True
    swModel.SketchManager.CreateCenterRectangle 0#, 0#, 0#, 0.025, 0.015, 0#
    swModel.SketchManager.CreateCircleByRadius 0#, 0#, 0#, 0.006
    swModel.SketchManager.InsertSketch True
    swModel.ForceRebuild3 False
End Sub
'''.strip(),
}


KEYWORD_TEMPLATE_MAP = {
    "cube": ("立方体", "正方体", "方块", "cube", "box"),
    "cylinder": ("圆柱", "圆柱体", "cylinder"),
    "extrude": ("拉伸", "凸台", "extrude", "boss"),
    "sketch": ("草图", "sketch"),
}


@dataclass
class MacroValidationResult:
    """VBA 宏校验结果。"""

    ok: bool
    issues: List[str]


@dataclass
class MacroGenerationResult:
    """宏生成结果。"""

    code: str
    source: str
    attempts: int
    validation: MacroValidationResult


def normalize_model_family(model_name: Optional[str]) -> str:
    """将具体模型名归一为 gpt / kimi / claude / generic。"""
    name = (model_name or "").strip().lower()
    if not name:
        return "generic"
    if any(token in name for token in ("gpt", "openai", "o3", "o4", "o1")):
        return "gpt"
    if "kimi" in name or "moonshot" in name:
        return "kimi"
    if "claude" in name or "anthropic" in name:
        return "claude"
    return "generic"


def build_prompt(user_request: str, model_name: Optional[str] = None, strict: Optional[bool] = None) -> str:
    """按模型族生成提示词。"""
    family = normalize_model_family(model_name)
    use_strict = strict if strict is not None else family in {"kimi", "claude", "generic"}
    system_prompt = STRICT_FORMAT_PROMPT if use_strict else GPT_PROMPT
    return f"{system_prompt}\n\n用户需求：\n{user_request.strip()}\n"


def extract_vba_code(text: str) -> str:
    """从模型输出中提取 VBA 代码。"""
    if not text:
        return ""
    fence = re.search(r"```(?:vb|vba|visualbasic)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text.strip()


def _contains_any_pattern(code: str, patterns: Iterable[str]) -> bool:
    """检查代码是否包含任一正则模式。"""
    return any(re.search(pattern, code, re.IGNORECASE) for pattern in patterns)


def validate_vba_macro(code: str) -> MacroValidationResult:
    """校验 VBA 宏是否满足 SolidWorks 执行前的最低合法性要求。"""
    issues: List[str] = []
    normalized = code.strip()
    if not normalized:
        issues.append("代码为空")
    if not _contains_any_pattern(normalized, CORE_OBJECT_PATTERNS):
        issues.append("缺少 SolidWorks 核心对象 SldWorks")
    if not _contains_any_pattern(normalized, MODELDOC_PATTERNS):
        issues.append("缺少 ModelDoc2 文档对象")
    if not re.search(SUB_PATTERN, normalized, re.IGNORECASE):
        issues.append("缺少 Sub 入口")
    if not re.search(END_SUB_PATTERN, normalized, re.IGNORECASE):
        issues.append("缺少 End Sub")
    if "..." in normalized or "TODO" in normalized.upper():
        issues.append("包含占位符或未完成代码")
    return MacroValidationResult(ok=not issues, issues=issues)


def select_template_key(user_request: str) -> Optional[str]:
    """根据用户指令关键词选择本地 VBA 模板。"""
    text = user_request.lower()
    for key, keywords in KEYWORD_TEMPLATE_MAP.items():
        if any(keyword.lower() in text for keyword in keywords):
            return key
    return None


def fallback_macro_for_request(user_request: str) -> Optional[str]:
    """按用户需求返回本地兜底 VBA 模板。"""
    key = select_template_key(user_request)
    if key is None:
        return None
    return VBA_TEMPLATES[key]


def generate_macro_with_guard(
    user_request: str,
    model_call: Callable[[str, int], str],
    model_name: Optional[str] = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = MAX_RETRIES,
) -> MacroGenerationResult:
    """
    生成 SolidWorks VBA 宏并执行校验、重试、模板兜底。

    model_call 由具体代理实现，签名为 `model_call(prompt, timeout_seconds)`。
    """
    last_validation = MacroValidationResult(ok=False, issues=["尚未调用模型"])
    prompt = build_prompt(user_request, model_name=model_name)
    attempts = 0

    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        try:
            raw_output = model_call(prompt, timeout_seconds)
        except TimeoutError:
            raw_output = ""
            last_validation = MacroValidationResult(ok=False, issues=["模型请求超时"])
        else:
            code = extract_vba_code(raw_output)
            validation = validate_vba_macro(code)
            last_validation = validation
            if validation.ok:
                return MacroGenerationResult(
                    code=code,
                    source="model",
                    attempts=attempts,
                    validation=validation,
                )

        prompt = build_prompt(user_request, model_name=model_name, strict=True) + RETRY_PROMPT_SUFFIX
        if last_validation.issues:
            prompt += "\n当前校验问题：\n" + "\n".join(f"- {issue}" for issue in last_validation.issues)

    fallback = fallback_macro_for_request(user_request)
    if fallback:
        validation = validate_vba_macro(fallback)
        return MacroGenerationResult(
            code=fallback,
            source="local_template",
            attempts=attempts,
            validation=validation,
        )

    raise ValueError("模型输出未通过校验，且没有匹配到本地 VBA 兜底模板: " + "; ".join(last_validation.issues))


def write_macro_file(code: str, output_path: str) -> str:
    """将 VBA 代码写入本地文件，供代理或人工复制到 SolidWorks 宏环境。"""
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    return str(path)


def _parse_args():
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="SolidWorks VBA 宏提示词、校验与本地模板工具。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prompt_parser = subparsers.add_parser("prompt", help="按模型族输出提示词。")
    prompt_parser.add_argument("--model", default="", help="模型名称，如 gpt-4.1、kimi、claude。")
    prompt_parser.add_argument("request", help="用户建模需求。")

    validate_parser = subparsers.add_parser("validate", help="校验 VBA 文件。")
    validate_parser.add_argument("file", help="VBA 文件路径。")

    template_parser = subparsers.add_parser("template", help="按关键词输出本地模板。")
    template_parser.add_argument("request", help="用户建模需求。")
    template_parser.add_argument("--output", help="写入输出文件。")
    return parser.parse_args()


def main() -> int:
    """命令行入口。"""
    args = _parse_args()
    if args.command == "prompt":
        print(build_prompt(args.request, model_name=args.model))
        return 0

    if args.command == "validate":
        code = Path(args.file).read_text(encoding="utf-8")
        result = validate_vba_macro(code)
        print(json.dumps({"ok": result.ok, "issues": result.issues}, ensure_ascii=False, indent=2))
        return 0 if result.ok else 1

    if args.command == "template":
        code = fallback_macro_for_request(args.request)
        if not code:
            print("未匹配到本地模板。")
            return 1
        if args.output:
            path = write_macro_file(code, args.output)
            print(path)
        else:
            print(code)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
