# CNC 多圆角/倒角建模经验

## 这次学到的事

本次“CNC 铝合金安装座”验证表明，SolidWorks COM 自动化可以稳定生成多圆角/倒角模型，但必须控制建模顺序和选边方法。成功模型包含底板、中心凸台、安装孔、沉孔、定位孔、中心长槽、减重口袋、真实 Fillet 和 Chamfer 特征，并通过 `sw_review` 规则审查。

最重要的结论：

- 圆角/倒角多的零件，要先让主体拓扑简单，再逐步增加复杂度。
- 大圆角和外轮廓倒角放在孔槽之前，比放在所有切除之后稳定。
- 用实体边对象选择比用自动边名或坐标点击稳定。
- 每个 SolidWorks 特征返回值都要检查 `None` / `False`，失败就立刻中止或降级。
- 同名输出文件如果已在 SolidWorks 打开，保存会失败，典型表现为 `SaveAs` 错误码 `1`。

## 推荐 API 和封装

必须优先调用父技能已有封装：

```python
from sw_session import SolidWorksSession
from sw_connect import mm, get_com_member, create_empty_dispatch_variant
from sw_export import export_to_step
from sw_review import run_review
from sw_appearance import set_document_appearance
```

常用 SolidWorks API：

```python
model.FeatureManager.FeatureExtrusion3(...)
model.FeatureManager.FeatureCut4(...)
model.FeatureManager.FeatureFillet(195, radius, 0, 0, None, None, None)
model.FeatureManager.InsertFeatureChamfer(4, 1, distance, math.pi / 4, 0, 0, 0, 0)
edge.Select2(append, 0)
model.GetBodies2(0, False)
body.GetEdges()
edge.GetCurve()
curve.IsLine()
curve.IsCircle()
curve.CircleParams()
```

pywin32 下 `GetStartVertex`、`GetEndVertex`、`FirstFeature` 等成员可能表现为伪可调用属性，读取时用 `get_com_member()`。

## 稳定选边模式

不要依赖 `Edge1`、`Edge2` 或空名称坐标选择。推荐模式：

```python
def edge_points(edge):
    start_vertex = get_com_member(edge, "GetStartVertex")
    end_vertex = get_com_member(edge, "GetEndVertex")
    if not start_vertex or not end_vertex:
        return None
    return (
        tuple(get_com_member(start_vertex, "GetPoint")),
        tuple(get_com_member(end_vertex, "GetPoint")),
    )

def midpoint(edge):
    points = edge_points(edge)
    if not points:
        return None
    start, end = points
    return tuple((start[i] + end[i]) / 2.0 for i in range(3))

def select_edges(model, predicate):
    model.ClearSelection2(True)
    count = 0
    for body in get_com_member(model, "GetBodies2", 0, False) or []:
        for edge in get_com_member(body, "GetEdges") or []:
            if predicate(edge) and edge.Select2(count > 0, 0):
                count += 1
    return count
```

按中点坐标、方向、是否直线/圆边、圆心半径分类边线。

## 推荐特征顺序

用于 CNC 安装座、连接块、机加工基座：

1. 基础矩形底板拉伸。
2. 顶部凸台拉伸。
3. 外轮廓大圆角和顶/底边倒角。
4. 减重口袋。
5. 贯穿安装孔。
6. 沉孔/沉头台阶。
7. 定位孔。
8. 中心长圆槽。
9. 孔口小倒角。
10. 保存、导出 STEP、审查预览。

如果步骤 3 放在孔槽之后，SolidWorks 可能在复杂拓扑上求解很久。若必须后置，先减少半径、减少边数，逐类测试。

## 半径和降级策略

保守默认值：

- 底板立角大圆角：R6-R10
- 凸台立角圆角：R3-R6
- 外轮廓倒角：C0.8-C2
- 凸台顶面倒角：C0.5-C1
- 孔口倒角：C0.3-C0.8

降级顺序：

1. 减小半径/倒角距离。
2. 减少一次选择的边数。
3. 把大圆角前置到孔槽之前。
4. 跳过槽口/口袋底部小圆角，记录为 `0`。
5. 保留主体、孔槽、关键外轮廓圆角，优先完成可导出的模型。

## 常见故障

### 拉伸返回 None

常见原因是复杂圆角草图没有闭合。改用简单矩形草图拉伸，再对立角做真实 Fillet。

### 圆角/倒角卡很久

多半是切孔后拓扑复杂、半径过大或选边过宽。先单独测试每一类边：底板立角、凸台立角、顶边、底边、孔口。

### SaveAs 错误码 1

目标文件可能已经在 SolidWorks 中打开。新建前关闭同名文档：

```python
try:
    session.close(title=Path(output_part).name)
except Exception:
    pass
```

### 预览偏透明或颜色怪

不要把外观问题当作几何失败。先确认审查报告和预览非空。外观要求高时使用 `set_document_appearance(model, "silver")` 或拆装配体分组件上色。

## 审查清单

完成后读取 review report，至少确认：

- `evaluation.status`
- `checks.previews_created`
- `checks.previews_not_blank`
- `checks.expected_outputs_exist`
- `model.features` 中是否有 `Fillet`、`Chamfer`、`Cut` 特征

若规则审查通过，还要人工看 `isometric` 和 `top` 预览，确认主体比例、孔位、沉孔、长槽、口袋和圆角方向。
