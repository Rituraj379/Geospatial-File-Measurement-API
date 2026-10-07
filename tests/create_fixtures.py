"""
Script to generate test fixture files programmatically.

Run once to produce:
  tests/fixtures/sample_shapefile.zip      — Shapefile with Polygon features (EPSG:4326)
  tests/fixtures/linestring_shapefile.zip  — Shapefile with LineString features (EPSG:4326)
  tests/fixtures/point_shapefile.zip       — Shapefile with Point features (EPSG:4326)
  tests/fixtures/no_crs_shapefile.zip      — Shapefile without CRS (.prj removed)
  tests/fixtures/polygon_only.kml          — Single polygon KML (known geometry)
  tests/fixtures/linestring_only.kml       — Single LineString KML (known geometry)

Execute:
    python tests/create_fixtures.py
"""

import sys
import tempfile
import zipfile
from pathlib import Path

# Ensure project root is on the path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402

FIXTURES_DIR = ROOT / "tests" / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_zip_from_dir(shapefile_dir: Path, zip_path: Path) -> None:
    """Package all files in shapefile_dir into zip_path."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(shapefile_dir.iterdir()):
            zf.write(f, arcname=f.name)
    print(f"  Created {zip_path.name} ({zip_path.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# Fixture 1: sample_shapefile.zip — Polygon features in EPSG:4326
# ---------------------------------------------------------------------------


def create_sample_shapefile_zip() -> None:
    """Shapefile containing two Polygon features."""
    geometries = [
        Polygon([
            (88.3639, 22.5726),
            (88.3729, 22.5726),
            (88.3729, 22.5816),
            (88.3639, 22.5816),
            (88.3639, 22.5726),
        ]),
        Polygon([
            (88.3750, 22.5726),
            (88.3840, 22.5726),
            (88.3840, 22.5816),
            (88.3750, 22.5816),
            (88.3750, 22.5726),
        ]),
    ]
    names = ["Polygon A", "Polygon B"]
    gdf = gpd.GeoDataFrame({"name": names, "geometry": geometries}, crs="EPSG:4326")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        gdf.to_file(str(tmp_path / "sample.shp"), driver="ESRI Shapefile")
        _make_zip_from_dir(tmp_path, FIXTURES_DIR / "sample_shapefile.zip")


# ---------------------------------------------------------------------------
# Fixture 2: linestring_shapefile.zip — LineString features in EPSG:4326
# ---------------------------------------------------------------------------


def create_linestring_shapefile_zip() -> None:
    """Shapefile containing one LineString feature."""
    geometries = [
        LineString([(88.3639, 22.5726), (88.3729, 22.5726)]),
    ]
    gdf = gpd.GeoDataFrame({"name": ["Line A"], "geometry": geometries}, crs="EPSG:4326")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        gdf.to_file(str(tmp_path / "linestring.shp"), driver="ESRI Shapefile")
        _make_zip_from_dir(tmp_path, FIXTURES_DIR / "linestring_shapefile.zip")


# ---------------------------------------------------------------------------
# Fixture 3: point_shapefile.zip — Point features in EPSG:4326
# ---------------------------------------------------------------------------


def create_point_shapefile_zip() -> None:
    """Shapefile containing one Point feature."""
    geometries = [Point(88.3639, 22.5726)]
    gdf = gpd.GeoDataFrame({"name": ["Point A"], "geometry": geometries}, crs="EPSG:4326")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        gdf.to_file(str(tmp_path / "point.shp"), driver="ESRI Shapefile")
        _make_zip_from_dir(tmp_path, FIXTURES_DIR / "point_shapefile.zip")


# ---------------------------------------------------------------------------
# Fixture 4: no_crs_shapefile.zip — Shapefile without .prj (no CRS)
# ---------------------------------------------------------------------------


def create_no_crs_shapefile_zip() -> None:
    """Polygon shapefile with the .prj file removed."""
    geometries = [Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])]
    gdf = gpd.GeoDataFrame({"name": ["Box"], "geometry": geometries}, crs="EPSG:4326")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        gdf.to_file(str(tmp_path / "no_crs.shp"), driver="ESRI Shapefile")

        # Remove the .prj file to simulate a Shapefile without CRS information
        prj_path = tmp_path / "no_crs.prj"
        if prj_path.exists():
            prj_path.unlink()

        _make_zip_from_dir(tmp_path, FIXTURES_DIR / "no_crs_shapefile.zip")


# ---------------------------------------------------------------------------
# Fixture 5: polygon_only.kml — One known polygon
# ---------------------------------------------------------------------------


def create_polygon_only_kml() -> None:
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Polygon Only</name>
    <Placemark>
      <name>Known Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              88.3639,22.5726,0
              88.3729,22.5726,0
              88.3729,22.5816,0
              88.3639,22.5816,0
              88.3639,22.5726,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""
    out = FIXTURES_DIR / "polygon_only.kml"
    out.write_text(kml_content, encoding="utf-8")
    print(f"  Created {out.name}")


# ---------------------------------------------------------------------------
# Fixture 6: linestring_only.kml — One known LineString
# ---------------------------------------------------------------------------


def create_linestring_only_kml() -> None:
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>LineString Only</name>
    <Placemark>
      <name>Known LineString</name>
      <LineString>
        <coordinates>
          88.3639,22.5726,0
          88.3729,22.5726,0
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""
    out = FIXTURES_DIR / "linestring_only.kml"
    out.write_text(kml_content, encoding="utf-8")
    print(f"  Created {out.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("Creating test fixtures...")
    create_sample_shapefile_zip()
    create_linestring_shapefile_zip()
    create_point_shapefile_zip()
    create_no_crs_shapefile_zip()
    create_polygon_only_kml()
    create_linestring_only_kml()
    print("Done.")
