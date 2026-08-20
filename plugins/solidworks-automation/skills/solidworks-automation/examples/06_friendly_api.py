"""
示例 6: 使用友好 Session API 创建并导出零件

运行前提:
    1. SolidWorks 已安装，可手动启动也可由脚本启动。
    2. 已安装 pywin32: pip install pywin32
"""
import sys

sys.path.insert(0, r"../scripts")

from sw_connect import mm
from sw_part import extrude_boss, sketch, sketch_circle
from sw_session import SolidWorksSession


def main():
    """创建一个圆柱体并导出 STEP。"""
    session = SolidWorksSession()
    model = session.new_part()

    with sketch(model, "Front Plane") as sketch_name:
        sketch_circle(model, 0, 0, mm(25))

    extrude_boss(model, sketch_name, mm(50))

    session.save(model, r"C:\temp\friendly_cylinder.sldprt")
    session.export(model, r"C:\temp\friendly_cylinder.step")
    print("完成: C:\\temp\\friendly_cylinder.sldprt / .step")


if __name__ == "__main__":
    main()
