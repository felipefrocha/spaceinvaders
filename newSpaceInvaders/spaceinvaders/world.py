"""The game engine — a pure, deterministic simulation.

:class:`GameWorld` owns all mutable state and advances it one fixed timestep at
a time via :meth:`step`. It has no threads, no locks and no rendering: a single
call chain per frame keeps everything on one execution path (the "performance is
a requirement" answer — the original spawned one thread + semaphore per entity).

Determinism is achieved by injecting the RNG, so tests can pin enemy fire and
target selection. Input arrives as ``{pid: set(Intent)}`` each tick, keeping the
engine independent of any keyboard backend. Rendering reads :meth:`snapshot`,
never the internal objects.
"""
import random
from enum import Enum

from .config import Config
from .entities import Bullet, Enemy, Player, ENEMY_OWNER
from .geometry import aabb_overlap
from .input import Intent


class GameState(Enum):
    RUNNING = "running"
    WON = "won"
    LOST = "lost"


_EMPTY_HELD = frozenset()


class GameWorld:
    def __init__(self, cfg: Config = None, rng: random.Random = None,
                 num_players: int = 2):
        self.cfg = cfg or Config()
        self.rng = rng or random.Random()
        self.num_players = num_players
        self.state = GameState.RUNNING
        self._enemy_dir = 1  # +1 => moving right, -1 => moving left
        self.players = self._spawn_players(num_players)
        self.enemies = self._spawn_formation()
        self.bullets = []

    # ------------------------------------------------------------------ setup
    def _spawn_players(self, num_players):
        cfg = self.cfg
        # Spread the ships evenly along the bottom band.
        span = cfg.max_x - cfg.min_x
        players = []
        for pid in range(num_players):
            frac = (pid + 1) / (num_players + 1)
            players.append(Player(
                pid=pid,
                x=cfg.min_x + span * frac,
                y=cfg.player_min_y + 40.0,
                speed=cfg.player_speed,
                fire_cooldown=cfg.player_fire_cooldown,
                lives=cfg.lives,
                w=cfg.player_w,
                h=cfg.player_h,
            ))
        return players

    def _spawn_formation(self):
        cfg = self.cfg
        enemies = []
        row_width = (cfg.enemy_cols - 1) * cfg.enemy_gap_x
        start_x = -row_width / 2.0
        for row in range(cfg.enemy_rows):
            y = cfg.enemy_top_y - row * cfg.enemy_gap_y
            for col in range(cfg.enemy_cols):
                enemies.append(Enemy(
                    x=start_x + col * cfg.enemy_gap_x,
                    y=y,
                    w=cfg.enemy_w,
                    h=cfg.enemy_h,
                ))
        return enemies

    # ----------------------------------------------------------------- per-tick
    def step(self, dt: float, inputs=None) -> None:
        """Advance the whole simulation by ``dt`` seconds."""
        if self.state is not GameState.RUNNING:
            return
        inputs = inputs or {}
        self._step_players(dt, inputs)
        self._step_enemies(dt)
        self._maybe_enemy_fire(dt)
        for bullet in self.bullets:
            bullet.step(dt)
        self._resolve_collisions()
        self._cull()
        self._check_end()

    def _step_players(self, dt, inputs):
        for player in self.players:
            if not player.alive:
                continue
            held = inputs.get(player.pid, _EMPTY_HELD)
            move_x, move_y = self._move_vector(held)
            player.step(move_x, move_y, dt, self.cfg)
            if Intent.FIRE in held and player.try_fire():
                self._spawn_player_bullet(player)

    @staticmethod
    def _move_vector(held):
        move_x = (Intent.RIGHT in held) - (Intent.LEFT in held)
        move_y = (Intent.UP in held) - (Intent.DOWN in held)
        return float(move_x), float(move_y)

    def _spawn_player_bullet(self, player):
        cfg = self.cfg
        self.bullets.append(Bullet(
            x=player.x,
            y=player.y + player.h,
            vy=cfg.bullet_speed,
            owner=player.pid,
            w=cfg.bullet_w,
            h=cfg.bullet_h,
        ))

    def _step_enemies(self, dt):
        living = [e for e in self.enemies if e.alive]
        if not living:
            return
        cfg = self.cfg
        dx = self._enemy_dir * cfg.enemy_speed * dt
        min_x = min(e.x for e in living)
        max_x = max(e.x for e in living)
        # Reverse + descend when the swarm's leading edge would leave the field.
        if max_x + dx > cfg.max_x or min_x + dx < cfg.min_x:
            self._enemy_dir *= -1
            for e in living:
                e.y -= cfg.enemy_step_down
        else:
            for e in living:
                e.x += dx

    def _maybe_enemy_fire(self, dt):
        living = [e for e in self.enemies if e.alive]
        if not living:
            return
        expected = self.cfg.enemy_fire_chance * dt
        if self.rng.random() < expected:
            shooter = self.rng.choice(living)
            self.bullets.append(Bullet(
                x=shooter.x,
                y=shooter.y - shooter.h,
                vy=-self.cfg.bullet_speed,
                owner=ENEMY_OWNER,
                w=self.cfg.bullet_w,
                h=self.cfg.bullet_h,
            ))

    def _resolve_collisions(self):
        for bullet in self.bullets:
            if not bullet.alive:
                continue
            if bullet.is_player_bullet:
                self._player_bullet_vs_enemies(bullet)
            else:
                self._enemy_bullet_vs_players(bullet)

    def _player_bullet_vs_enemies(self, bullet):
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            if aabb_overlap(bullet.x, bullet.y, bullet.w, bullet.h,
                            enemy.x, enemy.y, enemy.w, enemy.h):
                enemy.alive = False
                bullet.alive = False
                self._award(bullet.owner, self.cfg.points_per_enemy)
                return

    def _enemy_bullet_vs_players(self, bullet):
        for player in self.players:
            if not player.alive:
                continue
            if aabb_overlap(bullet.x, bullet.y, bullet.w, bullet.h,
                            player.x, player.y, player.w, player.h):
                player.hit()
                bullet.alive = False
                return

    def _award(self, pid, points):
        for player in self.players:
            if player.pid == pid:
                player.score += points
                return

    def _cull(self):
        cfg = self.cfg
        alive = []
        for bullet in self.bullets:
            if not bullet.alive:
                continue
            if cfg.min_y <= bullet.y <= cfg.max_y:
                alive.append(bullet)
        self.bullets = alive

    def _check_end(self):
        if all(not e.alive for e in self.enemies):
            self.state = GameState.WON
            return
        if all(not p.alive for p in self.players):
            self.state = GameState.LOST
            return
        if any(e.alive and e.y <= self.cfg.invasion_y for e in self.enemies):
            self.state = GameState.LOST

    # ------------------------------------------------------------------ output
    @property
    def enemies_alive(self) -> int:
        return sum(1 for e in self.enemies if e.alive)

    def snapshot(self) -> dict:
        """Render-friendly, backend-independent view of the current frame."""
        return {
            "state": self.state.name,
            "players": [
                {"pid": p.pid, "x": p.x, "y": p.y, "alive": p.alive,
                 "lives": p.lives, "score": p.score}
                for p in self.players
            ],
            "enemies": [
                {"x": e.x, "y": e.y} for e in self.enemies if e.alive
            ],
            "bullets": [
                {"x": b.x, "y": b.y,
                 "kind": "player" if b.is_player_bullet else "enemy"}
                for b in self.bullets
            ],
        }
