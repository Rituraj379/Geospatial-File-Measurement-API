"""Tests for API endpoints: GET /api/files/{id}/, GET /api/files/{id}/measurements/, GET /health."""

from fastapi.testclient import TestClient


def _upload_kml(client: TestClient, content: bytes, filename: str = "sample.kml") -> str:
    """Upload KML and return file ID."""
    response = client.post(
        "/api/files/",
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == 201
    return response.json()["id"]


class TestHealth:
    def test_health_returns_200(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_body(self, client: TestClient):
        response = client.get("/health")
        assert response.json() == {"status": "ok"}


class TestGetFile:
    def test_get_file_returns_correct_data(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_kml(client, polygon_kml_bytes, "polygon_only.kml")

        response = client.get(f"/api/files/{file_id}/")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == file_id
        assert data["filename"] == "polygon_only.kml"
        assert data["status"] == "COMPLETED"

    def test_get_file_has_all_required_fields(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_kml(client, polygon_kml_bytes, "polygon_only.kml")

        response = client.get(f"/api/files/{file_id}/")
        data = response.json()

        required_fields = ["id", "filename", "feature_count", "crs", "status"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_get_file_feature_count(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_kml(client, polygon_kml_bytes, "polygon_only.kml")
        response = client.get(f"/api/files/{file_id}/")
        assert response.json()["feature_count"] == 1


class TestFileNotFound:
    def test_get_nonexistent_file_returns_404(self, client: TestClient):
        response = client.get("/api/files/nonexistent-id-12345/")
        assert response.status_code == 404

    def test_get_nonexistent_measurements_returns_404(self, client: TestClient):
        response = client.get("/api/files/nonexistent-id-12345/measurements/")
        assert response.status_code == 404

    def test_404_has_detail_field(self, client: TestClient):
        response = client.get("/api/files/does-not-exist/")
        assert "detail" in response.json()


class TestGetMeasurements:
    def test_measurements_endpoint_returns_200(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_kml(client, polygon_kml_bytes, "polygon_only.kml")
        response = client.get(f"/api/files/{file_id}/measurements/")
        assert response.status_code == 200

    def test_measurements_response_structure(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_kml(client, polygon_kml_bytes, "polygon_only.kml")
        response = client.get(f"/api/files/{file_id}/measurements/")
        data = response.json()

        assert "file_id" in data
        assert "crs" in data
        assert "measurement_crs" in data
        assert "features" in data
        assert isinstance(data["features"], list)

    def test_measurements_file_id_matches(self, client: TestClient, polygon_kml_bytes):
        file_id = _upload_kml(client, polygon_kml_bytes, "polygon_only.kml")
        response = client.get(f"/api/files/{file_id}/measurements/")
        assert response.json()["file_id"] == file_id

    def test_feature_measurement_fields(self, client: TestClient, sample_kml_bytes):
        """Each feature must have the required measurement fields."""
        file_id = _upload_kml(client, sample_kml_bytes, "sample.kml")
        response = client.get(f"/api/files/{file_id}/measurements/")
        features = response.json()["features"]

        for feat in features:
            assert "feature_id" in feat
            assert "geometry_type" in feat
            assert "measurement_status" in feat

    def test_all_three_geometry_types_present(self, client: TestClient, sample_kml_bytes):
        """sample.kml has Polygon, LineString, and Point."""
        file_id = _upload_kml(client, sample_kml_bytes, "sample.kml")
        response = client.get(f"/api/files/{file_id}/measurements/")
        features = response.json()["features"]

        geom_types = {f["geometry_type"] for f in features}
        assert "Polygon" in geom_types
        assert "LineString" in geom_types
        assert "Point" in geom_types


class TestDocsEndpoints:
    def test_openapi_docs_available(self, client: TestClient):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_available(self, client: TestClient):
        response = client.get("/redoc")
        assert response.status_code == 200

    def test_openapi_schema_available(self, client: TestClient):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
