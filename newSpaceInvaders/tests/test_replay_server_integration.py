import dataclasses

from spaceinvaders.config import Config
from spaceinvaders.input import Intent, encode_inputs
from spaceinvaders.replay import RoundRecord, replay, state_hash
from spaceinvaders.server import DT, Room


def small_cfg(**kw):
    base = dict(enemy_rows=1, enemy_cols=2, enemy_fire_chance=0.0)
    base.update(kw)
    return Config(**base)


def make_room(max_players, cfg=None, seed=1):
    """A Room with connected-but-not-networked slots, ready to step directly."""
    room = Room("integration", max_players=max_players, cfg=cfg or small_cfg(), seed=seed)
    for pid in range(max_players):
        room.connections[pid] = object()
        room.held[pid] = set()
        room.disconnect_time[pid] = None
        room.world.activate_player(pid)  # mirrors Room.join()'s first-join activation
    return room


def step_room_once(room):
    """Mirrors the body of Room.run()'s tick loop, minus broadcast/sleep/is_idle."""
    inputs = {pid: room.held.get(pid, frozenset()) for pid in room.connections}
    room.world.step(DT, inputs)
    room.tick += 1
    room.input_log.append((room.tick, encode_inputs(inputs)))


def record_from_room(room) -> RoundRecord:
    return RoundRecord(
        seed=room.seed,
        cfg=dataclasses.asdict(room.cfg),
        num_players=room.max_players,
        dt=DT,
        ticks=room.tick,
        input_log=room.input_log,
        # The participant roster = pids that ever joined (are in connections).
        # This is membership, NOT current alive state: a player who died in
        # combat mid-round is still an active participant and must replay as
        # active from tick 0, whereas a pid that never joined must not.
        active_pids=[pid for pid in range(room.max_players) if pid in room.connections],
    )


def test_replay_of_real_room_input_log_matches_room_state_hash():
    room = make_room(max_players=3, seed=123)
    for i in range(30):
        if i == 5:
            room.held[0] = {Intent.RIGHT}
        if i == 12:
            room.held[0] = set()
            room.held[1] = {Intent.LEFT, Intent.FIRE}
        if i == 20:
            room.held[1] = set()
        step_room_once(room)

    record = record_from_room(room)
    replayed_world = replay(record)

    assert state_hash(replayed_world) == state_hash(room.world)


def test_replay_of_real_room_input_log_matches_with_enemy_fire_enabled():
    room = make_room(max_players=2, cfg=small_cfg(enemy_fire_chance=5.0), seed=999)
    for _ in range(40):
        room.held[0] = {Intent.FIRE, Intent.RIGHT}
        room.held[1] = {Intent.LEFT}
        step_room_once(room)

    record = record_from_room(room)
    replayed_world = replay(record)

    assert state_hash(replayed_world) == state_hash(room.world)
    # Sanity check the scenario actually exercised RNG-driven enemy fire, so
    # this test would catch an RNG-ordering mismatch, not just a no-op replay.
    assert any(held for _, held in record.input_log)


def test_replay_matches_when_a_joined_pid_never_sends_any_input():
    room = make_room(max_players=3, seed=42)
    for i in range(15):
        if i == 3:
            room.held[0] = {Intent.RIGHT}
        step_room_once(room)
    # pid 1 and pid 2 joined (present in room.connections/held) but never
    # held anything the whole round -- confirm Room really produces the
    # "missing/empty per-tick entry" shape replay.py expects for a dormant pid.
    assert all(1 not in held and 2 not in held for _, held in room.input_log)

    record = record_from_room(room)
    replayed_world = replay(record)

    assert state_hash(replayed_world) == state_hash(room.world)


def test_replay_matches_with_a_never_joined_ghost_pid_present():
    # max_players=3 but only pid 0 ever joins -- pids 1 and 2 stay permanent
    # non-participants (never in room.connections), matching a real online
    # room where capacity exceeds headcount. This is the scenario
    # record_from_room's active_pids field exists for.
    room = Room("integration", max_players=3, cfg=small_cfg(), seed=55)
    room.connections[0] = object()
    room.held[0] = set()
    room.disconnect_time[0] = None
    room.world.activate_player(0)

    for i in range(20):
        room.held[0] = {Intent.RIGHT, Intent.FIRE}
        step_room_once(room)

    record = record_from_room(room)
    assert record.active_pids == [0]
    # The never-joined slots are absent from the snapshot entirely (not
    # rendered as phantom destroyed players), and the replay reproduces that.
    assert len(room.world.snapshot()["players"]) == 1
    replayed_world = replay(record)

    assert state_hash(replayed_world) == state_hash(room.world)


def test_active_pids_reflects_join_membership_not_current_alive_state():
    # A joined player who died in combat mid-round is still an active
    # participant -- they were active at round start and a replay must
    # reproduce that. active_pids keys off connections membership, not
    # .alive, since a real player's alive state changes through gameplay.
    room = make_room(max_players=2, seed=3)
    room.world.players[0].alive = False  # simulates dying in combat, still joined
    record = record_from_room(room)
    assert record.active_pids == [0, 1]


def test_replay_matches_when_a_player_disconnects_mid_round():
    room = make_room(max_players=3, seed=7)
    for i in range(20):
        room.held[0] = {Intent.RIGHT}
        if i == 8:
            room.leave(1)  # connections[1] -> None, held[1] cleared
        step_room_once(room)

    record = record_from_room(room)
    replayed_world = replay(record)

    assert state_hash(replayed_world) == state_hash(room.world)
