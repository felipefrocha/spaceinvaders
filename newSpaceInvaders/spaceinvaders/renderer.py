"""Rendering seam for the in-process path.

The engine emits a plain-dict :meth:`~spaceinvaders.world.GameWorld.snapshot`
each frame; a :class:`Renderer` turns that into pixels. Keeping it an interface
lets the offline loop run fully headless (tests, benchmarks) with
:class:`NullRenderer`, while the turtle backend draws behind the same contract
in :mod:`spaceinvaders.turtle_app`.

The online server does not use this interface: it *serialises* the same
``snapshot()`` dict and broadcasts it (see :mod:`spaceinvaders.server`), and
the remote client draws it. So the portable seam is ``snapshot()`` itself —
this ``Renderer`` interface is just the in-process consumer of it.
"""


class Renderer:
    """Consumes a world snapshot. Subclasses do the actual drawing."""

    def draw(self, snapshot: dict) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class NullRenderer(Renderer):
    """A renderer that draws nothing — used for headless runs and tests."""

    def draw(self, snapshot: dict) -> None:
        return None
