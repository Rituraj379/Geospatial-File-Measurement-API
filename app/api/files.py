"""API routes for file upload, retrieval, and measurements.

All routes are thin: validation and business logic live in the service layer.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.core.config import Settings, get_settings
from app.schemas.file import (
    FeatureMeasurement,
    FileResponse,
    MeasurementResponse,
)
from app.services.crs_service import CRSError
from app.services.file_service import (
    FileNotFoundError,
    FileValidationError,
    load_measurements,
    load_metadata,
    process_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["Files"])


# ---------------------------------------------------------------------------
# POST /api/files/
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=FileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a geospatial file",
    description=(
        "Accept a `.kml` or `.zip` (ESRI Shapefile) file, extract geospatial "
        "features, detect the CRS, reproject to a suitable projected CRS, and "
        "calculate measurements (area for Polygons, length for LineStrings). "
        "Returns the file ID and processing status."
    ),
)
async def upload_file(
    file: UploadFile,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> FileResponse:
    """Upload a KML or Shapefile ZIP and trigger processing."""

    if file.filename is None or file.filename == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided.",
        )

    filename: str = file.filename

    try:
        # Read at most one byte beyond the configured cap so oversized bodies
        # are rejected before an unbounded amount of data is kept in memory.
        file_bytes = await file.read(settings.max_file_size_bytes + 1)
        metadata, _ = process_upload(filename, file_bytes, settings)
    except FileValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc
    except CRSError as exc:
        logger.error("CRS error processing %r: %s", filename, exc)
        raise HTTPException(
            status_code=422,
            detail=f"CRS error: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error processing upload %r", filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the file.",
        ) from exc
    finally:
        await file.close()

    return FileResponse(
        id=metadata.id,
        filename=metadata.filename,
        feature_count=metadata.feature_count,
        crs=metadata.crs,
        status=metadata.status.value,
    )


# ---------------------------------------------------------------------------
# GET /api/files/{id}/
# ---------------------------------------------------------------------------


@router.get(
    "/{file_id}/",
    response_model=FileResponse,
    summary="Retrieve file processing information",
    description="Return metadata for a previously uploaded file by its unique ID.",
)
def get_file(
    file_id: str,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> FileResponse:
    """Return stored metadata for a file."""
    try:
        metadata = load_metadata(file_id, settings)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error loading metadata for file %r", file_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve file information.",
        ) from exc

    return FileResponse(
        id=metadata.id,
        filename=metadata.filename,
        feature_count=metadata.feature_count,
        crs=metadata.crs,
        status=metadata.status.value,
    )


# ---------------------------------------------------------------------------
# GET /api/files/{id}/measurements/
# ---------------------------------------------------------------------------


@router.get(
    "/{file_id}/measurements/",
    response_model=MeasurementResponse,
    summary="Retrieve geospatial measurements for a file",
    description=(
        "Return per-feature measurement results for a processed file. "
        "Includes area (m²) for Polygons, length (m) for LineStrings, "
        "and the projected CRS used for calculations."
    ),
)
def get_measurements(
    file_id: str,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> MeasurementResponse:
    """Return stored measurement results for a file."""
    # Verify the file exists first
    try:
        load_metadata(file_id, settings)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    try:
        result = load_measurements(file_id, settings)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error loading measurements for file %r", file_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve measurements.",
        ) from exc

    features = [
        FeatureMeasurement(
            feature_id=f.feature_id,
            geometry_type=f.geometry_type,
            measurement_status=f.measurement_status.value,
            area=f.area,
            area_unit=f.area_unit,
            length=f.length,
            length_unit=f.length_unit,
        )
        for f in result.features
    ]

    return MeasurementResponse(
        file_id=result.file_id,
        crs=result.crs,
        measurement_crs=result.measurement_crs,
        features=features,
    )
