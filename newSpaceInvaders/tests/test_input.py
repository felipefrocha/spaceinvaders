from spaceinvaders.input import (
    DEFAULT_KEYMAPS,
    KEYMAP_P1,
    KEYMAP_P2,
    InputState,
    Intent,
)


def test_player1_uses_wasd_and_space():
    assert KEYMAP_P1["w"] is Intent.UP
    assert KEYMAP_P1["a"] is Intent.LEFT
    assert KEYMAP_P1["s"] is Intent.DOWN
    assert KEYMAP_P1["d"] is Intent.RIGHT
    assert KEYMAP_P1["space"] is Intent.FIRE


def test_player2_uses_arrows_and_return():
    assert KEYMAP_P2["Up"] is Intent.UP
    assert KEYMAP_P2["Left"] is Intent.LEFT
    assert KEYMAP_P2["Down"] is Intent.DOWN
    assert KEYMAP_P2["Right"] is Intent.RIGHT
    assert KEYMAP_P2["Return"] is Intent.FIRE


def test_default_keymaps_order():
    assert DEFAULT_KEYMAPS == (KEYMAP_P1, KEYMAP_P2)


def test_press_and_release_track_held_intents():
    state = InputState(KEYMAP_P1)
    assert state.press("d") is Intent.RIGHT
    assert state.is_held(Intent.RIGHT)
    assert state.release("d") is Intent.RIGHT
    assert not state.is_held(Intent.RIGHT)


def test_unknown_key_is_ignored():
    state = InputState(KEYMAP_P1)
    assert state.press("z") is None
    assert state.release("z") is None
    assert state.held == set()


def test_clear_drops_all_held():
    state = InputState(KEYMAP_P2)
    state.press("Up")
    state.press("Right")
    assert state.held == {Intent.UP, Intent.RIGHT}
    state.clear()
    assert state.held == set()


def test_repeated_press_is_idempotent():
    state = InputState(KEYMAP_P1)
    state.press("w")
    state.press("w")
    assert state.held == {Intent.UP}
    state.release("w")
    assert state.held == set()
