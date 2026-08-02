"""
conftest.py — Shared pytest fixtures for cv-service tests.

All fixtures here are available to every test module without importing.
"""

from __future__ import annotations

import io
import random
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Image Helpers
# ---------------------------------------------------------------------------

def make_rgb_array(
    height: int = 480,
    width:  int = 640,
    color:  tuple[int, int, int] = (200, 200, 200),
    seed:   int = 42,
) -> np.ndarray:
    """Return a solid-colour image with slight noise (simulates a wall)."""
    rng = np.random.default_rng(seed)
    img = np.full((height, width, 3), color, dtype=np.uint8)
    noise = rng.integers(-8, 8, img.shape, dtype=np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def make_image_with_holds(
    n_holds: int = 8,
    hold_colors: list[tuple[int, int, int]] | None = None,
    height: int = 480,
    width:  int = 640,
    seed:   int = 42,
) -> np.ndarray:
    """
    Return a synthetic wall image with coloured blobs simulating holds.
    Background is light grey; holds are brightly coloured circles.
    """
    rng = np.random.default_rng(seed)
    img = make_rgb_array(height, width, color=(210, 210, 210), seed=seed)

    if hold_colors is None:
        hold_colors = [
            (220, 50,  50 ),   # Red
            (50,  100, 220),   # Blue
            (50,  180, 50 ),   # Green
            (200, 160, 30 ),   # Yellow
            (160, 50,  200),   # Purple
        ]

    for i in range(n_holds):
        cx  = int(rng.integers(60, width  - 60))
        cy  = int(rng.integers(60, height - 60))
        r   = int(rng.integers(20, 45))
        col = hold_colors[i % len(hold_colors)]

        # Draw filled circle
        yy, xx = np.ogrid[:height, :width]
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2
        img[mask] = col

    return img


def array_to_jpeg_bytes(img: np.ndarray, quality: int = 85) -> bytes:
    """Convert numpy array to JPEG bytes (no cv2 required — uses PIL)."""
    from PIL import Image
    pil_img = Image.fromarray(img.astype(np.uint8))
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def array_to_png_bytes(img: np.ndarray) -> bytes:
    from PIL import Image
    pil_img = Image.fromarray(img.astype(np.uint8))
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Pytest Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def clean_wall_image() -> np.ndarray:
    """A blank grey wall with no holds."""
    return make_rgb_array(480, 640, color=(200, 200, 200))


@pytest.fixture(scope="session")
def wall_with_8_holds() -> np.ndarray:
    """Synthetic wall image with 8 coloured hold blobs."""
    return make_image_with_holds(n_holds=8, seed=42)


@pytest.fixture(scope="session")
def wall_with_holds_jpeg(wall_with_8_holds) -> bytes:
    return array_to_jpeg_bytes(wall_with_8_holds)


@pytest.fixture(scope="session")
def corrupt_image_bytes() -> bytes:
    """Truly corrupt bytes that cannot be decoded as any image format."""
    return b"\xFF\xFE\xFD\xFC" + b"\x00" * 100


@pytest.fixture(scope="session")
def oversized_image_bytes() -> bytes:
    """JPEG > 20 MB (simulated by a large buffer with JPEG header)."""
    # Real JPEG header + padding
    header = bytes([0xFF, 0xD8, 0xFF, 0xE0])
    return header + b"\x00" * (21 * 1024 * 1024)


@pytest.fixture(scope="function")
def mock_yolo_model():
    """Mock YOLOv8 model returning 3 synthetic detections."""
    model = MagicMock()

    det_mock = MagicMock()
    # 3 boxes: [x1, y1, x2, y2, conf, class]
    det_mock.boxes.data.cpu().numpy.return_value = np.array([
        [50,  60,  130, 140, 0.93, 0.0],
        [200, 180, 300, 280, 0.88, 0.0],
        [400, 350, 460, 410, 0.76, 0.0],
    ])
    model.return_value = [det_mock]
    return model


@pytest.fixture(scope="function")
def mock_sam_model():
    """Mock SAM predictor (returns a simple rectangular mask)."""
    predictor = MagicMock()
    mask = np.zeros((480, 640), dtype=bool)
    mask[60:140, 50:130] = True
    predictor.predict.return_value = ([mask], [0.95], None)
    return predictor


@pytest.fixture(scope="session")
def sample_holds_response() -> list[dict]:
    """Sample holds list as returned by the CV service."""
    return [
        {
            "id":              "hold_0001",
            "x":               0.078,
            "y":               0.125,
            "width":           0.125,
            "height":          0.167,
            "center_x":        0.141,
            "center_y":        0.208,
            "area":            0.020,
            "color":           "red",
            "color_hex":       "#E03232",
            "type":            "jug",
            "confidence":      0.93,
            "type_confidence": 0.88,
            "is_verified":     True,
        },
        {
            "id":              "hold_0002",
            "x":               0.313,
            "y":               0.375,
            "width":           0.156,
            "height":          0.208,
            "center_x":        0.391,
            "center_y":        0.479,
            "area":            0.032,
            "color":           "blue",
            "color_hex":       "#3264DC",
            "type":            "sloper",
            "confidence":      0.88,
            "type_confidence": 0.72,
            "is_verified":     True,
        },
        {
            "id":              "hold_0003",
            "x":               0.625,
            "y":               0.729,
            "width":           0.094,
            "height":          0.125,
            "center_x":        0.672,
            "center_y":        0.792,
            "area":            0.012,
            "color":           "green",
            "color_hex":       "#32B432",
            "type":            "crimp",
            "confidence":      0.76,
            "type_confidence": 0.65,
            "is_verified":     True,
        },
    ]
