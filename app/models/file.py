"""Internal domain models for file processing."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProcessingStatus(StrEnum):
    """Possible states for a processed file."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MeasurementStatus(StrEnum):
    """Status of an individual feature measurement."""

    MEASURED = "MEASURED"
    NO_MEASUREMENT = "NO_MEASUREMENT"
    UNSUPPORTED_GEOMETRY = "UNSUPPORTED_GEOMETRY"
    EMPTY_GEOMETRY = "EMPTY_GEOMETRY"
    INVALID_GEOMETRY = "INVALID_GEOMETRY"
    MEASUREMENT_FAILED = "MEASUREMENT_FAILED"
    FAILED = "FAILED"


@dataclass
class FeatureModel:
    """Internal representation of a single geospatial feature."""

    feature_id: int
    geometry_type: str
    geometry: dict[str, Any]  # GeoJSON-compatible geometry dict
    crs: str | None
    properties: dict[str, Any]


@dataclass
class FeatureMeasurementModel:
    """Measurement result for a single feature."""

    feature_id: int
    geometry_type: str
    measurement_status: MeasurementStatus
    area: float | None = None
    area_unit: str | None = None
    length: float | None = None
    length_unit: str | None = None


@dataclass
class FileMetadata:
    """Metadata stored after a file is processed."""

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: ProcessingStatus
    error: str | None = None


@dataclass
class MeasurementResult:
    """Complete measurement result for a processed file."""

    file_id: str
    crs: str | None
    measurement_crs: str | None
    features: list[FeatureMeasurementModel] = field(default_factory=list)
