"""Pydantic schemas for API request/response serialization."""

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# File schemas
# ---------------------------------------------------------------------------


class FileResponse(BaseModel):
    """Response returned after uploading and processing a file."""

    id: str = Field(..., description="Unique file identifier (UUID)")
    filename: str = Field(..., description="Original uploaded filename")
    feature_count: int = Field(..., description="Number of geospatial features extracted")
    crs: str | None = Field(None, description="Coordinate Reference System of the source file")
    status: str = Field(..., description="Processing status: PROCESSING | COMPLETED | FAILED")

    model_config = {"from_attributes": True}


class FileErrorResponse(BaseModel):
    """Response returned when file processing fails."""

    id: str
    filename: str
    status: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Feature schemas
# ---------------------------------------------------------------------------


class FeatureResponse(BaseModel):
    """Full feature representation including geometry and attributes."""

    feature_id: int = Field(..., description="Zero-based index of the feature")
    geometry_type: str = Field(..., description="Shapely geometry type (e.g. Polygon, LineString)")
    geometry: dict[str, Any] = Field(..., description="GeoJSON-compatible geometry object")
    crs: str | None = Field(None, description="CRS of the feature")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Feature attributes/properties"
    )


# ---------------------------------------------------------------------------
# Measurement schemas
# ---------------------------------------------------------------------------


class FeatureMeasurement(BaseModel):
    """Measurement result for a single feature."""

    feature_id: int = Field(..., description="Zero-based feature index")
    geometry_type: str = Field(..., description="Geometry type")
    measurement_status: str = Field(
        ...,
        description=(
            "MEASURED | NO_MEASUREMENT | UNSUPPORTED_GEOMETRY | EMPTY_GEOMETRY | "
            "INVALID_GEOMETRY | MEASUREMENT_FAILED"
        ),
    )
    area: float | None = Field(None, description="Area in square meters (Polygon only)")
    area_unit: str | None = Field(None, description="Unit for area (m²)")
    length: float | None = Field(None, description="Length in meters (LineString only)")
    length_unit: str | None = Field(None, description="Unit for length (m)")


class MeasurementResponse(BaseModel):
    """Full measurement response for a processed file."""

    file_id: str = Field(..., description="File identifier")
    crs: str | None = Field(None, description="Source CRS of the file")
    measurement_crs: str | None = Field(
        None,
        description="Projected CRS used for measurement calculations",
    )
    features: list[FeatureMeasurement] = Field(
        default_factory=list,
        description="Per-feature measurement results",
    )


# ---------------------------------------------------------------------------
# Health schema
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
