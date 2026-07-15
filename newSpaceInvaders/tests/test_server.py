import asyncio
import dataclasses
import json
import time

import pytest
import websockets

from spaceinvaders import protocol, server
from spaceinvaders.config import Config
from spaceinvaders.server import Room, RoomRegistry, start_server


def run(coro):
    return asyncio.run(coro)


async def _start(max_players=2, cfg=None):
    srv = await start_server(host="127.0.0.1", port=0, max_players=max_players, cfg=cfg)
    port = srv.sockets[0].getsockname()[1]
    return srv, f"ws://127.0.0.1:{port}"


async def _stop(srv):
    srv.close()
    await srv.wait_closed()


async def _connect_and_join(uri, name=None, token=None, room=None):
    ws = await websockets.connect(uri)
    await ws.send(protocol.encode(
        {"type": "join", "name": name, "token": token, "room": room}))
    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
    return ws, json.loads(raw)


async def _recv_until(ws, predicate, timeout=3.0):
    async def _loop():
        while True:
            raw = await ws.recv()
            obj = json.loads(raw)
            if predicate(obj):
                return obj
    return await asyncio.wait_for(_loop(), timeout=timeout)


def test_join_gets_welcome_pid_zero_with_expected_cfg_keys():
    async def scenario():
        srv, uri = await _start(max_players=2)
        try:
            ws, welcome = await _connect_and_join(uri)
            assert welcome["type"] == "welcome"
            assert welcome["pid"] == 0
            assert welcome["num_players"] == 2
            assert isinstance(welcome["token"], str) and welcome["token"]
            expected_keys = {f.name for f in dataclasses.fields(Config)}
            assert set(welcome["cfg"]) == expected_keys
            await ws.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_second_client_gets_pid_one_and_extra_client_gets_room_full_error():
    async def scenario():
        srv, uri = await _start(max_players=2)
        try:
            ws0, welcome0 = await _connect_and_join(uri)
            ws1, welcome1 = await _connect_and_join(uri)
            assert welcome0["pid"] == 0
            assert welcome1["pid"] == 1

            ws2 = await websockets.connect(uri)
            await ws2.send(protocol.encode(
                {"type": "join", "name": None, "token": None, "room": None}))
            raw = await asyncio.wait_for(ws2.recv(), timeout=2.0)
            obj = json.loads(raw)
            assert obj["type"] == "error"
            assert "full" in obj["message"]

            await ws0.close()
            await ws1.close()
            await ws2.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_independent_room_codes_full_room_a_does_not_block_room_b():
    async def scenario():
        srv, uri = await _start(max_players=1)
        try:
            ws_a, welcome_a = await _connect_and_join(uri, room="A")
            assert welcome_a["pid"] == 0

            ws_a2 = await websockets.connect(uri)
            await ws_a2.send(protocol.encode(
                {"type": "join", "name": None, "token": None, "room": "A"}))
            raw = await asyncio.wait_for(ws_a2.recv(), timeout=2.0)
            rejected = json.loads(raw)
            assert rejected["type"] == "error"

            ws_b, welcome_b = await _connect_and_join(uri, room="B")
            assert welcome_b["type"] == "welcome"
            assert welcome_b["pid"] == 0

            await ws_a.close()
            await ws_a2.close()
            await ws_b.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_input_moves_player_right():
    async def scenario():
        srv, uri = await _start(max_players=1)
        try:
            ws, welcome = await _connect_and_join(uri)
            first_snap = await _recv_until(ws, lambda o: o["type"] == "snapshot")
            x0 = first_snap["players"][0]["x"]

            await ws.send(protocol.encode({"type": "input", "held": ["RIGHT"]}))

            moved = False
            for _ in range(45):
                snap = await _recv_until(ws, lambda o: o["type"] == "snapshot")
                if snap["players"][0]["x"] > x0 + 1.0:
                    moved = True
                    break
            assert moved
            await ws.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_reconnect_with_same_token_reclaims_same_pid():
    async def scenario():
        srv, uri = await _start(max_players=1)
        try:
            ws1, welcome1 = await _connect_and_join(uri)
            token = welcome1["token"]
            pid = welcome1["pid"]
            await ws1.close()
            await asyncio.sleep(0.3)

            ws2, welcome2 = await _connect_and_join(uri, token=token)
            assert welcome2["pid"] == pid
            assert welcome2["type"] == "welcome"
            await ws2.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_reconnect_with_wrong_token_when_full_is_rejected_not_stolen():
    async def scenario():
        srv, uri = await _start(max_players=1)
        try:
            ws1, welcome1 = await _connect_and_join(uri)
            real_token = welcome1["token"]
            pid = welcome1["pid"]
            await ws1.close()
            await asyncio.sleep(0.3)

            ws_bad = await websockets.connect(uri)
            await ws_bad.send(protocol.encode(
                {"type": "join", "name": None, "token": "not-the-real-token", "room": None}))
            raw = await asyncio.wait_for(ws_bad.recv(), timeout=2.0)
            obj = json.loads(raw)
            assert obj["type"] == "error"
            await ws_bad.close()

            ws2, welcome2 = await _connect_and_join(uri, token=real_token)
            assert welcome2["pid"] == pid
            await ws2.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_malformed_frame_gets_error_and_connection_keeps_working():
    async def scenario():
        srv, uri = await _start(max_players=2)
        try:
            ws, welcome = await _connect_and_join(uri)
            await ws.send("not valid json {{{")
            err = await _recv_until(ws, lambda o: o["type"] == "error")
            assert "JSON" in err["message"] or "json" in err["message"]

            await ws.send(protocol.encode({"type": "ping", "t": 5.0}))
            pong = await _recv_until(ws, lambda o: o["type"] == "pong")
            assert pong["t"] == 5.0
            await ws.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_first_message_not_join_is_rejected_and_connection_closes():
    async def scenario():
        srv, uri = await _start(max_players=2)
        try:
            ws = await websockets.connect(uri)
            await ws.send(protocol.encode({"type": "ping", "t": 1.0}))
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            obj = json.loads(raw)
            assert obj["type"] == "error"
            assert "join" in obj["message"]
            with pytest.raises(websockets.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), timeout=2.0)
        finally:
            await _stop(srv)
    run(scenario())


def test_ping_gets_matching_pong():
    async def scenario():
        srv, uri = await _start(max_players=2)
        try:
            ws, welcome = await _connect_and_join(uri)
            await ws.send(protocol.encode({"type": "ping", "t": 9.5}))
            pong = await _recv_until(ws, lambda o: o["type"] == "pong")
            assert pong["t"] == 9.5
            await ws.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_join_timeout_sends_error_and_closes(monkeypatch):
    monkeypatch.setattr(server, "JOIN_TIMEOUT_SECONDS", 0.2)

    async def scenario():
        srv, uri = await _start(max_players=2)
        try:
            ws = await websockets.connect(uri)
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            obj = json.loads(raw)
            assert obj["type"] == "error"
        finally:
            await _stop(srv)
    run(scenario())


def test_max_players_is_clamped_to_valid_range():
    async def scenario():
        srv, uri = await _start(max_players=0)
        try:
            ws, welcome = await _connect_and_join(uri)
            assert welcome["num_players"] == server.MIN_PLAYERS
            await ws.close()
        finally:
            await _stop(srv)
    run(scenario())

    async def scenario_high():
        srv, uri = await _start(max_players=999)
        try:
            ws, welcome = await _connect_and_join(uri)
            assert welcome["num_players"] == server.MAX_PLAYERS
            await ws.close()
        finally:
            await _stop(srv)
    run(scenario_high())


def test_disconnect_broadcasts_player_left_to_remaining_player():
    async def scenario():
        srv, uri = await _start(max_players=2)
        try:
            ws0, welcome0 = await _connect_and_join(uri)
            ws1, welcome1 = await _connect_and_join(uri)
            await ws0.close()
            left = await _recv_until(ws1, lambda o: o["type"] == "player_left")
            assert left["pid"] == welcome0["pid"]
            await ws1.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_room_registry_reuses_existing_room_for_same_code():
    registry = RoomRegistry()
    r1 = registry.get_or_create("abc", max_players=2)
    r2 = registry.get_or_create("abc", max_players=2)
    assert r1 is r2


def test_room_registry_creates_distinct_rooms_for_distinct_codes():
    registry = RoomRegistry()
    r1 = registry.get_or_create("abc", max_players=2)
    r2 = registry.get_or_create("xyz", max_players=2)
    assert r1 is not r2
    assert r1.code == "abc"
    assert r2.code == "xyz"


def test_room_registry_remove_drops_the_room():
    registry = RoomRegistry()
    registry.get_or_create("abc", max_players=2)
    registry.remove("abc")
    assert "abc" not in registry.rooms
    registry.remove("does-not-exist")


def test_room_is_idle_false_with_no_connections_yet():
    room = Room("x", max_players=2)
    assert room.is_idle() is False


def test_room_is_idle_false_within_grace_window():
    room = Room("x", max_players=2)
    room.connections[0] = None
    room.disconnect_time[0] = time.monotonic()
    assert room.is_idle() is False


def test_room_is_idle_true_once_grace_window_elapses_for_all_pids():
    room = Room("x", max_players=2)
    room.connections[0] = None
    room.disconnect_time[0] = time.monotonic() - (server.ROOM_IDLE_SECONDS + 1)
    assert room.is_idle() is True


def test_room_is_idle_false_if_any_pid_still_connected():
    room = Room("x", max_players=2)
    room.connections[0] = None
    room.disconnect_time[0] = time.monotonic() - (server.ROOM_IDLE_SECONDS + 1)
    room.connections[1] = object()
    assert room.is_idle() is False


def test_free_pid_reclaims_slot_directly_after_grace_elapses():
    room = Room("x", max_players=1)
    room.connections[0] = None
    room.tokens[0] = "old-token"
    room.disconnect_time[0] = time.monotonic() - (server.RECONNECT_GRACE_SECONDS + 1)
    assert room._free_pid() == 0


def test_free_pid_does_not_reclaim_slot_within_grace_window():
    room = Room("x", max_players=1)
    room.connections[0] = None
    room.tokens[0] = "old-token"
    room.disconnect_time[0] = time.monotonic()
    assert room._free_pid() is None


def test_join_with_stale_token_past_grace_is_treated_as_a_new_join():
    room = Room("x", max_players=1)

    async def scenario():
        first_pid, first_token = await room.join(object(), None)
        room.leave(first_pid)
        room.disconnect_time[first_pid] = time.monotonic() - (server.RECONNECT_GRACE_SECONDS + 1)
        return first_pid, first_token, await room.join(object(), first_token)
    first_pid, first_token, (new_pid, new_token) = run(scenario())
    # The slot is still reclaimed (it's the only one), but as a fresh join —
    # the stale token no longer has special reconnect authority over it.
    assert new_pid == first_pid
    assert new_token != first_token


def test_join_with_correct_token_within_grace_reclaims_same_pid():
    room = Room("x", max_players=1)

    async def scenario():
        first_pid, first_token = await room.join(object(), None)
        room.leave(first_pid)
        return first_pid, first_token, await room.join(object(), first_token)
    first_pid, first_token, (reclaimed_pid, reclaimed_token) = run(scenario())
    assert reclaimed_pid == first_pid
    assert reclaimed_token == first_token


def test_new_player_can_claim_a_slot_abandoned_past_grace_with_no_token():
    room = Room("x", max_players=1)

    async def scenario():
        first_pid, _ = await room.join(object(), None)
        room.leave(first_pid)
        room.disconnect_time[first_pid] = time.monotonic() - (server.RECONNECT_GRACE_SECONDS + 1)
        return first_pid, await room.join(object(), None)
    first_pid, (new_pid, new_token) = run(scenario())
    assert new_pid == first_pid
    assert new_token is not None


def test_never_joined_slots_start_inactive():
    room = Room("x", max_players=3)
    # Slots nobody has joined are inactive (not participants) -- and so are
    # absent from the snapshot entirely rather than shown as phantom players.
    assert all(p.active is False for p in room.world.players)
    assert room.world.snapshot()["players"] == []


def test_player_becomes_active_on_first_join_only():
    room = Room("x", max_players=2)

    async def scenario():
        await room.join(object(), None)
    run(scenario())
    assert room.world.players[0].active is True
    assert room.world.players[1].active is False
    # Only the joined slot appears in the snapshot.
    assert [p["pid"] for p in room.world.snapshot()["players"]] == [0]


def test_lost_condition_does_not_wait_on_never_joined_ghost_slots():
    room = Room("x", max_players=3, cfg=Config(enemy_fire_chance=0.0, lives=1))

    async def scenario():
        return await room.join(object(), None)
    pid, _ = run(scenario())

    # Only pid joined; the other two never became active, so they must not
    # block the LOST condition once the one real participant dies.
    room.world.players[pid].hit()
    room.world.step(server.DT, {})

    assert room.world.state.name == "LOST"


def test_room_run_exits_immediately_when_already_idle():
    room = Room("x", max_players=1)
    room.connections[0] = None
    room.disconnect_time[0] = time.monotonic() - (server.ROOM_IDLE_SECONDS + 1)
    run(room.run())
    assert room.tick == 0


def test_room_broadcast_drops_pid_whose_send_raises_connection_closed():
    async def scenario():
        room = Room("x", max_players=2)

        class _DeadSocket:
            async def send(self, text):
                raise websockets.ConnectionClosed(None, None)

        room.connections[0] = _DeadSocket()
        room.connections[1] = None
        await room.broadcast("hello")
        assert room.connections[0] is None
        assert room.disconnect_time[0] is not None

    run(scenario())


def test_room_broadcast_reraises_unexpected_exception_not_swallowed_as_drop():
    async def scenario():
        room = Room("x", max_players=1)

        class _BrokenSocket:
            async def send(self, text):
                raise RuntimeError("boom")

        room.connections[0] = _BrokenSocket()
        with pytest.raises(RuntimeError, match="boom"):
            await room.broadcast("hello")
        # An unexpected error is not a normal disconnect -- the pid must
        # stay connected rather than silently being treated as dropped.
        assert room.connections[0] is not None

    run(scenario())


def test_room_broadcast_sends_to_all_targets_concurrently():
    async def scenario():
        room = Room("x", max_players=3)
        received = []

        class _RecordingSocket:
            def __init__(self, pid):
                self.pid = pid

            async def send(self, text):
                received.append(self.pid)

        room.connections[0] = _RecordingSocket(0)
        room.connections[1] = _RecordingSocket(1)
        room.connections[2] = None
        await room.broadcast("hello")
        assert sorted(received) == [0, 1]

    run(scenario())


def test_input_log_is_trimmed_once_it_exceeds_the_cap(monkeypatch):
    monkeypatch.setattr(server, "MAX_INPUT_LOG_ENTRIES", 10)
    room = Room("x", max_players=1)
    for room.tick in range(15):
        room._record_tick({})
    # No real 200,000-tick run needed to exercise the cap; confirms it
    # actually bounds growth and keeps the newest entries.
    assert len(room.input_log) <= 10
    assert room.input_log[-1][0] == 14


def test_second_join_message_mid_session_is_ignored_not_a_crash():
    async def scenario():
        srv, uri = await _start(max_players=2)
        try:
            ws, welcome = await _connect_and_join(uri)
            await ws.send(protocol.encode(
                {"type": "join", "name": None, "token": None, "room": None}))
            await ws.send(protocol.encode({"type": "ping", "t": 3.0}))
            pong = await _recv_until(ws, lambda o: o["type"] == "pong")
            assert pong["t"] == 3.0
            await ws.close()
        finally:
            await _stop(srv)
    run(scenario())


class _RaisingRecvSocket:
    async def recv(self):
        raise websockets.ConnectionClosed(None, None)


def test_handle_connection_swallows_connection_closed_on_initial_recv():
    async def scenario():
        registry = RoomRegistry()
        await server._handle_connection(_RaisingRecvSocket(), registry, 2, Config())
    run(scenario())


class _BadJoinThenDeadSendSocket:
    async def recv(self):
        return "not valid json {{{"

    async def send(self, text):
        raise websockets.ConnectionClosed(None, None)


def test_handle_connection_swallows_connection_closed_when_error_reply_also_fails():
    async def scenario():
        registry = RoomRegistry()
        await server._handle_connection(_BadJoinThenDeadSendSocket(), registry, 2, Config())
    run(scenario())


def test_handle_connection_swallows_connection_closed_from_player_left_broadcast(monkeypatch):
    original_broadcast = Room.broadcast
    calls = {"n": 0}

    async def flaky_broadcast(self, text):
        calls["n"] += 1
        if calls["n"] == 2:
            raise websockets.ConnectionClosed(None, None)
        return await original_broadcast(self, text)

    monkeypatch.setattr(Room, "broadcast", flaky_broadcast)
    monkeypatch.setattr(server, "ROOM_IDLE_SECONDS", -1.0)

    async def scenario():
        srv, uri = await _start(max_players=1)
        try:
            ws, welcome = await _connect_and_join(uri)  # 1st broadcast: player_joined
            await ws.close()  # triggers leave() -> 2nd broadcast (player_left) raises
            await asyncio.sleep(0.3)
        finally:
            await _stop(srv)
    run(scenario())
    assert calls["n"] >= 2


def test_run_forever_binds_prints_port_and_cleans_up_on_cancel(capsys):
    async def scenario():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(server._run_forever("127.0.0.1", 0, 2), timeout=0.3)
    run(scenario())
    captured = capsys.readouterr()
    assert "PORT=" in captured.out
    assert "Space Invaders server listening" in captured.out


def test_main_parses_args_and_invokes_run_forever(monkeypatch):
    calls = {}

    async def fake_run_forever(host, port, max_players):
        calls["args"] = (host, port, max_players)

    monkeypatch.setattr(server, "_run_forever", fake_run_forever)
    server.main(["--host", "127.0.0.1", "--port", "9999", "--max-players", "3"])
    assert calls["args"] == ("127.0.0.1", 9999, 3)


def test_main_uses_defaults_when_no_args_given(monkeypatch):
    calls = {}

    async def fake_run_forever(host, port, max_players):
        calls["args"] = (host, port, max_players)

    monkeypatch.setattr(server, "_run_forever", fake_run_forever)
    server.main([])
    assert calls["args"] == ("localhost", 8765, 2)
