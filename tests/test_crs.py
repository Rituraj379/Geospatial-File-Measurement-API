"""Tests for CRS detection, reprojection, and error handling."""

import geopandas as gpd
import pytest
from pyproj import CRS
from shapely.geometry import Point

from app.services.crs_service import (
    CRSError,
    crs_to_string,
    get_measurement_crs,
    get_source_crs,
    is_geographic,
    reproject_to_measurement_crs,
)

# ---------------------------------------------------------------------------
# Unit tests: CRS detection
# ---------------------------------------------------------------------------


class TestGetSourceCrs:
    def test_epsg4326_detected(self):
        gdf = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:4326")
        crs = get_source_crs(gdf)
        assert crs is not None
        assert crs.to_epsg() == 4326

    def test_no_crs_returns_none(self):
        gdf = gpd.GeoDataFrame({"geometry": [Point(0, 0)]})
        crs = get_source_crs(gdf)
        assert crs is None

    def test_projected_crs_detected(self):
        gdf = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:32643")
        crs = get_source_crs(gdf)
        assert crs is not None
        assert crs.to_epsg() == 32643


class TestIsGeographic:
    def test_epsg4326_is_geographic(self):
        crs = CRS("EPSG:4326")
        assert is_geographic(crs) is True

    def test_utm_is_not_geographic(self):
        crs = CRS("EPSG:32643")
        assert is_geographic(crs) is False

    def test_web_mercator_is_not_geographic(self):
        crs = CRS("EPSG:3857")
        assert is_geographic(crs) is False


class TestCrsToString:
    def test_epsg4326_string(self):
        crs = CRS("EPSG:4326")
        assert crs_to_string(crs) == "EPSG:4326"

    def test_epsg32643_string(self):
        crs = CRS("EPSG:32643")
        assert crs_to_string(crs) == "EPSG:32643"

    def test_none_returns_none(self):
        assert crs_to_string(None) is None


# ---------------------------------------------------------------------------
# Unit tests: measurement CRS selection
# ---------------------------------------------------------------------------


class TestGetMeasurementCrs:
    def test_epsg4326_returns_utm_crs(self):
        """Geographic input → UTM CRS should be returned."""
        gdf = gpd.GeoDataFrame(
            {"geometry": [Point(88.36, 22.57)]},
            crs="EPSG:4326",
        )
        measurement_crs = get_measurement_crs(gdf)
        assert not measurement_crs.is_geographic, "Measurement CRS must be projected."

    def test_no_crs_raises_crs_error(self):
        """Missing CRS must raise CRSError, not silently assume one."""
        gdf = gpd.GeoDataFrame({"geometry": [Point(0, 0)]})
        with pytest.raises(CRSError):
            get_measurement_crs(gdf)

    def test_projected_crs_returned_as_is(self):
        """Already-projected metric CRS should be returned directly."""
        # UTM zone 45N in metres — should pass through
        gdf = gpd.GeoDataFrame(
            {"geometry": [Point(500000, 2500000)]},
            crs="EPSG:32645",
        )
        measurement_crs = get_measurement_crs(gdf)
        assert not measurement_crs.is_geographic

    def test_measurement_crs_uses_estimate_utm(self):
        """For EPSG:4326 data near Kolkata, UTM zone 45N (EPSG:32645) or similar is expected."""
        gdf = gpd.GeoDataFrame(
            {"geometry": [Point(88.36, 22.57)]},
            crs="EPSG:4326",
        )
        measurement_crs = get_measurement_crs(gdf)
        epsg = measurement_crs.to_epsg()
        # Valid UTM zones for ~88°E: 45N (32645) or 46N (32646)
        assert epsg in (32645, 32646), f"Unexpected UTM zone: EPSG:{epsg}"


# ---------------------------------------------------------------------------
# Unit tests: reprojection
# ---------------------------------------------------------------------------


class TestReprojectToMeasurementCrs:
    def test_reprojection_changes_coordinates(self):
        """After reprojection, coordinates should change from degrees to metres."""
        gdf = gpd.GeoDataFrame(
            {"geometry": [Point(88.36, 22.57)]},
            crs="EPSG:4326",
        )
        measurement_crs = get_measurement_crs(gdf)
        reprojected = reproject_to_measurement_crs(gdf, measurement_crs)

        original_x = gdf.geometry.iloc[0].x
        reprojected_x = reprojected.geometry.iloc[0].x

        assert abs(original_x - reprojected_x) > 1, (
            "Coordinates should have changed significantly after reprojection."
        )

    def test_reprojection_preserves_feature_count(self):
        """Row count must be identical before and after reprojection."""
        gdf = gpd.GeoDataFrame(
            {"geometry": [Point(88.36, 22.57), Point(88.37, 22.58)]},
            crs="EPSG:4326",
        )
        measurement_crs = get_measurement_crs(gdf)
        reprojected = reproject_to_measurement_crs(gdf, measurement_crs)
        assert len(reprojected) == len(gdf)


# ---------------------------------------------------------------------------
# Integration tests: CRS via API
# ---------------------------------------------------------------------------


class TestEpsg4326ReprojectionViaApi:
    def test_geographic_input_produces_projected_measurement_crs(
        self, client, polygon_kml_bytes
    ):
        """KML is always EPSG:4326; the measurement CRS must be projected."""
        response = client.post(
            "/api/files/",
            files={"file": ("polygon_only.kml", polygon_kml_bytes, "application/octet-stream")},
        )
        assert response.status_code == 201
        file_id = response.json()["id"]

        meas_response = client.get(f"/api/files/{file_id}/measurements/")
        data = meas_response.json()

        # Source CRS must be geographic
        assert data["crs"] is not None
        assert "4326" in data["crs"]

        # Measurement CRS must be projected (not 4326)
        assert data["measurement_crs"] is not None
        assert "4326" not in data["measurement_crs"]


class TestMissingCrs:
    def test_missing_crs_returns_error(self, client, no_crs_zip_bytes):
        """Shapefile without .prj should be rejected with an appropriate error."""
        response = client.post(
            "/api/files/",
            files={"file": ("no_crs.zip", no_crs_zip_bytes, "application/zip")},
        )
        # Should fail with 422 (CRS error) or 400
        assert response.status_code in (400, 422)
        detail = response.json()["detail"].lower()
        assert "crs" in detail or "coordinate" in detail or "projection" in detail
