"""Best-effort sync of the material property database from the hepic_database
GitHub repo (https://github.com/ZLoverty/hepic_database), so material data can
be updated without shipping a new HEPiC / hepic_device release.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

GITHUB_REPO = "ZLoverty/hepic_database"
RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
REQUEST_TIMEOUT = 5  # seconds — a slow/offline network must never stall app startup for long

# Bundled "factory" snapshot shipped inside the HEPiC package: seeds a fresh
# cache on first run and is the offline fallback if a sync has never succeeded.
BUNDLED_MATERIALS_DIR = Path(__file__).parent / "materials"


def get_cache_dir() -> Path:
    """Per-user writable directory the synced material database lives in."""
    override = os.environ.get("HEPIC_MATERIALS_DIR")
    if override:
        return Path(override)

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "HEPiC" / "materials"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "HEPiC" / "materials"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "hepic" / "materials"


def _read_version(manifest_dir: Path) -> Optional[str]:
    manifest_file = manifest_dir / "manifest.json"
    if not manifest_file.exists():
        return None
    try:
        return json.loads(manifest_file.read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def _seed_if_empty(cache_dir: Path) -> None:
    if cache_dir.exists() and any(cache_dir.glob("*.yaml")):
        return
    if not BUNDLED_MATERIALS_DIR.exists():
        return

    cache_dir.mkdir(parents=True, exist_ok=True)
    for item in BUNDLED_MATERIALS_DIR.iterdir():
        shutil.copy2(item, cache_dir / item.name)
    logger.info("Seeded material cache at %s from bundled snapshot", cache_dir)


def _request_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hepic-materials-sync"}
    token = os.environ.get("HEPIC_MATERIALS_GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_latest_release() -> dict:
    request = urllib.request.Request(RELEASE_API_URL, headers=_request_headers())
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _verify_checksums(extracted_dir: Path, manifest: dict) -> bool:
    for filename, expected in manifest.get("families", {}).items():
        expected_hash = expected.split(":", 1)[-1]
        family_file = extracted_dir / "families" / filename
        if not family_file.exists():
            logger.warning("Downloaded material archive is missing %s", filename)
            return False
        actual_hash = hashlib.sha256(family_file.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            logger.warning("Checksum mismatch for %s in downloaded material archive", filename)
            return False
    return True


def _replace_cache_dir(cache_dir: Path, new_contents_dir: Path) -> None:
    """Atomically (as far as os.rename allows) swap cache_dir's contents for new_contents_dir's."""
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = cache_dir.parent / f"{cache_dir.name}.new"
    backup_dir = cache_dir.parent / f"{cache_dir.name}.old"
    shutil.rmtree(staging_dir, ignore_errors=True)
    shutil.rmtree(backup_dir, ignore_errors=True)

    shutil.copytree(new_contents_dir, staging_dir)
    if cache_dir.exists():
        cache_dir.rename(backup_dir)
    staging_dir.rename(cache_dir)
    shutil.rmtree(backup_dir, ignore_errors=True)


def sync_materials() -> Path:
    """Ensure the local material database cache exists and matches the latest
    hepic_database release. Always returns the directory MaterialDatabase
    should load from — never raises, so a flaky network can't block startup.
    """
    cache_dir = get_cache_dir()
    _seed_if_empty(cache_dir)

    try:
        local_version = _read_version(cache_dir)
        release = _fetch_latest_release()
        remote_tag = release.get("tag_name", "")
        remote_version = remote_tag[1:] if remote_tag.startswith("v") else remote_tag

        if not remote_version:
            logger.warning("hepic_database latest release has no tag_name; skipping sync")
            return cache_dir

        if remote_version == local_version:
            logger.info("Material database already up to date (version=%s)", local_version)
            return cache_dir

        asset_url = next(
            (
                asset["browser_download_url"]
                for asset in release.get("assets", [])
                if asset.get("name") == "materials.zip"
            ),
            None,
        )
        if not asset_url:
            logger.warning("hepic_database release %s has no materials.zip asset", remote_tag)
            return cache_dir

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / "materials.zip"
            with urllib.request.urlopen(asset_url, timeout=REQUEST_TIMEOUT) as response, open(zip_path, "wb") as f:
                shutil.copyfileobj(response, f)

            extract_dir = tmp_path / "extracted"
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)

            manifest = json.loads((extract_dir / "manifest.json").read_text(encoding="utf-8"))
            if not _verify_checksums(extract_dir, manifest):
                logger.error("Downloaded material database failed checksum verification; keeping local cache")
                return cache_dir

            # hepic_database repo layout nests family files under families/;
            # MaterialDatabase expects them flat alongside manifest.json.
            flat_dir = tmp_path / "flat"
            flat_dir.mkdir()
            shutil.copy2(extract_dir / "manifest.json", flat_dir / "manifest.json")
            for yaml_file in (extract_dir / "families").glob("*.yaml"):
                shutil.copy2(yaml_file, flat_dir / yaml_file.name)

            _replace_cache_dir(cache_dir, flat_dir)

        logger.info("Material database synced: %s -> %s", local_version or "none", remote_version)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Material database sync skipped (network issue): %s", exc)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.warning("Material database sync failed: %s", exc)

    return cache_dir
