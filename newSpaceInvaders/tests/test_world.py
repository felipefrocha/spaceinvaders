import random

from spaceinvaders.config import Config
from spaceinvaders.entities import Bullet, Enemy, ENEMY_OWNER
from spaceinvaders.input import Intent
from spaceinvaders.world import GameState, GameWorld


def small_cfg(**kw):
    base = dict(enemy_rows=1, enemy_cols=2, enemy_top_y=200.0,
                enemy_fire_chance=0.0)
    base.update(kw)
    return Config(**base)


def test_spawns_two_players_by_default():
    w = GameWorld(small_cfg())
    assert len(w.players) == 2
    assert [p.pid for p in w.players] == [0, 1]
    # Player 0 sits left of player 1.
    assert w.players[0].x < w.players[1].x


def test_formation_size_matches_rows_times_cols():
    w = GameWorld(Config(enemy_rows=3, enemy_cols=8, enemy_fire_chance=0.0))
    assert len(w.enemies) == 24
    assert w.enemies_alive == 24


def test_move_vector_combines_axes():
    assert GameWorld._move_vector({Intent.RIGHT}) == (1.0, 0.0)
    assert GameWorld._move_vector({Intent.LEFT}) == (-1.0, 0.0)
    assert GameWorld._move_vector({Intent.UP}) == (0.0, 1.0)
    assert GameWorld._move_vector({Intent.DOWN}) == (0.0, -1.0)
    assert GameWorld._move_vector({Intent.LEFT, Intent.RIGHT}) == (0.0, 0.0)


def test_firing_creates_upward_player_bullet():
    w = GameWorld(small_cfg())
    w.step(0.1, {0: {Intent.FIRE}})
    player_bullets = [b for b in w.bullets if b.is_player_bullet]
    assert len(player_bullets) == 1
    assert player_bullets[0].vy > 0
    assert player_bullets[0].owner == 0


def test_fire_cooldown_prevents_double_shot_same_frame_run():
    w = GameWorld(small_cfg(player_fire_cooldown=10.0))
    w.step(0.1, {0: {Intent.FIRE}})
    w.step(0.1, {0: {Intent.FIRE}})
    assert sum(1 for b in w.bullets if b.owner == 0) == 1


def test_player_bullet_destroys_enemy_and_awards_score():
    w = GameWorld(small_cfg())
    enemy = w.enemies[0]
    w.bullets.append(Bullet(x=enemy.x, y=enemy.y, vy=0.0, owner=0))
    w._resolve_collisions()
    assert enemy.alive is False
    assert w.players[0].score == w.cfg.points_per_enemy
    assert w.bullets[0].alive is False


def test_enemy_bullet_hits_player_and_reduces_lives():
    w = GameWorld(small_cfg())
    player = w.players[1]
    start_lives = player.lives
    w.bullets.append(Bullet(x=player.x, y=player.y, vy=0.0, owner=ENEMY_OWNER))
    w._resolve_collisions()
    assert player.lives == start_lives - 1
    assert w.bullets[0].alive is False


def test_enemies_reverse_and_descend_at_edge():
    cfg = small_cfg(enemy_speed=100.0, enemy_step_down=20.0)
    w = GameWorld(cfg)
    w.enemies = [Enemy(x=cfg.max_x - 1.0, y=100.0)]
    w._enemy_dir = 1
    w._step_enemies(1.0)  # dx = +100 would overshoot max_x
    assert w._enemy_dir == -1
    assert w.enemies[0].y == 80.0
    assert w.enemies[0].x == cfg.max_x - 1.0  # x unchanged on the reversing tick


def test_enemies_march_horizontally_within_bounds():
    cfg = small_cfg(enemy_speed=10.0)
    w = GameWorld(cfg)
    w.enemies = [Enemy(x=0.0, y=100.0)]
    w._enemy_dir = 1
    w._step_enemies(1.0)
    assert w.enemies[0].x == 10.0
    assert w.enemies[0].y == 100.0


def test_enemy_fire_is_deterministic_with_seeded_rng():
    cfg = small_cfg(enemy_fire_chance=1000.0)  # chance*dt >> 1 -> always fires
    w = GameWorld(cfg, rng=random.Random(1234))
    w._maybe_enemy_fire(0.1)
    enemy_bullets = [b for b in w.bullets if not b.is_player_bullet]
    assert len(enemy_bullets) == 1
    assert enemy_bullets[0].vy < 0


def test_no_enemy_fire_when_chance_zero():
    w = GameWorld(small_cfg(enemy_fire_chance=0.0), rng=random.Random(0))
    w._maybe_enemy_fire(0.1)
    assert w.bullets == []


def test_win_when_all_enemies_dead():
    w = GameWorld(small_cfg())
    for e in w.enemies:
        e.alive = False
    w.step(0.1)
    assert w.state is GameState.WON


def test_loss_when_all_players_dead():
    w = GameWorld(small_cfg())
    for p in w.players:
        p.alive = False
    w.step(0.1)
    assert w.state is GameState.LOST


def test_loss_when_enemy_reaches_invasion_line():
    cfg = small_cfg(invasion_y=-100.0)
    w = GameWorld(cfg)
    w.enemies = [Enemy(x=0.0, y=cfg.invasion_y - 5.0)]
    w.step(0.1)
    assert w.state is GameState.LOST


def test_step_is_noop_once_game_ended():
    w = GameWorld(small_cfg())
    w.state = GameState.WON
    w.step(0.1, {0: {Intent.FIRE}})
    assert w.bullets == []


def test_cull_removes_offscreen_and_dead_bullets():
    cfg = small_cfg()
    w = GameWorld(cfg)
    keep = Bullet(x=0.0, y=0.0, vy=0.0, owner=0)
    offscreen = Bullet(x=0.0, y=cfg.max_y + 100.0, vy=0.0, owner=0)
    dead = Bullet(x=0.0, y=0.0, vy=0.0, owner=0, alive=False)
    w.bullets = [keep, offscreen, dead]
    w._cull()
    assert w.bullets == [keep]


def test_snapshot_shape():
    w = GameWorld(small_cfg())
    w.bullets.append(Bullet(x=1.0, y=2.0, vy=1.0, owner=0))
    w.bullets.append(Bullet(x=3.0, y=4.0, vy=-1.0, owner=ENEMY_OWNER))
    snap = w.snapshot()
    assert snap["state"] == "RUNNING"
    assert len(snap["players"]) == 2
    assert set(snap["players"][0]) == {"pid", "x", "y", "alive", "lives", "score"}
    assert len(snap["enemies"]) == w.enemies_alive
    kinds = sorted(b["kind"] for b in snap["bullets"])
    assert kinds == ["enemy", "player"]


def test_single_player_configuration():
    w = GameWorld(small_cfg(), num_players=1)
    assert len(w.players) == 1
