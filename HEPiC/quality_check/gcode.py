"""G-code generation for quality-check routines."""


def build_quality_check_gcode(material_properties: dict) -> str:
    """Build the startup G-code for one quality-check material profile."""
    temperature = material_properties.get("temperature", 200)
    speed_mms = material_properties.get("speed", 5)
    extrude_length_mm = material_properties.get(
        "quality_check_extrude_length_mm",
        float(speed_mms) * 60.0,
    )
    feedrate = max(float(speed_mms) * 60.0, 1.0)
    return "\n".join(
        [
            "M118 STATUS 正在加热",
            f"M109 S{float(temperature):.0f}",
            "M118 START_QUALITY_CHECK",
            "M118 STATUS 正在挤出",
            "M83",
            f"G1 E{float(extrude_length_mm):.2f} F{feedrate:.2f}",
            "M118 STOP_QUALITY_CHECK",
            "M118 STATUS 质检完毕，请记录数据",
            "M104 S0",
        ]
    )
