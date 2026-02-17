import hashlib
import logging
import re
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import gdown
import httpx
import pandas as pd
from tqdm.auto import tqdm

from config import HF_TOKEN

logger = logging.getLogger(__name__)

# Type alias for path-like objects (accepts both str and Path)
type PathLike = str | Path


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
        pass
    return False


def _extract_gdrive_file_id(url: str) -> str | None:
    """Extract Google Drive file ID from URL (/file/d/ID, /d/ID, or ?id=ID)."""
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",  # /file/d/FILE_ID/...
        r"/d/([a-zA-Z0-9_-]+)",  # /d/FILE_ID/... (docs, sheets, etc.)
        r"[?&]id=([a-zA-Z0-9_-]+)",  # ?id=FILE_ID or &id=FILE_ID
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    logger.warning("Could not extract Google Drive file ID from URL: %s", url)
    return None


def _check_existing_file(
    output_path: Path, checksum: str | None, force_download: bool
) -> Path | None:
    """Return path if file exists and checksum matches, else None."""
    if force_download or not output_path.exists():
        return None

    logger.info("File already exists: %s", output_path)

    if checksum:
        if _verify_checksum(output_path, checksum):
            logger.info("Checksum verified for existing file: %s", output_path)
            return output_path
        logger.warning("Checksum mismatch for existing file: %s. Re-downloading...", output_path)
        output_path.unlink()
        return None

    return output_path


def _verify_checksum(file_path: PathLike, expected_checksum: str) -> bool:
    """Verify file SHA-256 checksum. Returns True if match, False otherwise."""
    file_path = Path(file_path)

    if not file_path.exists():
        logger.error("File not found for checksum verification: %s", file_path)
        return False

    # Calculate SHA-256 checksum
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)

    calculated_checksum = sha256_hash.hexdigest()

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


def _download_file(
    url: str,
    output_path: PathLike,
    force_download: bool = False,
    checksum: str | None = None,
    **kwargs: Any,
) -> Path:
    """Download a file from URL, auto-detecting Google Drive and HuggingFace sources."""
    output_path = Path(output_path)
    parsed_url = urlparse(url)

    if "drive.google.com" in parsed_url.netloc or "docs.google.com" in parsed_url.netloc:
        file_id = _extract_gdrive_file_id(url)
        if not file_id:
            raise RuntimeError(f"Could not extract Google Drive file ID from URL: {url}")
        return download_from_gdrive(
            file_id, output_path, force_download=force_download, checksum=checksum
        )
    if "huggingface.co" in parsed_url.netloc:
        return download_from_huggingface(
            url, output_path, force_download=force_download, checksum=checksum, **kwargs
        )
    return download_from_url(
        url, output_path, force_download=force_download, checksum=checksum, **kwargs
    )


def download_from_url(
    url: str,
    output_path: PathLike,
    force_download: bool = False,
    headers: dict[str, str] | None = None,
    checksum: str | None = None,
    max_retries: int = 3,
    **kwargs: Any,
) -> Path:
    """Download file from a direct URL with progress bar and retry logic."""
    output_path = Path(output_path)

    if existing := _check_existing_file(output_path, checksum, force_download):
        return existing

    output_path.parent.mkdir(parents=True, exist_ok=True)
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
                client.stream("GET", url, **kwargs) as response,
            ):
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))

                if total_size > 0:
                    with (
                        tqdm(
                            desc=f"Downloading {output_path.name}",
                            total=total_size,
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
                else:
                    with open(output_path, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=8192):
                            f.write(chunk)

            if output_path.stat().st_size == 0 or _is_html_error_page(output_path):
                output_path.unlink()
                raise RuntimeError(f"Server returned empty or HTML error page: {url}")

            logger.info("Successfully downloaded: %s", output_path)

            if checksum and not _verify_checksum(output_path, checksum):
                output_path.unlink()
                raise RuntimeError(f"Checksum mismatch for {output_path}")

            return output_path

        except Exception as e:
            last_exception = e
            logger.warning("Download attempt %d failed: %s", attempt + 1, e)
            if output_path.exists():
                output_path.unlink()

            if attempt < max_retries - 1:
                wait_minutes = 2 ** (attempt + 1)  # Exponential backoff: 2, 4, 8... minutes
                logger.info("Waiting %d minute(s) before retry...", wait_minutes)
                time.sleep(wait_minutes * 60)

    raise RuntimeError(f"Failed to download {url} after {max_retries} attempts: {last_exception}")


def download_from_gdrive(
    file_id: str,
    output_path: PathLike,
    force_download: bool = False,
    checksum: str | None = None,
) -> Path:
    """Download file from Google Drive using gdown."""
    output_path = Path(output_path)

    if existing := _check_existing_file(output_path, checksum, force_download):
        return existing

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Downloading from Google Drive to %s", output_path)
        gdown.download(f"https://drive.google.com/uc?id={file_id}", str(output_path), quiet=False)

        if not output_path.exists():
            raise RuntimeError(f"gdown failed to download file to {output_path}")

        logger.info("Successfully downloaded: %s", output_path)

        # Verify checksum if provided
        if checksum:
            if _verify_checksum(output_path, checksum):
                logger.info("Checksum verified: %s", output_path)
            else:
                output_path.unlink()
                raise RuntimeError(f"Checksum mismatch for {output_path}")

        return output_path

    except Exception as e:
        if output_path.exists():
            output_path.unlink()
        e.add_note(f"Google Drive ID: {file_id}")
        e.add_note(f"Output path: {output_path}")
        if checksum:
            e.add_note(f"Expected checksum: {checksum}")
        raise RuntimeError(f"Failed to download from Google Drive: {e}") from e


def download_from_huggingface(
    url: str,
    output_path: PathLike,
    checksum: str | None = None,
    **kwargs: Any,
) -> Path:
    """Download file from HuggingFace datasets. Requires HF_TOKEN environment variable."""
    if not HF_TOKEN:
        raise RuntimeError(
            "HF_TOKEN environment variable is required for HuggingFace downloads. "
            "Set HF_TOKEN in your .env file or environment."
        )

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {HF_TOKEN}"

    return download_from_url(
        url,
        output_path,
        headers=headers,
        checksum=checksum,
        **kwargs,
    )


def download_and_extract_zip(
    url: str,
    extract_path: PathLike,
    files_to_extract: list[str] | None = None,
    force_download: bool = False,
    checksum: str | None = None,
    **download_kwargs: Any,
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
        _download_file(url, temp_zip, force_download=True, checksum=checksum, **download_kwargs)

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


def load_or_download_csv(
    output_path: PathLike,
    url: str,
    force_download: bool = False,
    **read_csv_kwargs: Any,
) -> pd.DataFrame:
    """Load a CSV file, downloading it first if necessary."""
    output_path = Path(output_path)

    if not output_path.exists() or force_download:
        _download_file(url, output_path, force_download=force_download)

    try:
        return cast(pd.DataFrame, pd.read_csv(output_path, **read_csv_kwargs))
    except Exception as e:
        raise RuntimeError(f"Failed to load CSV file: {e}") from e
