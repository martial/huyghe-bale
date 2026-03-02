"""Tests for the interpolation engine."""

import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.interpolation import (
    linear, step, ease_in, ease_out, ease_in_out,
    sine, exponential, bezier, interpolate, evaluate_lane,
)


class TestBasicCurves:
    def test_linear(self):
        assert linear(0.0) == 0.0
        assert linear(0.5) == 0.5
        assert linear(1.0) == 1.0

    def test_step(self):
        assert step(0.0) == 0.0
        assert step(0.5) == 0.0
        assert step(0.99) == 0.0
        assert step(1.0) == 1.0

    def test_ease_in(self):
        assert ease_in(0.0) == 0.0
        assert ease_in(1.0) == 1.0
        # Should be below linear at midpoint
        assert ease_in(0.5) < 0.5

    def test_ease_out(self):
        assert ease_out(0.0) == 0.0
        assert ease_out(1.0) == 1.0
        # Should be above linear at midpoint
        assert ease_out(0.5) > 0.5

    def test_ease_in_out(self):
        assert ease_in_out(0.0) == 0.0
        assert ease_in_out(1.0) == 1.0
        assert ease_in_out(0.5) == pytest.approx(0.5, abs=0.01)

    def test_sine(self):
        assert sine(0.0) == pytest.approx(0.0, abs=1e-10)
        assert sine(1.0) == pytest.approx(1.0, abs=1e-10)
        assert sine(0.5) == pytest.approx(0.5, abs=0.01)

    def test_exponential(self):
        assert exponential(0.0) == 0.0
        assert exponential(1.0) == 1.0
        # Should be very small near start
        assert exponential(0.1) < 0.01

    def test_bezier_default(self):
        # No handles = linear fallback
        assert bezier(0.0) == pytest.approx(0.0, abs=0.01)
        assert bezier(1.0) == pytest.approx(1.0, abs=0.01)

    def test_bezier_with_handles(self):
        handles = {"x1": 0.42, "y1": 0.0, "x2": 0.58, "y2": 1.0}
        assert bezier(0.0, handles) == pytest.approx(0.0, abs=0.01)
        assert bezier(1.0, handles) == pytest.approx(1.0, abs=0.01)
        # Midpoint should be approximately 0.5
        mid = bezier(0.5, handles)
        assert 0.2 < mid < 0.8


class TestInterpolate:
    def test_dispatch(self):
        assert interpolate(0.5, "linear") == 0.5
        assert interpolate(0.5, "step") == 0.0
        assert interpolate(0.5, "ease-in") < 0.5

    def test_clamp(self):
        assert interpolate(-0.5, "linear") == 0.0
        assert interpolate(1.5, "linear") == 1.0

    def test_unknown_type_falls_back_to_linear(self):
        assert interpolate(0.5, "nonexistent") == 0.5


class TestEvaluateLane:
    def test_empty_points(self):
        assert evaluate_lane([], 5.0) == 0.0

    def test_before_first(self):
        points = [{"time": 10, "value": 0.5, "curve_type": "linear"}]
        assert evaluate_lane(points, 0.0) == 0.5

    def test_after_last(self):
        points = [
            {"time": 0, "value": 0.0, "curve_type": "linear"},
            {"time": 10, "value": 1.0, "curve_type": "linear"},
        ]
        assert evaluate_lane(points, 20.0) == 1.0

    def test_linear_midpoint(self):
        points = [
            {"time": 0, "value": 0.0, "curve_type": "linear"},
            {"time": 10, "value": 1.0, "curve_type": "linear"},
        ]
        assert evaluate_lane(points, 5.0) == pytest.approx(0.5, abs=0.01)

    def test_three_points(self):
        points = [
            {"time": 0, "value": 0.0, "curve_type": "linear"},
            {"time": 30, "value": 1.0, "curve_type": "linear"},
            {"time": 60, "value": 0.0, "curve_type": "linear"},
        ]
        assert evaluate_lane(points, 0.0) == pytest.approx(0.0)
        assert evaluate_lane(points, 15.0) == pytest.approx(0.5, abs=0.01)
        assert evaluate_lane(points, 30.0) == pytest.approx(1.0, abs=0.01)
        assert evaluate_lane(points, 45.0) == pytest.approx(0.5, abs=0.01)
        assert evaluate_lane(points, 60.0) == pytest.approx(0.0, abs=0.01)

    def test_step_curve(self):
        points = [
            {"time": 0, "value": 0.0, "curve_type": "linear"},
            {"time": 10, "value": 1.0, "curve_type": "step"},
        ]
        # Step holds previous value until the exact endpoint
        assert evaluate_lane(points, 5.0) == pytest.approx(0.0, abs=0.01)
        assert evaluate_lane(points, 10.0) == pytest.approx(1.0, abs=0.01)

    def test_zero_duration_segment(self):
        points = [
            {"time": 5, "value": 0.0, "curve_type": "linear"},
            {"time": 5, "value": 1.0, "curve_type": "linear"},
        ]
        assert evaluate_lane(points, 5.0) == 1.0
