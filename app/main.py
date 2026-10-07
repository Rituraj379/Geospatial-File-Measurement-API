"""FastAPI application entry point.

Creates the application, registers routers, configures logging, and
exposes the /health endpoint.
"""

import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.files import router as files_router
from app.core.config import get_settings
from app.schemas.file import HealthResponse

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

LOGGING_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
    "loggers": {
        "app": {
            "level": "DEBUG",
            "handlers": ["console"],
            "propagate": False,
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Initialise resources on startup and clean up on shutdown."""
    settings = get_settings()
    # Ensure the data directory exists
    settings.data_path.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Starting %s (env=%s, data_dir=%s)",
        settings.app_name,
        settings.environment,
        settings.data_path,
    )
    yield
    logger.info("Shutting down %s.", settings.app_name)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "A production-quality backend service for uploading and processing "
            "geospatial files (.kml, .zip/Shapefile). Calculates polygon area and "
            "LineString length with proper CRS transformation."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Register routers
    app.include_router(files_router)

    # ---------------------------------------------------------------------------
    # Global exception handlers
    # ---------------------------------------------------------------------------

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler — never exposes stack traces to clients."""
        logger.exception("Unhandled exception for %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal server error occurred."},
        )

    # ---------------------------------------------------------------------------
    # Health endpoint
    # ---------------------------------------------------------------------------

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Health check",
        description="Returns a simple status object confirming the service is running.",
    )
    def health_check() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
