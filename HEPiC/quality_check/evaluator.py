"""Force and stability evaluation for quality checks."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Sequence

DEFAULT_STABILITY_THRESHOLD = 0.1


@dataclass(frozen=True)
class ForceEvaluation:
    mean: float
    std: float
    stability_status: str
    force_status: str


def _float_range(value, default: tuple[float, float]) -> tuple[float, float]:
    if value is None:
        return default
    return float(value[0]), float(value[1])


def get_force_range(material_properties: dict) -> tuple[float, float]:
    return _float_range(material_properties.get("force_range"), (0.0, 0.0))


def get_excellent_force_range(material_properties: dict) -> tuple[float, float]:
    return _float_range(
        material_properties.get("excellent_force_range"),
        get_force_range(material_properties),
    )


def get_stability_threshold(material_properties: dict) -> float:
    return float(material_properties.get("stability_threshold", DEFAULT_STABILITY_THRESHOLD))


def evaluate_force_window(force_values: Sequence[float], material_properties: dict) -> ForceEvaluation | None:
    """Evaluate recent extrusion-force readings against the material profile."""
    if len(force_values) < 10:
        return None

    recent_values = [float(value) for value in force_values[-20:]]
    mean = fmean(recent_values)
    std = pstdev(recent_values)
    stability_threshold = get_stability_threshold(material_properties)
    excellent_min, excellent_max = get_excellent_force_range(material_properties)
    force_min, force_max = get_force_range(material_properties)

    if std < stability_threshold:
        stability_status = "stable"
    elif std < stability_threshold * 2:
        stability_status = "warning"
    else:
        stability_status = "unstable"

    if excellent_min <= mean <= excellent_max:
        force_status = "stable"
    elif force_min <= mean <= force_max:
        force_status = "warning"
    else:
        force_status = "unstable"

    return ForceEvaluation(
        mean=mean,
        std=std,
        stability_status=stability_status,
        force_status=force_status,
    )
