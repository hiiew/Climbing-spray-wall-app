"""
hold_detector.py — Core hold detection pipeline.

Orchestrates the full detection flow:
  1. Preprocessing (download, validate, enhance, resize)
  2. YOLO v8 inference (bounding box detection)
  3. Optional SAM segmentation (accurate mode)
  4. Post-processing (NMS, coordinate normalisation, de-duplication)
  5. Hold-type classification
  6. Colour classification per hold
  7. Construction of DetectedHold response objects

Architecture note:
  The YOLO model is loaded once at application startup (via the lifespan event
  in main.py) and injected into this module to avoid per-request model loading
  overhead. SAM is loaded lazily on first accurate-mode request.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

import cv2
import numpy as np

from app.color_classifier import classify_hold_color
from app.preprocessor import PreprocessedImage, preprocess
from app.schemas import (
    DetectedHold,
    DetectionMetadata,
    DetectionMode,
    DetectionOptions,
    DetectHoldsResponse,
    HoldColor,
    HoldType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level model handles (set by main.py lifespan)
# ---------------------------------------------------------------------------

_yolo_model  = None   # ultralytics.YOLO instance
_sam_model   = None   # segment_anything.SamPredictor instance (lazy)

MODEL_VERSION = "yolov8m-holds-v2.1"   # Update when model weights are replaced


def set_yolo_model(model) -> None:
    """Called by main.py after loading the YOLO weights at startup."""
    global _yolo_model
    _yolo_model = model
    logger.info("YOLO model registered in hold_detector. Version: %s", MODEL_VERSION)


def get_yolo_model():
    if _yolo_model is None:
        raise RuntimeError("YOLO model not loaded. Call set_yolo_model() at startup.")
    return _yolo_model


# ---------------------------------------------------------------------------
# Hold-type classification heuristic
# ---------------------------------------------------------------------------

# Maps YOLO class index → HoldType (update when retraining with more classes)
_YOLO_CLASS_TO_HOLD_TYPE: dict[int, HoldType] = {
    0: HoldType.JUG,
    1: HoldType.CRIMP,
    2: HoldType.SLOPER,
    3: HoldType.PINCH,
    4: HoldType.POCKET,
    5: HoldType.FOOTHOLD,
    6: HoldType.VOLUME,
}


def _classify_hold_type_heuristic(
    width_norm: float,
    height_norm: float,
    aspect_ratio: float,
    yolo_class: Optional[int],
    yolo_class_conf: Optional[float],
    classify_types: bool,
) -> tuple[HoldType, Optional[float]]:
    """
    Two-tier hold type classification:

    Tier 1 (preferred): If YOLO was trained with multi-class hold detection,
        use the predicted class directly.

    Tier 2 (fallback): Geometry-based heuristic using normalised bounding box
        size and aspect ratio. This acts as a reasonable default when using a
        single-class "hold" detector.

    Returns:
        Tuple of (HoldType, confidence or None).
    """
    # Tier 1: model-predicted class
    if classify_types and yolo_class is not None and yolo_class in _YOLO_CLASS_TO_HOLD_TYPE:
        return _YOLO_CLASS_TO_HOLD_TYPE[yolo_class], yolo_class_conf

    if not classify_types:
        return HoldType.UNKNOWN, None

    # Tier 2: geometry heuristic
    area = width_norm * height_norm

    if area > 0.015:
        return HoldType.VOLUME, 0.60
    if aspect_ratio > 3.5:
        return HoldType.CRIMP, 0.55
    if aspect_ratio < 0.6:
        return HoldType.POCKET, 0.55
    if area > 0.004:
        return HoldType.JUG, 0.60
    if area < 0.001:
        return HoldType.FOOTHOLD, 0.55

    return HoldType.SLOPER, 0.50


# ---------------------------------------------------------------------------
# YOLO inference
# ---------------------------------------------------------------------------

def _run_yolo(
    image: np.ndarray,
    conf_threshold: float,
    iou_threshold: float,
) -> list[dict]:
    """
    Run YOLO v8 inference on an image and return raw detection results.

    Returns a list of dicts:
        [{ 'x1', 'y1', 'x2', 'y2', 'confidence', 'class_id', 'class_conf' }, ...]
    All coordinates are in pixels relative to the `image` passed in.
    """
    model   = get_yolo_model()
    results = model.predict(
        source      = image,
        conf        = conf_threshold,
        iou         = iou_threshold,
        verbose     = False,
        device      = "cpu",    # Switch to "cuda:0" when GPU is available
    )

    detections = []
    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue
        for i in range(len(boxes)):
            xyxy        = boxes.xyxy[i].cpu().numpy()
            conf        = float(boxes.conf[i].cpu().numpy())
            cls_id      = int(boxes.cls[i].cpu().numpy()) if boxes.cls is not None else None
            cls_conf    = None  # ultralytics doesn't expose per-class conf separately

            detections.append({
                "x1":        float(xyxy[0]),
                "y1":        float(xyxy[1]),
                "x2":        float(xyxy[2]),
                "y2":        float(xyxy[3]),
                "confidence": conf,
                "class_id":  cls_id,
                "class_conf": cls_conf,
            })

    logger.debug("YOLO returned %d raw detections.", len(detections))
    return detections


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

def _filter_by_area(
    detections: list[dict],
    image_w: int,
    image_h: int,
    min_hold_area: float,
) -> list[dict]:
    """Remove detections whose bounding box area is below the minimum threshold."""
    image_area  = image_w * image_h
    min_px_area = image_area * min_hold_area
    filtered    = [
        d for d in detections
        if (d["x2"] - d["x1"]) * (d["y2"] - d["y1"]) >= min_px_area
    ]
    removed = len(detections) - len(filtered)
    if removed:
        logger.debug("Removed %d detections below min area threshold.", removed)
    return filtered


def _to_normalised(
    detections: list[dict],
    inf_w: int,
    inf_h: int,
    scale_x: float,
    scale_y: float,
) -> list[dict]:
    """
    Convert pixel coordinates (inference image space) → normalised [0,1]
    coordinates in the original image space.
    """
    normalised = []
    for d in detections:
        # Scale back to original pixel space
        x1_orig = d["x1"] * scale_x
        y1_orig = d["y1"] * scale_y
        x2_orig = d["x2"] * scale_x
        y2_orig = d["y2"] * scale_y

        orig_w  = inf_w * scale_x
        orig_h  = inf_h * scale_y

        x_norm  = x1_orig / orig_w
        y_norm  = y1_orig / orig_h
        w_norm  = (x2_orig - x1_orig) / orig_w
        h_norm  = (y2_orig - y1_orig) / orig_h

        normalised.append({
            **d,
            "x":      max(0.0, min(1.0, x_norm)),
            "y":      max(0.0, min(1.0, y_norm)),
            "width":  max(0.0, min(1.0, w_norm)),
            "height": max(0.0, min(1.0, h_norm)),
        })
    return normalised


# ---------------------------------------------------------------------------
# Main detection pipeline
# ---------------------------------------------------------------------------

async def detect_holds(
    wall_id: str,
    image_url: str,
    mode: DetectionMode,
    options: DetectionOptions,
) -> DetectHoldsResponse:
    """
    Full detection pipeline — the single entry point called by the FastAPI route.

    Returns:
        DetectHoldsResponse with all detected holds and run metadata.

    Raises:
        ValueError:     For image quality/download issues (→ 422 / 400 response).
        RuntimeError:   For model or internal errors (→ 500 response).
    """
    t_start = time.monotonic()

    # ── Step 1: Preprocess ──────────────────────────────────────────────────
    logger.info("[wall=%s] Starting hold detection. Mode=%s", wall_id, mode)
    preprocessed: PreprocessedImage = await preprocess(
        image_url        = str(image_url),
        enhance_contrast = options.enhance_contrast,
    )

    # ── Step 2: YOLO inference ──────────────────────────────────────────────
    raw_detections = _run_yolo(
        image          = preprocessed.inference_bgr,
        conf_threshold = options.confidence_threshold,
        iou_threshold  = options.iou_threshold,
    )

    # ── Step 3: Area filter ─────────────────────────────────────────────────
    raw_detections = _filter_by_area(
        detections    = raw_detections,
        image_w       = preprocessed.inference_width,
        image_h       = preprocessed.inference_height,
        min_hold_area = options.min_hold_area,
    )

    # ── Step 4: Normalise coordinates ───────────────────────────────────────
    normalised = _to_normalised(
        detections = raw_detections,
        inf_w      = preprocessed.inference_width,
        inf_h      = preprocessed.inference_height,
        scale_x    = preprocessed.scale_x,
        scale_y    = preprocessed.scale_y,
    )

    if not normalised:
        raise ValueError("NO_HOLDS_DETECTED")

    # ── Step 5: Build DetectedHold objects ──────────────────────────────────
    detected_holds: list[DetectedHold] = []

    for idx, det in enumerate(normalised):
        x      = det["x"]
        y      = det["y"]
        w      = det["width"]
        h      = det["height"]
        conf   = det["confidence"]

        # Colour classification
        color_result = classify_hold_color(
            original_bgr = preprocessed.original_bgr,
            x=x, y=y, width=w, height=h,
        )

        # Hold type classification
        aspect_ratio = (w / h) if h > 0 else 1.0
        hold_type, type_conf = _classify_hold_type_heuristic(
            width_norm      = w,
            height_norm     = h,
            aspect_ratio    = aspect_ratio,
            yolo_class      = det.get("class_id"),
            yolo_class_conf = det.get("class_conf"),
            classify_types  = options.classify_types,
        )

        hold = DetectedHold(
            id              = f"{wall_id}_hold_{idx + 1:04d}",
            x               = round(x, 6),
            y               = round(y, 6),
            width           = round(w, 6),
            height          = round(h, 6),
            center_x        = round(x + w / 2, 6),
            center_y        = round(y + h / 2, 6),
            area            = round(w * h, 8),
            color           = color_result.color,
            color_hex       = color_result.color_hex,
            type            = hold_type,
            confidence      = round(conf, 4),
            type_confidence = round(type_conf, 4) if type_conf else None,
            is_verified     = conf >= 0.50,
        )
        detected_holds.append(hold)

    # ── Step 6: Sort by position (top-left → bottom-right, natural reading order) ─
    detected_holds.sort(key=lambda h: (round(h.center_y * 10), round(h.center_x * 10)))

    # ── Step 7: Build metadata ───────────────────────────────────────────────
    elapsed_ms = int((time.monotonic() - t_start) * 1000)
    verified   = sum(1 for h in detected_holds if h.is_verified)

    metadata = DetectionMetadata(
        model_version       = MODEL_VERSION,
        processing_time_ms  = elapsed_ms,
        image_width_px      = preprocessed.original_width,
        image_height_px     = preprocessed.original_height,
        mode                = mode,
        holds_detected      = len(detected_holds),
        holds_verified      = verified,
        holds_unverified    = len(detected_holds) - verified,
    )

    logger.info(
        "[wall=%s] Detection complete. %d holds found in %dms.",
        wall_id, len(detected_holds), elapsed_ms,
    )

    return DetectHoldsResponse(
        wall_id  = wall_id,
        holds    = detected_holds,
        metadata = metadata,
    )
