"""Measurement service: area and length calculations on projected geometries.

Flow
----
1. Receive the source GeoDataFrame (geographic or projected).
2. Determine an appropriate projected CRS via crs_service.
3. Reproject the GeoDataFrame.
4. Iterate features and calculate:
   - Polygon  → area  (m²)
   - LineString → length (m)
   - Point     → no measurement
   - Other     → UNSUPPORTED_GEOMETRY (does not crash the pipeline)

Important
---------
Measurements are NEVER performed on geographic coordinates.  All
geometry.area / geometry.length calls happen only after reprojection into
a metre-based CRS.
"""

import logging
import math

import geopandas as gpd

from app.models.file import (
    FeatureMeasurementModel,
    MeasurementResult,
    MeasurementStatus,
)
from app.services.crs_service import (
    CRSError,
    crs_to_string,
    get_measurement_crs,
    reproject_to_measurement_crs,
)

logger = logging.getLogger(__name__)

# Geometry types that produce metric measurements
_POLYGON_TYPES = {"Polygon", "MultiPolygon"}
_LINE_TYPES = {"LineString", "MultiLineString", "LinearRing"}
_POINT_TYPES = {"Point", "MultiPoint"}


def calculate_measurements(file_id: str, gdf: gpd.GeoDataFrame) -> MeasurementResult:
    """
    Calculate measurements for all features in *gdf*.

    Args:
        file_id: The unique ID of the processed file (used for the result object).
        gdf: Source GeoDataFrame (may be in any CRS).

    Returns:
        MeasurementResult containing per-feature measurements and the CRS
        strings used for source and measurement projections.

    Raises:
        CRSError: If the source CRS is missing (propagated to caller).
    """
    # Resolve source CRS string. A missing CRS remains a file-level error; the
    # service never guesses one, even when individual geometries need no metric.
    source_crs_str = crs_to_string(gdf.crs) if gdf.crs is not None else None
    if gdf.crs is None:
        get_measurement_crs(gdf)  # Raises the established CRSError for missing CRS.

    candidate_positions = [
        position
        for position, geom in enumerate(gdf.geometry)
        if geom is not None
        and not geom.is_empty
        and geom.geom_type in {"Polygon", "LineString"}
        and geom.is_valid
    ]
    measurement_crs = None
    if candidate_positions:
        # Ignore point and unsupported feature outliers when estimating a local
        # measurement CRS. A point far away should not distort polygon/line work.
        candidates = gdf.iloc[candidate_positions]
        try:
            measurement_crs = get_measurement_crs(candidates)
        except CRSError as exc:
            # Keep extracted features available when no single local projection
            # is suitable (for example, an antimeridian-crossing dataset).
            logger.warning("Could not select a measurement CRS for file %s: %s", file_id, exc)

    measurement_crs_str = crs_to_string(measurement_crs)

    feature_measurements: list[FeatureMeasurementModel] = []

    for position, (_, row) in enumerate(gdf.iterrows()):
        geom = row.geometry
        feature_id = position

        if geom is None or geom.is_empty:
            logger.warning("Feature %d has null/empty geometry; skipping measurement.", feature_id)
            feature_measurements.append(
                FeatureMeasurementModel(
                    feature_id=feature_id,
                    geometry_type=geom.geom_type if geom is not None else "Unknown",
                    measurement_status=MeasurementStatus.EMPTY_GEOMETRY,
                )
            )
            continue

        geom_type = geom.geom_type

        if geom_type == "Point":
            feature_measurements.append(
                FeatureMeasurementModel(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_status=MeasurementStatus.NO_MEASUREMENT,
                )
            )
            continue

        if geom_type not in {"Polygon", "LineString"}:
            feature_measurements.append(
                FeatureMeasurementModel(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_status=MeasurementStatus.UNSUPPORTED_GEOMETRY,
                )
            )
            continue

        if not geom.is_valid:
            feature_measurements.append(
                FeatureMeasurementModel(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_status=MeasurementStatus.INVALID_GEOMETRY,
                )
            )
            continue

        if measurement_crs is None:
            feature_measurements.append(
                FeatureMeasurementModel(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_status=MeasurementStatus.MEASUREMENT_FAILED,
                )
            )
            continue

        try:
            projected_gdf = reproject_to_measurement_crs(gdf.iloc[[position]], measurement_crs)
            projected_geometry = projected_gdf.geometry.iloc[0]
            if projected_geometry is None or not projected_geometry.is_valid:
                raise ValueError("Projected geometry is invalid")
            measurement = _measure_geometry(feature_id, geom_type, projected_geometry)
        except Exception as exc:
            logger.error("Measurement failed for feature %d (%s): %s", feature_id, geom_type, exc)
            measurement = FeatureMeasurementModel(
                feature_id=feature_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.MEASUREMENT_FAILED,
            )

        feature_measurements.append(measurement)

    logger.info(
        "Completed measurements for file %s: %d features, source CRS=%s, measurement CRS=%s",
        file_id,
        len(feature_measurements),
        source_crs_str,
        measurement_crs_str,
    )

    return MeasurementResult(
        file_id=file_id,
        crs=source_crs_str,
        measurement_crs=measurement_crs_str,
        features=feature_measurements,
    )


def _measure_geometry(
    feature_id: int,
    geom_type: str,
    geom,
) -> FeatureMeasurementModel:
    """
    Measure a single geometry.

    Returns a FeatureMeasurementModel with the appropriate measurement or
    UNSUPPORTED_GEOMETRY status.
    """
    if geom_type == "Polygon":
        area = geom.area
        if not math.isfinite(area):
            raise ValueError("Area measurement is not finite")
        logger.debug("Feature %d (Polygon): area=%.4f m²", feature_id, area)
        return FeatureMeasurementModel(
            feature_id=feature_id,
            geometry_type=geom_type,
            measurement_status=MeasurementStatus.MEASURED,
            area=round(area, 4),
            area_unit="m²",
        )

    if geom_type == "LineString":
        length = geom.length
        if not math.isfinite(length):
            raise ValueError("Length measurement is not finite")
        logger.debug("Feature %d (LineString): length=%.4f m", feature_id, length)
        return FeatureMeasurementModel(
            feature_id=feature_id,
            geometry_type=geom_type,
            measurement_status=MeasurementStatus.MEASURED,
            length=round(length, 4),
            length_unit="m",
        )

    if geom_type == "Point":
        logger.debug("Feature %d (Point): no measurement required.", feature_id)
        return FeatureMeasurementModel(
            feature_id=feature_id,
            geometry_type=geom_type,
            measurement_status=MeasurementStatus.NO_MEASUREMENT,
        )

    # MultiPolygon, MultiLineString, GeometryCollection, etc.
    logger.info(
        "Feature %d has unsupported geometry type '%s'; returning UNSUPPORTED_GEOMETRY.",
        feature_id,
        geom_type,
    )
    return FeatureMeasurementModel(
        feature_id=feature_id,
        geometry_type=geom_type,
        measurement_status=MeasurementStatus.UNSUPPORTED_GEOMETRY,
    )
