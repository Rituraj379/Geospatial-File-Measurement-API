"""Tests for file upload endpoint: POST /api/files/"""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient


class TestValidKmlUpload:
    def test_valid_kml_upload_returns_201(self, client: TestClient, sample_kml_bytes):
        response = client.post(
            "/api/files/",
            files={
                "file": ("sample.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")
            },
        )
        assert response.status_code == 201

    def test_valid_kml_upload_response_fields(self, client: TestClient, sample_kml_bytes):
        response = client.post(
            "/api/files/",
            files={
                "file": ("sample.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")
            },
        )
        data = response.json()
        assert "id" in data
        assert data["filename"] == "sample.kml"
        assert data["status"] == "COMPLETED"
        assert isinstance(data["feature_count"], int)
        assert data["feature_count"] > 0

    def test_valid_kml_has_crs(self, client: TestClient, sample_kml_bytes):
        response = client.post(
            "/api/files/",
            files={
                "file": ("sample.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")
            },
        )
        data = response.json()
        assert data["crs"] is not None
        assert "4326" in data["crs"]  # KML is always EPSG:4326

    def test_kml_feature_count(self, client: TestClient, sample_kml_bytes):
        """sample.kml has 3 features: Polygon, LineString, Point."""
        response = client.post(
            "/api/files/",
            files={
                "file": ("sample.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")
            },
        )
        assert response.json()["feature_count"] == 3


class TestValidShapefileUpload:
    def test_valid_shapefile_upload_returns_201(
        self, client: TestClient, sample_shapefile_zip_bytes
    ):
        response = client.post(
            "/api/files/",
            files={"file": ("sample.zip", sample_shapefile_zip_bytes, "application/zip")},
        )
        assert response.status_code == 201

    def test_valid_shapefile_response_fields(self, client: TestClient, sample_shapefile_zip_bytes):
        response = client.post(
            "/api/files/",
            files={"file": ("polygons.zip", sample_shapefile_zip_bytes, "application/zip")},
        )
        data = response.json()
        assert "id" in data
        assert data["status"] == "COMPLETED"
        assert data["feature_count"] == 2  # sample_shapefile has 2 polygons

    def test_valid_shapefile_has_crs(self, client: TestClient, sample_shapefile_zip_bytes):
        response = client.post(
            "/api/files/",
            files={"file": ("polygons.zip", sample_shapefile_zip_bytes, "application/zip")},
        )
        data = response.json()
        assert data["crs"] is not None


class TestInvalidExtension:
    def test_txt_file_rejected(self, client: TestClient):
        response = client.post(
            "/api/files/",
            files={"file": ("data.txt", b"some text", "text/plain")},
        )
        assert response.status_code == 400
        assert "Unsupported file format" in response.json()["detail"]

    def test_geojson_rejected(self, client: TestClient):
        response = client.post(
            "/api/files/",
            files={"file": ("data.geojson", b"{}", "application/json")},
        )
        assert response.status_code == 400

    def test_pdf_rejected(self, client: TestClient):
        response = client.post(
            "/api/files/",
            files={"file": ("report.pdf", b"%PDF", "application/pdf")},
        )
        assert response.status_code == 400


class TestEmptyFile:
    def test_empty_kml_rejected(self, client: TestClient):
        response = client.post(
            "/api/files/",
            files={"file": ("empty.kml", b"", "application/vnd.google-earth.kml+xml")},
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_empty_zip_rejected(self, client: TestClient):
        response = client.post(
            "/api/files/",
            files={"file": ("empty.zip", b"", "application/zip")},
        )
        assert response.status_code == 400


class TestInvalidZip:
    def test_not_a_zip_file_rejected(self, client: TestClient):
        """A .zip extension but garbage bytes should be rejected."""
        response = client.post(
            "/api/files/",
            files={"file": ("fake.zip", b"not a zip file at all", "application/zip")},
        )
        assert response.status_code == 400

    def test_zip_without_shapefile_rejected(self, client: TestClient):
        """A valid ZIP but without any .shp inside."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "no shapefile here")
        response = client.post(
            "/api/files/",
            files={"file": ("no_shp.zip", buf.getvalue(), "application/zip")},
        )
        assert response.status_code == 400
        assert (
            "shp" in response.json()["detail"].lower()
            or "shapefile" in response.json()["detail"].lower()
        )

    def test_zip_path_traversal_rejected(self, client: TestClient):
        """A ZIP containing path-traversal entries should be rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../evil.sh", "rm -rf /")
        response = client.post(
            "/api/files/",
            files={"file": ("evil.zip", buf.getvalue(), "application/zip")},
        )
        assert response.status_code == 400


@pytest.mark.parametrize(
    "member_name",
    ["folder/evil.txt:stream", "CON.txt", "folder/trailing."],
)
def test_windows_unsafe_zip_paths_are_rejected(client: TestClient, member_name: str):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member_name, "unsafe")

    response = client.post(
        "/api/files/",
        files={"file": ("unsafe.zip", buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 400
    assert "unsafe path" in response.json()["detail"].lower()


def test_case_insensitive_duplicate_zip_paths_are_rejected(client: TestClient):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "one")
        archive.writestr("README.TXT", "two")

    response = client.post(
        "/api/files/",
        files={"file": ("duplicate.zip", buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 400
    assert "duplicate" in response.json()["detail"].lower()


def test_zip_expansion_limit_is_enforced(client: TestClient, test_settings):
    original_limit = test_settings.max_uncompressed_size_mb
    test_settings.max_uncompressed_size_mb = 1
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("large.txt", b"x" * (1024 * 1024 + 1))

        response = client.post(
            "/api/files/",
            files={"file": ("expanded.zip", buffer.getvalue(), "application/zip")},
        )
    finally:
        test_settings.max_uncompressed_size_mb = original_limit

    assert response.status_code == 413
    assert "expands" in response.json()["detail"].lower()


def test_zip_entry_count_limit_is_enforced(client: TestClient, test_settings):
    original_limit = test_settings.max_zip_entries
    test_settings.max_zip_entries = 1
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("one.txt", "one")
            archive.writestr("two.txt", "two")

        response = client.post(
            "/api/files/",
            files={"file": ("many-entries.zip", buffer.getvalue(), "application/zip")},
        )
    finally:
        test_settings.max_zip_entries = original_limit

    assert response.status_code == 400
    assert "too many entries" in response.json()["detail"].lower()


def test_upload_size_is_rejected_before_unbounded_read(client: TestClient, test_settings):
    original_limit = test_settings.max_file_size_mb
    test_settings.max_file_size_mb = 1
    try:
        response = client.post(
            "/api/files/",
            files={"file": ("too-large.kml", b"x" * (1024 * 1024 + 1), "application/xml")},
        )
    finally:
        test_settings.max_file_size_mb = original_limit

    assert response.status_code == 413


def test_zip_with_multiple_shapefiles_is_rejected(client: TestClient):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("one.shp", b"shape one")
        archive.writestr("two.shp", b"shape two")

    response = client.post(
        "/api/files/",
        files={"file": ("ambiguous.zip", buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 400
    assert "exactly one" in response.json()["detail"].lower()
