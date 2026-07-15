import dataclasses

import pytest

from spaceinvaders.config import Config
from spaceinvaders.input import Intent
from spaceinvaders.replay import (
    from_json,
    main,
    record_headless,
    replay,
    state_hash,
    to_json,
)
from spaceinvaders.world import GameWorld


def small_cfg(**kw):
    base = dict(enemy_rows=1, enemy_cols=2, enemy_fire_chance=0.0)
    base.update(kw)
    return Config(**base)


def test_record_headless_produces_valid_record():
    cfg = small_cfg()
    record = record_headless(cfg, seed=1, num_players=2, dt=0.1, steps=5)
    assert record.seed == 1
    assert record.cfg == dataclasses.asdict(cfg)
    assert record.num_players == 2
    assert record.dt == 0.1
    assert record.ticks == 5
    assert record.final_hash is not None


def test_record_headless_logs_only_nonempty_holds():
    cfg = small_cfg()
    record = record_headless(cfg, seed=1, num_players=2, dt=0.1, steps=3,
                             inputs_by_step={1: {0: {Intent.FIRE}}})
    assert record.input_log == [(1, {}), (2, {0: ["FIRE"]}), (3, {})]


def test_record_headless_stops_early_when_game_ends():
    cfg = small_cfg(enemy_rows=0, enemy_cols=0)  # no enemies -> instant win
    record = record_headless(cfg, seed=1, num_players=2, dt=0.1, steps=100)
    assert record.ticks == 1


def test_replay_twice_yields_identical_hash():
    cfg = small_cfg(enemy_speed=50.0)
    record = record_headless(cfg, seed=7, num_players=2, dt=0.05, steps=20,
                             inputs_by_step={0: {0: {Intent.RIGHT, Intent.FIRE}}})
    hash_a = state_hash(replay(record))
    hash_b = state_hash(replay(record))
    assert hash_a == hash_b == record.final_hash


def test_tampered_input_log_changes_hash():
    cfg = small_cfg(enemy_speed=50.0)
    record = record_headless(cfg, seed=7, num_players=2, dt=0.05, steps=20,
                             inputs_by_step={0: {0: {Intent.RIGHT}}})
    original_hash = state_hash(replay(record))
    tampered = dataclasses.replace(record, input_log=[(1, {0: ["LEFT"]})])
    tampered_hash = state_hash(replay(tampered))
    assert tampered_hash != original_hash


def test_json_round_trip_preserves_equality():
    cfg = small_cfg()
    record = record_headless(cfg, seed=3, num_players=2, dt=0.1, steps=4,
                             inputs_by_step={0: {0: {Intent.FIRE}}})
    restored = from_json(to_json(record))
    assert restored == record


def test_empty_input_log_still_replays_and_moves_enemies():
    cfg = small_cfg(enemy_speed=50.0)
    record = record_headless(cfg, seed=5, num_players=2, dt=0.1, steps=5)
    assert all(held == {} for _, held in record.input_log)
    fresh_x = GameWorld(cfg).enemies[0].x
    world = replay(record)
    assert world.enemies[0].x != fresh_x


def test_state_hash_accepts_snapshot_dict_too():
    cfg = small_cfg()
    world = GameWorld(cfg)
    assert state_hash(world) == state_hash(world.snapshot())


def test_cli_record_demo_and_verify_round_trip(tmp_path, capsys):
    path = tmp_path / "demo.json"
    main(["--record-demo", str(path)])
    assert "wrote" in capsys.readouterr().out

    main(["--verify", str(path)])
    assert "OK" in capsys.readouterr().out


def test_cli_verify_detects_mismatch(tmp_path, capsys):
    path = tmp_path / "demo.json"
    main(["--record-demo", str(path)])
    capsys.readouterr()
    record = from_json(path.read_text())
    tampered = dataclasses.replace(record, final_hash="deadbeef")
    path.write_text(to_json(tampered))

    with pytest.raises(SystemExit):
        main(["--verify", str(path)])
    assert "MISMATCH" in capsys.readouterr().out


def test_cli_requires_one_of_record_or_verify():
    with pytest.raises(SystemExit):
        main([])
