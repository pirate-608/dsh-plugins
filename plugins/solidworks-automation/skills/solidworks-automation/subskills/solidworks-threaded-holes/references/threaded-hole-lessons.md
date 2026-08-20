# SolidWorks 螺纹孔建模经验

## 这次学到的事

本次 M6x1 内螺纹盲孔样件验证表明，SolidWorks COM 自动化可以稳定生成“可加工语义正确”的螺纹孔模型，但真实 Thread 特征不能作为唯一交付路径。最可靠的结果由四层组成：

- 攻丝底孔真实切除：M6x1 使用 5.0 mm 底孔，盲孔深度 13 mm。
- 螺纹参数属性：规格、深度、底孔、状态写入自定义属性和 JSON。
- 孔口倒角：M6 默认 C0.6，改善加工表达和视觉识别。
- 可见 3D 螺旋线：用于预览审查和用户确认“这是螺纹孔”。

最终 M6 样件参数：

- 基体：`40 x 30 x 16 mm`
- 打孔面：默认 `top`，从上表面向实体内部打孔
- 螺纹：`M6x1 internal blind thread`
- 攻丝底孔：`5.0 mm`
- 底孔深度：`13 mm`
- 螺纹深度：`12 mm`
- 孔口倒角：`C0.6`
- 审查结果：`pass / 100`

## 实测接口结论

枚举值：

```python
swFmSweepThread = 87
swThreadMethod_Cut = 0
swThreadEndCondition_Blind = 0
swCosmeticStandardType_e.swStandardType_StandardISO = 8
swCosmeticEndConditions_e.swEndConditionBlind = 0
```

`InsertCosmeticThread3` 实测签名：

```python
InsertCosmeticThread3(Standard, StandardType, Size, Diameter, EndType, Depth, Note)
```

本机反射看到 `IThreadFeatureData` 可写属性包括：

```text
Edge, StartEntity, EndCondition, BlindDepth, Pitch, ThreadMethod, Type, Size,
Diameter, PitchOverride, DiameterOverride
```

但真实 Thread 特征创建仍不稳定：

- `CreateFeature(ThreadFeatureData)` 返回过 `None`。
- `LoadReferences(edge)` 在本机不可用或失败。
- `MajorDiameter/MinorDiameter/ThreadClass/ThreadType/ThreadSize` 等属性不可设置。

因此代码必须先尝试、检查返回值、失败降级，不要凭 API 名称承诺一定成功。

## 推荐表达策略

按优先级执行：

1. 真实几何底孔：必须成功，否则停止。
2. `ThreadFeatureData`：作为增强项尝试，失败不影响底孔交付。
3. `InsertCosmeticThread3`：作为工程图/特征树表达尝试，返回非空也要审查保存后的特征树。
4. 3D 草图螺旋线：作为可见兜底，不当作真实切削牙型。
5. 自定义属性：作为最终可靠语义来源，必须写入。

对于 STEP：

- STEP 一定能保留底孔、倒角和实体几何。
- STEP 不一定保留 SolidWorks 装饰螺纹/工程图语义。
- 若客户要求 CAM 可直接识别真实牙型，需要改用显式螺旋扫掠切除，但要单独评估建模时间、文件大小和重建稳定性。

## 稳定选边模式

不要依赖 `Edge1`、自动特征名或坐标点击。推荐枚举实体边：

```python
def circle_center_radius(edge):
    curve = get_com_member(edge, "GetCurve")
    if not curve or not get_com_member(curve, "IsCircle"):
        return None
    values = get_com_member(curve, "CircleParams")
    return (float(values[0]), float(values[1]), float(values[2])), float(values[6])

def select_top_hole_edge(model, x, y, z_top, radius):
    model.ClearSelection2(True)
    for body in get_com_member(model, "GetBodies2", 0, False) or []:
        for edge in get_com_member(body, "GetEdges") or []:
            data = circle_center_radius(edge)
            if not data:
                continue
            center, edge_radius = data
            if close(center[0], x) and close(center[1], y) and close(center[2], z_top) and close(edge_radius, radius):
                if edge.Select2(False, 0):
                    return edge
    raise RuntimeError("未找到孔口圆边")
```

判断容差建议：

- 圆心 XY：`0.2 mm`
- 顶面 Z：`0.5 mm`
- 半径：`0.3 mm`

## 常用粗牙内螺纹底孔

| 螺纹 | 螺距 mm | 底孔 mm |
|---|---:|---:|
| M3 | 0.5 | 2.5 |
| M4 | 0.7 | 3.3 |
| M5 | 0.8 | 4.2 |
| M6 | 1.0 | 5.0 |
| M8 | 1.25 | 6.8 |
| M10 | 1.5 | 8.5 |
| M12 | 1.75 | 10.2 |

盲孔默认经验：

- 螺纹深度：约 `2D`，或按用户要求。
- 底孔深度：螺纹深度 + `1-2P`，但不能穿透非通孔零件。
- 孔口倒角：`0.1D` 左右，M6 可用 `C0.6`。

## 常见故障

### 真实 Thread 特征返回 None

保留底孔、倒角、属性和 3D 螺旋线，报告 `thread_status`。不要为了追 Thread API 卡住整体交付。

### CosmeticThread 返回对象但特征树看不到

这是实测出现过的情况。保存后遍历特征树或查看预览，不能把“返回非空”当作最终成功。

### 找不到孔口圆边

确认底孔是否已重建，顶面参考高度是否正确，底孔半径是否用的是攻丝底孔半径而不是公称半径。

如果是侧面孔，确认模板参数 `--hole-face front/right` 与建模基准面一致；默认 `top` 适合安装座上表面螺纹孔。

### STEP 中没有螺纹线

正常。STEP 可靠保留的是底孔和倒角。需要视觉螺纹时保留 3D 草图；需要真实牙型时另做显式螺旋切除。

## 审查清单

完成后读取 review report，至少确认：

- 输出文件存在且非空。
- `model.features` 中有底孔切除，如 `Cut_M6_Tap_Drill_Blind`。
- `model.features` 中有孔口倒角，如 `Chamfer_Thread_Mouth`。
- 若真实/装饰螺纹失败，模型属性里写明失败原因和降级方式。
- 等轴测和俯视预览中孔位正确，孔口倒角可见，没有异常悬空线或比例错误。
