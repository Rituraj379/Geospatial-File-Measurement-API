"""Utility functions for file handling and validation."""

import logging
import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

logger = logging.getLogger(__name__)

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ZipFileTooLargeError(ValueError):
    """Raised when a ZIP exceeds its configured expanded-size limit."""


def _safe_zip_member(member_name: str, is_directory: bool) -> PurePosixPath:
    """Normalize and validate a ZIP member path on both POSIX and Windows."""
    normalized = member_name.replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    raw_path = normalized.rstrip("/") if is_directory else normalized
    raw_parts = raw_path.split("/")
    if (
        not raw_path
        or normalized.startswith("/")
        or windows_path.drive
        or windows_path.root
        or any(part in {"", ".."} for part in raw_parts)
    ):
        raise ValueError("ZIP archive contains an unsafe path")

    parts = [part for part in raw_parts if part != "."]
    for part in parts:
        basename = part.split(".", 1)[0].upper()
        if (
            ":" in part
            or part.endswith((".", " "))
            or any(ord(char) < 32 for char in part)
            or basename in WINDOWS_RESERVED_NAMES
        ):
            raise ValueError("ZIP archive contains an unsafe path")

    if not parts:
        raise ValueError("ZIP archive contains an unsafe path")
    return PurePosixPath(*parts)


def is_safe_zip_path(member_name: str, extract_dir: Path) -> bool:
    """
    Check whether a ZIP member's resolved path stays within extract_dir.

    Prevents path-traversal attacks (e.g. '../../etc/passwd').
    """
    # Resolve prospective extraction path
    target = (extract_dir / member_name).resolve()
    try:
        target.relative_to(extract_dir.resolve())
        return True
    except ValueError:
        return False


def extract_zip_safely(
    zip_path: Path,
    extract_dir: Path,
    max_uncompressed_bytes: int,
    max_entries: int = 10_000,
) -> None:
    """
    Extract a ZIP archive safely, rejecting any path-traversal attempts.

    Args:
        zip_path: Path to the ZIP file.
        extract_dir: Destination directory for extraction.

    Raises:
        ValueError: If a ZIP member path is unsafe or the archive is malformed.
        ZipFileTooLargeError: If expanded contents exceed the configured limit.
        zipfile.BadZipFile: If the archive is corrupt or not a ZIP.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > max_entries:
            raise ValueError("ZIP archive contains too many entries")
        declared_size = sum(info.file_size for info in infos)
        if declared_size > max_uncompressed_bytes:
            raise ZipFileTooLargeError("ZIP archive expands beyond the configured size limit")

        entries: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        seen_paths: set[str] = set()
        file_paths: set[str] = set()
        for info in infos:
            member = _safe_zip_member(info.filename, info.is_dir())
            normalized = "/".join(member.parts).casefold()
            if normalized in seen_paths:
                raise ValueError("ZIP archive contains duplicate paths")
            if any(
                "/".join(member.parts[:length]).casefold() in file_paths
                for length in range(1, len(member.parts))
            ):
                raise ValueError("ZIP archive contains conflicting file paths")
            if not info.is_dir() and any(
                existing.startswith(normalized + "/") for existing in seen_paths
            ):
                raise ValueError("ZIP archive contains conflicting file paths")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("ZIP archive contains a symbolic link")
            seen_paths.add(normalized)
            if not info.is_dir():
                file_paths.add(normalized)
            entries.append((info, member))

        extract_dir.mkdir(parents=True, exist_ok=True)
        actual_size = 0
        for info, member in entries:
            target = extract_dir.joinpath(*member.parts)
            if not is_safe_zip_path(str(member), extract_dir):
                raise ValueError("ZIP archive contains an unsafe path")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zf.open(info, "r") as source, target.open("wb") as destination:
                    while chunk := source.read(1024 * 1024):
                        actual_size += len(chunk)
                        if actual_size > max_uncompressed_bytes:
                            raise ZipFileTooLargeError(
                                "ZIP archive expands beyond the configured size limit"
                            )
                        destination.write(chunk)
            except (RuntimeError, NotImplementedError, EOFError) as exc:
                raise ValueError("ZIP archive is corrupt or uses unsupported compression") from exc
        logger.debug("Extracted %d entries from %s to %s", len(infos), zip_path, extract_dir)


def find_shapefile(directory: Path) -> Path | None:
    """
    Recursively search *directory* for a .shp file.

    Returns the unique match, or None if there are zero or multiple matches.
    """
    matches = [
        path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() == ".shp"
    ]
    return matches[0] if len(matches) == 1 else None


def validate_shapefile_components(shp_path: Path, required_extensions: list[str]) -> list[str]:
    """
    Verify that required Shapefile sidecar files exist alongside the .shp.

    Args:
        shp_path: Path to the .shp file.
        required_extensions: List of required extensions, e.g. ['.shx', '.dbf'].

    Returns:
        List of missing file extensions (empty list means all present).
    """
    stem = shp_path.stem.casefold()
    present = {
        path.suffix.casefold()
        for path in shp_path.parent.iterdir()
        if path.is_file() and path.stem.casefold() == stem
    }
    missing = [ext for ext in required_extensions if ext.casefold() not in present]
    return missing


def get_file_extension(filename: str) -> str:
    """Return the lowercase file extension including the leading dot."""
    return Path(filename).suffix.lower()


def human_readable_size(num_bytes: int) -> str:
    """Convert a byte count to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes //= 1024
    return f"{num_bytes:.1f} TB"
