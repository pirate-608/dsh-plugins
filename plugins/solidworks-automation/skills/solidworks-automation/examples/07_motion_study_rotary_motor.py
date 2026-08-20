"""
示例：给已有风扇装配体添加 Motion Study 旋转马达。

运行前提：
1. SolidWorks 已安装，且 Python 环境已安装 pywin32 / comtypes。
2. 修改 assembly_path 为你的风扇装配体路径。
3. 装配体中存在中心立柱组件和叶轮组件；叶轮同心 Mate 未锁定旋转。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from sw_connect import connect_solidworks, mm, open_document
from sw_assembly import find_component_by_name
from sw_motion import (
    create_motion_study,
    add_constant_speed_rotary_motor_by_cylinders,
    calculate_and_play,
)


def main():
    """打开装配体并添加 60RPM 旋转马达。"""
    assembly_path = r"C:\temp\desktop_mini_cooling_fan.SLDASM"
    sw, _ = connect_solidworks()
    asm = open_document(sw, assembly_path, silent=True, raise_on_error=True)

    stand_comp = find_component_by_name(asm, "stand")
    impeller_comp = find_component_by_name(asm, "impeller")

    study = create_motion_study(
        asm,
        name="叶轮_60RPM_循环转动",
        duration=4.0,
    )
    add_constant_speed_rotary_motor_by_cylinders(
        study,
        shaft_component=stand_comp,
        rotor_component=impeller_comp,
        shaft_radius=(mm(4.5), mm(5.5)),
        rotor_radius=(mm(10.5), mm(11.5)),
        rpm=60.0,
        name="叶轮旋转马达_60RPM",
    )
    print(f"Motion Study 计算结果: {calculate_and_play(study)}")


if __name__ == "__main__":
    main()
