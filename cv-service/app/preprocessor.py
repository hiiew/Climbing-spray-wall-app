"""
preprocessor.py — Image preprocessing pipeline for hold detection.

Handles downloading, validation, resizing, and enhancement of spray wall
images before they are passed to the YOLO inference engine.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import httpx
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_DIMENSION_PX    = 640          # Minimum accepted side length
MAX_INFERENCE_DIM   = 1280         # Image is downscaled to this before inference
CLAHE_CLIP_LIMIT    = 2.0
CLAHE_TILE_GRID     = (8, 8)
DOWNLOAD_TIMEOUT_S  = 30


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class PreprocessedImage:
    """Container for preprocessed image data passed to the detector."""

    original_bgr: np.ndarray           # Original BGR image (full resolution)
    inference_bgr: np.ndarray          # Resized BGR image for YOLO inference
    original_width: int
    original_height: int
    inference_width: int
    inference_height: int
    scale_x: float                     # original_width  / inference_width
    scale_y: float                     # original_height / inference_height


# ---------------------------------------------------------------------------
# Preprocessing functions
# ---------------------------------------------------------------------------

async def download_image(url: str) -> np.ndarray:
    """
    Download an image from S3/URL and decode it into an OpenCV BGR array.

    Raises:
        ValueError: If download fails or bytes cannot be decoded as an image.
    """
    logger.info("Downloading image from: %s", url)
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_S) as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise ValueError(
                f"Failed to download image. HTTP {response.status_code}: {url}"
            )

    image_bytes = response.content
    np_array    = np.frombuffer(image_bytes, dtype=np.uint8)
    bgr_image   = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

    if bgr_image is None:
        raise ValueError("Downloaded bytes could not be decoded as a valid image.")

    logger.info(
        "Image downloaded successfully. Shape: %s", bgr_image.shape
    )
    return bgr_image


def validate_image(image: np.ndarray) -> None:
    """
    Validate image dimensions and quality before processing.

    Raises:
        ValueError: With a descriptive message for the specific failure.
    """
    h, w = image.shape[:2]

    if w < MIN_DIMENSION_PX or h < MIN_DIMENSION_PX:
        raise ValueError(
            f"Image too small ({w}×{h}px). "
            f"Minimum required: {MIN_DIMENSION_PX}×{MIN_DIMENSION_PX}px."
        )

    # Blurriness check via Laplacian variance
    gray       = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian  = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian < 50.0:
        raise ValueError(
            f"Image appears blurry (Laplacian variance={laplacian:.1f}). "
            "Please upload a sharper photo of your wall."
        )

    logger.debug("Image validated. Size=%dx%d, Laplacian=%.1f", w, h, laplacian)


def resize_for_inference(image: np.ndarray) -> tuple[np.ndarray, float, float]:
    """
    Resize image so the largest dimension ≤ MAX_INFERENCE_DIM while preserving
    aspect ratio. Returns (resized_image, scale_x, scale_y).

    Scale factors are used to map YOLO coordinates back to the original image.
    """
    h, w = image.shape[:2]

    if max(h, w) <= MAX_INFERENCE_DIM:
        return image, 1.0, 1.0

    scale     = MAX_INFERENCE_DIM / max(h, w)
    new_w     = int(w * scale)
    new_h     = int(h * scale)
    resized   = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    scale_x   = w / new_w
    scale_y   = h / new_h

    logger.debug(
        "Resized image from %dx%d to %dx%d (scale=%.3f)", w, h, new_w, new_h, scale
    )
    return resized, scale_x, scale_y


def apply_clahe(image: np.ndarray) -> np.ndarray:
    """
    Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) on the
    L-channel of the LAB colour space to improve hold visibility under
    uneven lighting without over-saturating colours.

    Returns a BGR image.
    """
    lab                     = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a, b         = cv2.split(lab)

    clahe                   = cv2.createCLAHE(
        clipLimit   = CLAHE_CLIP_LIMIT,
        tileGridSize= CLAHE_TILE_GRID,
    )
    l_enhanced              = clahe.apply(l_channel)

    enhanced_lab            = cv2.merge([l_enhanced, a, b])
    enhanced_bgr            = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
    return enhanced_bgr


def remove_background_bias(image: np.ndarray) -> np.ndarray:
    """
    Mild colour normalisation to reduce the effect of coloured wall backgrounds
    (common in spray walls painted grey, blue, or wood-toned).

    Uses per-channel mean subtraction with a grey-world assumption.
    """
    float_img   = image.astype(np.float32)
    mean        = float_img.mean(axis=(0, 1), keepdims=True)
    grey_target = mean.mean()
    scale       = grey_target / (mean + 1e-7)
    normalised  = np.clip(float_img * scale, 0, 255).astype(np.uint8)
    return normalised


async def preprocess(
    image_url: str,
    enhance_contrast: bool = True,
) -> PreprocessedImage:
    """
    Full preprocessing pipeline: download → validate → enhance → resize.

    Returns a PreprocessedImage dataclass ready for YOLO inference.

    Raises:
        ValueError: For any validation or download failure (caller maps to HTTP error).
    """
    raw_bgr = await download_image(image_url)
    validate_image(raw_bgr)

    original_h, original_w = raw_bgr.shape[:2]

    enhanced = apply_clahe(raw_bgr) if enhance_contrast else raw_bgr
    enhanced = remove_background_bias(enhanced)

    inference_bgr, scale_x, scale_y = resize_for_inference(enhanced)
    inf_h, inf_w = inference_bgr.shape[:2]

    return PreprocessedImage(
        original_bgr    = raw_bgr,
        inference_bgr   = inference_bgr,
        original_width  = original_w,
        original_height = original_h,
        inference_width = inf_w,
        inference_height= inf_h,
        scale_x         = scale_x,
        scale_y         = scale_y,
    )
