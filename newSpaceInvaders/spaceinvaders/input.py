"""Input abstraction — the seam that decouples the game from the keyboard.

The simulation never sees raw key names. A backend (the turtle app, or a test)
translates physical keys through a *key map* into :class:`Intent` values and
feeds an :class:`InputState` per player. Holding a key keeps its intent in the
``held`` set, so continuous movement is just "is this intent held this tick?" —
O(1) per event, no polling, no threads.

Two default maps ship the requested control scheme:

* **Player 1** — ``W`` up, ``A`` left, ``S`` down, ``D`` right, ``space`` fire.
* **Player 2** — arrow keys to move, ``Return`` to fire.
"""
from enum import Enum


class Intent(Enum):
    """A backend-independent player action."""
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    FIRE = "fire"


# Physical-key -> Intent maps. Key names follow Tk's naming (used by turtle),
# but nothing here imports turtle, so any backend can reuse them.
KEYMAP_P1 = {
    "w": Intent.UP,
    "a": Intent.LEFT,
    "s": Intent.DOWN,
    "d": Intent.RIGHT,
    "space": Intent.FIRE,
}

KEYMAP_P2 = {
    "Up": Intent.UP,
    "Left": Intent.LEFT,
    "Down": Intent.DOWN,
    "Right": Intent.RIGHT,
    "Return": Intent.FIRE,
}

DEFAULT_KEYMAPS = (KEYMAP_P1, KEYMAP_P2)


def encode_inputs(inputs: dict) -> dict:
    """Encode a ``{pid: set(Intent)}`` tick's inputs into ``{pid: [name, ...]}``.

    This is the wire/log shape used by both ``server.Room.input_log`` and
    ``replay.RoundRecord.input_log`` — sharing one implementation is what
    keeps the two interchangeable (see ``replay.py``'s module docstring).
    A pid with an empty held-set is omitted entirely rather than written as
    ``[]``, so a pid absent from the result means "no input that tick", not
    an error.
    """
    return {
        pid: sorted(intent.name for intent in held)
        for pid, held in inputs.items() if held
    }


class InputState:
    """Tracks which intents are currently held for a single player.

    ``press``/``release`` take raw key names and resolve them through the map;
    unknown keys are ignored. ``held`` is read by the world each tick.
    """

    __slots__ = ("_keymap", "held")

    def __init__(self, keymap):
        self._keymap = dict(keymap)
        self.held = set()

    def press(self, key):
        intent = self._keymap.get(key)
        if intent is not None:
            self.held.add(intent)
        return intent

    def release(self, key):
        intent = self._keymap.get(key)
        if intent is not None:
            self.held.discard(intent)
        return intent

    def is_held(self, intent) -> bool:
        return intent in self.held

    def clear(self):
        self.held.clear()
