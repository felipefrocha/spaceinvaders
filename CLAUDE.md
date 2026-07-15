# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A college final project ("Trabalho final de ATR" — Real-Time Automation): a two-player
Space Invaders clone in Python `turtle` graphics. It has been **rewritten** onto a decoupled
architecture (the `spaceinvaders/` package) with a pure, headless, unit-tested game core; the
original thread-per-entity + `turtle` implementation is kept alongside it as **legacy**.

All source lives in the `newSpaceInvaders/` subdirectory. There is no root-level project file.

## Commands

The live game is the `spaceinvaders/` package. Tests use `pytest` + coverage.

```bash
cd newSpaceInvaders
python3 -m spaceinvaders                         # run the 2-player game (needs display + tkinter)
python3 -m pip install -r requirements-dev.txt   # test tooling
python3 -m pytest                                # run the unit tests
python3 -m pytest --cov --cov-report=term-missing  # tests + coverage (core is at 100%)
python3 -m pytest tests/test_world.py::test_win_when_all_enemies_dead  # a single test
```

- The **core** package (everything except `turtle_app.py`) is **stdlib-only** and runs
  headless — no display needed for tests. Target runtime is Python 3.7+ (uses dataclasses).
- Running the actual game needs a graphical display and `tkinter` (`python3-tk`). Coverage
  omits `turtle_app.py`/`__main__.py` (they require a live display) — see `.coveragerc`.
- Controls: **Player 1 = WASD + Space** to fire; **Player 2 = arrow keys + Enter** to fire.
  Key→action mapping lives in `spaceinvaders/input.py` (`KEYMAP_P1`/`KEYMAP_P2`).

## Architecture — the live game (`spaceinvaders/` package)

Strictly layered; each module depends only on those below it, and the game logic knows
nothing about the keyboard or the screen:

- `config.py` — one frozen `Config` dataclass; speeds are **units/second** (multiply by `dt`).
- `geometry.py` — `clamp` + `aabb_overlap` (centre-anchored boxes). No dependencies.
- `input.py` — `Intent` enum, `KEYMAP_P1`/`KEYMAP_P2`, and `InputState` (held-key `set`). The
  seam that decouples the sim from any keyboard backend.
- `entities.py` — `Player`/`Enemy`/`Bullet`: data + local update rules, no I/O.
- `world.py` — `GameWorld`: the **deterministic** simulation. `step(dt, inputs)` advances one
  frame; `inputs` is `{pid: set(Intent)}`. RNG is **injected** for testability. Rendering reads
  `snapshot()` (a plain dict), never the internal objects.
- `engine.py` — `GameLoop.tick(dt)` (owns world + per-player `InputState` + renderer) and
  `run_headless(...)` for driving the sim with no screen (tests/benchmarks).
- `renderer.py` — `Renderer` interface + `NullRenderer`. Headless-safe.
- `turtle_app.py` — the **only** module that imports `turtle`. Owns the `Screen`, binds both
  key maps via `onkeypress`/`onkeyrelease`, and re-arms a single `ontimer` frame callback on the
  main thread. `TurtleRenderer` uses a stamp pool. Excluded from coverage.

Design intent to preserve when editing: **single-threaded fixed-timestep loop** (no thread/
semaphore per entity like the legacy engine — that is the performance answer), determinism via
injected RNG + explicit `dt`, and rendering driven only by `snapshot()`.

## Legacy engine (kept as historical artifact — not the live game)

`game.py`, `Enemy.py`, `Player.py`, `Disparo.py`, `Score.py`, `constants.py`, `logServer.py`,
and `testes.py` are the **original** thread-per-entity + `turtle` implementation. Do not extend
them; new work goes in the `spaceinvaders/` package. Notable traits if you must read them:
`game.py`'s `__main__` spawns one `move_enemy_horizontally` worker thread per enemy and funnels
turtle calls through an `actions = Queue`/`process_queue` pump (but not consistently — some
turtle calls happen directly on worker threads); `Enemy`/`Disparo` are a second, unused engine;
`game_over` is dead (only ever set `True`, never read to end the loop).

### Distributed logging path (legacy)

- `game.py:init_logger()` spawns `logServer.py:main()` as a **separate process**
  (`multiprocessing.Process`), waits with a hard-coded `time.sleep(5)`, then attaches a
  `logging.handlers.DatagramHandler` (UDP) to the root logger.
- `logServer.py` is a `ThreadingUDPServer` that receives pickled `LogRecord`s and writes them
  to `log.txt`. **Security note:** it calls `pickle.loads()` on network data — do not extend
  this pattern; prefer a safe serialization if touching it.
- `logging.yaml` is present but currently **not loaded by anything** and contains invalid
  handler keys; `constants.LOG_PATH` points at a non-existent `logConfig.yaml`.

## Working in this repo

- The active branch for review/development work is `claude/college-project-review-9lri3u`.
- `venv/`, `__pycache__/`, and `.idea/` are all committed and should normally be excluded from
  diffs; the only `.gitignore` (`newSpaceInvaders/.gitignore`) ignores just `log.txt`.
- Code comments, logs, and the README are in Portuguese (Brazilian); keep that language when
  editing user-facing strings unless asked otherwise.
