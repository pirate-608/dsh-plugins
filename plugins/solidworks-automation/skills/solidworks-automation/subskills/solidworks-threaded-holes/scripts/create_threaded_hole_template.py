"""
@file create_threaded_hole_template.py
@brief 生成带内螺纹孔表达的 SolidWorks 样件。

默认创建 M6x1 内螺纹盲孔：真实攻丝底孔 + 孔口倒角 + 属性 + 可见螺旋线。
真实 Thread / CosmeticThread 特征会先尝试，失败时自动降级，不阻断可审查模型交付。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

THIS_FILE = Path(__file__).resolve()
PARENT_SKILL_DIR = THIS_FILE.parents[3]
PARENT_SCRIPT_DIR = PARENT_SKILL_DIR / "scripts"
sys.path.insert(0, str(PARENT_SCRIPT_DIR))

from sw_appearance import set_document_appearance  # noqa: E402
from sw_connect import create_empty_dispatch_variant, get_com_member, mm  # noqa: E402
from sw_export import export_to_step  # noqa: E402
from sw_part import extrude_boss, sketch, sketch_rectangle  # noqa: E402
from sw_review import run_review  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402

SW_SOLID_BODY = 0
SW_FM_SWEEP_THREAD = 87
SW_THREAD_METHOD_CUT = 0
SW_THREAD_END_BLIND = 0
SW_COSMETIC_STANDARD_ISO = 8
SW_COSMETIC_END_BLIND = 0


THREAD_TABLE = {
    "M3X0.5": {"label": "M3x0.5", "nominal_mm": 3.0, "pitch_mm": 0.5, "tap_drill_mm": 2.5},
    "M4X0.7": {"label": "M4x0.7", "nominal_mm": 4.0, "pitch_mm": 0.7, "tap_drill_mm": 3.3},
    "M5X0.8": {"label": "M5x0.8", "nominal_mm": 5.0, "pitch_mm": 0.8, "tap_drill_mm": 4.2},
    "M6X1.0": {"label": "M6x1.0", "nominal_mm": 6.0, "pitch_mm": 1.0, "tap_drill_mm": 5.0},
    "M8X1.25": {"label": "M8x1.25", "nominal_mm": 8.0, "pitch_mm": 1.25, "tap_drill_mm": 6.8},
    "M10X1.5": {"label": "M10x1.5", "nominal_mm": 10.0, "pitch_mm": 1.5, "tap_drill_mm": 8.5},
    "M12X1.75": {"label": "M12x1.75", "nominal_mm": 12.0, "pitch_mm": 1.75, "tap_drill_mm": 10.2},
}

THREAD_ALIASES = {
    "M3": "M3X0.5",
    "M4": "M4X0.7",
    "M5": "M5X0.8",
    "M6": "M6X1.0",
    "M8": "M8X1.25",
    "M10": "M10X1.5",
    "M12": "M12X1.75",
}

FACE_CONFIGS = {
    "front": {"base_plane": "Front Plane", "axis": 2, "plane_axes": (0, 1)},
    "top": {"base_plane": "Top Plane", "axis": 1, "plane_axes": (0, 2)},
    "right": {"base_plane": "Right Plane", "axis": 0, "plane_axes": (1, 2)},
}


@dataclass
class ThreadedHoleParams:
    """@brief 螺纹孔样件参数，单位均为 mm。"""

    thread_label: str
    block_length_mm: float
    block_width_mm: float
    block_thickness_mm: float
    hole_x_mm: float
    hole_y_mm: float
    nominal_diameter_mm: float
    pitch_mm: float
    tap_drill_diameter_mm: float
    pilot_depth_mm: float
    thread_depth_mm: float
    mouth_chamfer_mm: float
    through_hole: bool
    hole_face: str


def normalize_thread_key(value: str) -> str:
    """@brief 将 M6、M6x1、M6x1.0 等写法归一到表键。"""
    raw = value.strip().upper().replace(" ", "").replace("*", "X")
    if raw in THREAD_ALIASES:
        return THREAD_ALIASES[raw]
    if "X" not in raw:
        raise ValueError(f"暂不支持的螺纹规格: {value}")
    major, pitch = raw.split("X", 1)
    try:
        pitch_value = float(pitch)
    except ValueError as exc:
        raise ValueError(f"螺距格式错误: {value}") from exc
    key = f"{major}X{pitch_value:g}"
    for known in THREAD_TABLE:
        known_major, known_pitch = known.split("X", 1)
        if known_major == major and abs(float(known_pitch) - pitch_value) < 1e-9:
            return known
    raise ValueError(f"暂不支持的螺纹规格: {value}，可选: {', '.join(sorted(THREAD_ALIASES))}")


def face_config(face_name: str) -> dict:
    """@brief 获取打孔面的坐标配置。"""
    key = face_name.strip().lower()
    if key not in FACE_CONFIGS:
        raise ValueError(f"暂不支持的打孔面: {face_name}，可选: top/front/right")
    return FACE_CONFIGS[key]


def assert_feature(feature, label: str):
    """@brief 检查 SolidWorks 特征对象。"""
    if feature is None:
        raise RuntimeError(f"{label} 创建失败")
    print(f"OK {label}: {getattr(feature, 'Name', '<未命名>')}")
    return feature


def clear(model) -> None:
    """@brief 清空选择集。"""
    model.ClearSelection2(True)


def select_plane(model, plane_name: str) -> str:
    """@brief 兼容中英文基准面名称并选择。"""
    clear(model)
    aliases = {
        "Front Plane": ("Front Plane", "前视基准面"),
        "Top Plane": ("Top Plane", "上视基准面"),
        "Right Plane": ("Right Plane", "右视基准面"),
    }[plane_name]
    for name in aliases:
        selected = model.Extension.SelectByID2(
            name,
            "PLANE",
            0,
            0,
            0,
            False,
            0,
            create_empty_dispatch_variant(),
            0,
        )
        if selected:
            return name
    raise RuntimeError(f"无法选择基准面: {plane_name}")


def current_sketch_name(model, fallback: str) -> str:
    """@brief 获取当前草图名称。"""
    active = model.SketchManager.ActiveSketch
    return active.Name if active else fallback


def create_offset_plane(model, name: str, base_plane: str, offset_mm: float) -> str:
    """@brief 从指定基准面偏移创建打孔起始参考平面。"""
    if model.FeatureByName(name):
        return name
    select_plane(model, base_plane)
    feature = assert_feature(model.FeatureManager.InsertRefPlane(8, mm(offset_mm), 0, 0, 0, 0), name)
    feature.Name = name
    return name


def select_sketch(model, name: str) -> None:
    """@brief 选择指定草图。"""
    clear(model)
    selected = model.Extension.SelectByID2(
        name,
        "SKETCH",
        0,
        0,
        0,
        False,
        0,
        create_empty_dispatch_variant(),
        0,
    )
    if not selected:
        raise RuntimeError(f"无法选择草图: {name}")


def cut_blind_from_sketch(model, sketch_name: str, depth_mm: float, label: str):
    """@brief 按草图创建盲孔切除。"""
    select_sketch(model, sketch_name)
    feature = model.FeatureManager.FeatureCut4(
        True, False, False, 0, 0, mm(depth_mm), 0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, False,
        True, True, True, True,
        False, 0, 0, False, False,
    )
    return assert_feature(feature, label)


def circle_center_radius(edge):
    """@brief 读取圆边圆心和半径。"""
    try:
        curve = get_com_member(edge, "GetCurve")
        if not curve or not get_com_member(curve, "IsCircle"):
            return None
        values = get_com_member(curve, "CircleParams")
        return (float(values[0]), float(values[1]), float(values[2])), float(values[6])
    except Exception:
        return None


def all_edges(model):
    """@brief 枚举实体所有边线。"""
    model.ForceRebuild3(False)
    edges = []
    for body in get_com_member(model, "GetBodies2", SW_SOLID_BODY, False) or []:
        edges.extend(list(get_com_member(body, "GetEdges") or []))
    return edges


def model_point_from_local(params: ThreadedHoleParams, u_m: float, v_m: float, axis_m: float) -> tuple[float, float, float]:
    """@brief 将打孔面局部坐标转换为模型 XYZ 坐标。"""
    config = face_config(params.hole_face)
    coords = [0.0, 0.0, 0.0]
    coords[config["plane_axes"][0]] = u_m
    coords[config["plane_axes"][1]] = v_m
    coords[config["axis"]] = axis_m
    return tuple(coords)


def locate_hole_mouth_edge(model, params: ThreadedHoleParams, select: bool = True):
    """@brief 定位打孔起始面的孔口圆边和圆心。"""
    config = face_config(params.hole_face)
    axis_index = config["axis"]
    u_index, v_index = config["plane_axes"]
    face_offset = mm(params.block_thickness_mm)
    target_radius = mm(params.tap_drill_diameter_mm / 2.0)
    if select:
        clear(model)
    for edge in all_edges(model):
        data = circle_center_radius(edge)
        if not data:
            continue
        center, radius = data
        center_matches = (
            abs(center[u_index] - mm(params.hole_x_mm)) < mm(0.2)
            and abs(center[v_index] - mm(params.hole_y_mm)) < mm(0.2)
            and abs(abs(center[axis_index]) - face_offset) < mm(0.5)
        )
        radius_matches = abs(radius - target_radius) < mm(0.3)
        if center_matches and radius_matches:
            if not select or edge.Select2(False, 0):
                return edge, center
    raise RuntimeError("未找到打孔起始面的孔口圆边")


def select_hole_mouth_edge(model, params: ThreadedHoleParams):
    """@brief 选择打孔起始面的孔口圆边。"""
    edge, _center = locate_hole_mouth_edge(model, params, select=True)
    return edge


def add_hole_mouth_chamfer(model, params: ThreadedHoleParams):
    """@brief 给孔口添加 45 度小倒角。"""
    select_hole_mouth_edge(model, params)
    feature = model.FeatureManager.InsertFeatureChamfer(
        4, 1, mm(params.mouth_chamfer_mm), math.pi / 4.0, 0, 0, 0, 0
    )
    assert_feature(feature, "孔口倒角").Name = "Chamfer_Thread_Mouth"
    clear(model)
    return feature


def add_real_thread_feature(model, params: ThreadedHoleParams):
    """@brief 尝试添加 SolidWorks 真实 Thread 特征。"""
    edge = select_hole_mouth_edge(model, params)
    thread_data = model.FeatureManager.CreateDefinition(SW_FM_SWEEP_THREAD)
    if thread_data is None:
        raise RuntimeError("CreateDefinition(swFmSweepThread) 返回 None")

    try:
        thread_data.InitializeThreadData()
    except Exception as exc:
        print(f"WARN InitializeThreadData 跳过: {exc}")

    for attr, value in (
        ("Edge", edge),
        ("StartEntity", edge),
        ("ThreadMethod", SW_THREAD_METHOD_CUT),
        ("EndCondition", SW_THREAD_END_BLIND),
        ("BlindDepth", mm(params.thread_depth_mm)),
        ("Pitch", mm(params.pitch_mm)),
        ("Diameter", mm(params.nominal_diameter_mm)),
        ("Size", params.thread_label),
        ("PitchOverride", True),
        ("DiameterOverride", True),
    ):
        try:
            setattr(thread_data, attr, value)
            print(f"  {attr}={value}")
        except Exception as exc:
            print(f"WARN 设置 {attr} 失败: {exc}")

    try:
        loaded = thread_data.LoadReferences(edge)
        print(f"  LoadReferences(edge): {loaded}")
    except Exception as exc:
        print(f"WARN LoadReferences(edge) 失败: {exc}")

    clear(model)
    if not edge.Select2(False, 0):
        raise RuntimeError("选择孔口圆边失败，无法创建 Thread 特征")
    feature = model.FeatureManager.CreateFeature(thread_data)
    if feature is None:
        raise RuntimeError("CreateFeature(ThreadFeatureData) 返回 None")
    feature.Name = f"Thread_{params.thread_label}_Internal_Blind"
    return assert_feature(feature, f"{params.thread_label} 真实内螺纹")


def add_cosmetic_thread_feature(model, params: ThreadedHoleParams):
    """@brief 添加 SolidWorks Cosmetic Thread 螺纹表达。"""
    edge = select_hole_mouth_edge(model, params)
    clear(model)
    if not edge.Select2(False, 0):
        raise RuntimeError("选择孔口圆边失败，无法创建 Cosmetic Thread")
    feature = model.FeatureManager.InsertCosmeticThread3(
        SW_COSMETIC_STANDARD_ISO,
        "Tapped Hole",
        params.thread_label,
        mm(params.nominal_diameter_mm),
        SW_COSMETIC_END_BLIND,
        mm(params.thread_depth_mm),
        f"{params.thread_label} - 6H",
    )
    if feature is None:
        raise RuntimeError("InsertCosmeticThread3 返回 None")
    feature.Name = f"CosmeticThread_{params.thread_label}_Internal_Blind"
    clear(model)
    return assert_feature(feature, f"{params.thread_label} 装饰螺纹")


def add_visible_thread_helix(model, params: ThreadedHoleParams) -> int:
    """@brief 用 3D 草图短线段生成可见内螺纹螺旋线。"""
    _edge, mouth_center = locate_hole_mouth_edge(model, params, select=False)
    config = face_config(params.hole_face)
    axis_index = config["axis"]
    mouth_axis = mouth_center[axis_index]
    inward_sign = -1.0 if mouth_axis >= 0 else 1.0
    turns = max(1, int(round(params.thread_depth_mm / params.pitch_mm)))
    segment_count = max(120, turns * 32)
    radius = mm(max(params.tap_drill_diameter_mm / 2.0 + 0.15, params.nominal_diameter_mm / 2.0 - 0.08))
    z_depth = mm(params.thread_depth_mm)

    sketch_mgr = model.SketchManager
    sketch_mgr.Insert3DSketch(True)
    sketch_name = current_sketch_name(model, f"Sketch_{params.thread_label}_Visible_Thread_Helix")
    previous = None
    created = 0
    for index in range(segment_count + 1):
        angle = 2.0 * math.pi * turns * index / segment_count
        axis_value = mouth_axis + inward_sign * (mm(0.3) + z_depth * index / segment_count)
        point = model_point_from_local(
            params,
            mm(params.hole_x_mm) + radius * math.cos(angle),
            mm(params.hole_y_mm) + radius * math.sin(angle),
            axis_value,
        )
        if previous is not None:
            segment = sketch_mgr.CreateLine(
                previous[0],
                previous[1],
                previous[2],
                point[0],
                point[1],
                point[2],
            )
            if segment:
                created += 1
        previous = point
    sketch_mgr.Insert3DSketch(True)

    feature = model.FeatureByName(sketch_name)
    if feature:
        feature.Name = f"Sketch_{params.thread_label}_Visible_Internal_Thread_Helix"
    print(f"OK 可见螺纹螺旋线: {created} 段, {turns} 圈")
    return created


def write_thread_properties(model, params: ThreadedHoleParams, thread_status: str, visible_segments: int) -> None:
    """@brief 写入模型自定义属性。"""
    manager = model.Extension.CustomPropertyManager("")
    manager.Add3("螺纹规格", 30, f"{params.thread_label} internal thread", 2)
    manager.Add3("攻丝底孔", 30, f"{params.tap_drill_diameter_mm} mm", 2)
    manager.Add3("螺纹深度", 30, f"{params.thread_depth_mm} mm", 2)
    manager.Add3("底孔深度", 30, f"{params.pilot_depth_mm} mm", 2)
    manager.Add3("螺纹状态", 30, thread_status, 2)
    manager.Add3("可见螺纹螺旋线", 30, f"{visible_segments} segments", 2)
    manager.Add3("螺纹建模说明", 30, "底孔和孔口倒角为真实几何；Thread/CosmeticThread 失败时以属性和 3D 螺旋线表达。", 2)


def build_params(args) -> ThreadedHoleParams:
    """@brief 从命令行参数生成螺纹孔参数。"""
    key = normalize_thread_key(args.thread)
    spec = THREAD_TABLE[key]
    thread_depth = args.thread_depth
    if thread_depth is None:
        thread_depth = min(spec["nominal_mm"] * 2.0, args.block_thickness - 4.0)
    pilot_depth = args.pilot_depth
    if pilot_depth is None:
        pilot_depth = min(thread_depth + max(spec["pitch_mm"], 1.0), args.block_thickness - 1.0)
    if args.through:
        pilot_depth = args.block_thickness + 1.0
        thread_depth = args.block_thickness
    if pilot_depth <= 0 or thread_depth <= 0:
        raise ValueError("孔深和螺纹深度必须大于 0")
    if not args.through and pilot_depth >= args.block_thickness:
        raise ValueError("盲孔底孔深度不能大于等于零件厚度；需要通孔请传 --through")
    return ThreadedHoleParams(
        thread_label=spec["label"],
        block_length_mm=args.block_length,
        block_width_mm=args.block_width,
        block_thickness_mm=args.block_thickness,
        hole_x_mm=args.hole_x,
        hole_y_mm=args.hole_y,
        nominal_diameter_mm=spec["nominal_mm"],
        pitch_mm=spec["pitch_mm"],
        tap_drill_diameter_mm=args.tap_drill or spec["tap_drill_mm"],
        pilot_depth_mm=pilot_depth,
        thread_depth_mm=thread_depth,
        mouth_chamfer_mm=args.mouth_chamfer,
        through_hole=bool(args.through),
        hole_face=args.hole_face.strip().lower(),
    )


def create_threaded_hole_block(params: ThreadedHoleParams, output_dir: Path, basename: str):
    """@brief 创建螺纹孔样件并保存导出审查。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    part_path = output_dir / f"{basename}.SLDPRT"
    step_path = output_dir / f"{basename}.step"
    param_path = output_dir / f"{basename}_parameters.json"

    session = SolidWorksSession(visible=True)
    try:
        session.close(title=part_path.name)
    except Exception:
        pass
    model = session.new_part()
    config = face_config(params.hole_face)

    with sketch(model, config["base_plane"]) as base_sketch:
        sketch_rectangle(model, 0, 0, mm(params.block_length_mm), mm(params.block_width_mm))
    base_feature = extrude_boss(model, base_sketch, mm(params.block_thickness_mm), direction=False)
    assert_feature(base_feature, "基体").Name = "Boss_Thread_Test_Block"

    top_plane = create_offset_plane(model, "Plane_Hole_Start", config["base_plane"], params.block_thickness_mm)
    clear(model)
    model.Extension.SelectByID2(top_plane, "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
    model.SketchManager.InsertSketch(True)
    hole_sketch = current_sketch_name(model, "Sketch_Tap_Drill_Hole")
    model.SketchManager.CreateCircleByRadius(
        mm(params.hole_x_mm),
        mm(params.hole_y_mm),
        0,
        mm(params.tap_drill_diameter_mm / 2.0),
    )
    model.SketchManager.InsertSketch(True)
    cut_feature = cut_blind_from_sketch(
        model,
        hole_sketch,
        params.pilot_depth_mm,
        f"{params.thread_label} 攻丝底孔 {params.tap_drill_diameter_mm}mm",
    )
    cut_feature.Name = f"Cut_{params.thread_label}_Tap_Drill"

    thread_status = "real-thread-created"
    try:
        add_real_thread_feature(model, params)
    except Exception as exc:
        print(f"WARN 真实 Thread 特征失败，尝试 Cosmetic Thread: {exc}")
        try:
            add_cosmetic_thread_feature(model, params)
            thread_status = f"cosmetic-thread-created; real-thread-failed: {exc}"
        except Exception as cosmetic_exc:
            thread_status = f"thread-feature-failed: real={exc}; cosmetic={cosmetic_exc}"
            print(f"WARN Cosmetic Thread 也失败，降级为属性和可见螺旋线: {cosmetic_exc}")

    visible_segments = add_visible_thread_helix(model, params)
    add_hole_mouth_chamfer(model, params)
    write_thread_properties(model, params, thread_status, visible_segments)

    set_document_appearance(model, "silver")
    model.ForceRebuild3(False)
    model.ViewZoomtofit2()

    param_path.write_text(
        json.dumps(
            {
                "units": "mm",
                "params": asdict(params),
                "thread_status": thread_status,
                "visible_thread_helix_segments": visible_segments,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if not session.save(model, str(part_path)):
        raise RuntimeError(f"保存失败: {part_path}")
    if not export_to_step(model, str(step_path)):
        raise RuntimeError(f"STEP 导出失败: {step_path}")

    report, report_path = run_review(
        model,
        output_dir,
        basename=basename,
        expected_outputs=[str(part_path), str(step_path)],
    )
    print(f"审查报告: {report_path}")
    print(f"审查状态: {report['evaluation']['status']} / {report['evaluation']['score']}")
    print(f"螺纹状态: {thread_status}")
    return {
        "part_path": str(part_path),
        "step_path": str(step_path),
        "param_path": str(param_path),
        "review_path": str(report_path),
        "review": report["evaluation"],
        "thread_status": thread_status,
    }


def parse_args():
    """@brief 解析命令行参数。"""
    parser = argparse.ArgumentParser(description="生成 SolidWorks 内螺纹孔样件。")
    parser.add_argument("--thread", default="M6", help="螺纹规格，默认 M6；支持 M3/M4/M5/M6/M8/M10/M12 或 M6x1.0。")
    parser.add_argument("--block-length", type=float, default=40.0, help="基体长度 mm。")
    parser.add_argument("--block-width", type=float, default=30.0, help="基体宽度 mm。")
    parser.add_argument("--block-thickness", type=float, default=16.0, help="基体厚度 mm。")
    parser.add_argument("--hole-x", type=float, default=0.0, help="孔中心 X 坐标 mm。")
    parser.add_argument("--hole-y", type=float, default=0.0, help="孔中心 Y 坐标 mm。")
    parser.add_argument("--tap-drill", type=float, help="覆盖默认攻丝底孔直径 mm。")
    parser.add_argument("--pilot-depth", type=float, help="底孔深度 mm；不传则按螺纹深度和厚度估算。")
    parser.add_argument("--thread-depth", type=float, help="螺纹深度 mm；不传默认约 2D。")
    parser.add_argument("--mouth-chamfer", type=float, default=0.6, help="孔口 45 度倒角距离 mm。")
    parser.add_argument("--through", action="store_true", help="生成通孔底孔；螺纹表达仍按保守盲孔 API 尝试。")
    parser.add_argument("--hole-face", choices=sorted(FACE_CONFIGS), default="top", help="打孔面，默认 top；也可选 front/right。")
    parser.add_argument("--basename", help="输出文件名前缀；不传则按螺纹规格生成。")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "solidworks_threaded_hole_output",
        help="输出目录。",
    )
    return parser.parse_args()


def main() -> int:
    """@brief 命令行入口。"""
    args = parse_args()
    params = build_params(args)
    basename = args.basename or f"{params.thread_label.replace('.', '_')}_Internal_Threaded_Hole_Block"
    result = create_threaded_hole_block(params, args.output_dir, basename)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
