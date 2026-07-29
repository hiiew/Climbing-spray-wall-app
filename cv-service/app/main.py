"""
main.py — FastAPI application entry point for the CV Microservice.

Startup sequence:
  1. Load YOLO v8 model weights into memory (blocks until complete).
  2. Register model with hold_detector module.
  3. Start serving HTTP requests.

All routes return JSON with a consistent envelope matching the Laravel backend
error contract defined in WORKFLOW.md §10.4.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.hold_detector import detect_holds, set_yolo_model
from app.schemas import (
    DetectHoldsRequest,
    DetectHoldsResponse,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (from environment variables)
# ---------------------------------------------------------------------------

YOLO_WEIGHTS_PATH   = os.getenv("YOLO_WEIGHTS_PATH",   "models/yolov8m-holds.pt")
DETECTION_TIMEOUT_S = int(os.getenv("DETECTION_TIMEOUT_S", "120"))
CORS_ORIGINS        = os.getenv("CORS_ORIGINS", "*").split(",")
APP_ENV             = os.getenv("APP_ENV", "production")

_startup_time: float = 0.0


# ---------------------------------------------------------------------------
# App lifespan — model loading
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the YOLO model once at startup and release on shutdown."""
    global _startup_time
    _startup_time = time.monotonic()

    logger.info("Loading YOLO model from: %s", YOLO_WEIGHTS_PATH)
    try:
        from ultralytics import YOLO  # Import here to keep startup explicit
        model = YOLO(YOLO_WEIGHTS_PATH)
        set_yolo_model(model)
        logger.info("YOLO model loaded successfully.")
    except Exception as exc:
        logger.critical("Failed to load YOLO model: %s", exc)
        # Do not raise — allow the app to start in degraded mode so /health
        # returns a meaningful response rather than crashing the container.

    yield  # Application is running

    logger.info("Shutting down CV microservice.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title       = "Climbing Spray Wall — CV Microservice",
    description = (
        "Computer vision microservice for detecting climbing holds in spray wall "
        "images and generating routes. Consumed exclusively by the Laravel backend."
    ),
    version     = "1.0.0",
    docs_url    = "/docs" if APP_ENV != "production" else None,
    redoc_url   = "/redoc" if APP_ENV != "production" else None,
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins   = CORS_ORIGINS,
    allow_methods   = ["POST", "GET"],
    allow_headers   = ["*"],
)


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s", request.url)
    return JSONResponse(
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
        content     = ErrorResponse(
            status = "error",
            error  = ErrorDetail(
                code    = ErrorCode.INTERNAL_ERROR,
                message = "An unexpected error occurred.",
                details = {"exception": str(exc)},
            ),
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Background callback helper
# ---------------------------------------------------------------------------

async def _post_callback(callback_url: str, payload: dict) -> None:
    """POST detection results to the Laravel backend webhook URL."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(callback_url, json=payload)
            logger.info(
                "Callback to %s returned HTTP %d.", callback_url, response.status_code
            )
    except Exception as exc:
        logger.error("Callback to %s failed: %s", callback_url, exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    response_model = HealthResponse,
    summary        = "Health check — returns model load status.",
    tags           = ["Ops"],
)
async def health_check() -> HealthResponse:
    from app.hold_detector import _yolo_model
    return HealthResponse(
        status          = "ok" if _yolo_model else "degraded",
        model_loaded    = _yolo_model is not None,
        model_version   = "yolov8m-holds-v2.1",
        uptime_seconds  = round(time.monotonic() - _startup_time, 1),
    )


@app.post(
    "/detect-holds",
    response_model  = DetectHoldsResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "Detect climbing holds in a spray wall image.",
    tags            = ["Detection"],
    responses       = {
        200: {"description": "Holds detected successfully."},
        400: {"description": "Image quality issue or no holds found.", "model": ErrorResponse},
        422: {"description": "Validation error in request payload."},
        503: {"description": "Model not loaded or service unavailable.", "model": ErrorResponse},
        504: {"description": "Detection timed out.", "model": ErrorResponse},
    },
)
async def detect_holds_endpoint(
    request:          DetectHoldsRequest,
    background_tasks: BackgroundTasks,
) -> DetectHoldsResponse | JSONResponse:
    """
    Primary endpoint consumed by the Laravel `HoldDetectionService`.

    If `callback_url` is provided, the HTTP response is returned immediately
    with `status: "processing"` and the results are POSTed to `callback_url`
    when detection completes (asynchronous mode).

    If `callback_url` is absent, detection runs synchronously within the request
    and the full result is returned in the response body.
    """
    from app.hold_detector import _yolo_model

    # Guard: model must be loaded
    if _yolo_model is None:
        return JSONResponse(
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
            content     = ErrorResponse(
                wall_id = request.wall_id,
                error   = ErrorDetail(
                    code    = ErrorCode.MODEL_LOAD_FAILED,
                    message = "YOLO model is not loaded. Service is in degraded mode.",
                ),
            ).model_dump(),
        )

    async def _run_detection() -> DetectHoldsResponse:
        """Inner coroutine — runs detection with a timeout guard."""
        try:
            return await asyncio.wait_for(
                detect_holds(
                    wall_id   = request.wall_id,
                    image_url = str(request.image_url),
                    mode      = request.mode,
                    options   = request.options,
                ),
                timeout = DETECTION_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code = status.HTTP_504_GATEWAY_TIMEOUT,
                detail      = ErrorResponse(
                    wall_id = request.wall_id,
                    error   = ErrorDetail(
                        code    = ErrorCode.DETECTION_TIMEOUT,
                        message = (
                            f"Detection did not complete within {DETECTION_TIMEOUT_S}s. "
                            "Try again with a smaller image or FAST mode."
                        ),
                    ),
                ).model_dump(),
            )
        except ValueError as exc:
            error_str = str(exc)

            code_map = {
                "NO_HOLDS_DETECTED":    (ErrorCode.NO_HOLDS_DETECTED,    "No climbing holds were detected. Please upload a clearer photo of your spray wall."),
                "Image too small":      (ErrorCode.IMAGE_TOO_SMALL,       error_str),
                "Image appears blurry": (ErrorCode.IMAGE_QUALITY_LOW,     error_str),
                "Failed to download":   (ErrorCode.IMAGE_DOWNLOAD_FAILED, error_str),
            }

            matched_code    = ErrorCode.INTERNAL_ERROR
            matched_message = error_str
            for key, (code, msg) in code_map.items():
                if key in error_str:
                    matched_code    = code
                    matched_message = msg
                    break

            raise HTTPException(
                status_code = status.HTTP_400_BAD_REQUEST,
                detail      = ErrorResponse(
                    wall_id = request.wall_id,
                    error   = ErrorDetail(
                        code    = matched_code,
                        message = matched_message,
                    ),
                ).model_dump(),
            )

    # ── Async callback mode ──────────────────────────────────────────────────
    if request.callback_url:
        async def _detect_and_callback():
            try:
                result = await _run_detection()
                await _post_callback(str(request.callback_url), result.model_dump())
            except HTTPException as http_exc:
                await _post_callback(str(request.callback_url), http_exc.detail)

        background_tasks.add_task(_detect_and_callback)
        return JSONResponse(
            status_code = status.HTTP_202_ACCEPTED,
            content     = {
                "wall_id": request.wall_id,
                "status":  "processing",
                "message": "Detection started. Results will be sent to callback_url.",
            },
        )

    # ── Synchronous mode ────────────────────────────────────────────────────
    return await _run_detection()
