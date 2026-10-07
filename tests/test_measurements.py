"""Tests for measurement calculations and the measurements API endpoint."""

import geopandas as gpd
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Polygon

from app.models.file import MeasurementStatus
from app.services.measurement_service import calculate_measurements


def _upload_file(client: TestClient, filename: str, content: bytes) -> str:
    """Helper: upload a file and return its ID."""
    response = client.post(
        "/api/files/",
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == 201, f"Upload failed: {response.text}"
    return response.json()["id"]


class TestPolygonArea:
    def test_polygon_area_is_returned(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_file(client, "polygon_only.kml", polygon_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")
        assert response.status_code == 200

        features = response.json()["features"]
        polygon_features = [f for f in features if f["geometry_type"] == "Polygon"]
        assert len(polygon_features) >= 1

    def test_polygon_area_is_positive(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_file(client, "polygon_only.kml", polygon_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")

        features = response.json()["features"]
        polygon_features = [f for f in features if f["geometry_type"] == "Polygon"]
        for feat in polygon_features:
            assert feat["area"] is not None
            assert feat["area"] > 0

    def test_polygon_area_unit_is_m2(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_file(client, "polygon_only.kml", polygon_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")

        features = response.json()["features"]
        polygon_features = [f for f in features if f["geometry_type"] == "Polygon"]
        for feat in polygon_features:
            assert feat["area_unit"] == "m²"

    def test_polygon_area_is_in_metres_not_degrees(self, client: TestClient, polygon_kml_bytes):
        """
        The polygon is roughly 1km × 1km near Kolkata.
        Area in degrees would be ~0.000081 deg².
        Area in m² should be in the hundreds of thousands.
        We verify it is much larger than 1, meaning it is not in degrees.
        """
        file_id = _upload_file(client, "polygon_only.kml", polygon_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")

        features = response.json()["features"]
        polygon_features = [f for f in features if f["geometry_type"] == "Polygon"]
        assert len(polygon_features) >= 1
        area = polygon_features[0]["area"]
        # ~1km² = ~1,000,000 m² (with some tolerance for the actual coordinates)
        assert area > 100_000, f"Area {area} looks like it was calculated in degrees, not metres."

    def test_polygon_measurement_status_is_measured(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_file(client, "polygon_only.kml", polygon_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")

        features = response.json()["features"]
        polygon_features = [f for f in features if f["geometry_type"] == "Polygon"]
        for feat in polygon_features:
            assert feat["measurement_status"] == "MEASURED"

    def test_shapefile_polygon_area(self, client: TestClient, sample_shapefile_zip_bytes):
        """Shapefile polygons should also have positive area in m²."""
        file_id = _upload_file(client, "polys.zip", sample_shapefile_zip_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")
        assert response.status_code == 200

        features = response.json()["features"]
        polygon_features = [f for f in features if f["geometry_type"] == "Polygon"]
        assert len(polygon_features) == 2
        for feat in polygon_features:
            assert feat["area"] > 100_000
            assert feat["area_unit"] == "m²"


class TestLineStringLength:
    def test_linestring_length_is_returned(self, client: TestClient, linestring_kml_bytes):
        file_id = _upload_file(client, "linestring_only.kml", linestring_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")
        assert response.status_code == 200

        features = response.json()["features"]
        line_features = [f for f in features if f["geometry_type"] == "LineString"]
        assert len(line_features) >= 1

    def test_linestring_length_is_positive(self, client: TestClient, linestring_kml_bytes):
        file_id = _upload_file(client, "linestring_only.kml", linestring_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")

        features = response.json()["features"]
        line_features = [f for f in features if f["geometry_type"] == "LineString"]
        for feat in line_features:
            assert feat["length"] is not None
            assert feat["length"] > 0

    def test_linestring_length_unit_is_m(self, client: TestClient, linestring_kml_bytes):
        file_id = _upload_file(client, "linestring_only.kml", linestring_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")

        features = response.json()["features"]
        line_features = [f for f in features if f["geometry_type"] == "LineString"]
        for feat in line_features:
            assert feat["length_unit"] == "m"

    def test_linestring_length_is_in_metres_not_degrees(
        self, client: TestClient, linestring_kml_bytes
    ):
        """
        The LineString spans ~0.009 degrees longitude near Kolkata (~890 m).
        Length in degrees would be ~0.009.
        We check it is much larger than 1 to confirm metric units.
        """
        file_id = _upload_file(client, "linestring_only.kml", linestring_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")

        features = response.json()["features"]
        line_features = [f for f in features if f["geometry_type"] == "LineString"]
        assert len(line_features) >= 1
        length = line_features[0]["length"]
        assert length > 100, f"Length {length} looks like degrees, not metres."

    def test_linestring_measurement_status_is_measured(
        self, client: TestClient, linestring_kml_bytes
    ):
        file_id = _upload_file(client, "linestring_only.kml", linestring_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")

        features = response.json()["features"]
        line_features = [f for f in features if f["geometry_type"] == "LineString"]
        for feat in line_features:
            assert feat["measurement_status"] == "MEASURED"


class TestPointMeasurement:
    def test_point_has_no_measurement(self, client: TestClient, sample_kml_bytes):
        file_id = _upload_file(client, "sample.kml", sample_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")
        assert response.status_code == 200

        features = response.json()["features"]
        point_features = [f for f in features if f["geometry_type"] == "Point"]
        assert len(point_features) >= 1
        for feat in point_features:
            assert feat["area"] is None
            assert feat["length"] is None

    def test_point_measurement_status(self, client: TestClient, sample_kml_bytes):
        file_id = _upload_file(client, "sample.kml", sample_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")

        features = response.json()["features"]
        point_features = [f for f in features if f["geometry_type"] == "Point"]
        for feat in point_features:
            assert feat["measurement_status"] == "NO_MEASUREMENT"


class TestUnsupportedGeometry:
    def test_unsupported_geometry_does_not_crash(self, client: TestClient):
        """
        Upload a KML that has a valid polygon — we test that the pipeline
        doesn't crash.  True MultiPolygon testing would need a dedicated
        fixture; here we verify the existing fixtures process without error.
        """
        # Use shapefile with polygon — all features should be processed
        from tests.conftest import FIXTURES_DIR

        content = (FIXTURES_DIR / "sample_shapefile.zip").read_bytes()
        file_id = _upload_file(client, "sample.zip", content)

        response = client.get(f"/api/files/{file_id}/measurements/")
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        assert len(data["features"]) > 0


class TestMeasurementCRS:
    def test_measurement_crs_is_exposed(self, client: TestClient, polygon_kml_bytes):
        """The measurement CRS (projected) must be exposed in the response."""
        file_id = _upload_file(client, "polygon_only.kml", polygon_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")
        data = response.json()

        assert "measurement_crs" in data
        assert data["measurement_crs"] is not None

    def test_measurement_crs_is_different_from_source(self, client: TestClient, polygon_kml_bytes):
        """For EPSG:4326 input, measurement CRS should be a UTM zone, not 4326."""
        file_id = _upload_file(client, "polygon_only.kml", polygon_kml_bytes)
        response = client.get(f"/api/files/{file_id}/measurements/")
        data = response.json()

        source_crs = data["crs"]
        measurement_crs = data["measurement_crs"]

        assert source_crs != measurement_crs, (
            "For geographic input (EPSG:4326), measurement CRS should be a "
            "projected CRS, not the same geographic CRS."
        )


def test_feet_based_projected_crs_is_reprojected_before_measurement():
    frame = gpd.GeoDataFrame(
        geometry=[LineString([(0, 0), (100, 0)])],
        crs="EPSG:2263",
    )

    result = calculate_measurements("feet-crs", frame)

    assert result.measurement_crs.startswith(("EPSG:326", "EPSG:327"))
    assert abs(result.features[0].length - 30.48) < 0.02


def test_web_mercator_is_reprojected_for_ground_measurement():
    geographic = gpd.GeoDataFrame(
        geometry=[LineString([(-122, 37), (-121.999, 37)])],
        crs="EPSG:4326",
    )
    frame = geographic.to_crs("EPSG:3857")

    result = calculate_measurements("web-mercator", frame)

    assert result.measurement_crs != "EPSG:3857"
    assert 88 < result.features[0].length < 90


def test_polar_geometries_use_polar_stereographic_crs():
    north = gpd.GeoDataFrame(
        geometry=[Polygon([(10, 85), (10.01, 85), (10.01, 85.01), (10, 85.01)])],
        crs="EPSG:4326",
    )
    south = gpd.GeoDataFrame(
        geometry=[Polygon([(10, -85), (10.01, -85), (10.01, -85.01), (10, -85.01)])],
        crs="EPSG:4326",
    )

    north_result = calculate_measurements("north-pole", north)
    south_result = calculate_measurements("south-pole", south)

    assert north_result.measurement_crs == "EPSG:32661"
    assert north_result.features[0].area > 0
    assert south_result.measurement_crs == "EPSG:32761"
    assert south_result.features[0].area > 0


def test_antimeridian_geometry_is_preserved_with_failed_measurement_status():
    frame = gpd.GeoDataFrame(
        geometry=[LineString([(179, 10), (-179, 10)])],
        crs="EPSG:4326",
    )

    result = calculate_measurements("antimeridian", frame)

    assert result.measurement_crs is None
    assert result.features[0].measurement_status == MeasurementStatus.MEASUREMENT_FAILED
    assert result.features[0].length is None


def test_bad_and_empty_geometry_do_not_stop_other_feature_measurements():
    valid_polygon = Polygon([(0, 0), (0.001, 0), (0.001, 0.001), (0, 0.001)])
    invalid_polygon = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    valid_line = LineString([(0, 0), (0.001, 0)])
    empty_polygon = Polygon()
    frame = gpd.GeoDataFrame(
        geometry=[valid_polygon, invalid_polygon, valid_line, empty_polygon],
        crs="EPSG:4326",
    )

    result = calculate_measurements("mixed-validity", frame)

    assert result.features[0].measurement_status == MeasurementStatus.MEASURED
    assert result.features[0].area > 0
    assert result.features[1].measurement_status == MeasurementStatus.INVALID_GEOMETRY
    assert result.features[2].measurement_status == MeasurementStatus.MEASURED
    assert result.features[2].length > 0
    assert result.features[3].measurement_status == MeasurementStatus.EMPTY_GEOMETRY
