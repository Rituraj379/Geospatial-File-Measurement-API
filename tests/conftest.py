"""Shared pytest fixtures."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Settings override — use a temporary data directory for each test session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def temp_data_dir(tmp_path_factory):
    """Session-scoped temporary data directory."""
    return tmp_path_factory.mktemp("data")


@pytest.fixture(scope="session")
def test_settings(temp_data_dir):
    """Override settings to use the temp data directory."""
    return Settings(data_dir=str(temp_data_dir))


@pytest.fixture(scope="session")
def client(test_settings):
    """FastAPI TestClient with overridden settings."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Fixture file helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sample_kml_bytes():
    return (FIXTURES_DIR / "sample.kml").read_bytes()


@pytest.fixture(scope="session")
def polygon_kml_bytes():
    return (FIXTURES_DIR / "polygon_only.kml").read_bytes()


@pytest.fixture(scope="session")
def linestring_kml_bytes():
    return (FIXTURES_DIR / "linestring_only.kml").read_bytes()


@pytest.fixture(scope="session")
def sample_shapefile_zip_bytes():
    return (FIXTURES_DIR / "sample_shapefile.zip").read_bytes()


@pytest.fixture(scope="session")
def linestring_shapefile_zip_bytes():
    return (FIXTURES_DIR / "linestring_shapefile.zip").read_bytes()


@pytest.fixture(scope="session")
def point_shapefile_zip_bytes():
    return (FIXTURES_DIR / "point_shapefile.zip").read_bytes()


@pytest.fixture(scope="session")
def no_crs_zip_bytes():
    return (FIXTURES_DIR / "no_crs_shapefile.zip").read_bytes()
