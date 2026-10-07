"""Geospatial file reading and feature extraction service.

Responsibilities
----------------
- Read KML files via GeoPandas / Fiona.
- Read Shapefiles from an extracted ZIP directory.
- Serialize geometries to GeoJSON-compatible dicts.
- Return a list of FeatureModel objects plus a raw GeoDataFrame for further
  processing.
"""

import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from app.models.file import FeatureModel

logger = logging.getLogger(__name__)


class GeospatialReadError(Exception):
    """Raised when a geospatial file cannot be read or parsed."""


def _geometry_to_geojson(geom: BaseGeometry | None) -> dict[str, Any]:
    """Convert a Shapely geometry to a GeoJSON-compatible dict."""
    if geom is None or geom.is_empty:
        return {"type": "null", "coordinates": []}
    from shapely.geometry import mapping
    return dict(mapping(geom))


def _safe_properties(row_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a GeoDataFrame row dict to a JSON-serialisable properties dict.

    Drops the geometry key and coerces non-serialisable values to strings.
    """
    props: dict[str, Any] = {}
    for key, value in row_dict.items():
        if key == "geometry":
            continue
        if value is None or isinstance(value, (str, int, float, bool)):
            props[key] = value
        else:
            props[key] = str(value)
    return props


def read_kml(kml_path: Path) -> gpd.GeoDataFrame:
    """
    Read a KML file into a GeoDataFrame.

    GeoPandas/Fiona uses the 'KML' driver.  Some KML files contain multiple
    layers; we merge all of them.

    Args:
        kml_path: Absolute path to the .kml file.

    Returns:
        A GeoDataFrame with all features from the file.

    Raises:
        GeospatialReadError: If the file cannot be read.
    """
    try:
        import fiona

        layers = fiona.listlayers(str(kml_path))
        logger.debug("KML layers found: %s", layers)

        frames: list[gpd.GeoDataFrame] = []
        for layer in layers:
            try:
                gdf = gpd.read_file(str(kml_path), driver="KML", layer=layer)
                if not gdf.empty:
                    frames.append(gdf)
            except Exception as layer_exc:
                logger.warning("Skipping KML layer %r: %s", layer, layer_exc)

        if not frames:
            raise GeospatialReadError("KML file contains no readable features.")

        combined = gpd.GeoDataFrame(
            gpd.pd.concat(frames, ignore_index=True),
            crs=frames[0].crs,
        )
        logger.info("Read %d features from KML: %s", len(combined), kml_path.name)
        return combined

    except GeospatialReadError:
        raise
    except Exception as exc:
        raise GeospatialReadError(f"Failed to read KML file: {exc}") from exc


def read_shapefile(shp_path: Path) -> gpd.GeoDataFrame:
    """
    Read a Shapefile into a GeoDataFrame.

    Args:
        shp_path: Absolute path to the .shp file.

    Returns:
        A GeoDataFrame with all features.

    Raises:
        GeospatialReadError: If the file cannot be read.
    """
    try:
        gdf = gpd.read_file(str(shp_path))
        logger.info("Read %d features from Shapefile: %s", len(gdf), shp_path.name)
        return gdf
    except Exception as exc:
        raise GeospatialReadError(f"Failed to read Shapefile: {exc}") from exc


def extract_features(gdf: gpd.GeoDataFrame) -> list[FeatureModel]:
    """
    Convert a GeoDataFrame into a list of FeatureModel objects.

    Each feature captures its index, geometry type, GeoJSON geometry,
    CRS, and non-geometry properties.

    Args:
        gdf: Input GeoDataFrame (source CRS, before reprojection).

    Returns:
        Ordered list of FeatureModel instances.
    """
    crs_str: str | None = None
    if gdf.crs is not None:
        from pyproj import CRS as ProjCRS

        from app.services.crs_service import crs_to_string
        crs_str = crs_to_string(ProjCRS(gdf.crs))

    features: list[FeatureModel] = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        row_dict = row.to_dict()

        feature = FeatureModel(
            feature_id=int(idx),  # type: ignore[arg-type]
            geometry_type=geom.geom_type if geom is not None else "Unknown",
            geometry=_geometry_to_geojson(geom),
            crs=crs_str,
            properties=_safe_properties(row_dict),
        )
        features.append(feature)

    logger.debug("Extracted %d features from GeoDataFrame.", len(features))
    return features
