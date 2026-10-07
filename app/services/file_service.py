"""File service: upload validation, storage management, and orchestration.

Responsibilities
----------------
- Validate incoming uploads (extension, size, emptiness).
- Persist uploaded bytes to a temp file.
- Orchestrate geospatial reading → CRS detection → measurement calculation.
- Persist metadata and measurement results as JSON under data/<file-id>/.
- Retrieve stored metadata and measurements by ID.

Storage layout
--------------
    data/
        <uuid>/
            metadata.json     ← FileMetadata (serialised)
            measurements.json ← MeasurementResult (serialised)
"""

import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import geopandas as gpd

from app.core.config import Settings
from app.models.file import (
    FileMetadata,
    MeasurementResult,
    ProcessingStatus,
)
from app.services.crs_service import crs_to_string, get_source_crs
from app.services.geospatial_service import (
    read_kml,
    read_shapefile,
)
from app.services.measurement_service import calculate_measurements
from app.utils.file_utils import (
    ZipFileTooLargeError,
    extract_zip_safely,
    find_shapefile,
    get_file_extension,
    validate_shapefile_components,
)

logger = logging.getLogger(__name__)


class FileValidationError(Exception):
    """Raised when an uploaded file fails validation."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class FileNotFoundError(Exception):  # noqa: A001
    """Raised when a requested file ID does not exist in storage."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_data_dir(settings: Settings) -> Path:
    """Create and return the data directory."""
    data_path = settings.data_path
    data_path.mkdir(parents=True, exist_ok=True)
    return data_path


def _file_dir(settings: Settings, file_id: str) -> Path:
    """Return the storage directory for a given file ID."""
    return _ensure_data_dir(settings) / file_id


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)


def _read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_upload(filename: str, file_size: int, settings: Settings) -> None:
    """
    Validate an incoming upload before any processing.

    Raises FileValidationError with an appropriate HTTP status code on failure.
    """
    if file_size == 0:
        raise FileValidationError("Uploaded file is empty.")

    if file_size > settings.max_file_size_bytes:
        mb = settings.max_file_size_mb
        raise FileValidationError(
            f"File size exceeds the maximum allowed size of {mb} MB.",
            status_code=413,
        )

    ext = get_file_extension(filename)
    if ext not in settings.supported_extensions:
        raise FileValidationError(
            "Unsupported file format. Only .kml and .zip Shapefile archives are supported."
        )


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def save_metadata(file_id: str, metadata: FileMetadata, settings: Settings) -> None:
    """Persist FileMetadata as JSON."""
    file_dir = _file_dir(settings, file_id)
    _write_json(
        file_dir / "metadata.json",
        {
            "id": metadata.id,
            "filename": metadata.filename,
            "feature_count": metadata.feature_count,
            "crs": metadata.crs,
            "status": metadata.status.value,
            "error": metadata.error,
        },
    )


def save_measurements(file_id: str, result: MeasurementResult, settings: Settings) -> None:
    """Persist MeasurementResult as JSON."""
    file_dir = _file_dir(settings, file_id)
    features_data = []
    for f in result.features:
        features_data.append(
            {
                "feature_id": f.feature_id,
                "geometry_type": f.geometry_type,
                "measurement_status": f.measurement_status.value,
                "area": f.area,
                "area_unit": f.area_unit,
                "length": f.length,
                "length_unit": f.length_unit,
            }
        )
    _write_json(
        file_dir / "measurements.json",
        {
            "file_id": result.file_id,
            "crs": result.crs,
            "measurement_crs": result.measurement_crs,
            "features": features_data,
        },
    )


def load_metadata(file_id: str, settings: Settings) -> FileMetadata:
    """Load FileMetadata from storage.

    Raises FileNotFoundError when the ID does not exist.
    """
    path = _file_dir(settings, file_id) / "metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"File with ID '{file_id}' not found.")
    data = _read_json(path)
    return FileMetadata(
        id=data["id"],
        filename=data["filename"],
        feature_count=data["feature_count"],
        crs=data.get("crs"),
        status=ProcessingStatus(data["status"]),
        error=data.get("error"),
    )


def load_measurements(file_id: str, settings: Settings) -> MeasurementResult:
    """Load MeasurementResult from storage.

    Raises FileNotFoundError when the ID does not exist.
    """
    path = _file_dir(settings, file_id) / "measurements.json"
    if not path.exists():
        raise FileNotFoundError(f"Measurements for file ID '{file_id}' not found.")
    data = _read_json(path)

    from app.models.file import FeatureMeasurementModel, MeasurementStatus

    features = [
        FeatureMeasurementModel(
            feature_id=f["feature_id"],
            geometry_type=f["geometry_type"],
            measurement_status=MeasurementStatus(f["measurement_status"]),
            area=f.get("area"),
            area_unit=f.get("area_unit"),
            length=f.get("length"),
            length_unit=f.get("length_unit"),
        )
        for f in data.get("features", [])
    ]
    return MeasurementResult(
        file_id=data["file_id"],
        crs=data.get("crs"),
        measurement_crs=data.get("measurement_crs"),
        features=features,
    )


# ---------------------------------------------------------------------------
# Processing pipeline
# ---------------------------------------------------------------------------


def _read_geospatial_file(
    file_path: Path,
    filename: str,
    settings: Settings,
) -> gpd.GeoDataFrame:
    """
    Read a KML or ZIP/Shapefile and return a GeoDataFrame.

    Temporary files created during ZIP extraction are cleaned up by the
    caller via a context manager.
    """
    ext = get_file_extension(filename)

    if ext == ".kml":
        return read_kml(file_path)

    if ext == ".zip":
        return _read_shapefile_from_zip(file_path, settings)

    raise FileValidationError(
        "Unsupported file format. Only .kml and .zip Shapefile archives are supported."
    )


def _read_shapefile_from_zip(zip_path: Path, settings: Settings) -> gpd.GeoDataFrame:
    """Extract a ZIP archive and read the enclosed Shapefile."""
    import zipfile as zipmod

    # Verify it is actually a ZIP before trying to extract
    if not zipmod.is_zipfile(zip_path):
        raise FileValidationError("The uploaded .zip file is not a valid ZIP archive.")

    with tempfile.TemporaryDirectory(prefix="geoapi_zip_") as tmp_dir:
        extract_dir = Path(tmp_dir)
        try:
            extract_zip_safely(
                zip_path,
                extract_dir,
                max_uncompressed_bytes=settings.max_uncompressed_size_bytes,
                max_entries=settings.max_zip_entries,
            )
        except ZipFileTooLargeError as exc:
            raise FileValidationError(str(exc), status_code=413) from exc
        except ValueError as exc:
            raise FileValidationError(str(exc)) from exc
        except zipmod.BadZipFile as exc:
            raise FileValidationError(f"Corrupt or invalid ZIP archive: {exc}") from exc

        shp_files = [
            path
            for path in extract_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".shp"
        ]
        if len(shp_files) > 1:
            raise FileValidationError("The ZIP archive must contain exactly one Shapefile.")
        shp_path = find_shapefile(extract_dir)
        if shp_path is None:
            raise FileValidationError("The ZIP archive does not contain a Shapefile (.shp).")

        missing = validate_shapefile_components(shp_path, settings.required_shapefile_extensions)
        if missing:
            raise FileValidationError(
                f"Incomplete Shapefile: missing required component(s): " f"{', '.join(missing)}."
            )

        return read_shapefile(shp_path)


def process_upload(
    filename: str,
    file_bytes: bytes,
    settings: Settings,
) -> tuple[FileMetadata, MeasurementResult]:
    """
    Full upload processing pipeline.

    Steps
    -----
    1. Validate (extension, size).
    2. Write to a temporary file.
    3. Read geospatial data.
    4. Detect CRS and extract features.
    5. Calculate measurements.
    6. Persist metadata + measurements.
    7. Clean up temp file.
    8. Return FileMetadata + MeasurementResult.

    Raises FileValidationError for client-side problems.
    Raises CRSError for missing/unsupported CRS.
    Other unexpected errors propagate as-is.
    """
    # Never persist or return an untrusted client path as the filename.
    filename = Path(filename.replace("\\", "/")).name
    file_size = len(file_bytes)
    validate_upload(filename, file_size, settings)

    file_id = str(uuid.uuid4())
    logger.info(
        "Processing upload: filename=%r, size=%d bytes, id=%s", filename, file_size, file_id
    )

    ext = get_file_extension(filename)

    # Write upload to temp file
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(file_bytes)

    try:
        gdf = _read_geospatial_file(tmp_path, filename, settings)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Build initial metadata
    source_crs = get_source_crs(gdf)
    crs_str = crs_to_string(source_crs)
    feature_count = len(gdf)

    logger.info(
        "File %s: %d features, CRS=%s",
        file_id,
        feature_count,
        crs_str,
    )

    # Calculate measurements — may raise CRSError
    measurement_result = calculate_measurements(file_id, gdf)

    # Persist
    metadata = FileMetadata(
        id=file_id,
        filename=filename,
        feature_count=feature_count,
        crs=crs_str,
        status=ProcessingStatus.COMPLETED,
    )
    save_metadata(file_id, metadata, settings)
    save_measurements(file_id, measurement_result, settings)

    logger.info("File %s processed and stored successfully.", file_id)
    return metadata, measurement_result
