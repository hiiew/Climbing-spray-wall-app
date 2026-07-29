"""
color_classifier.py — Dominant colour classification for detected holds.

Uses HSV colour space analysis on the hold's cropped region from the original
image to assign a human-readable colour label and a representative hex code.

Why HSV instead of RGB?
  RGB colour distance is perceptually non-uniform (a small RGB delta can be
  a large perceptual change). HSV separates Hue (colour identity) from
  Saturation and Value (brightness), making hue-range matching reliable
  under varying lighting conditions — critical for spray walls.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

import cv2
import numpy as np

from app.schemas import HoldColor


# ---------------------------------------------------------------------------
# HSV hue ranges (H in OpenCV is 0–179)
# ---------------------------------------------------------------------------

# Format: (color_name, h_min, h_max, s_min, v_min)
# s_min/v_min filter out near-grey and near-black pixels before hue matching.
_HSV_RANGES: list[tuple[HoldColor, int, int, int, int]] = [
    (HoldColor.RED,    0,   10,  80, 60),
    (HoldColor.RED,  165,  179,  80, 60),   # Red wraps around 0/179 in HSV
    (HoldColor.ORANGE, 11,  25,  80, 60),
    (HoldColor.YELLOW, 26,  35,  80, 60),
    (HoldColor.GREEN,  36,  85,  60, 50),
    (HoldColor.BLUE,   86, 130,  60, 50),
    (HoldColor.PURPLE,131, 155,  50, 40),
    (HoldColor.PINK,  156, 164,  60, 60),
]

# Achromatic colour thresholds (checked after hue matching)
_GREY_S_MAX  = 40
_WHITE_V_MIN = 200
_BLACK_V_MAX = 50

# Representative display colours for each label (used as color_hex in response)
_COLOR_HEX: dict[HoldColor, str] = {
    HoldColor.RED:     "#EF4444",
    HoldColor.ORANGE:  "#F97316",
    HoldColor.YELLOW:  "#EAB308",
    HoldColor.GREEN:   "#22C55E",
    HoldColor.BLUE:    "#3B82F6",
    HoldColor.PURPLE:  "#A855F7",
    HoldColor.PINK:    "#EC4899",
    HoldColor.BLACK:   "#1F2937",
    HoldColor.WHITE:   "#F9FAFB",
    HoldColor.GREY:    "#6B7280",
    HoldColor.UNKNOWN: "#9CA3AF",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class ColorResult:
    color: HoldColor
    color_hex: str


def classify_hold_color(
    original_bgr: np.ndarray,
    x: float,
    y: float,
    width: float,
    height: float,
) -> ColorResult:
    """
    Classify the dominant colour of a hold given its normalised bounding box.

    Steps:
    1. Crop the hold region from the full-resolution original image.
    2. Convert to HSV.
    3. Build a mask excluding background-like pixels (low saturation or value).
    4. For each colour range, count matching pixels.
    5. Return the colour with the highest pixel count.

    Args:
        original_bgr: Full-resolution BGR image (not the inference-scaled copy).
        x, y, width, height: Normalised bounding box coordinates [0.0–1.0].

    Returns:
        ColorResult with the detected HoldColor and its hex code.
    """
    img_h, img_w = original_bgr.shape[:2]

    # Convert normalised coords → pixel coords (with clamping)
    x1 = max(0, int(x * img_w))
    y1 = max(0, int(y * img_h))
    x2 = min(img_w, int((x + width) * img_w))
    y2 = min(img_h, int((y + height) * img_h))

    crop = original_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return ColorResult(HoldColor.UNKNOWN, _COLOR_HEX[HoldColor.UNKNOWN])

    hsv_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    # Shrink crop by 15% inward to reduce background bleed-in on hold edges
    shrink = 0.15
    h_s, w_s = hsv_crop.shape[:2]
    dy  = max(1, int(h_s * shrink))
    dx  = max(1, int(w_s * shrink))
    hsv_crop = hsv_crop[dy:h_s-dy, dx:w_s-dx]

    if hsv_crop.size == 0:
        return ColorResult(HoldColor.UNKNOWN, _COLOR_HEX[HoldColor.UNKNOWN])

    h_ch = hsv_crop[:, :, 0]   # Hue
    s_ch = hsv_crop[:, :, 1]   # Saturation
    v_ch = hsv_crop[:, :, 2]   # Value

    # Check achromatic colours first
    low_sat_mask  = s_ch < _GREY_S_MAX
    high_val_mask = v_ch > _WHITE_V_MIN
    low_val_mask  = v_ch < _BLACK_V_MAX

    white_px  = int((low_sat_mask & high_val_mask).sum())
    black_px  = int((low_sat_mask & low_val_mask).sum())
    grey_px   = int((low_sat_mask & ~high_val_mask & ~low_val_mask).sum())

    # Count chromatic colour pixels
    chromatic_counts: dict[HoldColor, int] = {}
    for (color, h_min, h_max, s_min, v_min) in _HSV_RANGES:
        mask = (
            (h_ch >= h_min) & (h_ch <= h_max) &
            (s_ch >= s_min) &
            (v_ch >= v_min)
        )
        count = int(mask.sum())
        chromatic_counts[color] = chromatic_counts.get(color, 0) + count

    # Build final competition: chromatic winners + achromatic
    all_counts: dict[HoldColor, int] = dict(chromatic_counts)
    all_counts[HoldColor.WHITE] = white_px
    all_counts[HoldColor.BLACK] = black_px
    all_counts[HoldColor.GREY]  = grey_px

    best_color = max(all_counts, key=lambda c: all_counts[c])

    # Fallback if all counts are zero (uniform background crop)
    if all_counts[best_color] == 0:
        best_color = HoldColor.UNKNOWN

    return ColorResult(best_color, _COLOR_HEX[best_color])
