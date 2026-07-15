from spaceinvaders.renderer import NullRenderer
from spaceinvaders.world import GameWorld


def test_null_renderer_draws_nothing():
    r = NullRenderer()
    assert r.draw(GameWorld().snapshot()) is None
