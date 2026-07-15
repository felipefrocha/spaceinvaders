"""Edge-branch coverage for the collision and scoring internals."""
from spaceinvaders.config import Config
from spaceinvaders.entities import Bullet, Enemy, ENEMY_OWNER
from spaceinvaders.world import GameWorld


def small_cfg(**kw):
    base = dict(enemy_rows=1, enemy_cols=1, enemy_fire_chance=0.0)
    base.update(kw)
    return Config(**base)


def test_resolve_skips_already_dead_bullets():
    w = GameWorld(small_cfg())
    enemy = w.enemies[0]
    dead_bullet = Bullet(x=enemy.x, y=enemy.y, vy=0.0, owner=0, alive=False)
    w.bullets = [dead_bullet]
    w._resolve_collisions()
    # Dead bullet must not damage the overlapping enemy.
    assert enemy.alive is True


def test_player_bullet_ignores_already_dead_enemy():
    w = GameWorld(small_cfg())
    enemy = w.enemies[0]
    enemy.alive = False
    bullet = Bullet(x=enemy.x, y=enemy.y, vy=0.0, owner=0)
    w.bullets = [bullet]
    w._resolve_collisions()
    assert bullet.alive is True  # nothing to hit
    assert w.players[0].score == 0


def test_enemy_bullet_ignores_already_dead_player():
    w = GameWorld(small_cfg())
    player = w.players[0]
    player.alive = False
    bullet = Bullet(x=player.x, y=player.y, vy=0.0, owner=ENEMY_OWNER)
    w.bullets = [bullet]
    w._resolve_collisions()
    assert bullet.alive is True  # dead player is not a target


def test_award_to_unknown_pid_is_ignored():
    w = GameWorld(small_cfg())
    scores_before = [p.score for p in w.players]
    w._award(999, 50)  # no such player -> loop exits without awarding
    assert [p.score for p in w.players] == scores_before
