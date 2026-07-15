"""Wire protocol for online play — plain, allow-listed JSON.

This is the safe replacement for the legacy logging path
(``logServer.py``), which deserialized network bytes with ``pickle.loads()``
(arbitrary code execution by design). Nothing in this module ever calls
``pickle``, ``eval`` or ``exec``; ``json.loads`` only ever produces plain
dicts/lists/primitives, and every field is validated against an explicit
allow-list before it touches the simulation.

Message shapes (client <-> server), one JSON object per WebSocket text frame:

Client -> server
    {"type": "join", "name": "<str, optional>", "token": "<str, optional>", "room": "<str, optional>"}
    {"type": "input", "held": ["LEFT", "RIGHT", ...]}   # full held-set, idempotent
    {"type": "ping", "t": <float>}

Server -> client
    {"type": "welcome", "pid": <int>, "token": "<str>", "cfg": {...}, "num_players": <int>}
    {"type": "snapshot", "tick": <int>, "state": "...", "players": [...], "enemies": [...], "bullets": [...]}
    {"type": "pong", "t": <float>}
    {"type": "player_joined" | "player_left", "pid": <int>}
    {"type": "error", "message": "<str>"}

``encode_input``/``decode_input`` and friends give both the server and any
client implementation (Electron, a test harness, ...) one shared definition
of what is on the wire, instead of each side inventing its own dict shape.
"""
import json

from .input import Intent

MAX_FRAME_BYTES = 4096          # generous upper bound for a control message
MAX_NAME_LEN = 32

_INTENT_NAMES = {i.name for i in Intent}
_NAME_TO_INTENT = {i.name: i for i in Intent}


class ProtocolError(ValueError):
    """Raised for any malformed or out-of-allow-list message."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def decode_message(raw: str) -> dict:
    """Parse and validate one incoming client message.

    Never uses ``pickle`` / ``eval``; ``json.loads`` yields only JSON
    primitives. Returns a small, allow-listed dict; raises
    :class:`ProtocolError` on anything else (unknown type, wrong types,
    oversized payload, unknown intent names).
    """
    _require(isinstance(raw, str), "frame must be text")
    try:
        frame_size = len(raw.encode("utf-8"))
    except UnicodeError as exc:
        # A lone surrogate (e.g. chr(0xd800)) is a valid Python str but has no
        # UTF-8 encoding; treat it as malformed input rather than crashing.
        raise ProtocolError(f"frame is not valid UTF-8: {exc}") from exc
    _require(frame_size <= MAX_FRAME_BYTES, "frame too large")

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc

    _require(isinstance(obj, dict), "message must be a JSON object")
    msg_type = obj.get("type")
    _require(isinstance(msg_type, str), "missing/invalid 'type'")

    if msg_type == "join":
        name = obj.get("name")
        _require(name is None or (isinstance(name, str) and len(name) <= MAX_NAME_LEN),
                 "invalid 'name'")
        token = obj.get("token")
        _require(token is None or isinstance(token, str), "invalid 'token'")
        room = obj.get("room")
        _require(room is None or (isinstance(room, str) and 1 <= len(room) <= 32),
                 "invalid 'room'")
        return {"type": "join", "name": name, "token": token, "room": room}

    if msg_type == "input":
        held = obj.get("held")
        _require(isinstance(held, list), "'held' must be a list")
        _require(len(held) <= len(_INTENT_NAMES), "'held' has too many entries")
        intents = set()
        for name in held:
            _require(isinstance(name, str) and name in _INTENT_NAMES,
                     f"unknown intent {name!r}")
            intents.add(_NAME_TO_INTENT[name])
        return {"type": "input", "held": intents}

    if msg_type == "ping":
        t = obj.get("t")
        _require(isinstance(t, (int, float)), "invalid 'ping' timestamp")
        return {"type": "ping", "t": t}

    raise ProtocolError(f"unknown message type {msg_type!r}")


def encode(obj: dict) -> str:
    """Serialize an outgoing message. Plain ``json.dumps`` — no pickle, ever."""
    return json.dumps(obj, separators=(",", ":"))


def welcome_message(pid: int, token: str, cfg_dict: dict, num_players: int) -> str:
    return encode({
        "type": "welcome",
        "pid": pid,
        "token": token,
        "cfg": cfg_dict,
        "num_players": num_players,
    })


def snapshot_message(tick: int, snapshot: dict) -> str:
    msg = {"type": "snapshot", "tick": tick}
    msg.update(snapshot)
    return encode(msg)


def pong_message(t) -> str:
    return encode({"type": "pong", "t": t})


def presence_message(kind: str, pid: int) -> str:
    _require(kind in ("player_joined", "player_left"), "invalid presence kind")
    return encode({"type": kind, "pid": pid})


def error_message(text: str) -> str:
    return encode({"type": "error", "message": text})
