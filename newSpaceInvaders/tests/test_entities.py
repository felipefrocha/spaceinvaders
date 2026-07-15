import math

from spaceinvaders.config import Config
from spaceinvaders.entities import Bullet, Enemy, Player, ENEMY_OWNER


def make_player(**kw):
    defaults = dict(pid=0, x=0.0, y=-200.0, speed=100.0,
                    fire_cooldown=0.5, lives=3)
    defaults.update(kw)
    return Player(**defaults)


def test_player_moves_by_speed_times_dt():
    cfg = Config()
    p = make_player(x=0.0, y=-200.0, speed=100.0)
    p.step(1.0, 0.0, 0.5, cfg)   # +x for half a second at 100 u/s -> +50
    assert p.x == 50.0
    assert p.y == -200.0


def test_player_movement_is_clamped_to_bounds():
    cfg = Config()
    p = make_player(x=cfg.max_x - 1.0, speed=1000.0)
    p.step(1.0, 0.0, 1.0, cfg)
    assert p.x == cfg.max_x

    p2 = make_player(y=cfg.player_max_y - 1.0, speed=1000.0)
    p2.step(0.0, 1.0, 1.0, cfg)
    assert p2.y == cfg.player_max_y


def test_diagonal_movement_is_normalised():
    cfg = Config()
    p = make_player(x=0.0, y=-100.0, speed=100.0)
    p.step(1.0, 1.0, 1.0, cfg)
    assert math.isclose(p.x, 100.0 * (1 / math.sqrt(2)), rel_tol=1e-9)
    assert math.isclose(p.y, -100.0 + 100.0 * (1 / math.sqrt(2)), rel_tol=1e-9)


def test_fire_respects_cooldown():
    p = make_player(fire_cooldown=1.0)
    assert p.try_fire() is True      # first shot
    assert p.try_fire() is False     # still cooling down
    p.step(0.0, 0.0, 1.0, Config())  # advance cooldown by 1s
    assert p.try_fire() is True


def test_dead_player_cannot_fire():
    p = make_player(lives=1)
    p.hit()
    assert p.alive is False
    assert p.try_fire() is False


def test_hit_decrements_lives_then_kills():
    p = make_player(lives=2)
    p.hit()
    assert p.lives == 1 and p.alive is True
    p.hit()
    assert p.lives == 0 and p.alive is False
    p.hit()  # no-op once dead
    assert p.lives == 0 and p.alive is False


def test_bullet_moves_along_velocity():
    b = Bullet(x=0.0, y=0.0, vy=100.0, owner=0)
    b.step(0.5)
    assert b.y == 50.0
    assert b.is_player_bullet is True


def test_enemy_bullet_flag():
    b = Bullet(x=0.0, y=0.0, vy=-100.0, owner=ENEMY_OWNER)
    assert b.is_player_bullet is False


def test_enemy_defaults_alive():
    e = Enemy(x=1.0, y=2.0)
    assert e.alive is True
