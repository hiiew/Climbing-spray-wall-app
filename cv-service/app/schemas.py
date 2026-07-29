"""
schemas.py — Pydantic request/response models for the CV Microservice.

All coordinate values (x, y, width, height) are normalised to [0.0, 1.0]
relative to the original image dimensions, making them resolution-independent.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class HoldType(str, Enum):
    JUG        = "jug"
    CRIMP      = "crimp"
    SLOPER     = "sloper"
    PINCH      = "pinch"
    POCKET     = "pocket"
    FOOTHOLD   = "foothold"
    VOLUME     = "volume"
    UNKNOWN    = "unknown"


class HoldColor(str, Enum):
    RED     = "red"
    ORANGE  = "orange"
    YELLOW  = "yellow"
    GREEN   = "green"
    BLUE    = "blue"
    PURPLE  = "purple"
    PINK    = "pink"
    BLACK   = "black"
    WHITE   = "white"
    GREY    = "grey"
    UNKNOWN = "unknown"


class DetectionMode(str, Enum):
    FAST     = "fast"     # YOLO only — lower latency, slightly less accurate
    ACCURATE = "accurate" # YOLO + SAM — higher latency, precise segmentation


class ErrorCode(str, Enum):
    IMAGE_DOWNLOAD_FAILED  = "IMAGE_DOWNLOAD_FAILED"
    IMAGE_TOO_SMALL        = "IMAGE_TOO_SMALL"
    IMAGE_QUALITY_LOW      = "IMAGE_QUALITY_LOW"
    NO_HOLDS_DETECTED      = "NO_HOLDS_DETECTED"
    DETECTION_TIMEOUT      = "DETECTION_TIMEOUT"
    MODEL_LOAD_FAILED      = "MODEL_LOAD_FAILED"
    INTERNAL_ERROR         = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class DetectHoldsRequest(BaseModel):
    """Payload sent by the Laravel backend to trigger hold detection."""

    wall_id: str = Field(
        ...,
        description="ULID of the wall record in Laravel's database.",
        example="01HZ9K2M5QR3V4X6Y8Z0A1B2C3",
    )
    image_url: HttpUrl = Field(
        ...,
        description="Pre-signed S3 URL or public URL of the uploaded wall image.",
        example="https://s3.amazonaws.com/spraywall/walls/01HZ9K.jpg",
    )
    mode: DetectionMode = Field(
        default=DetectionMode.FAST,
        description="Detection accuracy/speed trade-off.",
    )
    callback_url: Optional[HttpUrl] = Field(
        default=None,
        description=(
            "Optional Laravel webhook URL. If provided, the service POSTs results "
            "back asynchronously instead of returning them in the HTTP response."
        ),
    )
    options: DetectionOptions = Field(
        default_factory=lambda: DetectionOptions(),
        description="Fine-tuned detection parameters.",
    )


class DetectionOptions(BaseModel):
    """Optional tuning knobs for the detection pipeline."""

    confidence_threshold: float = Field(
        default=0.45,
        ge=0.1,
        le=0.95,
        description="Minimum YOLO confidence score to accept a detection.",
    )
    iou_threshold: float = Field(
        default=0.40,
        ge=0.1,
        le=0.95,
        description="IoU threshold for NMS (Non-Maximum Suppression).",
    )
    min_hold_area: float = Field(
        default=0.0005,
        ge=0.0001,
        description=(
            "Minimum hold area as a fraction of total image area. "
            "Filters out tiny noise detections."
        ),
    )
    classify_types: bool = Field(
        default=True,
        description="Whether to run hold-type classification (jug/crimp/sloper…).",
    )
    enhance_contrast: bool = Field(
        default=True,
        description="Apply CLAHE contrast enhancement before inference.",
    )


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class DetectedHold(BaseModel):
    """A single detected hold with normalised coordinates and metadata."""

    id: str = Field(
        ...,
        description="Deterministic hold ID: '{wall_id}_hold_{index:04d}'",
        example="01HZ9K_hold_0001",
    )
    x: float = Field(..., ge=0.0, le=1.0, description="Left edge (normalised).")
    y: float = Field(..., ge=0.0, le=1.0, description="Top edge (normalised).")
    width: float = Field(..., ge=0.0, le=1.0, description="Bounding box width (normalised).")
    height: float = Field(..., ge=0.0, le=1.0, description="Bounding box height (normalised).")
    center_x: float = Field(..., ge=0.0, le=1.0, description="Centroid X (normalised).")
    center_y: float = Field(..., ge=0.0, le=1.0, description="Centroid Y (normalised).")
    area: float = Field(..., description="Bounding box area as fraction of image area.")
    color: HoldColor = Field(..., description="Dominant colour of the hold.")
    color_hex: str = Field(..., description="Hex colour for frontend rendering.", example="#3B82F6")
    type: HoldType = Field(..., description="Hold shape classification.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="YOLO detection confidence.")
    type_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Hold-type classification confidence (null if classify_types=False).",
    )
    is_verified: bool = Field(
        default=True,
        description=(
            "False if confidence_score < 0.50 — frontend should prompt "
            "user to manually confirm this hold."
        ),
    )


class DetectionMetadata(BaseModel):
    """Runtime statistics for the detection job."""

    model_version: str          = Field(..., example="yolov8m-holds-v2.1")
    processing_time_ms: int     = Field(..., description="Total inference time in milliseconds.")
    image_width_px: int         = Field(..., description="Original image width in pixels.")
    image_height_px: int        = Field(..., description="Original image height in pixels.")
    mode: DetectionMode
    holds_detected: int
    holds_verified: int         = Field(..., description="Holds with confidence ≥ 0.50.")
    holds_unverified: int       = Field(..., description="Holds with confidence < 0.50.")


class DetectHoldsResponse(BaseModel):
    """Successful hold detection response."""

    wall_id: str
    status: str = Field(default="success")
    holds: list[DetectedHold]
    metadata: DetectionMetadata


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Standardised error response matching the Laravel error envelope."""

    wall_id: Optional[str] = None
    status: str = Field(default="error")
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str
    uptime_seconds: float
