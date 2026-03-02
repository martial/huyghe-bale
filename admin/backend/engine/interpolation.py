"""Interpolation functions for timeline curve evaluation.

All functions take a normalized t in [0, 1] and return a value in [0, 1]
representing the easing progress. The actual output value is then linearly
interpolated between the start and end point values.
"""

import math
from typing import Optional


def linear(t: float) -> float:
    return t


def step(t: float) -> float:
    return 0.0 if t < 1.0 else 1.0


def ease_in(t: float) -> float:
    return t * t


def ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2


def ease_in_out(t: float) -> float:
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def sine(t: float) -> float:
    return (1.0 - math.cos(t * math.pi)) / 2.0


def exponential(t: float) -> float:
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    return math.pow(2.0, 10.0 * (t - 1.0))


def bezier(t: float, handles: Optional[dict] = None) -> float:
    """Cubic bezier easing with control points.

    handles: {"x1": float, "y1": float, "x2": float, "y2": float}
    Control points for cubic bezier from (0,0) to (1,1).
    """
    if handles is None:
        return t  # Fallback to linear

    x1 = handles.get("x1", 0.25)
    y1 = handles.get("y1", 0.0)
    x2 = handles.get("x2", 0.75)
    y2 = handles.get("y2", 1.0)

    # Find t_bezier such that bezier_x(t_bezier) = t using Newton's method
    t_bezier = t  # Initial guess
    for _ in range(8):
        # Cubic bezier x(tb) = 3(1-tb)^2*tb*x1 + 3(1-tb)*tb^2*x2 + tb^3
        tb = t_bezier
        x = 3.0 * (1 - tb) ** 2 * tb * x1 + 3.0 * (1 - tb) * tb ** 2 * x2 + tb ** 3
        if abs(x - t) < 1e-7:
            break
        # Derivative dx/dtb
        dx = 3.0 * (1 - tb) ** 2 * x1 + 6.0 * (1 - tb) * tb * (x2 - x1) + 3.0 * tb ** 2 * (1 - x2)
        if abs(dx) < 1e-7:
            break
        t_bezier -= (x - t) / dx

    t_bezier = max(0.0, min(1.0, t_bezier))
    # Evaluate y at t_bezier
    tb = t_bezier
    return 3.0 * (1 - tb) ** 2 * tb * y1 + 3.0 * (1 - tb) * tb ** 2 * y2 + tb ** 3


INTERPOLATORS = {
    "linear": linear,
    "step": step,
    "ease-in": ease_in,
    "ease-out": ease_out,
    "ease-in-out": ease_in_out,
    "sine": sine,
    "exponential": exponential,
    "bezier": bezier,
}


def interpolate(t: float, curve_type: str, bezier_handles: Optional[dict] = None) -> float:
    """Evaluate an interpolation function at normalized t.

    Args:
        t: Normalized time in [0, 1].
        curve_type: One of the INTERPOLATORS keys.
        bezier_handles: Required if curve_type is "bezier".

    Returns:
        Easing progress in [0, 1].
    """
    t = max(0.0, min(1.0, t))
    func = INTERPOLATORS.get(curve_type, linear)
    if curve_type == "bezier":
        return func(t, bezier_handles)
    return func(t)


def evaluate_lane(points: list[dict], current_time: float) -> float:
    """Evaluate a lane's value at the given time.

    Args:
        points: Sorted list of point dicts with keys: time, value, curve_type, bezier_handles.
        current_time: Absolute time in seconds.

    Returns:
        Interpolated value in [0, 1].
    """
    if not points:
        return 0.0

    # After or at last point
    if current_time >= points[-1]["time"]:
        return points[-1]["value"]

    # Before first point
    if current_time <= points[0]["time"]:
        return points[0]["value"]

    # Find segment
    for i in range(len(points) - 1):
        p0 = points[i]
        p1 = points[i + 1]
        if p0["time"] <= current_time <= p1["time"]:
            segment_duration = p1["time"] - p0["time"]
            if segment_duration == 0:
                return p1["value"]
            t = (current_time - p0["time"]) / segment_duration
            eased = interpolate(t, p1["curve_type"], p1.get("bezier_handles"))
            return p0["value"] + (p1["value"] - p0["value"]) * eased

    return points[-1]["value"]
