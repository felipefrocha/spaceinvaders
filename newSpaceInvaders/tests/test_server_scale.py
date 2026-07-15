import asyncio
import json

import websockets

from spaceinvaders import protocol
from spaceinvaders.config import Config
from spaceinvaders.server import start_server


def run(coro):
    return asyncio.run(coro)


def small_cfg(**kw):
    base = dict(enemy_rows=1, enemy_cols=2, enemy_fire_chance=0.0)
    base.update(kw)
    return Config(**base)


async def _start(max_players, cfg=None):
    srv = await start_server(host="127.0.0.1", port=0, max_players=max_players, cfg=cfg)
    port = srv.sockets[0].getsockname()[1]
    return srv, f"ws://127.0.0.1:{port}"


async def _stop(srv):
    srv.close()
    await srv.wait_closed()


async def _connect_and_join(uri, token=None, room=None):
    ws = await websockets.connect(uri)
    await ws.send(protocol.encode(
        {"type": "join", "name": None, "token": token, "room": room}))
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


def test_five_concurrent_joins_get_five_distinct_pids():
    async def scenario():
        srv, uri = await _start(max_players=5, cfg=small_cfg())
        try:
            results = await asyncio.gather(*(_connect_and_join(uri) for _ in range(5)))
            welcomes = [welcome for _, welcome in results]
            assert all(w["type"] == "welcome" for w in welcomes)
            assert sorted(w["pid"] for w in welcomes) == [0, 1, 2, 3, 4]

            for ws, _ in results:
                await ws.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_sixth_concurrent_join_to_full_room_is_rejected():
    async def scenario():
        srv, uri = await _start(max_players=5, cfg=small_cfg())
        try:
            results = await asyncio.gather(*(_connect_and_join(uri) for _ in range(5)))
            assert sorted(w["pid"] for _, w in results) == [0, 1, 2, 3, 4]

            ws6, welcome6 = await _connect_and_join(uri)
            assert welcome6["type"] == "error"
            assert "full" in welcome6["message"]

            for ws, _ in results:
                await ws.close()
            await ws6.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_concurrent_inputs_do_not_bleed_across_players():
    async def scenario():
        srv, uri = await _start(max_players=5, cfg=small_cfg())
        try:
            results = await asyncio.gather(*(_connect_and_join(uri) for _ in range(5)))
            by_pid = {welcome["pid"]: ws for ws, welcome in results}

            first_snaps = await asyncio.gather(
                *(_recv_until(ws, lambda o: o["type"] == "snapshot") for ws in by_pid.values()))
            x0_by_pid = {
                pid: next(p["x"] for p in snap["players"] if p["pid"] == pid)
                for pid, snap in zip(by_pid.keys(), first_snaps)
            }

            await by_pid[0].send(protocol.encode({"type": "input", "held": ["RIGHT"]}))
            await by_pid[1].send(protocol.encode({"type": "input", "held": ["LEFT"]}))

            # Drain a couple of broadcasts on every connection so all five
            # sockets are known to have observed at least two ticks each.
            for pid, ws in by_pid.items():
                for _ in range(2):
                    await _recv_until(ws, lambda o: o["type"] == "snapshot")

            final = await _recv_until(by_pid[0], lambda o: o["type"] == "snapshot")
            by_snapshot_pid = {p["pid"]: p for p in final["players"]}

            assert by_snapshot_pid[0]["x"] > x0_by_pid[0]
            assert by_snapshot_pid[1]["x"] < x0_by_pid[1]
            for pid in (2, 3, 4):
                assert by_snapshot_pid[pid]["x"] == x0_by_pid[pid]

            for ws in by_pid.values():
                await ws.close()
        finally:
            await _stop(srv)
    run(scenario())


def test_one_disconnect_mid_round_does_not_affect_the_other_four():
    async def scenario():
        srv, uri = await _start(max_players=5, cfg=small_cfg())
        try:
            results = await asyncio.gather(*(_connect_and_join(uri) for _ in range(5)))
            by_pid = {welcome["pid"]: ws for ws, welcome in results}

            await asyncio.gather(
                *(_recv_until(ws, lambda o: o["type"] == "snapshot") for ws in by_pid.values()))

            await by_pid[2].close()

            remaining = {pid: ws for pid, ws in by_pid.items() if pid != 2}
            snaps = await asyncio.gather(
                *(_recv_until(ws, lambda o: o["type"] == "snapshot") for ws in remaining.values()))

            for snap in snaps:
                assert snap["state"] == "RUNNING"
                alive_pids = {p["pid"] for p in snap["players"] if p["alive"]}
                assert {0, 1, 3, 4} <= alive_pids

            for ws in remaining.values():
                await ws.close()
        finally:
            await _stop(srv)
    run(scenario())
