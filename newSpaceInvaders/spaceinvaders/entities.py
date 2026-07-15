"""Game entities — plain data + local update rules, no engine or I/O.

Entities depend only on :mod:`spaceinvaders.geometry` and read tuning values
from a :class:`~spaceinvaders.config.Config` passed in by the caller. They know
nothing about input, rendering, or the world that owns them, which is what
makes them trivially unit-testable.
"""
from dataclasses import dataclass, field

from .geometry import clamp

_DIAG = 0.7071067811865476  # 1/sqrt(2): normalise diagonal movement


@dataclass
class Player:
    pid: int
    x: float
    y: float
    speed: float
    fire_cooldown: float
    lives: int
    w: float = 20.0
    h: float = 20.0
    score: int = 0
    # `active` = is this slot a participant this round (someone is/was playing
    # it)? `alive` = has it survived combat? They are distinct: a never-joined
    # online slot is inactive (not simulated, not rendered, ignored by the
    # win/loss check), while a joined player who died is active-but-not-alive.
    # Offline play and tests leave every slot active (the default).
    active: bool = True
    alive: bool = True
    _cooldown_left: float = 0.0

    def step(self, move_x: float, move_y: float, dt: float, cfg) -> None:
        """Advance position by a (already sign-only) movement vector.

        ``move_x``/``move_y`` are each -1, 0 or 1; diagonals are normalised so
        players are not faster on the diagonal. Movement is clamped to the
        player band. The fire cooldown ticks down here too.
        """
        if move_x and move_y:
            move_x *= _DIAG
            move_y *= _DIAG
        self.x = clamp(self.x + move_x * self.speed * dt, cfg.min_x, cfg.max_x)
        self.y = clamp(self.y + move_y * self.speed * dt,
                       cfg.player_min_y, cfg.player_max_y)
        if self._cooldown_left > 0.0:
            self._cooldown_left = max(0.0, self._cooldown_left - dt)

    def try_fire(self) -> bool:
        """Fire if alive and off cooldown; return whether a shot was produced."""
        if not self.alive or self._cooldown_left > 0.0:
            return False
        self._cooldown_left = self.fire_cooldown
        return True

    def hit(self) -> None:
        """Absorb one enemy hit; die when out of lives."""
        if not self.alive:
            return
        self.lives -= 1
        if self.lives <= 0:
            self.lives = 0
            self.alive = False


@dataclass
class Enemy:
    x: float
    y: float
    w: float = 24.0
    h: float = 20.0
    alive: bool = True


@dataclass
class Bullet:
    x: float
    y: float
    vy: float          # signed vertical speed (units/second): +up, -down
    owner: int         # player pid (>= 0) or ENEMY_OWNER (-1)
    w: float = 4.0
    h: float = 12.0
    alive: bool = True

    def step(self, dt: float) -> None:
        self.y += self.vy * dt

    @property
    def is_player_bullet(self) -> bool:
        return self.owner >= 0


ENEMY_OWNER = -1
