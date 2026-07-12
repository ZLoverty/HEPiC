"""Material property database backed by YAML files."""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency fallback
    yaml = None


class MaterialDatabase:
    """Load material properties from YAML family files."""

    def __init__(self, materials_dir: Optional[Path] = None):
        self.logger = logging.getLogger(__name__)
        if materials_dir is None:
            from .materials_sync import get_cache_dir

            materials_dir = get_cache_dir()

        self.materials_dir = materials_dir
        self.material_families: dict[str, dict[str, dict[str, Any]]] = {}
        self.materials: dict[str, dict[str, Any]] = {}
        self.version: Optional[str] = None
        self.load()

    def load(self):
        """Load all material definitions from YAML files."""
        self.material_families = {}
        self.materials = {}

        # Fall back to the bundled snapshot if the synced cache is missing or
        # empty (e.g. sync_materials() was never called, or has no network yet).
        from .materials_sync import BUNDLED_MATERIALS_DIR

        if self.materials_dir != BUNDLED_MATERIALS_DIR:
            has_synced_data = self.materials_dir.exists() and any(self.materials_dir.glob("*.yaml"))
            if not has_synced_data and BUNDLED_MATERIALS_DIR.exists():
                self.logger.warning(
                    "No synced material data in %s; falling back to bundled snapshot at %s",
                    self.materials_dir,
                    BUNDLED_MATERIALS_DIR,
                )
                self.materials_dir = BUNDLED_MATERIALS_DIR

        self.version = self._load_manifest_version()

        if not self.materials_dir.exists():
            self.logger.warning(f"Material database directory not found: {self.materials_dir}")
            return

        yaml_files = sorted(self.materials_dir.glob("*.yaml"))
        if not yaml_files:
            self.logger.warning(f"No material YAML files found in: {self.materials_dir}")
            return

        for yaml_file in yaml_files:
            self._load_yaml_file(yaml_file)

        self.logger.info(
            "Loaded %s material families and %s materials from %s (version=%s)",
            len(self.material_families),
            len(self.materials),
            self.materials_dir,
            self.version or "unknown",
        )

    def _load_manifest_version(self) -> Optional[str]:
        """Read the data version out of manifest.json, if one is present."""
        manifest_file = self.materials_dir / "manifest.json"
        if not manifest_file.exists():
            return None

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            version = manifest.get("version")
            return str(version) if version else None
        except Exception as exc:
            self.logger.warning(f"Failed to read material manifest {manifest_file}: {exc}")
            return None

    def get_version(self) -> str:
        """Get the loaded material database's data version, for diagnostics."""
        return self.version or "unknown"

    def _load_yaml_file(self, yaml_file: Path):
        try:
            raw_data = self._load_yaml_mapping(yaml_file)
        except Exception as exc:
            self.logger.error(f"Failed to load material YAML file {yaml_file}: {exc}")
            return

        if not isinstance(raw_data, dict):
            self.logger.warning(f"Skipped non-mapping YAML file: {yaml_file}")
            return

        records = {
            key: value
            for key, value in raw_data.items()
            if isinstance(value, dict) and value.get("PI_Code")
        }
        if not records:
            self.logger.warning(f"No material records found in YAML file: {yaml_file}")
            return

        family_name = self._resolve_family_name(yaml_file, records)
        family_bucket = self.material_families.setdefault(family_name, {})

        for record_key, properties in records.items():
            pi_code = str(properties.get("PI_Code") or record_key).strip()
            if not pi_code:
                continue

            normalized = dict(properties)
            normalized["PI_Code"] = pi_code
            normalized["family"] = family_name
            normalized.setdefault("name", family_name)

            family_bucket[pi_code] = normalized
            self.materials[pi_code] = normalized

    def _load_yaml_mapping(self, yaml_file: Path) -> dict[str, Any]:
        with open(yaml_file, "r", encoding="utf-8") as f:
            content = f.read()

        if yaml is not None:
            return yaml.safe_load(content) or {}

        return self._load_simple_yaml(content)

    def _load_simple_yaml(self, content: str) -> dict[str, Any]:
        """Parse the limited YAML subset used by material family files."""
        sections: dict[str, dict[str, Any]] = {}
        anchors: dict[str, str] = {}
        current_key = None

        for raw_line in content.splitlines():
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue

            if not raw_line.startswith(" "):
                key_part, _, remainder = line.partition(":")
                current_key = key_part.strip()
                sections[current_key] = {}
                remainder = remainder.strip()
                if remainder.startswith("&"):
                    anchors[remainder[1:]] = current_key
                continue

            if current_key is None:
                continue

            item = line.strip()
            item_key, _, item_value = item.partition(":")
            sections[current_key][item_key.strip()] = self._parse_simple_yaml_value(item_value.strip())

        resolved: dict[str, dict[str, Any]] = {}
        for section_key, values in sections.items():
            merged = {}
            merge_value = values.get("<<")
            if isinstance(merge_value, str) and merge_value.startswith("*"):
                anchor_key = anchors.get(merge_value[1:], merge_value[1:])
                merged.update(sections.get(anchor_key, {}))

            merged.update({key: value for key, value in values.items() if key != "<<"})
            resolved[section_key] = merged

        return resolved

    def _parse_simple_yaml_value(self, value: str) -> Any:
        if not value:
            return ""

        if value.startswith(("'", '"')) and value.endswith(("'", '"')):
            try:
                return ast.literal_eval(value)
            except Exception:
                return value.strip("'\"")

        if value.startswith("[") and value.endswith("]"):
            return ast.literal_eval(value)

        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return float(value)
        except ValueError:
            pass

        return value

    def _resolve_family_name(
        self, yaml_file: Path, records: dict[str, dict[str, Any]]
    ) -> str:
        names = [str(item.get("name", "")).strip() for item in records.values() if item.get("name")]
        if names:
            return names[0]

        stem = yaml_file.stem
        return stem[:-7].upper() if stem.endswith("_family") else stem.upper()

    def get_material(self, name: str, family: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Get one material by PI_Code, optionally scoped by family."""
        if family:
            return self.material_families.get(family, {}).get(name)
        return self.materials.get(name)

    def get_all_materials(self) -> dict[str, dict[str, Any]]:
        """Get all materials keyed by PI_Code."""
        return {key: value.copy() for key, value in self.materials.items()}

    def get_material_families(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Get all materials grouped by family."""
        return {
            family: {pi_code: props.copy() for pi_code, props in materials.items()}
            for family, materials in self.material_families.items()
        }

    def get_material_names(self) -> list[str]:
        """Get all PI_Code values."""
        return list(self.materials.keys())

    def get_family_names(self) -> list[str]:
        """Get all material family names."""
        return list(self.material_families.keys())

    def get_pi_codes(self, family: str) -> list[str]:
        """Get all PI_Code values under a family."""
        return list(self.material_families.get(family, {}).keys())

    def add_material(self, name: str, properties: dict[str, Any]):
        """Update the in-memory index for one material."""
        family = str(properties.get("family") or properties.get("name") or "").strip()
        if not family:
            raise ValueError("Material properties must include family or name")

        normalized = dict(properties)
        normalized["PI_Code"] = name
        normalized["family"] = family
        normalized.setdefault("name", family)

        self.material_families.setdefault(family, {})[name] = normalized
        self.materials[name] = normalized
        self.logger.info(f"Added/Updated material: {family}/{name}")

    def delete_material(self, name: str) -> bool:
        """Delete one material from the in-memory index."""
        material = self.materials.pop(name, None)
        if material is None:
            return False

        family = material.get("family")
        if family in self.material_families:
            self.material_families[family].pop(name, None)
            if not self.material_families[family]:
                del self.material_families[family]

        self.logger.info(f"Deleted material: {name}")
        return True

    def get_forcerange(self, name: str) -> tuple[float, float]:
        material = self.get_material(name)
        if material:
            force_range = material.get("force_range", [0, 0])
            return float(force_range[0]), float(force_range[1])
        return (0.0, 0.0)

    def get_temperature(self, name: str) -> float:
        material = self.get_material(name)
        return float(material.get("temperature", 0.0)) if material else 0.0

    def get_speed(self, name: str) -> float:
        material = self.get_material(name)
        return float(material.get("speed", 0.0)) if material else 0.0

    def get_stability_threshold(self, name: str) -> float:
        material = self.get_material(name)
        return float(material.get("stability_threshold", 2.0)) if material else 2.0


_global_db = None


def get_material_database() -> MaterialDatabase:
    """Get the global material database instance."""
    global _global_db
    if _global_db is None:
        _global_db = MaterialDatabase()
    return _global_db
