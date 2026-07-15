# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A college final project ("Trabalho final de ATR" — Real-Time Automation) implementing a
Space Invaders clone in Python `turtle` graphics. The academic point of the assignment is
concurrency: modeling game entities as threads and coordinating them with synchronization
primitives, plus a network (UDP) logging server. It is a learning artifact, not production
software — see "Architecture" below before assuming any file is live or correct.

All source lives in the `newSpaceInvaders/` subdirectory. There is no root-level project file.

## Commands

There is no build system, test runner, or linter configured. Everything runs directly.

```bash
cd newSpaceInvaders
python3 game.py          # run the game (opens a turtle/Tk window; needs a display)
python3 testes.py        # run the standalone enemy-movement prototype (unrelated to game.py)
```

- Target runtime is **Python 3.6** (now EOL); a committed `venv/` under `newSpaceInvaders/`
  pins it. `requirements.txt` lists `actions`, `bunch`, `PyYAML`, but only `PyYAML` is actually
  used (by the log server). `turtle`, `threading`, `multiprocessing`, `socketserver` are stdlib.
- The game needs a graphical display — it will not run headless without a virtual framebuffer
  (e.g. `xvfb-run python3 game.py`), and even then it is interactive (arrow keys + space).
- There are **no automated tests**. `testes.py` is a throwaway prototype despite its name.

## Architecture — the one thing to understand first

**There are two incompatible engine designs in the tree, and only one is wired up.**

1. **The live engine is `game.py`'s `__main__` block.** It creates raw `turtle.Turtle`
   objects directly and spawns one `move_enemy_horizontally` worker thread per enemy. Player
   input, the score, and the log server are all started here. This is what actually runs.

2. **The dead engine is `Enemy.py` + `Disparo.py` + the `INVADERS_POS`/`PLAYER_POS` globals.**
   These implement a "thread-per-entity sharing global position lists guarded by semaphores"
   model. `game.py` imports `Enemy`/`Disparo` but **never instantiates `Enemy`**
   (`create_enemy()` is defined and never called). Treat these files, `testes.py`, and the
   large commented-out `game()` function at the top of `game.py` as **dead code** unless a task
   explicitly revives them. Do not assume changing `Enemy.py` affects the running game.

### How the live engine coordinates threads (the ATR core)

- `turtle`/Tk is **not thread-safe**, so the intended discipline is that worker threads push
  turtle mutations as a callable (or `(callable, arg)` / `(callable, (a, b))` tuple) onto a
  shared `actions = Queue(...)` for the main thread to apply. Note the discipline is **not
  fully followed**: `move_enemy_horizontally` also calls some turtle methods directly from the
  worker thread (e.g. `player.draw.hideturtle()` at game.py:229/253, and reads `enemy.position()`
  / `enemy.ycor()`). Don't assume all drawing is already funneled — this is a latent bug source.
- `process_queue()` runs on the **main thread**, drains the queue, and re-arms itself via
  `screen.ontimer(process_queue, 100)` while threads are alive. This funnel is the mechanism
  that keeps Tk calls on the main thread — respect it when adding entity behavior.
- Shared state is module-level globals (`game_over`, `number_of_enemies`, `player_bullet`,
  and the `*_POS` lists in `constants.py`). Note `game_over` is effectively **dead**: it is
  initialized `True` and only ever assigned `True` (never `False`), and `screen.mainloop()`
  never reads it — so setting `game_over = False` will not end the game. `constants.py` also
  holds screen bounds and the `sem`/`lock` semaphores.
- Collision detection is polling-based distance checks (`is_colision*` functions compare
  entity coordinates against the player / player bullet within a pixel threshold).

### Distributed logging path

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
