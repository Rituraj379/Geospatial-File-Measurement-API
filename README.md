# Geospatial File Measurement API

## Setup

Requires Python 3.11 or later. In VS Code, open this project folder, then run these commands in a PowerShell terminal:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The `.env` file is optional. It can configure `MAX_FILE_SIZE_MB`, `MAX_UNCOMPRESSED_SIZE_MB`, `MAX_ZIP_ENTRIES`, and `DATA_DIR`. Defaults are 50 MB per upload, 200 MB extracted per ZIP, and 10,000 ZIP entries.

Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive API docs. Run the tests with `python -m pytest -q`.

## API

Uploads use multipart form data with the field name `file`. Supported inputs are `.kml` files and `.zip` archives containing exactly one Shapefile with its `.shp`, `.shx`, and `.dbf` components. A source CRS is required.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/files/` | Upload and process a KML or Shapefile ZIP |
| `GET` | `/api/files/{id}/` | Read file metadata |
| `GET` | `/api/files/{id}/measurements/` | Read feature measurements |

### Example requests

```powershell
curl.exe http://localhost:8000/health
curl.exe -F "file=@tests/fixtures/polygon_only.kml" http://localhost:8000/api/files/
$fileId = "<id returned by the upload request>"
curl.exe "http://localhost:8000/api/files/$fileId/"
curl.exe "http://localhost:8000/api/files/$fileId/measurements/"
```

### Example responses

Health check:

```json
{"status": "ok"}
```

Upload and file information:

```json
{
  "id": "f4d7c1e2-3a1b-4e5f-9c2d-8b7a6e5d4c3b",
  "filename": "polygon_only.kml",
  "feature_count": 1,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

Measurements:

```json
{
  "file_id": "f4d7c1e2-3a1b-4e5f-9c2d-8b7a6e5d4c3b",
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32610",
  "features": [
    {
      "feature_id": 0,
      "geometry_type": "Polygon",
      "measurement_status": "MEASURED",
      "area": 12345.6789,
      "area_unit": "m²",
      "length": null,
      "length_unit": null
    }
  ]
}
```

Polygons return area in square meters; LineStrings return length in meters. Points have status `NO_MEASUREMENT`. Unsupported, empty, invalid, or unmeasurable features receive a per-feature status so other features can still be processed. Invalid file requests return a JSON `detail` message; missing IDs return 404, oversized uploads or ZIP expansions return 413, and missing CRS returns 422.

## Architecture

### Application structure

```text
app/
  api/files.py            HTTP routes
  core/config.py          Environment-based settings
  models/file.py          Internal data models and statuses
  schemas/file.py         API response models
  services/
    file_service.py       Validation, processing orchestration, JSON storage
    geospatial_service.py GeoPandas readers and feature extraction
    crs_service.py        CRS selection and reprojection
    measurement_service.py Per-feature area and length calculation
  utils/file_utils.py     Safe ZIP extraction and Shapefile validation
data/<id>/                Stored metadata.json and measurements.json
tests/                    API, upload, measurement, and CRS tests
```

### File-processing flow

The API reads the upload within its configured size limit and passes it to the file service. The service validates the extension and content. KML is read with GeoPandas; ZIP entries are checked for unsafe paths, duplicate names, excessive expansion, and excessive entry counts before extraction. The archive must contain one complete Shapefile. Temporary files are cleaned up after processing, and metadata and measurements are saved under `data/<id>/`.

### Measurement calculation flow

The service identifies valid Polygon and LineString features, selects a measurement CRS, and reprojects each measurable feature before using Shapely's `area` or `length`. Results use square meters and meters. Points need no measurement; unsupported, invalid, empty, and failed features are marked individually.

### CRS handling

The source CRS is required and is never guessed. A projected CRS with meter units is retained except EPSG:3857 (Web Mercator), which is reprojected because its scale distortion makes its coordinates unsuitable for ground measurements. Geographic and non-metric projected data are transformed to WGS 84 to select a local UTM CRS. Data wholly in polar regions use UPS. For datasets crossing the antimeridian or spanning UTM and polar regions, measurements are marked failed rather than returning a misleading value. The source and selected measurement CRS are returned by the measurements endpoint.

## Design Decisions

- **GeoPandas, Shapely, and PyProj:** Use established geospatial readers, geometry operations, and coordinate transformations instead of implementing file parsing or projections manually.
- **Local JSON storage:** Keep the initial service easy to run without a database. PostgreSQL/PostGIS or object storage would suit larger, shared deployments.
- **Bounded synchronous processing:** Keep this version simple for small uploads. A background queue such as Celery or RQ would be a better fit for long-running jobs.
- **Local CRS selection:** UTM and UPS provide suitable local metric coordinates for supported datasets. A single automatic projection is deliberately not chosen for antimeridian-crossing or UTM/polar-spanning data.
- **Safe ZIP extraction:** Validate archive paths and resource limits before writing entries, instead of relying on unrestricted extraction.

## Learning

This project applies FastAPI routing and response schemas, GeoPandas file ingestion, Shapely geometry validation, and PyProj CRS transformations. It also practices secure upload handling, per-feature error isolation, local persistence, and automated API and geospatial testing.

## Future Scope

Possible extensions include PostgreSQL/PostGIS or S3 storage, background processing, authentication, additional geospatial formats, measurement support for multipart geometries, pagination, rate limiting, monitoring, and cloud deployment.
