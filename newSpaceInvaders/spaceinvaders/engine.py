"""Frame driving, independent of any windowing backend.

:class:`GameLoop` ties together a world, the per-player input states and a
renderer, and exposes a single :meth:`tick` that a real backend calls from a
timer (see :mod:`spaceinvaders.turtle_app`). Because ``tick`` takes an explicit
``dt`` and never touches the clock or the screen, the exact same loop can be
driven synchronously in a test or a benchmark via :func:`run_headless`.
"""
from .input import DEFAULT_KEYMAPS, InputState
from .renderer import NullRenderer
from .world import GameWorld


class GameLoop:
    def __init__(self, world: GameWorld = None, renderer=None, keymaps=None):
        self.world = world or GameWorld()
        self.renderer = renderer or NullRenderer()
        keymaps = keymaps or DEFAULT_KEYMAPS
        # One InputState per player, keyed by pid for O(1) lookup each tick.
        self.inputs = {
            player.pid: InputState(keymaps[player.pid % len(keymaps)])
            for player in self.world.players
        }

    # --- input plumbing: a backend forwards raw key events straight through ---
    def press(self, pid: int, key: str):
        state = self.inputs.get(pid)
        return state.press(key) if state else None

    def release(self, pid: int, key: str):
        state = self.inputs.get(pid)
        return state.release(key) if state else None

    def _held_by_pid(self):
        return {pid: state.held for pid, state in self.inputs.items()}

    def tick(self, dt: float) -> None:
        """Advance the world one frame and render the result."""
        self.world.step(dt, self._held_by_pid())
        self.renderer.draw(self.world.snapshot())


def run_headless(world: GameWorld, steps: int, dt: float,
                 inputs_by_step=None) -> GameWorld:
    """Advance ``world`` ``steps`` times with no rendering.

    ``inputs_by_step`` optionally maps a step index to a ``{pid: set(Intent)}``
    dict, letting tests script inputs on specific frames. Returns the world so
    callers can assert on its final state. Stops early once the game ends.
    """
    inputs_by_step = inputs_by_step or {}
    for i in range(steps):
        if world.state.value != "running":
            break
        world.step(dt, inputs_by_step.get(i))
    return world
