"""Verified GitHub-release discovery and download for the external updater."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Callable, Dict, Iterable, Optional
import urllib.request


LATEST_RELEASE_API = "https://api.github.com/repos/torubaev/crystengkit-orca-v1.0/releases/latest"
USER_AGENT = "CrystEngKit-ORCA-Updater"


@dataclass(frozen=True)
class ReleaseInstaller:
    version: str
    release_url: str
    asset_name: str
    download_url: str
    sha256: str


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value).strip())
    if not match:
        raise ValueError(f"Invalid release version: {value!r}")
    return tuple(int(part) for part in match.groups())


def is_development_checkout(app_root: Path) -> bool:
    return (Path(app_root) / ".git").exists()


def _asset_digest(asset: Dict) -> str:
    digest = str(asset.get("digest") or "").strip().lower()
    if digest.startswith("sha256:") and re.fullmatch(r"[0-9a-f]{64}", digest[7:]):
        return digest[7:]
    return ""


def select_release_installer(payload: Dict) -> ReleaseInstaller:
    tag = str(payload.get("tag_name") or "").strip()
    version = ".".join(str(part) for part in version_tuple(tag))
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError("The GitHub release contains no asset list.")
    expected = f"CrystEngKit-ORCA-Setup-{version}-web.exe".lower()
    installer = next(
        (asset for asset in assets if str(asset.get("name") or "").lower() == expected),
        None,
    )
    if not isinstance(installer, dict):
        raise ValueError(f"Release {version} does not contain the expected web installer {expected}.")
    download_url = str(installer.get("browser_download_url") or "").strip()
    if not download_url.startswith("https://github.com/"):
        raise ValueError("The release installer has an invalid download URL.")
    sha256 = _asset_digest(installer)
    if not sha256:
        checksum_name = str(installer.get("name")) + ".sha256"
        checksum_asset = next(
            (asset for asset in assets if str(asset.get("name") or "") == checksum_name),
            None,
        )
        if isinstance(checksum_asset, dict):
            checksum_url = str(checksum_asset.get("browser_download_url") or "").strip()
            if checksum_url.startswith("https://github.com/"):
                sha256 = "url:" + checksum_url
    if not sha256:
        raise ValueError("The release installer has no GitHub SHA-256 digest or checksum asset.")
    return ReleaseInstaller(
        version=version,
        release_url=str(payload.get("html_url") or "").strip(),
        asset_name=str(installer.get("name")),
        download_url=download_url,
        sha256=sha256,
    )


def _read_url(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_latest_installer(timeout: float = 20.0) -> ReleaseInstaller:
    payload = json.loads(_read_url(LATEST_RELEASE_API, timeout=timeout).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub returned an invalid release response.")
    return select_release_installer(payload)


def _resolve_sha256(installer: ReleaseInstaller, timeout: float) -> str:
    if not installer.sha256.startswith("url:"):
        return installer.sha256
    text = _read_url(installer.sha256[4:], timeout=timeout).decode("ascii", errors="replace")
    match = re.search(r"\b[0-9A-Fa-f]{64}\b", text)
    if not match:
        raise ValueError("The published checksum file does not contain a SHA-256 value.")
    return match.group(0).lower()


def download_verified_installer(
    installer: ReleaseInstaller,
    *,
    timeout: float = 120.0,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Path:
    expected_hash = _resolve_sha256(installer, timeout)
    target_dir = Path(tempfile.gettempdir()) / "CrystEngKit-ORCA-update" / installer.version
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / installer.asset_name
    request = urllib.request.Request(installer.download_url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            output.write(block)
            digest.update(block)
            written += len(block)
            if progress:
                progress(written, total)
    if digest.hexdigest().lower() != expected_hash:
        target.unlink(missing_ok=True)
        raise ValueError("The downloaded installer failed SHA-256 verification and was removed.")
    return target
