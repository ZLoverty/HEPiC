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

# Tencent COS mirror of the same materials.zip, used only when GitHub itself is
# unreachable (e.g. GitHub is blocked/slow from mainland China). The release
# workflow overwrites these three fixed objects on every release, so there is
# no need for a COS-side "latest release" API call — just fetch and compare.
COS_BASE_URL = "https://hepic-database-1456772252.cos.ap-guangzhou.myqcloud.com/latest"
COS_MANIFEST_URL = f"{COS_BASE_URL}/manifest.json"
COS_ZIP_URL = f"{COS_BASE_URL}/materials.zip"
COS_SHA256_URL = f"{COS_BASE_URL}/materials.zip.sha256"

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


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "hepic-materials-sync"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read().decode("utf-8")


def _download_to(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "hepic-materials-sync"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response, open(dest, "wb") as f:
        shutil.copyfileobj(response, f)


def _sha256_matches(zip_path: Path, expected_hex: str) -> bool:
    actual = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    expected = expected_hex.strip().lower()
    if actual != expected:
        logger.warning("materials.zip digest mismatch: expected %s, got %s", expected, actual)
        return False
    return True


def _verify_zip_digest(zip_path: Path, expected_digest: Optional[str]) -> bool:
    """Verify zip_path against the sha256 digest GitHub reports for the release asset.

    GitHub computes and serves this digest itself (Releases API `digest` field),
    so there is no need to separately maintain per-file checksums in manifest.json.
    """
    if not expected_digest:
        logger.warning("Release asset has no digest to verify against; skipping integrity check")
        return True
    if not expected_digest.startswith("sha256:"):
        logger.warning("Unsupported digest algorithm in %s; skipping integrity check", expected_digest)
        return True

    return _sha256_matches(zip_path, expected_digest.split(":", 1)[1])


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


def _install_zip(cache_dir: Path, zip_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        extract_dir = Path(tmp) / "extracted"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        # hepic_database repo layout nests family files under families/;
        # MaterialDatabase expects them flat alongside manifest.json.
        flat_dir = Path(tmp) / "flat"
        flat_dir.mkdir()
        shutil.copy2(extract_dir / "manifest.json", flat_dir / "manifest.json")
        for yaml_file in (extract_dir / "families").glob("*.yaml"):
            shutil.copy2(yaml_file, flat_dir / yaml_file.name)

        _replace_cache_dir(cache_dir, flat_dir)


def _sync_from_github(cache_dir: Path, local_version: Optional[str]) -> None:
    """Raises (URLError, TimeoutError, OSError) if GitHub is unreachable, which
    signals the caller to fall back to the Tencent COS mirror."""
    release = _fetch_latest_release()
    remote_tag = release.get("tag_name", "")
    remote_version = remote_tag[1:] if remote_tag.startswith("v") else remote_tag

    if not remote_version:
        logger.warning("hepic_database latest release has no tag_name; skipping sync")
        return

    if remote_version == local_version:
        logger.info("Material database already up to date (version=%s)", local_version)
        return

    asset = next(
        (a for a in release.get("assets", []) if a.get("name") == "materials.zip"),
        None,
    )
    if not asset:
        logger.warning("hepic_database release %s has no materials.zip asset", remote_tag)
        return

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "materials.zip"
        _download_to(asset["browser_download_url"], zip_path)

        if not _verify_zip_digest(zip_path, asset.get("digest")):
            logger.error("Downloaded materials.zip (GitHub) failed integrity check; keeping local cache")
            return

        _install_zip(cache_dir, zip_path)

    logger.info("Material database synced via GitHub: %s -> %s", local_version or "none", remote_version)


def _sync_from_cos(cache_dir: Path, local_version: Optional[str]) -> None:
    """Fallback path used only when GitHub itself couldn't be reached (e.g. it's
    blocked/slow from mainland China). Raises the same network exceptions as
    _sync_from_github; the caller treats those as "sync skipped, use cache"."""
    remote_version = json.loads(_fetch_text(COS_MANIFEST_URL)).get("version")

    if not remote_version:
        logger.warning("COS materials manifest has no version; skipping sync")
        return

    if remote_version == local_version:
        logger.info("Material database already up to date via COS (version=%s)", local_version)
        return

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "materials.zip"
        _download_to(COS_ZIP_URL, zip_path)

        expected_hex = _fetch_text(COS_SHA256_URL)
        if not _sha256_matches(zip_path, expected_hex):
            logger.error("Downloaded materials.zip (COS) failed integrity check; keeping local cache")
            return

        _install_zip(cache_dir, zip_path)

    logger.info("Material database synced via Tencent COS: %s -> %s", local_version or "none", remote_version)


def sync_materials() -> Path:
    """Ensure the local material database cache exists and matches the latest
    hepic_database release. Always returns the directory MaterialDatabase
    should load from — never raises, so a flaky network can't block startup.

    Tries GitHub first; only falls back to the Tencent COS mirror if GitHub
    itself is unreachable (not merely if the local copy is already current).
    """
    cache_dir = get_cache_dir()
    _seed_if_empty(cache_dir)
    local_version = _read_version(cache_dir)

    try:
        _sync_from_github(cache_dir, local_version)
        return cache_dir
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("GitHub unreachable (%s); falling back to Tencent COS mirror", exc)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.warning("Material database sync via GitHub failed: %s", exc)
        return cache_dir

    try:
        _sync_from_cos(cache_dir, local_version)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Material database sync skipped (COS also unreachable): %s", exc)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.warning("Material database sync via Tencent COS failed: %s", exc)

    return cache_dir
