"""Multiplayer performance simulation — real rooms, real WebSocket clients.

This is not a correctness test (see tests/test_server_scale.py for that) — it
spins up the actual :mod:`spaceinvaders.server` and drives it with real
``websockets`` client connections on loopback, at realistic input cadence, to
measure the numbers "performance is a requirement" is actually about: whether
the 30 Hz tick loop keeps up under concurrent load, how steady the ~15 Hz
snapshot broadcast is, round-trip input latency (via the protocol's ping/pong),
and bandwidth per connection. All measured from the client side, deliberately —
a server whose event loop is falling behind shows up as growing ping RTT and
irregular snapshot gaps without needing to instrument the server itself.

Usage::

    python3 -m spaceinvaders.loadtest --rooms 5 --players-per-room 5 --duration 10
"""
import argparse
import asyncio
import json
import statistics
import time

import websockets

from . import protocol
from .config import Config
from .server import start_server

INPUT_INTERVAL_S = 0.033   # ~30/s, matches the client convention used elsewhere
PING_INTERVAL_S = 0.5

# A handful of held-intent patterns cycled per simulated player so the swarm
# sees varied, non-degenerate input rather than every player doing the same thing.
_INTENT_CYCLES = (
    (["LEFT"],),
    (["RIGHT"],),
    (["FIRE"],),
    (["LEFT", "FIRE"],),
    (["RIGHT", "FIRE"],),
)


class ClientStats:
    def __init__(self):
        self.rtts = []
        self.snapshot_gaps = []
        self.snapshot_bytes = []
        self.errors = 0
        self._last_snapshot_at = None

    def record_snapshot(self, raw_len):
        now = time.monotonic()
        if self._last_snapshot_at is not None:
            self.snapshot_gaps.append(now - self._last_snapshot_at)
        self._last_snapshot_at = now
        self.snapshot_bytes.append(raw_len)


async def _run_client(uri, room, stats: ClientStats, duration: float, cycle):
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(protocol.encode({"type": "join", "room": room}))
            welcome = json.loads(await ws.recv())
            if welcome["type"] != "welcome":
                stats.errors += 1
                return

            async def input_loop():
                i = 0
                while True:
                    await ws.send(protocol.encode({"type": "input", "held": cycle[i % len(cycle)]}))
                    i += 1
                    await asyncio.sleep(INPUT_INTERVAL_S)

            async def ping_loop():
                while True:
                    await ws.send(protocol.encode({"type": "ping", "t": time.monotonic()}))
                    await asyncio.sleep(PING_INTERVAL_S)

            async def receive_loop():
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg["type"] == "snapshot":
                        stats.record_snapshot(len(raw))
                    elif msg["type"] == "pong":
                        stats.rtts.append(time.monotonic() - msg["t"])

            tasks = [asyncio.create_task(input_loop()),
                    asyncio.create_task(ping_loop()),
                    asyncio.create_task(receive_loop())]
            try:
                await asyncio.sleep(duration)
            finally:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (websockets.ConnectionClosed, OSError):
        stats.errors += 1


async def _run_room(uri, room, players, duration):
    stats = [ClientStats() for _ in range(players)]
    await asyncio.gather(*(
        _run_client(uri, room, stats[i], duration, _INTENT_CYCLES[i % len(_INTENT_CYCLES)])
        for i in range(players)
    ))
    return stats


async def run(rooms: int, players_per_room: int, duration: float,
              max_players: int, host: str, port: int) -> dict:
    """Run the simulation and return a plain-dict report (also usable by tests)."""
    server = await start_server(host=host, port=port, max_players=max_players, cfg=Config())
    bound_port = server.sockets[0].getsockname()[1]
    uri = f"ws://{host}:{bound_port}"

    t0 = time.monotonic()
    try:
        room_results = await asyncio.gather(*(
            _run_room(uri, f"loadtest-{r}", players_per_room, duration)
            for r in range(rooms)
        ))
    finally:
        server.close()
        await server.wait_closed()
    wall = time.monotonic() - t0

    all_stats = [s for room in room_results for s in room]
    rtts = [r for s in all_stats for r in s.rtts]
    gaps = [g for s in all_stats for g in s.snapshot_gaps]
    sizes = [b for s in all_stats for b in s.snapshot_bytes]
    errors = sum(s.errors for s in all_stats)

    return {
        "connections": len(all_stats),
        "rooms": rooms,
        "players_per_room": players_per_room,
        "duration_s": duration,
        "wall_s": wall,
        "errors": errors,
        "rtt_ms": _summary(rtts, scale=1000),
        "snapshot_gap_ms": _summary(gaps, scale=1000),
        "snapshot_bytes": _summary(sizes, scale=1),
        "bandwidth_kb_per_s_total": (sum(sizes) / duration / 1024) if sizes else 0.0,
    }


def _summary(values, scale):
    if not values:
        return None
    scaled = sorted(v * scale for v in values)
    return {
        "n": len(scaled),
        "mean": statistics.mean(scaled),
        "p95": scaled[int(len(scaled) * 0.95)] if len(scaled) > 1 else scaled[0],
        "max": scaled[-1],
    }


def _print_report(report: dict) -> None:
    print("\n=== Space Invaders multiplayer load test ===")
    print(f"connections: {report['connections']} "
          f"({report['rooms']} rooms x {report['players_per_room']} players)")
    print(f"wall time: {report['wall_s']:.2f}s (target {report['duration_s']:.2f}s, "
          f"overhead {report['wall_s'] - report['duration_s']:+.2f}s)")
    print(f"errors: {report['errors']}")
    if report["rtt_ms"]:
        r = report["rtt_ms"]
        print(f"ping/pong RTT (ms): mean={r['mean']:.2f} p95={r['p95']:.2f} max={r['max']:.2f}")
    if report["snapshot_gap_ms"]:
        g = report["snapshot_gap_ms"]
        print(f"snapshot inter-arrival (ms): mean={g['mean']:.2f} p95={g['p95']:.2f} "
              f"max={g['max']:.2f}  (target ~66.7ms at 15Hz)")
    if report["snapshot_bytes"]:
        b = report["snapshot_bytes"]
        print(f"snapshot size (bytes): mean={b['mean']:.0f} max={b['max']:.0f}")
    print(f"aggregate downstream bandwidth: {report['bandwidth_kb_per_s_total']:.1f} KB/s")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Space Invaders multiplayer load simulation")
    parser.add_argument("--rooms", type=int, default=1)
    parser.add_argument("--players-per-room", type=int, default=5)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--max-players", type=int, default=5)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    if args.players_per_room > args.max_players:
        parser.error("--players-per-room cannot exceed --max-players")
    report = asyncio.run(run(args.rooms, args.players_per_room, args.duration,
                             args.max_players, args.host, args.port))
    _print_report(report)  # pragma: no cover - coverage loses trace after asyncio.run() returns here; verified executed via test_main_runs_end_to_end_and_prints_report's captured-output assertion


if __name__ == "__main__":  # pragma: no cover
    main()
