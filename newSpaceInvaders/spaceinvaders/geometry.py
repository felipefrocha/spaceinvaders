"""Tiny, dependency-free geometry helpers used across the simulation.

Positions are treated as *centres*; sizes are full width/height. Kept separate
so both entities and the world collision pass share one definition of "overlap".
"""


def clamp(value: float, low: float, high: float) -> float:
    """Constrain ``value`` to the inclusive ``[low, high]`` range."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def aabb_overlap(ax: float, ay: float, aw: float, ah: float,
                 bx: float, by: float, bw: float, bh: float) -> bool:
    """Axis-aligned bounding-box overlap test for two centre-anchored boxes."""
    return (abs(ax - bx) * 2.0 < (aw + bw)) and (abs(ay - by) * 2.0 < (ah + bh))
