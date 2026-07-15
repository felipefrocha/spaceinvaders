from spaceinvaders.geometry import aabb_overlap, clamp


def test_clamp_below_within_above():
    assert clamp(-5, 0, 10) == 0
    assert clamp(5, 0, 10) == 5
    assert clamp(15, 0, 10) == 10


def test_clamp_boundaries_are_inclusive():
    assert clamp(0, 0, 10) == 0
    assert clamp(10, 0, 10) == 10


def test_aabb_overlap_true_when_boxes_intersect():
    assert aabb_overlap(0, 0, 10, 10, 4, 4, 10, 10) is True


def test_aabb_overlap_false_when_separated():
    assert aabb_overlap(0, 0, 10, 10, 100, 0, 10, 10) is False


def test_aabb_overlap_false_when_exactly_touching():
    # Centres 10 apart, half-widths sum to 10 -> touching, not overlapping.
    assert aabb_overlap(0, 0, 10, 10, 10, 0, 10, 10) is False
