"""CRS detection, selection, and reprojection service.

This module is responsible for:
- Detecting whether the source CRS is geographic or projected.
- Selecting an appropriate projected CRS for accurate metric measurements.
- Reprojecting a GeoDataFrame into the selected CRS.

Key design decision
-------------------
Geographic coordinate systems (e.g. EPSG:4326) express coordinates in
degrees of latitude/longitude.  Calculating geometry.area or geometry.length
on degree-based coordinates yields results in *degrees²* or *degrees*, which
are meaningless for real-world area/length measurements.

We therefore always reproject to a suitable *projected* CRS (metre-based)
before performing any measurement.  The preferred strategy is to call
``gdf.estimate_utm_crs()`` which selects the best UTM zone for the dataset's
bounding box.
"""

import logging
import math

import geopandas as gpd
from pyproj import CRS

logger = logging.getLogger(__name__)


class CRSError(Exception):
    """Raised when CRS cannot be determined or is unsuitable."""


def get_source_crs(gdf: gpd.GeoDataFrame) -> CRS | None:
    """Return the source CRS of a GeoDataFrame, or None if undefined."""
    if gdf.crs is None:
        return None
    return CRS(gdf.crs)


def is_geographic(crs: CRS) -> bool:
    """Return True when *crs* is a geographic (lat/lon degree-based) CRS."""
    return crs.is_geographic


def get_measurement_crs(gdf: gpd.GeoDataFrame) -> CRS:
    """
    Determine the most appropriate projected CRS for metric measurements.

    Metric projected CRSs are retained except Web Mercator, whose scale
    distortion makes its coordinates unsuitable for ground measurements.
    Other inputs are transformed to WGS 84 to select a local UTM or polar CRS.
    Datasets crossing the antimeridian or spanning UTM and polar regions are
    rejected because one automatic local projection would be misleading.

    Returns
    -------
    pyproj.CRS
        A projected, metre-based CRS suitable for area/length measurements.

    Raises
    ------
    CRSError
        When the GeoDataFrame has no CRS.
    """
    source_crs = get_source_crs(gdf)

    if source_crs is None:
        raise CRSError(
            "Input file does not contain CRS information. "
            "Cannot determine a measurement CRS without a known source CRS."
        )

    logger.debug("Source CRS: %s (geographic=%s)", source_crs.to_epsg(), source_crs.is_geographic)

    if source_crs.is_projected:
        # Use conversion factors instead of unit names to handle equivalent units.
        axis_info = source_crs.axis_info[:2]
        uses_metres = len(axis_info) == 2 and all(
            axis.unit_conversion_factor is not None
            and math.isclose(
                axis.unit_conversion_factor,
                1.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            for axis in axis_info
        )
        if uses_metres and source_crs.to_epsg() != 3857:
            logger.info("Source CRS %s is already metric; using it for measurement.", source_crs)
            return source_crs

    # Geographic, Web Mercator, or non-metric projected input.
    try:
        geographic_gdf = gdf if source_crs.is_geographic else gdf.to_crs("EPSG:4326")
        west, south, east, north = geographic_gdf.total_bounds
    except Exception as exc:
        raise CRSError(f"Failed to transform dataset bounds to EPSG:4326: {exc}") from exc

    if not all(math.isfinite(value) for value in (west, south, east, north)):
        raise CRSError("Dataset has empty or invalid geographic bounds.")
    if east - west > 180:
        raise CRSError(
            "Dataset crosses the antimeridian; split it before calculating measurements."
        )

    if south >= 84:
        return CRS.from_epsg(32661)  # WGS 84 / UPS North
    if north <= -80:
        return CRS.from_epsg(32761)  # WGS 84 / UPS South
    if south < -80 or north > 84:
        raise CRSError(
            "Dataset spans UTM and polar regions; split it before calculating measurements."
        )

    try:
        estimated_crs = geographic_gdf.estimate_utm_crs()
    except Exception as exc:
        raise CRSError(f"Failed to estimate a suitable UTM CRS: {exc}") from exc
    if estimated_crs is None:
        raise CRSError("Could not determine a suitable projected measurement CRS.")
    utm_crs = CRS.from_user_input(estimated_crs)

    logger.info(
        "Estimated measurement CRS %s from source CRS %s",
        utm_crs.to_string(),
        source_crs.to_string(),
    )
    return utm_crs


def reproject_to_measurement_crs(
    gdf: gpd.GeoDataFrame,
    measurement_crs: CRS,
) -> gpd.GeoDataFrame:
    """
    Reproject *gdf* to *measurement_crs*.

    Returns a new GeoDataFrame; the original is not modified.

    Raises
    ------
    CRSError
        When reprojection fails.
    """
    try:
        reprojected = gdf.to_crs(measurement_crs)
        logger.debug(
            "Reprojected GeoDataFrame from %s to %s",
            gdf.crs,
            measurement_crs.to_epsg(),
        )
        return reprojected
    except Exception as exc:
        raise CRSError(f"Reprojection failed: {exc}") from exc


def crs_to_string(crs: CRS | None) -> str | None:
    """Convert a CRS object to a human-readable EPSG string, or None."""
    if crs is None:
        return None
    epsg = crs.to_epsg()
    if epsg:
        return f"EPSG:{epsg}"
    # Fall back to the authority string if EPSG is not available
    return crs.to_string()
