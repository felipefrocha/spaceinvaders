"""Turtle backend — the only module that touches the screen.

This is intentionally thin: it owns a :class:`~spaceinvaders.engine.GameLoop`,
wires the two control schemes to Tk key events, and re-arms a single
``ontimer`` callback on the main thread. All game logic lives in the pure core,
so this file is excluded from unit-test coverage (it needs a live display).

Rendering uses a small pool of template turtles and ``stamp``/``clearstamps``
instead of creating a turtle per entity every frame, which keeps redraw cheap.
"""
import turtle

from .config import DT, Config
from .engine import GameLoop
from .input import KEYMAP_P1, KEYMAP_P2
from .world import GameWorld

TICK_MS = round(DT * 1000)  # ontimer granularity is integer ms (~30 FPS)

_COLORS = {
    "player": ("cyan", "royal blue"),
    "enemy": "red",
    "player_bullet": "yellow",
    "enemy_bullet": "orange",
}


class TurtleRenderer:
    def __init__(self, screen):
        self.screen = screen
        self._players = self._make_pen("square")
        self._enemies = self._make_pen("triangle")
        self._pbullets = self._make_pen("square")
        self._ebullets = self._make_pen("square")
        self._hud = turtle.Turtle(visible=False)
        self._hud.penup()
        self._hud.color("white")

    @staticmethod
    def _make_pen(shape):
        pen = turtle.Turtle(visible=False)
        pen.shape(shape)
        pen.penup()
        pen.speed(0)
        return pen

    def draw(self, snapshot):
        self.screen.tracer(0)
        for pen in (self._players, self._enemies, self._pbullets,
                    self._ebullets):
            pen.clearstamps()
        self._hud.clear()

        for i, p in enumerate(snapshot["players"]):
            if not p["alive"]:
                continue
            colors = _COLORS["player"]
            self._players.color(colors[i % len(colors)])
            self._players.goto(p["x"], p["y"])
            self._players.stamp()

        self._enemies.color(_COLORS["enemy"])
        for e in snapshot["enemies"]:
            self._enemies.goto(e["x"], e["y"])
            self._enemies.stamp()

        for b in snapshot["bullets"]:
            pen = self._pbullets if b["kind"] == "player" else self._ebullets
            pen.color(_COLORS["player_bullet"] if b["kind"] == "player"
                      else _COLORS["enemy_bullet"])
            pen.goto(b["x"], b["y"])
            pen.stamp()

        self._draw_hud(snapshot)
        self.screen.update()

    def _draw_hud(self, snapshot):
        parts = [f"P{p['pid'] + 1}  score {p['score']}  lives {p['lives']}"
                 for p in snapshot["players"]]
        line = "     ".join(parts)
        self._hud.goto(-290, 300)
        self._hud.write(line, font=("Courier", 14, "bold"))
        if snapshot["state"] != "RUNNING":
            self._hud.goto(0, 0)
            self._hud.color("lime" if snapshot["state"] == "WON" else "red")
            self._hud.write("VOCÊ VENCEU!" if snapshot["state"] == "WON"
                            else "FIM DE JOGO",
                            align="center", font=("Courier", 32, "bold"))
            self._hud.color("white")


def _bind_player(screen, loop, pid, keymap):
    for key in keymap:
        screen.onkeypress(lambda k=key, p=pid: loop.press(p, k), key)
        screen.onkeyrelease(lambda k=key, p=pid: loop.release(p, k), key)


def build_loop(cfg: Config = None):
    """Create screen, world, renderer and input bindings; return (screen, loop)."""
    screen = turtle.Screen()
    screen.setup(width=640, height=680)
    screen.bgcolor("black")
    screen.title("Space Invaders — 2 Players (WASD vs Arrows)")

    world = GameWorld(cfg or Config(), num_players=2)
    renderer = TurtleRenderer(screen)
    loop = GameLoop(world=world, renderer=renderer,
                    keymaps=(KEYMAP_P1, KEYMAP_P2))

    _bind_player(screen, loop, 0, KEYMAP_P1)
    _bind_player(screen, loop, 1, KEYMAP_P2)
    screen.listen()
    return screen, loop


def main():  # pragma: no cover - requires a display, exercised manually
    screen, loop = build_loop()

    def frame():
        loop.tick(DT)
        screen.ontimer(frame, TICK_MS)

    frame()
    screen.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
