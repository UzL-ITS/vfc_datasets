import hashlib
import logging
import re
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import gdown
import httpx
from tqdm.auto import tqdm

from vfc_datasets.config import HF_TOKEN

logger = logging.getLogger(__name__)


def _is_html_error_page(file_path: Path) -> bool:
    """Check if downloaded file is actually an HTML error page."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(1024).lower()
            # Check for HTML signatures
            if b"<!doctype html" in header or b"<html" in header:
                return True
            # Check for common error page patterns
            if b"403 forbidden" in header or b"access denied" in header:
                return True
    except Exception:
        logger.debug("Failed to check if %s is an HTML error page", file_path, exc_info=True)
    return False


_GDRIVE_PATTERNS = [
    re.compile(r"/file/d/([a-zA-Z0-9_-]+)"),  # /file/d/FILE_ID/...
    re.compile(r"/d/([a-zA-Z0-9_-]+)"),  # /d/FILE_ID/... (docs, sheets, etc.)
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),  # ?id=FILE_ID or &id=FILE_ID
]


def _extract_gdrive_file_id(url: str) -> str | None:
    """Extract Google Drive file ID from URL (/file/d/ID, /d/ID, or ?id=ID)."""
    for pattern in _GDRIVE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)

    logger.warning("Could not extract Google Drive file ID from URL: %s", url)
    return None


def _verify_checksum(file_path: str | Path, expected_checksum: str) -> bool:
    """Verify file SHA-256 checksum. Returns True if match, False otherwise."""
    file_path = Path(file_path)

    if not file_path.exists():
        logger.error("File not found for checksum verification: %s", file_path)
        return False

    with open(file_path, "rb") as f:
        calculated_checksum = hashlib.file_digest(f, "sha256").hexdigest()

    if calculated_checksum.lower() != expected_checksum.lower():
        logger.warning(
            "Checksum mismatch for %s: expected %s, got %s",
            file_path.name,
            expected_checksum,
            calculated_checksum,
        )
        return False

    logger.info("Checksum verified for %s", file_path.name)
    return True


def _download_gdrive(file_id: str, output_path: Path) -> None:
    """Download file from Google Drive using gdown."""
    try:
        logger.info("Downloading from Google Drive to %s", output_path)
        gdown.download(f"https://drive.google.com/uc?id={file_id}", str(output_path), quiet=False)

        if not output_path.exists():
            raise RuntimeError(f"gdown failed to download file to {output_path}")

        logger.info("Successfully downloaded: %s", output_path)

    except Exception as e:
        if output_path.exists():
            output_path.unlink()
        e.add_note(f"Google Drive ID: {file_id}")
        e.add_note(f"Output path: {output_path}")
        raise RuntimeError(f"Failed to download from Google Drive: {e}") from e


def _download_http(
    url: str,
    output_path: Path,
    headers: dict[str, str] | None,
    max_retries: int,
) -> None:
    """Download file from a direct URL with progress bar and retry logic."""
    request_headers = headers.copy() if headers else {}
    last_exception = None

    for attempt in range(max_retries):
        try:
            logger.info(
                "Downloading %s to %s (attempt %d/%d)", url, output_path, attempt + 1, max_retries
            )

            with (
                httpx.Client(
                    http2=True,
                    timeout=httpx.Timeout(300, connect=30.0),
                    headers=request_headers,
                    follow_redirects=True,
                ) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))

                with (
                    tqdm(
                        desc=f"Downloading {output_path.name}",
                        total=total_size or None,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        dynamic_ncols=True,
                    ) as pbar,
                    open(output_path, "wb") as f,
                ):
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))

            if output_path.stat().st_size == 0 or _is_html_error_page(output_path):
                output_path.unlink()
                raise RuntimeError(f"Server returned empty or HTML error page: {url}")

            logger.info("Successfully downloaded: %s", output_path)
            return

        except Exception as e:
            last_exception = e
            logger.warning("Download attempt %d failed: %s", attempt + 1, e)
            if output_path.exists():
                output_path.unlink()

            if attempt < max_retries - 1:
                wait_seconds = 20 * 2**attempt  # Exponential backoff: 20s, 40s, 80s
                logger.info("Waiting %d seconds before retry...", wait_seconds)
                time.sleep(wait_seconds)

    raise RuntimeError(f"Failed to download {url} after {max_retries} attempts: {last_exception}")


def download_file(
    url: str,
    output_path: str | Path,
    *,
    force_download: bool = False,
    checksum: str | None = None,
    max_retries: int = 3,
) -> Path:
    """Download a file from URL, auto-detecting Google Drive and HuggingFace sources."""
    output_path = Path(output_path)

    if force_download or not output_path.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        parsed_url = urlparse(url)

        if "drive.google.com" in parsed_url.netloc or "docs.google.com" in parsed_url.netloc:
            file_id = _extract_gdrive_file_id(url)
            if not file_id:
                raise RuntimeError(f"Could not extract Google Drive file ID from URL: {url}")
            _download_gdrive(file_id, output_path)
        else:
            headers: dict[str, str] | None = None
            if "huggingface.co" in parsed_url.netloc and HF_TOKEN:
                headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            _download_http(url, output_path, headers, max_retries)
    else:
        logger.info("File already exists: %s", output_path)

    if checksum and not _verify_checksum(output_path, checksum):
        raise RuntimeError(f"Checksum mismatch for {output_path}")

    return output_path


def download_and_extract_zip(
    url: str,
    extract_path: str | Path,
    *,
    files_to_extract: list[str] | None = None,
    force_download: bool = False,
    checksum: str | None = None,
) -> Path:
    """Download a zip file and extract specific files (or all if files_to_extract is None)."""
    extract_path = Path(extract_path)
    extract_path.mkdir(parents=True, exist_ok=True)

    # Check if we need to download (if any requested file is missing)
    if not force_download and files_to_extract:
        all_exist = all((extract_path / f).exists() for f in files_to_extract)
        if all_exist:
            logger.info("All requested files already exist in %s", extract_path)
            return extract_path

    with tempfile.TemporaryDirectory() as temp_dir:
        # Download zip file
        temp_zip = Path(temp_dir) / "download.zip"
        download_file(url, temp_zip, force_download=True, checksum=checksum)

        try:
            # Extract files
            logger.info("Extracting files to %s", extract_path)
            with zipfile.ZipFile(temp_zip, "r") as zip_ref:
                if files_to_extract:
                    # Extract specific files
                    for pattern in files_to_extract:
                        for member in zip_ref.namelist():
                            if pattern in member:
                                zip_ref.extract(member, extract_path)
                                logger.info("Extracted: %s", member)
                else:
                    # Extract all files
                    zip_ref.extractall(extract_path)
                    logger.info("Extracted all files")

            return extract_path

        except Exception as e:
            e.add_note(f"Zip URL: {url}")
            e.add_note(f"Extract path: {extract_path}")
            if files_to_extract:
                e.add_note(f"Files to extract: {files_to_extract}")
            raise RuntimeError(f"Failed to extract zip file: {e}") from e
