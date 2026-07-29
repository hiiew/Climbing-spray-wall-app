"""
test_hold_detector.py — Unit and integration tests for the hold detection pipeline.

Run with:
    pytest cv-service/tests/ -v --cov=app

Test strategy:
  - Unit:        Individual functions (colour classifier, heuristics, normalisation)
  - Integration: Full pipeline with mocked YOLO model and synthetic images
  - Error paths: Low-quality image, no holds detected, timeout simulation
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.color_classifier import classify_hold_color
from app.hold_detector import (
    _classify_hold_type_heuristic,
    _filter_by_area,
    _to_normalised,
    detect_holds,
    set_yolo_model,
)
from app.preprocessor import validate_image
from app.schemas import DetectionMode, DetectionOptions, HoldColor, HoldType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_wall_image() -> np.ndarray:
    """
    Generate a synthetic 1200×1200 white-background image with 5 coloured
    rectangles simulating holds at known positions.
    """
    img = np.full((1200, 1200, 3), 240, dtype=np.uint8)   # Off-white background

    # Draw coloured rectangles as fake holds (BGR)
    holds = [
        ((100, 100, 200, 160), (0,   0, 220)),   # Red hold
        ((400, 200, 480, 260), (200, 50,   0)),   # Blue hold
        ((700, 150, 790, 220), (30, 180,  30)),   # Green hold
        ((300, 500, 380, 560), (0, 160, 220)),    # Yellow hold
        ((900, 600, 970, 660), (180,  0, 180)),   # Purple hold
    ]
    for (x1, y1, x2, y2), color in holds:
        img[y1:y2, x1:x2] = color

    return img


@pytest.fixture
def mock_yolo_detections():
    """Five fake YOLO bounding boxes for the synthetic_wall_image."""
    return [
        {"x1": 100, "y1": 100, "x2": 200, "y2": 160, "confidence": 0.92, "class_id": 0, "class_conf": 0.88},
        {"x1": 400, "y1": 200, "x2": 480, "y2": 260, "confidence": 0.87, "class_id": 1, "class_conf": 0.82},
        {"x1": 700, "y1": 150, "x2": 790, "y2": 220, "confidence": 0.79, "class_id": 2, "class_conf": 0.74},
        {"x1": 300, "y1": 500, "x2": 380, "y2": 560, "confidence": 0.95, "class_id": 0, "class_conf": 0.91},
        {"x1": 900, "y1": 600, "x2": 970, "y2": 660, "confidence": 0.65, "class_id": 3, "class_conf": 0.60},
    ]


# ---------------------------------------------------------------------------
# Unit Tests — Color Classifier
# ---------------------------------------------------------------------------

class TestColorClassifier:

    def test_red_hold_detected(self):
        """A mostly-red crop should be classified as RED."""
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        img[:] = (0, 0, 200)   # BGR red
        result = classify_hold_color(img, 0.0, 0.0, 1.0, 1.0)
        assert result.color == HoldColor.RED

    def test_blue_hold_detected(self):
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        img[:] = (200, 50, 0)   # BGR blue
        result = classify_hold_color(img, 0.0, 0.0, 1.0, 1.0)
        assert result.color == HoldColor.BLUE

    def test_white_background_classified_as_white(self):
        img = np.full((200, 200, 3), 245, dtype=np.uint8)  # Near-white
        result = classify_hold_color(img, 0.0, 0.0, 1.0, 1.0)
        assert result.color == HoldColor.WHITE

    def test_black_hold_detected(self):
        img = np.zeros((200, 200, 3), dtype=np.uint8)   # Black
        result = classify_hold_color(img, 0.0, 0.0, 1.0, 1.0)
        assert result.color == HoldColor.BLACK

    def test_color_hex_format(self):
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        img[:] = (0, 0, 200)
        result = classify_hold_color(img, 0.0, 0.0, 1.0, 1.0)
        assert result.color_hex.startswith("#")
        assert len(result.color_hex) == 7

    def test_empty_crop_returns_unknown(self):
        """Zero-area bounding box should return UNKNOWN without crashing."""
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        result = classify_hold_color(img, 0.5, 0.5, 0.0, 0.0)
        assert result.color == HoldColor.UNKNOWN


# ---------------------------------------------------------------------------
# Unit Tests — Hold Type Heuristic
# ---------------------------------------------------------------------------

class TestHoldTypeHeuristic:

    def test_volume_large_area(self):
        hold_type, conf = _classify_hold_type_heuristic(0.2, 0.2, 1.0, None, None, True)
        assert hold_type == HoldType.VOLUME
        assert conf is not None

    def test_crimp_high_aspect_ratio(self):
        hold_type, conf = _classify_hold_type_heuristic(0.04, 0.01, 4.0, None, None, True)
        assert hold_type == HoldType.CRIMP

    def test_pocket_low_aspect_ratio(self):
        hold_type, conf = _classify_hold_type_heuristic(0.01, 0.03, 0.4, None, None, True)
        assert hold_type == HoldType.POCKET

    def test_model_class_overrides_heuristic(self):
        """If YOLO provides a class, it should take priority over geometry."""
        hold_type, _ = _classify_hold_type_heuristic(0.2, 0.2, 1.0, 1, 0.9, True)
        assert hold_type == HoldType.CRIMP   # class_id=1 → CRIMP

    def test_classify_types_false_returns_unknown(self):
        hold_type, conf = _classify_hold_type_heuristic(0.05, 0.05, 1.0, None, None, False)
        assert hold_type == HoldType.UNKNOWN
        assert conf is None


# ---------------------------------------------------------------------------
# Unit Tests — Area Filter and Coordinate Normalisation
# ---------------------------------------------------------------------------

class TestPostProcessing:

    def test_area_filter_removes_small_boxes(self):
        detections = [
            {"x1": 0, "y1": 0, "x2": 5, "y2": 5, "confidence": 0.9},     # tiny → filtered
            {"x1": 0, "y1": 0, "x2": 100, "y2": 100, "confidence": 0.9},  # kept
        ]
        result = _filter_by_area(detections, 1000, 1000, min_hold_area=0.001)
        assert len(result) == 1
        assert result[0]["x2"] == 100

    def test_normalised_values_in_range(self):
        detections = [{"x1": 100, "y1": 100, "x2": 200, "y2": 200,
                        "confidence": 0.9, "class_id": None, "class_conf": None}]
        result = _to_normalised(detections, inf_w=1000, inf_h=1000, scale_x=1.0, scale_y=1.0)
        assert 0.0 <= result[0]["x"] <= 1.0
        assert 0.0 <= result[0]["y"] <= 1.0
        assert 0.0 <= result[0]["width"] <= 1.0
        assert 0.0 <= result[0]["height"] <= 1.0


# ---------------------------------------------------------------------------
# Unit Tests — Image Validation
# ---------------------------------------------------------------------------

class TestImageValidation:

    def test_small_image_raises(self):
        small_img = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="too small"):
            validate_image(small_img)

    def test_blurry_image_raises(self):
        """A uniform (zero-variance) image is maximally blurry."""
        flat_img = np.full((1000, 1000, 3), 128, dtype=np.uint8)
        with pytest.raises(ValueError, match="blurry"):
            validate_image(flat_img)

    def test_valid_image_passes(self, synthetic_wall_image):
        """Synthetic wall image with coloured shapes should pass validation."""
        validate_image(synthetic_wall_image)   # Should not raise


# ---------------------------------------------------------------------------
# Integration Tests — Full Pipeline (mocked YOLO + mocked download)
# ---------------------------------------------------------------------------

class TestDetectHoldsPipeline:

    @pytest.mark.asyncio
    async def test_happy_path_returns_correct_hold_count(
        self, synthetic_wall_image, mock_yolo_detections
    ):
        """Full pipeline with mocked I/O should return 5 holds."""
        mock_model         = MagicMock()
        mock_result        = MagicMock()
        mock_boxes         = MagicMock()

        import torch
        # Build fake YOLO result boxes
        xyxy_data = [[d["x1"], d["y1"], d["x2"], d["y2"]] for d in mock_yolo_detections]
        conf_data = [d["confidence"] for d in mock_yolo_detections]
        cls_data  = [d["class_id"]   for d in mock_yolo_detections]

        mock_boxes.xyxy = MagicMock(
            __len__ = lambda s: len(xyxy_data),
            __iter__= lambda s: iter(xyxy_data),
        )
        mock_boxes.xyxy.__getitem__ = lambda s, i: MagicMock(
            cpu=lambda: MagicMock(numpy=lambda: np.array(xyxy_data[i]))
        )
        mock_boxes.conf = MagicMock(
            __getitem__=lambda s, i: MagicMock(
                cpu=lambda: MagicMock(numpy=lambda: np.array(conf_data[i]))
            )
        )
        mock_boxes.cls = MagicMock(
            __getitem__=lambda s, i: MagicMock(
                cpu=lambda: MagicMock(numpy=lambda: np.array(cls_data[i]))
            )
        )
        mock_result.boxes = mock_boxes
        mock_model.predict.return_value = [mock_result]

        set_yolo_model(mock_model)

        with patch(
            "app.preprocessor.download_image",
            new=AsyncMock(return_value=synthetic_wall_image),
        ):
            response = await detect_holds(
                wall_id   = "test_wall_001",
                image_url = "https://example.com/wall.jpg",
                mode      = DetectionMode.FAST,
                options   = DetectionOptions(),
            )

        assert response.wall_id == "test_wall_001"
        assert len(response.holds) == 5
        assert response.metadata.holds_detected == 5
        assert all(0.0 <= h.x <= 1.0 for h in response.holds)
        assert all(0.0 <= h.confidence <= 1.0 for h in response.holds)

    @pytest.mark.asyncio
    async def test_no_holds_detected_raises_value_error(self, synthetic_wall_image):
        """When YOLO returns no detections, ValueError should be raised."""
        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.boxes = None
        mock_model.predict.return_value = [mock_result]
        set_yolo_model(mock_model)

        with patch("app.preprocessor.download_image", new=AsyncMock(return_value=synthetic_wall_image)):
            with pytest.raises(ValueError, match="NO_HOLDS_DETECTED"):
                await detect_holds(
                    wall_id   = "test_wall_002",
                    image_url = "https://example.com/wall.jpg",
                    mode      = DetectionMode.FAST,
                    options   = DetectionOptions(),
                )

    @pytest.mark.asyncio
    async def test_download_failure_raises_value_error(self):
        """When the image URL is unreachable, a ValueError should propagate."""
        with patch(
            "app.preprocessor.download_image",
            new=AsyncMock(side_effect=ValueError("Failed to download image.")),
        ):
            with pytest.raises(ValueError, match="Failed to download"):
                await detect_holds(
                    wall_id   = "test_wall_003",
                    image_url = "https://bad-url.invalid/wall.jpg",
                    mode      = DetectionMode.FAST,
                    options   = DetectionOptions(),
                )
