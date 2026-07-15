"""Decoupled Space Invaders core.

Import surface deliberately excludes the turtle backend so that importing
``spaceinvaders`` never requires a display. The turtle app lives in
:mod:`spaceinvaders.turtle_app` and is imported only when you actually render.
"""
from .config import Config
from .entities import Bullet, Enemy, Player, ENEMY_OWNER
from .input import (
    DEFAULT_KEYMAPS,
    KEYMAP_P1,
    KEYMAP_P2,
    InputState,
    Intent,
)
from .engine import GameLoop, run_headless
from .renderer import NullRenderer, Renderer
from .world import GameState, GameWorld

__all__ = [
    "Config",
    "Player",
    "Enemy",
    "Bullet",
    "ENEMY_OWNER",
    "Intent",
    "InputState",
    "KEYMAP_P1",
    "KEYMAP_P2",
    "DEFAULT_KEYMAPS",
    "GameWorld",
    "GameState",
    "Renderer",
    "NullRenderer",
    "GameLoop",
    "run_headless",
]
