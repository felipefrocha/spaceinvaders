"""Rendering seam.

The engine emits a plain-dict :meth:`~spaceinvaders.world.GameWorld.snapshot`
each frame; a renderer turns that into pixels. Keeping this an interface means
the simulation can run fully headless (tests, benchmarks, a future network
server) with :class:`NullRenderer`, while the turtle backend lives behind the
same contract in :mod:`spaceinvaders.turtle_app`.
"""


class Renderer:
    """Consumes a world snapshot. Subclasses do the actual drawing."""

    def draw(self, snapshot: dict) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class NullRenderer(Renderer):
    """A renderer that draws nothing — used for headless runs and tests."""

    def draw(self, snapshot: dict) -> None:
        return None
