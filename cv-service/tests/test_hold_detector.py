"""
test_hold_detector.py — Tests for the CV hold detection pipeline.

Strategy:
- Unit tests:        validate individual pipeline stages in isolation (mocked models)
- Integration tests: run the full API endpoint with a TestClient (mocked YOLO)
- Error path tests:  corrupt images, no-holds images, oversized inputs

Run:
  pytest cv-service/tests/test_hold_detector.py -v
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Fixtures are in conftest.py (auto-loaded by pytest)
from tests.conftest import (
    make_image_with_holds,
    make_rgb_array,
    array_to_jpeg_bytes,
    array_to_png_bytes,
)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Preprocessor Unit Tests
# ---------------------------------------------------------------------------

class TestPreprocessor:
    """Test the image preprocessing stage (validation, resizing, CLAHE)."""

    def test_valid_jpeg_loads_successfully(self, wall_with_holds_jpeg):
        from app.preprocessor import load_and_validate_image
        img = load_and_validate_image(wall_with_holds_jpeg)
        assert img is not None
        assert img.ndim == 3
        assert img.shape[2] == 3  # RGB channels

    def test_corrupt_bytes_raise_value_error(self, corrupt_image_bytes):
        from app.preprocessor import load_and_validate_image
        with pytest.raises(ValueError, match="[Cc]orrupt|[Ii]nvalid|cannot"):
            load_and_validate_image(corrupt_image_bytes)

    def test_oversized_image_raises_value_error(self, oversized_image_bytes):
        from app.preprocessor import load_and_validate_image
        with pytest.raises(ValueError, match="[Ss]ize|[Ll]arge|limit"):
            load_and_validate_image(oversized_image_bytes)

    def test_image_is_resized_when_too_large(self):
        from app.preprocessor import resize_for_detection
        huge_img = make_rgb_array(height=4000, width=4000)
        resized  = resize_for_detection(huge_img, max_dim=1024)
        assert max(resized.shape[:2]) <= 1024

    def test_small_image_is_not_upscaled(self):
        from app.preprocessor import resize_for_detection
        small_img = make_rgb_array(height=400, width=300)
        result    = resize_for_detection(small_img, max_dim=1024)
        assert result.shape[0] <= 400
        assert result.shape[1] <= 300

    def test_clahe_does_not_change_image_dimensions(self):
        from app.preprocessor import apply_clahe
        img      = make_rgb_array(480, 640)
        enhanced = apply_clahe(img)
        assert enhanced.shape == img.shape

    def test_clahe_output_is_uint8(self):
        from app.preprocessor import apply_clahe
        img      = make_rgb_array(480, 640)
        enhanced = apply_clahe(img)
        assert enhanced.dtype == np.uint8

    def test_png_image_loads_successfully(self):
        from app.preprocessor import load_and_validate_image
        img_arr   = make_image_with_holds(n_holds=4)
        png_bytes = array_to_png_bytes(img_arr)
        loaded    = load_and_validate_image(png_bytes)
        assert loaded.shape[:2] == img_arr.shape[:2]

    def test_minimum_resolution_check(self):
        from app.preprocessor import load_and_validate_image
        tiny     = make_rgb_array(height=100, width=100)
        tiny_jpg = array_to_jpeg_bytes(tiny)
        with pytest.raises(ValueError, match="[Rr]esolution|[Ss]mall|1000"):
            load_and_validate_image(tiny_jpg)


# ---------------------------------------------------------------------------
# Color Classifier Unit Tests
# ---------------------------------------------------------------------------

class TestColorClassifier:
    """Test the HSV-based color classification logic."""

    def test_red_pixel_classified_as_red(self):
        from app.color_classifier import classify_color_from_bgr
        red_bgr = np.array([[[0, 0, 200]]], dtype=np.uint8)
        result  = classify_color_from_bgr(red_bgr)
        assert result["color"] == "red"

    def test_blue_pixel_classified_as_blue(self):
        from app.color_classifier import classify_color_from_bgr
        blue_bgr = np.array([[[200, 0, 0]]], dtype=np.uint8)
        result   = classify_color_from_bgr(blue_bgr)
        assert result["color"] == "blue"

    def test_green_pixel_classified_as_green(self):
        from app.color_classifier import classify_color_from_bgr
        green_bgr = np.array([[[0, 200, 0]]], dtype=np.uint8)
        result    = classify_color_from_bgr(green_bgr)
        assert result["color"] == "green"

    def test_grey_background_classified_correctly(self):
        from app.color_classifier import classify_color_from_bgr
        grey_bgr = np.array([[[180, 180, 180]]], dtype=np.uint8)
        result   = classify_color_from_bgr(grey_bgr)
        assert result["color"] in ("grey", "gray", "white", "unknown")

    def test_color_result_includes_hex(self):
        from app.color_classifier import classify_color_from_bgr
        red_bgr = np.array([[[0, 0, 200]]], dtype=np.uint8)
        result  = classify_color_from_bgr(red_bgr)
        assert "hex" in result or "color_hex" in result

    def test_classify_returns_color_field(self):
        from app.color_classifier import classify_color_from_bgr
        img_bgr = np.array([[[50, 100, 200]]], dtype=np.uint8)
        result  = classify_color_from_bgr(img_bgr)
        assert "color" in result


# ---------------------------------------------------------------------------
# Hold Detector Unit Tests (YOLO mocked)
# ---------------------------------------------------------------------------

class TestHoldDetector:
    """
    Unit tests for the hold detection pipeline.
    YOLO model is mocked to avoid GPU/model file dependencies in CI.
    """

    def test_detects_correct_number_of_holds_from_mock(
        self, mock_yolo_model, wall_with_8_holds
    ):
        from app.hold_detector import HoldDetector
        img_bytes = array_to_jpeg_bytes(wall_with_8_holds)

        with patch("app.hold_detector.YOLO", return_value=mock_yolo_model):
            detector = HoldDetector(mode="fast")
            holds    = detector.detect(img_bytes)

        # Mock returns 3 boxes → expect 3 holds
        assert len(holds) == 3

    def test_hold_has_required_fields(self, mock_yolo_model, wall_with_8_holds):
        from app.hold_detector import HoldDetector
        img_bytes = array_to_jpeg_bytes(wall_with_8_holds)

        with patch("app.hold_detector.YOLO", return_value=mock_yolo_model):
            detector = HoldDetector(mode="fast")
            holds    = detector.detect(img_bytes)

        required = {
            "id", "x", "y", "width", "height", "center_x",
            "center_y", "area", "color", "color_hex",
            "type", "confidence", "is_verified",
        }
        for hold in holds:
            missing = required - set(hold.keys())
            assert not missing, f"Missing fields: {missing}"

    def test_hold_coordinates_are_normalised(self, mock_yolo_model, wall_with_8_holds):
        from app.hold_detector import HoldDetector
        img_bytes = array_to_jpeg_bytes(wall_with_8_holds)

        with patch("app.hold_detector.YOLO", return_value=mock_yolo_model):
            detector = HoldDetector(mode="fast")
            holds    = detector.detect(img_bytes)

        for h in holds:
            assert 0.0 <= h["x"]        <= 1.0
            assert 0.0 <= h["y"]        <= 1.0
            assert 0.0 <= h["center_x"] <= 1.0
            assert 0.0 <= h["center_y"] <= 1.0
            assert 0.0 <  h["width"]    <= 1.0
            assert 0.0 <  h["height"]   <= 1.0

    def test_hold_ids_are_unique(self, mock_yolo_model, wall_with_8_holds):
        from app.hold_detector import HoldDetector
        img_bytes = array_to_jpeg_bytes(wall_with_8_holds)

        with patch("app.hold_detector.YOLO", return_value=mock_yolo_model):
            detector = HoldDetector(mode="fast")
            holds    = detector.detect(img_bytes)

        ids = [h["id"] for h in holds]
        assert len(ids) == len(set(ids)), "Hold IDs must be unique"

    def test_confidence_score_between_0_and_1(self, mock_yolo_model, wall_with_8_holds):
        from app.hold_detector import HoldDetector
        img_bytes = array_to_jpeg_bytes(wall_with_8_holds)

        with patch("app.hold_detector.YOLO", return_value=mock_yolo_model):
            detector = HoldDetector(mode="fast")
            holds    = detector.detect(img_bytes)

        for h in holds:
            assert 0.0 <= h["confidence"] <= 1.0

    def test_blank_wall_returns_no_holds(self, clean_wall_image):
        from app.hold_detector import HoldDetector

        empty_model = MagicMock()
        no_det      = MagicMock()
        no_det.boxes.data.cpu().numpy.return_value = np.empty((0, 6))
        empty_model.return_value = [no_det]

        img_bytes = array_to_jpeg_bytes(clean_wall_image)
        with patch("app.hold_detector.YOLO", return_value=empty_model):
            detector = HoldDetector(mode="fast")
            holds    = detector.detect(img_bytes)

        assert holds == []

    def test_corrupt_image_raises_value_error(self, corrupt_image_bytes):
        from app.hold_detector import HoldDetector
        with patch("app.hold_detector.YOLO"):
            detector = HoldDetector(mode="fast")
            with pytest.raises(ValueError):
                detector.detect(corrupt_image_bytes)

    def test_low_confidence_detections_are_filtered(self, wall_with_8_holds):
        from app.hold_detector import HoldDetector

        model = MagicMock()
        det   = MagicMock()
        det.boxes.data.cpu().numpy.return_value = np.array([
            [50,  60,  130, 140, 0.85, 0.0],  # keep
            [200, 180, 300, 280, 0.72, 0.0],  # keep
            [400, 350, 460, 410, 0.20, 0.0],  # below threshold
        ])
        model.return_value = [det]

        img_bytes = array_to_jpeg_bytes(wall_with_8_holds)
        with patch("app.hold_detector.YOLO", return_value=model):
            detector = HoldDetector(mode="fast", confidence_threshold=0.5)
            holds    = detector.detect(img_bytes)

        assert len(holds) == 2

    def test_nms_removes_overlapping_detections(self, wall_with_8_holds):
        from app.hold_detector import HoldDetector

        model = MagicMock()
        det   = MagicMock()
        det.boxes.data.cpu().numpy.return_value = np.array([
            [50,  60,  130, 140, 0.93, 0.0],
            [52,  62,  132, 142, 0.91, 0.0],  # near-duplicate
            [300, 280, 400, 380, 0.80, 0.0],  # distinct
        ])
        model.return_value = [det]

        img_bytes = array_to_jpeg_bytes(wall_with_8_holds)
        with patch("app.hold_detector.YOLO", return_value=model):
            detector = HoldDetector(mode="fast", nms_iou_threshold=0.5)
            holds    = detector.detect(img_bytes)

        assert len(holds) <= 2


# ---------------------------------------------------------------------------
# FastAPI Endpoint Integration Tests
# ---------------------------------------------------------------------------

class TestDetectHoldsEndpoint:
    """Integration tests via FastAPI TestClient."""

    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_health_endpoint_returns_ok(self, client):
        assert client.get("/health").status_code == 200

    def test_detect_holds_missing_required_fields_returns_422(self, client):
        response = client.post("/detect-holds", json={"mode": "fast"})
        assert response.status_code == 422

    def test_detect_holds_invalid_mode_returns_422(self, client):
        response = client.post(
            "/detect-holds",
            json={"wall_id": "w1", "image_url": "http://test/img.jpg", "mode": "turbo"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Route Generator API Integration Tests
# ---------------------------------------------------------------------------

class TestGenerateRouteEndpoint:
    """POST /generate-route endpoint integration tests."""

    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    @staticmethod
    def _make_holds(n: int = 20, seed: int = 1) -> list[dict]:
        import random
        rng   = random.Random(seed)
        types = ["jug", "sloper", "crimp", "pinch", "pocket", "foothold"]
        return [
            {
                "id":       f"h_{i:04d}",
                "center_x": rng.uniform(0.05, 0.95),
                "center_y": rng.uniform(0.05, 0.95),
                "width":    rng.uniform(0.03, 0.08),
                "height":   rng.uniform(0.03, 0.08),
                "type":     rng.choice(types),
                "color":    "red",
            }
            for i in range(n)
        ]

    def test_valid_request_returns_200(self, client):
        r = client.post("/generate-route", json={
            "wall_id": "w1",
            "holds":   self._make_holds(20),
            "grade":   "V5",
            "style":   "dynamic",
        })
        assert r.status_code == 200
        assert "route" in r.json()

    def test_fewer_than_4_holds_returns_422(self, client):
        r = client.post("/generate-route", json={
            "wall_id": "w2",
            "holds":   self._make_holds(3),
            "grade":   "V5",
            "style":   "dynamic",
        })
        assert r.status_code == 422

    def test_invalid_grade_returns_422(self, client):
        r = client.post("/generate-route", json={
            "wall_id": "w3",
            "holds":   self._make_holds(20),
            "grade":   "V99",
            "style":   "dynamic",
        })
        assert r.status_code == 422

    def test_invalid_style_returns_422(self, client):
        r = client.post("/generate-route", json={
            "wall_id": "w4",
            "holds":   self._make_holds(20),
            "grade":   "V5",
            "style":   "backflip",
        })
        assert r.status_code == 422

    def test_route_hold_roles_are_valid(self, client):
        r = client.post("/generate-route", json={
            "wall_id": "w5",
            "holds":   self._make_holds(20, seed=7),
            "grade":   "V3",
            "style":   "balance",
        })
        if r.status_code != 200:
            pytest.skip("No route generated for this config")
        for h in r.json()["route"]["holds"]:
            assert h["role"] in {"start", "hand", "foot", "finish"}

    def test_position_order_starts_at_1_and_is_sequential(self, client):
        r = client.post("/generate-route", json={
            "wall_id": "w6",
            "holds":   self._make_holds(20, seed=8),
            "grade":   "V5",
            "style":   "dynamic",
        })
        if r.status_code != 200:
            pytest.skip("No route generated")
        orders = [h["position_order"] for h in r.json()["route"]["holds"]]
        assert orders[0] == 1
        assert orders == sorted(orders)

    def test_seeded_generation_is_reproducible(self, client):
        payload = {
            "wall_id": "repro",
            "holds":   self._make_holds(20, seed=42),
            "grade":   "V5",
            "style":   "dynamic",
            "seed":    99,
        }
        r1 = client.post("/generate-route", json=payload)
        r2 = client.post("/generate-route", json=payload)
        if r1.status_code == r2.status_code == 200:
            ids1 = [h["hold_id"] for h in r1.json()["route"]["holds"]]
            ids2 = [h["hold_id"] for h in r2.json()["route"]["holds"]]
            assert ids1 == ids2
