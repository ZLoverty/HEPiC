"""Fallback material data used before the YAML database is loaded."""

DEFAULT_MATERIAL_FAMILIES = {
    "PLA": {
        "L1002": {
            "PI_Code": "L1002",
            "family": "PLA",
            "name": "PLA",
            "expected_force": 5.0,
            "excellent_force_range": (4.5, 5.5),
            "force_range": (3.0, 7.0),
            "temperature": 200,
            "speed": 30,
            "stability_threshold": 0.1,
        }
    }
}
