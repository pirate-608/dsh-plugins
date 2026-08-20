"""
SolidWorks CNC 安装座多圆角/倒角模板。

@brief 生成一个可复用的 CNC 风格安装座示例。
@details
    运行前先执行父技能 scripts/sw_preflight.py。
    本模板默认输出到当前工作目录下的 solidworks_fillet_chamfer_output。
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from sw_appearance import set_document_appearance  # noqa: E402
from sw_connect import create_empty_dispatch_variant, get_com_member, mm  # noqa: E402
from sw_export import export_to_step  # noqa: E402
from sw_part import sketch_slot  # noqa: E402
from sw_review import run_review  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402


SW_SOLID_BODY = 0
EPS = 1e-5


@dataclass(frozen=True)
class MountParameters:
    """CNC 安装座模板参数，单位毫米。"""

    length: float = 120.0
    width: float = 80.0
    thickness: float = 18.0
    boss_length: float = 58.0
    boss_width: float = 34.0
    boss_height: float = 10.0
    base_corner_radius: float = 8.0
    boss_corner_radius: float = 5.0
    top_chamfer: float = 1.0
    bottom_chamfer: float = 0.8
    boss_top_chamfer: float = 0.8
    hole_chamfer: float = 0.5
    mount_hole_diameter: float = 7.0
    counterbore_diameter: float = 13.0
    counterbore_depth: float = 4.0
    mount_hole_x: float = 46.0
    mount_hole_y: float = 28.0
    dowel_hole_diameter: float = 5.0
    dowel_hole_x: float = 32.0
    slot_length: float = 62.0
    slot_width: float = 16.0
    pocket_length: float = 24.0
    pocket_width: float = 30.0
    pocket_center_x: float = 43.0
    pocket_depth: float = 4.0


P = MountParameters()


def assert_feature(feature, label: str):
    """检查特征是否创建成功。"""
    if feature is None:
        raise RuntimeError(f"{label} 创建失败")
    print(f"OK: {label} -> {getattr(feature, 'Name', '<unnamed>')}")
    return feature


def clear(model) -> None:
    """清空选择集。"""
    model.ClearSelection2(True)


def select_plane(model, aliases: tuple[str, ...]) -> None:
    """选择中英文基准面。"""
    clear(model)
    for name in aliases:
        if model.Extension.SelectByID2(name, "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0):
            return
    raise RuntimeError(f"无法选择基准面: {aliases}")


def sketch_name(model, fallback: str) -> str:
    """读取当前草图名称。"""
    active = model.SketchManager.ActiveSketch
    return active.Name if active else fallback


def offset_front_plane(model, name: str, z_mm: float) -> str:
    """创建平行前视基准面的偏置面。"""
    if model.FeatureByName(name):
        return name
    select_plane(model, ("Front Plane", "前视基准面"))
    plane = assert_feature(model.FeatureManager.InsertRefPlane(8, mm(z_mm), 0, 0, 0, 0), name)
    plane.Name = name
    return name


def select_sketch(model, name: str) -> None:
    """选择草图。"""
    clear(model)
    if not model.Extension.SelectByID2(name, "SKETCH", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0):
        raise RuntimeError(f"无法选择草图: {name}")


def extrude_boss(model, name: str, depth_mm: float, label: str):
    """创建凸台拉伸。"""
    select_sketch(model, name)
    return assert_feature(
        model.FeatureManager.FeatureExtrusion3(
            True, False, False, 0, 0, mm(depth_mm), 0,
            False, False, False, False, 0, 0,
            False, False, False, False,
            True, False, True, 0, 0, False,
        ),
        label,
    )


def cut(model, name: str, depth_mm: float, label: str, through_all: bool = False):
    """创建拉伸切除。"""
    select_sketch(model, name)
    end_condition = 1 if through_all else 0
    depth = mm(max(depth_mm, P.thickness + P.boss_height + 4.0) if through_all else depth_mm)
    return assert_feature(
        model.FeatureManager.FeatureCut4(
            True, False, False, end_condition, 0, depth, 0,
            False, False, False, False, 0, 0,
            False, False, False, False, False,
            True, True, True, True,
            False, 0, 0, False, False,
        ),
        label,
    )


def edge_points(edge):
    """读取边线端点。"""
    try:
        start = get_com_member(edge, "GetStartVertex")
        end = get_com_member(edge, "GetEndVertex")
        if not start or not end:
            return None
        return tuple(get_com_member(start, "GetPoint")), tuple(get_com_member(end, "GetPoint"))
    except Exception:
        return None


def midpoint(edge):
    """计算边线中点。"""
    points = edge_points(edge)
    if not points:
        return None
    start, end = points
    return tuple((start[index] + end[index]) / 2.0 for index in range(3))


def edge_direction(edge):
    """判断边线主方向。"""
    points = edge_points(edge)
    if not points:
        return None
    start, end = points
    deltas = [abs(end[index] - start[index]) for index in range(3)]
    if max(deltas) < EPS:
        return None
    return "xyz"[deltas.index(max(deltas))]


def circle_center_radius(edge):
    """读取圆边的圆心和半径。"""
    try:
        curve = get_com_member(edge, "GetCurve")
        if not curve or not get_com_member(curve, "IsCircle"):
            return None
        values = get_com_member(curve, "CircleParams")
        return (float(values[0]), float(values[1]), float(values[2])), float(values[6])
    except Exception:
        return None


def all_edges(model):
    """枚举所有实体边。"""
    model.ForceRebuild3(False)
    edges = []
    for body in get_com_member(model, "GetBodies2", SW_SOLID_BODY, False) or []:
        edges.extend(list(get_com_member(body, "GetEdges") or []))
    return edges


def select_edges(model, predicate, label: str) -> int:
    """按几何条件选择边线。"""
    clear(model)
    count = 0
    for edge in all_edges(model):
        try:
            if predicate(edge) and edge.Select2(count > 0, 0):
                count += 1
        except Exception:
            continue
    print(f"SELECT: {label} -> {count}")
    return count


def fillet(model, radius_mm: float, label: str) -> None:
    """对当前选择集添加圆角。"""
    feature = model.FeatureManager.FeatureFillet(195, mm(radius_mm), 0, 0, None, None, None)
    assert_feature(feature, label).Name = label
    clear(model)


def chamfer(model, distance_mm: float, label: str) -> None:
    """对当前选择集添加 45 度倒角。"""
    feature = model.FeatureManager.InsertFeatureChamfer(4, 1, mm(distance_mm), math.pi / 4, 0, 0, 0, 0)
    assert_feature(feature, label).Name = label
    clear(model)


def build_model(output_dir: Path) -> None:
    """构建、保存、导出并审查模型。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    part = output_dir / "CNC_Mount_Template.SLDPRT"
    step = output_dir / "CNC_Mount_Template.step"

    session = SolidWorksSession(visible=True)
    try:
        session.close(title=part.name)
    except Exception:
        pass
    model = session.new_part()

    select_plane(model, ("Front Plane", "前视基准面"))
    model.SketchManager.InsertSketch(True)
    base_sketch = sketch_name(model, "Sketch_Base")
    model.SketchManager.CreateCenterRectangle(0, 0, 0, mm(P.length / 2), mm(P.width / 2), 0)
    model.SketchManager.InsertSketch(True)
    extrude_boss(model, base_sketch, P.thickness, "Base")
    offset_front_plane(model, "Plane_Base_Top", P.thickness)

    clear(model)
    model.Extension.SelectByID2("Plane_Base_Top", "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
    model.SketchManager.InsertSketch(True)
    boss_sketch = sketch_name(model, "Sketch_Boss")
    model.SketchManager.CreateCenterRectangle(0, 0, 0, mm(P.boss_length / 2), mm(P.boss_width / 2), 0)
    model.SketchManager.InsertSketch(True)
    extrude_boss(model, boss_sketch, P.boss_height, "Boss")

    z_top = mm(P.thickness)
    z_boss = mm(P.thickness + P.boss_height)
    hx, hy = mm(P.length / 2), mm(P.width / 2)
    bx, by = mm(P.boss_length / 2), mm(P.boss_width / 2)

    select_edges(model, lambda e: (m := midpoint(e)) and edge_direction(e) == "z" and abs(abs(m[0]) - hx) < mm(1.5) and abs(abs(m[1]) - hy) < mm(1.5), "base vertical")
    fillet(model, P.base_corner_radius, "Fillet_Base_Corners")
    select_edges(model, lambda e: (m := midpoint(e)) and edge_direction(e) == "z" and z_top < m[2] < z_boss and abs(abs(m[0]) - bx) < mm(1.5) and abs(abs(m[1]) - by) < mm(1.5), "boss vertical")
    fillet(model, P.boss_corner_radius, "Fillet_Boss_Corners")
    select_edges(model, lambda e: (m := midpoint(e)) and edge_direction(e) in {"x", "y"} and abs(m[2] - z_top) < mm(0.8) and (abs(abs(m[0]) - hx) < mm(2.5) or abs(abs(m[1]) - hy) < mm(2.5)), "top outer")
    chamfer(model, P.top_chamfer, "Chamfer_Top_Outer")
    select_edges(model, lambda e: (m := midpoint(e)) and edge_direction(e) in {"x", "y"} and abs(m[2]) < mm(0.8) and (abs(abs(m[0]) - hx) < mm(2.5) or abs(abs(m[1]) - hy) < mm(2.5)), "bottom outer")
    chamfer(model, P.bottom_chamfer, "Chamfer_Bottom_Outer")
    select_edges(model, lambda e: (m := midpoint(e)) and edge_direction(e) in {"x", "y"} and abs(m[2] - z_boss) < mm(0.8) and (abs(abs(m[0]) - bx) < mm(2.5) or abs(abs(m[1]) - by) < mm(2.5)), "boss top")
    chamfer(model, P.boss_top_chamfer, "Chamfer_Boss_Top")

    clear(model)
    model.Extension.SelectByID2("Plane_Base_Top", "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
    model.SketchManager.InsertSketch(True)
    pocket_sketch = sketch_name(model, "Sketch_Pockets")
    for cx in (-P.pocket_center_x, P.pocket_center_x):
        model.SketchManager.CreateCenterRectangle(mm(cx), 0, 0, mm(cx + P.pocket_length / 2), mm(P.pocket_width / 2), 0)
    model.SketchManager.InsertSketch(True)
    cut(model, pocket_sketch, P.pocket_depth, "Lightening_Pockets")

    for sketch_label, radius, positions, depth, through_all, label in [
        ("Sketch_Mount_Holes", P.mount_hole_diameter / 2, [(x, y) for x in (-P.mount_hole_x, P.mount_hole_x) for y in (-P.mount_hole_y, P.mount_hole_y)], P.thickness + 4, True, "Mount_Holes"),
        ("Sketch_Counterbores", P.counterbore_diameter / 2, [(x, y) for x in (-P.mount_hole_x, P.mount_hole_x) for y in (-P.mount_hole_y, P.mount_hole_y)], P.counterbore_depth, False, "Counterbores"),
        ("Sketch_Dowels", P.dowel_hole_diameter / 2, [(-P.dowel_hole_x, 0), (P.dowel_hole_x, 0)], P.thickness + 4, True, "Dowel_Holes"),
    ]:
        clear(model)
        model.Extension.SelectByID2("Plane_Base_Top", "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
        model.SketchManager.InsertSketch(True)
        name = sketch_name(model, sketch_label)
        for x, y in positions:
            model.SketchManager.CreateCircleByRadius(mm(x), mm(y), 0, mm(radius))
        model.SketchManager.InsertSketch(True)
        cut(model, name, depth, label, through_all=through_all)

    plane_boss = offset_front_plane(model, "Plane_Boss_Top", P.thickness + P.boss_height)
    clear(model)
    model.Extension.SelectByID2(plane_boss, "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
    model.SketchManager.InsertSketch(True)
    slot_sketch = sketch_name(model, "Sketch_Center_Slot")
    half_line = P.slot_length / 2 - P.slot_width / 2
    sketch_slot(model, mm(-half_line), 0, mm(half_line), 0, mm(P.slot_width / 2))
    model.SketchManager.InsertSketch(True)
    cut(model, slot_sketch, P.thickness + P.boss_height + 4, "Center_Slot", through_all=True)

    hole_targets = [(x, y) for x in (-P.mount_hole_x, P.mount_hole_x) for y in (-P.mount_hole_y, P.mount_hole_y)]
    hole_targets += [(-P.dowel_hole_x, 0), (P.dowel_hole_x, 0)]

    def hole_mouth(edge) -> bool:
        circle = circle_center_radius(edge)
        if not circle:
            return False
        center, radius = circle
        expected_radius = abs(radius - mm(P.counterbore_diameter / 2)) < mm(0.8) or abs(radius - mm(P.dowel_hole_diameter / 2)) < mm(0.8)
        near_target = any(abs(center[0] - mm(x)) < mm(1.5) and abs(center[1] - mm(y)) < mm(1.5) for x, y in hole_targets)
        return abs(center[2] - z_top) < mm(1.0) and expected_radius and near_target

    if select_edges(model, hole_mouth, "hole mouths"):
        chamfer(model, P.hole_chamfer, "Chamfer_Hole_Mouths")

    set_document_appearance(model, "silver")
    model.ForceRebuild3(False)
    model.ViewZoomtofit2()

    (output_dir / "CNC_Mount_Template_parameters.json").write_text(
        json.dumps({"units": "mm", "parameters": asdict(P)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not session.save(model, str(part)):
        raise RuntimeError(f"保存失败: {part}")
    if not export_to_step(model, str(step)):
        raise RuntimeError(f"STEP 导出失败: {step}")
    report, report_path = run_review(model, output_dir, basename="CNC_Mount_Template", expected_outputs=[str(part), str(step)])
    print(f"review={report_path} status={report['evaluation']['status']} score={report['evaluation']['score']}")


def main() -> int:
    """命令行入口。"""
    output = Path.cwd() / "solidworks_fillet_chamfer_output"
    build_model(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
