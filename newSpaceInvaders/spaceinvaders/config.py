"""Immutable game tuning parameters.

Everything the simulation needs to know about the play field, entity sizes and
speeds lives here as a single frozen dataclass. Speeds are expressed in
*units per second* so the simulation is frame-rate independent: multiply by the
frame delta (``dt``) inside :mod:`spaceinvaders.world`.

Keeping this decoupled from the engine lets tests build a small, deterministic
world (few enemies, fast cooldowns) without touching the real defaults.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # Play-field bounds (screen is centred on the origin).
    min_x: float = -290.0
    max_x: float = 290.0
    min_y: float = -290.0
    max_y: float = 290.0

    # Vertical band the players are allowed to roam in.
    player_min_y: float = -290.0
    player_max_y: float = 0.0

    # Player ship.
    player_speed: float = 240.0          # units / second
    player_w: float = 20.0
    player_h: float = 20.0
    player_fire_cooldown: float = 0.35   # seconds between shots
    lives: int = 3

    # Bullets (shared by both sides; direction is per-bullet).
    bullet_speed: float = 420.0
    bullet_w: float = 4.0
    bullet_h: float = 12.0

    # Enemy formation.
    enemy_w: float = 24.0
    enemy_h: float = 20.0
    enemy_speed: float = 55.0            # horizontal units / second
    enemy_step_down: float = 22.0        # drop when the formation reverses
    enemy_rows: int = 3
    enemy_cols: int = 8
    enemy_gap_x: float = 46.0
    enemy_gap_y: float = 40.0
    enemy_top_y: float = 250.0
    enemy_fire_chance: float = 0.55      # expected shots / second across the swarm
    invasion_y: float = -230.0           # enemies reaching this line => players lose

    points_per_enemy: int = 10
