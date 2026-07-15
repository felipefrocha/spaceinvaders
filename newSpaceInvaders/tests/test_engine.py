import random

import pytest

from spaceinvaders.config import Config
from spaceinvaders.engine import GameLoop, run_headless
from spaceinvaders.input import Intent
from spaceinvaders.renderer import Renderer
from spaceinvaders.world import GameState, GameWorld


def small_cfg(**kw):
    base = dict(enemy_rows=1, enemy_cols=2, enemy_fire_chance=0.0)
    base.update(kw)
    return Config(**base)


class RecordingRenderer(Renderer):
    def __init__(self):
        self.snapshots = []

    def draw(self, snapshot):
        self.snapshots.append(snapshot)


def test_loop_routes_keys_to_the_right_player():
    loop = GameLoop(GameWorld(small_cfg()))
    # Player 0 uses WASD, player 1 uses arrows.
    loop.press(0, "d")
    loop.press(1, "Left")
    assert loop.inputs[0].held == {Intent.RIGHT}
    assert loop.inputs[1].held == {Intent.LEFT}
    loop.release(0, "d")
    assert loop.inputs[0].held == set()


def test_press_release_ignore_unknown_player():
    loop = GameLoop(GameWorld(small_cfg(), num_players=1))
    assert loop.press(9, "d") is None
    assert loop.release(9, "d") is None


def test_tick_advances_world_and_renders():
    world = GameWorld(small_cfg())
    renderer = RecordingRenderer()
    loop = GameLoop(world=world, renderer=renderer)
    loop.press(0, "d")
    x_before = world.players[0].x
    loop.tick(0.1)
    assert world.players[0].x > x_before
    assert len(renderer.snapshots) == 1
    assert renderer.snapshots[0]["state"] == "RUNNING"


def test_run_headless_stops_when_game_ends():
    world = GameWorld(small_cfg())
    for e in world.enemies:
        e.alive = False
    run_headless(world, steps=100, dt=0.1)
    assert world.state is GameState.WON


def test_run_headless_scripted_input_fires_a_bullet():
    world = GameWorld(small_cfg())
    run_headless(world, steps=3, dt=0.1,
                 inputs_by_step={0: {0: {Intent.FIRE}}})
    assert any(b.owner == 0 for b in world.bullets)


def test_run_headless_runs_all_steps_when_no_end():
    world = GameWorld(small_cfg())
    ticks = {"n": 0}
    original = world.step

    def counting_step(dt, inputs=None):
        ticks["n"] += 1
        original(dt, inputs)

    world.step = counting_step
    run_headless(world, steps=5, dt=0.01)
    assert ticks["n"] == 5


def test_renderer_base_class_is_abstract():
    with pytest.raises(NotImplementedError):
        Renderer().draw({})
