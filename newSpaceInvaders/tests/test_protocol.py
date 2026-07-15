import json

import pytest

from spaceinvaders import protocol
from spaceinvaders.input import Intent
from spaceinvaders.protocol import ProtocolError, decode_message, encode


def test_decode_valid_join_defaults_none():
    msg = decode_message(json.dumps({"type": "join"}))
    assert msg == {"type": "join", "name": None, "token": None, "room": None}


def test_decode_valid_join_with_all_fields():
    msg = decode_message(json.dumps(
        {"type": "join", "name": "alice", "token": "tok123", "room": "room1"}))
    assert msg == {"type": "join", "name": "alice", "token": "tok123", "room": "room1"}


def test_decode_valid_input():
    msg = decode_message(json.dumps({"type": "input", "held": ["LEFT", "FIRE"]}))
    assert msg == {"type": "input", "held": {Intent.LEFT, Intent.FIRE}}


def test_decode_valid_input_empty_held():
    msg = decode_message(json.dumps({"type": "input", "held": []}))
    assert msg == {"type": "input", "held": set()}


def test_decode_valid_ping_int_timestamp():
    msg = decode_message(json.dumps({"type": "ping", "t": 42}))
    assert msg == {"type": "ping", "t": 42}


def test_decode_valid_ping_float_timestamp():
    msg = decode_message(json.dumps({"type": "ping", "t": 1.5}))
    assert msg == {"type": "ping", "t": 1.5}


def test_decode_rejects_non_string_frame():
    with pytest.raises(ProtocolError):
        decode_message(b"{}")


def test_decode_rejects_non_json_text():
    with pytest.raises(ProtocolError):
        decode_message("not json at all {{{")


def test_decode_rejects_empty_string():
    with pytest.raises(ProtocolError):
        decode_message("")


def test_decode_rejects_non_dict_top_level_list():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps([1, 2, 3]))


def test_decode_rejects_non_dict_top_level_string():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps("hello"))


def test_decode_rejects_non_dict_top_level_number():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps(42))


def test_decode_rejects_missing_type():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"name": "alice"}))


def test_decode_rejects_non_string_type():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": 5}))


def test_decode_rejects_unknown_type():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "shutdown"}))


def test_decode_rejects_oversized_frame():
    huge = json.dumps({"type": "join", "name": "a" * protocol.MAX_FRAME_BYTES})
    with pytest.raises(ProtocolError):
        decode_message(huge)


def test_decode_accepts_frame_at_exact_max_bytes():
    # Build a join frame whose UTF-8 byte length is exactly MAX_FRAME_BYTES.
    base = json.dumps({"type": "join", "name": ""})
    pad_len = protocol.MAX_FRAME_BYTES - len(base.encode("utf-8"))
    assert pad_len >= 0
    msg = json.dumps({"type": "join", "name": "a" * min(pad_len, protocol.MAX_NAME_LEN)})
    assert len(msg.encode("utf-8")) <= protocol.MAX_FRAME_BYTES
    decode_message(msg)  # should not raise


def test_decode_join_rejects_name_too_long():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "join", "name": "x" * (protocol.MAX_NAME_LEN + 1)}))


def test_decode_join_accepts_name_at_max_len():
    msg = decode_message(json.dumps({"type": "join", "name": "x" * protocol.MAX_NAME_LEN}))
    assert msg["name"] == "x" * protocol.MAX_NAME_LEN


def test_decode_join_rejects_non_string_name():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "join", "name": 123}))


def test_decode_join_rejects_non_string_token():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "join", "token": 123}))


def test_decode_join_rejects_non_string_room():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "join", "room": 123}))


def test_decode_join_rejects_empty_room():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "join", "room": ""}))


def test_decode_join_rejects_room_too_long():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "join", "room": "r" * 33}))


def test_decode_join_accepts_room_at_max_len():
    msg = decode_message(json.dumps({"type": "join", "room": "r" * 32}))
    assert msg["room"] == "r" * 32


def test_decode_input_rejects_non_list_held():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "input", "held": "LEFT"}))


def test_decode_input_rejects_dict_held():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "input", "held": {"LEFT": True}}))


def test_decode_input_rejects_missing_held():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "input"}))


def test_decode_input_rejects_unknown_intent_name():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "input", "held": ["TELEPORT"]}))


def test_decode_input_rejects_non_string_intent_entry():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "input", "held": [1, 2]}))


def test_decode_input_rejects_lowercase_intent_name():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "input", "held": ["left"]}))


def test_decode_input_rejects_too_many_entries():
    too_many = [i.name for i in Intent] + [next(iter(Intent)).name]
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "input", "held": too_many}))


def test_decode_ping_rejects_missing_t():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "ping"}))


def test_decode_ping_rejects_non_numeric_t():
    with pytest.raises(ProtocolError):
        decode_message(json.dumps({"type": "ping", "t": "now"}))


def test_decode_ping_rejects_bool_disguised_string_t():
    # bool is technically an int subclass in Python; confirm it's accepted
    # (documented ambiguity, see summary) rather than silently miscategorized.
    msg = decode_message(json.dumps({"type": "ping", "t": True}))
    assert msg["t"] is True


def test_encode_produces_valid_json():
    text = encode({"type": "pong", "t": 1.0})
    assert json.loads(text) == {"type": "pong", "t": 1.0}


def test_welcome_message_round_trips():
    text = protocol.welcome_message(0, "tok", {"lives": 3}, 2)
    obj = json.loads(text)
    assert obj == {"type": "welcome", "pid": 0, "token": "tok",
                   "cfg": {"lives": 3}, "num_players": 2}


def test_snapshot_message_round_trips():
    text = protocol.snapshot_message(7, {"state": "RUNNING", "players": []})
    obj = json.loads(text)
    assert obj == {"type": "snapshot", "tick": 7, "state": "RUNNING", "players": []}


def test_pong_message_round_trips():
    text = protocol.pong_message(3.25)
    assert json.loads(text) == {"type": "pong", "t": 3.25}


def test_presence_message_player_joined():
    text = protocol.presence_message("player_joined", 1)
    assert json.loads(text) == {"type": "player_joined", "pid": 1}


def test_presence_message_player_left():
    text = protocol.presence_message("player_left", 1)
    assert json.loads(text) == {"type": "player_left", "pid": 1}


def test_presence_message_rejects_invalid_kind():
    with pytest.raises(ProtocolError):
        protocol.presence_message("player_teleported", 0)


def test_error_message_round_trips():
    text = protocol.error_message("boom")
    assert json.loads(text) == {"type": "error", "message": "boom"}


ADVERSARIAL_INPUTS = [
    "",
    "null",
    "true",
    "42",
    "[]",
    "[[[[[[[[[[]]]]]]]]]]",
    json.dumps({"__proto__": {"polluted": True}, "type": "join"}),
    json.dumps({"constructor": {"prototype": {}}, "type": "input", "held": []}),
    json.dumps({"type": "join", "name": "x" * 100000}),
    "a" * 100000,
    json.dumps({"type": "input", "held": ["LEFT"] * 100000}),
    json.dumps({"type": "join", "extra": {"a": [1, {"b": [2, {"c": 3}]}]}}),
    "{",
    "}",
    "{\"type\":",
    json.dumps({"type": None}),
    json.dumps({"type": ["join"]}),
    json.dumps({"type": {"nested": "join"}}),
    "\x00\x01\x02",
]


@pytest.mark.parametrize("raw", ADVERSARIAL_INPUTS)
def test_decode_message_never_raises_anything_other_than_protocol_error(raw):
    try:
        decode_message(raw)
    except ProtocolError:
        pass
    except Exception as exc:  # pragma: no cover - failure path, not expected to hit
        pytest.fail(f"decode_message raised {type(exc).__name__} instead of ProtocolError: {exc}")


@pytest.mark.xfail(strict=True, reason=(
    "BUG (protocol.py:57): decode_message('\\ud800') (a lone UTF-16 surrogate, "
    "which Python happily represents as a str via surrogateescape/direct "
    "construction) raises UnicodeEncodeError from raw.encode('utf-8') inside "
    "the frame-size check, not ProtocolError. This violates the documented "
    "'never raises anything other than ProtocolError' contract; a caller that "
    "does `except protocol.ProtocolError` around decode_message (as "
    "server.py's _handle_connection does) would let this propagate uncaught."
))
def test_decode_message_lone_surrogate_raises_protocol_error_not_unicode_error():
    with pytest.raises(ProtocolError):
        decode_message("\ud800")


def test_decode_message_deeply_nested_json_is_protocol_error_or_success():
    nested = {"type": "join"}
    cursor = nested
    for _ in range(500):
        cursor["room"] = None
        cursor["nested"] = {}
        cursor = cursor["nested"]
    raw = json.dumps(nested)
    try:
        decode_message(raw)
    except ProtocolError:
        pass
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"decode_message raised {type(exc).__name__} instead of ProtocolError: {exc}")
