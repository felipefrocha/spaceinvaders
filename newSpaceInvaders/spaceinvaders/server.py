"""Authoritative multiplayer server — reuses the sim core unchanged.

A :class:`Room` owns exactly one :class:`~spaceinvaders.world.GameWorld` and
drives it with the same ``step(dt, inputs)`` call the offline turtle client
uses (see :mod:`spaceinvaders.engine`); only the source of ``inputs`` and the
destination of ``snapshot()`` differ. The simulation tick (30 Hz) is
decoupled from the network send rate (every other tick, ~15 Hz) so one slow
connection never stalls the room.

This is also the process Electron spawns locally for **offline** play
(``--port 0``, single machine, no real network): offline and online play run
through the exact same protocol and tick loop, which is the point — there is
only one game engine, ever.

Wire format is :mod:`spaceinvaders.protocol` (plain, allow-listed JSON) —
this is the direct, safety-motivated replacement for the legacy
``logServer.py``, which deserialized arbitrary network bytes with
``pickle.loads()``.
"""
import argparse
import asyncio
import dataclasses
import random
import secrets
import time

import websockets

from . import protocol
from .config import Config
from .input import encode_inputs
from .world import GameWorld

TICK_HZ = 30
DT = 1.0 / TICK_HZ
SEND_EVERY_N_TICKS = 2          # ~15 Hz snapshot broadcast
RECONNECT_GRACE_SECONDS = 30.0  # a disconnected pid's slot stays reclaimable
ROOM_IDLE_SECONDS = 60.0        # room is torn down once idle this long
MIN_PLAYERS = 1
MAX_PLAYERS = 5
JOIN_TIMEOUT_SECONDS = 10.0
# Caps Room.input_log's memory for a pathologically long-lived room (~3+
# hours of continuous ticks at 30Hz); irrelevant for any realistic session.
# Trimmed in a batch, not one entry at a time, so the amortized per-tick
# cost stays O(1) instead of shifting the whole list on every append.
MAX_INPUT_LOG_ENTRIES = 200_000


class Room:
    """One authoritative round: one :class:`GameWorld`, up to ``max_players``.

    Player slots are fixed at room creation (``GameWorld`` sizes ship spacing
    from ``num_players`` at construction), so ``max_players`` is the room's
    capacity, not a live headcount. A slot that has never been claimed by a
    connection starts out ``alive=False`` (a "ghost" is not a participant, so
    it can't be hit and doesn't block the LOST condition) and only becomes a
    real, live player the moment someone actually joins that pid.

    A disconnected player's slot is held open for
    :data:`RECONNECT_GRACE_SECONDS` and reclaimed by presenting the same
    session token; once that window elapses, the slot — and whatever game
    state its player was left in — becomes available to any new joiner, not
    just the original token holder.
    """

    def __init__(self, code: str, max_players: int, cfg: Config = None, seed: int = None):
        self.code = code
        self.max_players = max_players
        self.cfg = cfg or Config()
        self.seed = seed if seed is not None else secrets.randbits(32)
        self.world = GameWorld(self.cfg, rng=random.Random(self.seed),
                               num_players=max_players)
        for player in self.world.players:
            player.alive = False  # not a participant until someone actually joins
        self.connections = {}       # pid -> websocket | None (disconnected)
        self.tokens = {}            # pid -> session token
        self.held = {}              # pid -> set(Intent), current input state
        self.disconnect_time = {}   # pid -> monotonic() | None
        self.tick = 0
        self.input_log = []         # [(tick, {pid: [intent names]})] for replay
        self.task = None

    def _free_pid(self):
        now = time.monotonic()
        for pid in range(self.max_players):
            if pid not in self.connections:
                return pid
            if (self.connections[pid] is None
                    and self.disconnect_time.get(pid) is not None
                    and now - self.disconnect_time[pid] > RECONNECT_GRACE_SECONDS):
                return pid
        return None

    async def join(self, websocket, token):
        """Assign (or reclaim) a pid for a connecting client.

        Returns ``(pid, session_token)``, or ``(None, None)`` if the room is
        full and the token doesn't match a disconnected slot still within its
        reconnect grace window.
        """
        now = time.monotonic()
        if token:
            for pid, existing in self.tokens.items():
                if (existing == token
                        and self.connections.get(pid) is None
                        and self.disconnect_time.get(pid) is not None
                        and now - self.disconnect_time[pid] <= RECONNECT_GRACE_SECONDS):
                    self.connections[pid] = websocket
                    self.disconnect_time[pid] = None
                    return pid, token

        pid = self._free_pid()
        if pid is None:
            return None, None
        new_token = secrets.token_urlsafe(16)
        first_join = pid not in self.connections
        self.connections[pid] = websocket
        self.tokens[pid] = new_token
        self.held[pid] = set()
        self.disconnect_time[pid] = None
        if first_join:
            self.world.players[pid].alive = True
        return pid, new_token

    def leave(self, pid: int) -> None:
        self.connections[pid] = None
        self.held[pid] = set()
        self.disconnect_time[pid] = time.monotonic()

    def is_idle(self) -> bool:
        """True once every slot that ever joined has been gone past the grace window."""
        if not self.connections:
            # Not reachable via Room.run()/_handle_connection today (both only
            # call is_idle() after a successful join), but all(...) over an
            # empty generator is vacuously True — keep this guard so a future
            # caller can't have a brand-new, never-joined room misclassified
            # as idle and torn down.
            return False
        now = time.monotonic()
        return all(
            self.disconnect_time.get(pid) is not None
            and now - self.disconnect_time[pid] > ROOM_IDLE_SECONDS
            for pid in self.connections
        )

    async def broadcast(self, text: str) -> None:
        targets = [(pid, ws) for pid, ws in self.connections.items() if ws is not None]
        if not targets:
            return
        results = await asyncio.gather(
            *(ws.send(text) for _, ws in targets), return_exceptions=True)
        dropped = []
        for (pid, _), result in zip(targets, results):
            if isinstance(result, websockets.ConnectionClosed):
                dropped.append(pid)
            elif isinstance(result, BaseException):
                raise result
        for pid in dropped:
            self.leave(pid)

    def _record_tick(self, inputs) -> None:
        """Append one tick's inputs to the log, trimmed in a batch once it's
        over :data:`MAX_INPUT_LOG_ENTRIES` (not one entry at a time, which
        would turn a rare event into an O(n) shift on every subsequent tick).
        """
        self.input_log.append((self.tick, encode_inputs(inputs)))
        if len(self.input_log) > MAX_INPUT_LOG_ENTRIES:
            del self.input_log[:len(self.input_log) - MAX_INPUT_LOG_ENTRIES // 2]

    async def run(self) -> None:
        """The authoritative tick loop. One instance per room, while non-idle."""
        loop = asyncio.get_event_loop()
        next_tick_at = loop.time()
        while not self.is_idle():
            inputs = {pid: self.held.get(pid, frozenset()) for pid in self.connections}
            self.world.step(DT, inputs)
            self.tick += 1
            self._record_tick(inputs)
            if self.tick % SEND_EVERY_N_TICKS == 0:
                await self.broadcast(protocol.snapshot_message(self.tick, self.world.snapshot()))
            next_tick_at += DT
            await asyncio.sleep(max(0.0, next_tick_at - loop.time()))


class RoomRegistry:
    """In-memory room directory keyed by join code. One process, many rooms."""

    def __init__(self):
        self.rooms = {}

    def get_or_create(self, code: str, max_players: int, cfg: Config = None) -> Room:
        room = self.rooms.get(code)
        if room is None:
            room = Room(code, max_players=max_players, cfg=cfg)
            self.rooms[code] = room
        return room

    def remove(self, code: str) -> None:
        self.rooms.pop(code, None)


async def _handle_connection(websocket, registry: RoomRegistry,
                             default_max_players: int, default_cfg: Config) -> None:
    room = None
    pid = None
    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=JOIN_TIMEOUT_SECONDS)
        msg = protocol.decode_message(raw)
        if msg["type"] != "join":
            await websocket.send(protocol.error_message("first message must be 'join'"))
            return

        room_code = msg["room"] or "default"
        room = registry.get_or_create(room_code, max_players=default_max_players,
                                      cfg=default_cfg)
        pid, token = await room.join(websocket, msg["token"])
        if pid is None:
            await websocket.send(protocol.error_message("room is full"))
            return

        await websocket.send(protocol.welcome_message(
            pid, token, dataclasses.asdict(room.cfg), room.max_players))
        await room.broadcast(protocol.presence_message("player_joined", pid))
        if room.task is None or room.task.done():
            room.task = asyncio.create_task(room.run())

        async for raw in websocket:
            try:
                incoming = protocol.decode_message(raw)
            except protocol.ProtocolError as exc:
                await websocket.send(protocol.error_message(str(exc)))
                continue
            if incoming["type"] == "input":
                room.held[pid] = incoming["held"]
            elif incoming["type"] == "ping":
                await websocket.send(protocol.pong_message(incoming["t"]))

    except (protocol.ProtocolError, asyncio.TimeoutError) as exc:
        try:
            await websocket.send(protocol.error_message(str(exc)))
        except websockets.ConnectionClosed:
            pass
    except websockets.ConnectionClosed:
        pass
    finally:
        if room is not None and pid is not None:
            room.leave(pid)
            try:
                await room.broadcast(protocol.presence_message("player_left", pid))
            except websockets.ConnectionClosed:
                pass
            if room.is_idle():
                registry.remove(room.code)


async def start_server(host: str = "localhost", port: int = 8765,
                       max_players: int = 2, cfg: Config = None):
    """Start listening and return the running ``websockets`` server.

    ``port=0`` binds an ephemeral port (used for local/offline play and for
    tests); read the actual port back from ``server.sockets[0]``.
    """
    max_players = max(MIN_PLAYERS, min(MAX_PLAYERS, max_players))
    registry = RoomRegistry()

    async def handler(websocket):
        await _handle_connection(websocket, registry, max_players, cfg or Config())

    return await websockets.serve(handler, host, port)


async def _run_forever(host: str, port: int, max_players: int) -> None:
    server = await start_server(host, port, max_players)
    bound_port = server.sockets[0].getsockname()[1]
    # A parent process (e.g. the Electron client spawning a local server for
    # offline play) reads this line to discover the ephemeral port.
    print(f"PORT={bound_port}", flush=True)
    print(f"Space Invaders server listening on ws://{host}:{bound_port}", flush=True)
    try:
        await asyncio.Future()
    finally:
        server.close()
        await server.wait_closed()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Space Invaders authoritative server")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8765,
                        help="0 picks an ephemeral port (used for local/offline play)")
    parser.add_argument("--max-players", type=int, default=2)
    args = parser.parse_args(argv)
    asyncio.run(_run_forever(args.host, args.port, args.max_players))


if __name__ == "__main__":  # pragma: no cover
    main()
