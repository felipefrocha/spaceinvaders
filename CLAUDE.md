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
python3 -m pip install -r requirements-dev.txt   # test tooling (includes websockets)
python3 -m pytest                                # run the unit tests
python3 -m pytest --cov --cov-report=term-missing  # tests + coverage (core is at 100%)
python3 -m pytest tests/test_world.py::test_win_when_all_enemies_dead  # a single test

python3 -m pip install -r requirements-server.txt          # server-only runtime dep
python3 -m spaceinvaders.server --port 8765 --max-players 5  # run the online server

cd electron-client && npm install && npm start             # run the Electron desktop client
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
  Also the **single source of truth for the timestep**: `TICK_HZ`/`DT` live here so every frame
  driver (turtle loop, server) advances by the same `dt` and replays stay bit-identical.
- `geometry.py` — `clamp` + `aabb_overlap` (centre-anchored boxes). No dependencies.
- `input.py` — `Intent` enum, `KEYMAP_P1`/`KEYMAP_P2`, `InputState` (held-key `set`), and
  `encode_inputs` (the one wire/log encoder shared by server + replay). `InputState`/keymaps are
  used by the **offline** path only; online input arrives as pre-mapped `Intent` names (the
  client owns the keymap). The seam that decouples the sim from any keyboard backend.
- `entities.py` — `Player`/`Enemy`/`Bullet`: data + local update rules, no I/O. Note `Player`
  has **`active`** (is this slot a participant this round?) distinct from **`alive`** (survived
  combat?) — see the online section.
- `world.py` — `GameWorld`: the **deterministic** simulation. `step(dt, inputs)` advances one
  frame; `inputs` is `{pid: set(Intent)}`. RNG is **injected** for testability. Rendering reads
  `snapshot()` (a plain dict; inactive slots are omitted), never the internal objects.
  `active_pids` (ctor) + `activate_player(pid)` are the only occupancy controls — nothing else
  reaches into player state.
- `engine.py` — `GameLoop.tick(dt)` (owns world + per-player `InputState` + renderer) and
  `run_headless(...)` for driving the sim with no screen. **Offline driver only** — the server
  has its own async loop (see below); the two share `world.step`/`snapshot`, not this loop.
- `renderer.py` — `Renderer` interface + `NullRenderer`. In-process consumer of `snapshot()`;
  the server broadcasts the same dict instead of using this interface.
- `turtle_app.py` — the **only** module that imports `turtle`. Owns the `Screen`, binds both
  key maps via `onkeypress`/`onkeyrelease`, and re-arms a single `ontimer` frame callback on the
  main thread. `TurtleRenderer` uses a stamp pool. Excluded from coverage.

The portable seam across every path is exactly **`world.step(dt, inputs)` + `world.snapshot()`
+ injected RNG** — that (not any single loop or renderer) is what "one engine" means here.

Design intent to preserve when editing: **single-threaded fixed-timestep loop** (no thread/
semaphore per entity like the legacy engine — that is the performance answer), determinism via
injected RNG + explicit `dt`, and rendering driven only by `snapshot()`.

## Online multiplayer (`spaceinvaders/server.py` + `spaceinvaders/protocol.py`)

An **authoritative server** for up to 5 synced players, built on the exact same core — it calls
`world.step(dt, inputs)` unchanged; only the source of `inputs` and the destination of
`snapshot()` differ from the offline/turtle path.

- `protocol.py` — the wire format: plain, **allow-listed JSON** (`decode_message` rejects
  anything outside the documented shapes, never raises anything but `ProtocolError` on bad
  input). This is the deliberate, security-motivated replacement for the legacy
  `logServer.py`'s `pickle.loads()`-on-the-network pattern — **never reintroduce pickle for
  anything touching a socket.** Read the module docstring for the exact message shapes.
- `server.py` — `Room` (one `GameWorld` + per-pid connections/tokens/held-input + its **own**
  async 30 Hz tick loop — `Room.run`, not `engine.GameLoop` — broadcasting snapshots every other
  tick, ~15 Hz) and `RoomRegistry` (room-code → `Room`, created lazily on join). `start_server(...)`
  returns a running `websockets` server — pass `port=0` for an ephemeral port (used by tests and
  local/offline play). Reconnect: a disconnected pid's slot is held for `RECONNECT_GRACE_SECONDS`
  and reclaimed by presenting the same session token; past that window the slot frees for any new
  joiner. **Occupancy:** a `Room` sizes its world at `max_players` (capacity) but starts it with
  an empty active set and calls `world.activate_player(pid)` as clients join — so an unclaimed
  slot is never simulated, rendered, or counted toward the loss. The server never touches player
  fields directly; `activate_player` + `step`/`snapshot` are its only world surface.
- **Offline Electron play reuses this same server**, spawned as a local child process on an
  ephemeral port (it prints `PORT=<n>` to stdout as its first line) — the same one engine and one
  protocol whether the peer is a local process or remote. (The **turtle** client is the exception:
  it drives the core in-process via `engine.GameLoop` and never touches the server or protocol at
  all — so "same core" spans both frontends, but "same protocol" is the Electron/server axis only.)
- `replay.py` — deterministic record/replay (`RoundRecord`, `record_headless`, `replay`,
  `state_hash`) built directly from `Room.input_log`'s shape (`[(tick, {pid: [intent_name,...]})]`).
  This is the desync-detection and reproducibility primitive: replaying the same `(seed, cfg,
  input_log)` must yield a bit-identical `state_hash` every time. JSON only, no pickle, same rule
  as above.
- `loadtest.py` — a performance **simulation**, not a correctness test: it starts a real
  `start_server(...)` and drives it with real `websockets` client connections on loopback at
  realistic input/ping cadence, then reports round-trip latency, snapshot cadence, and bandwidth
  measured client-side (a server whose tick loop is falling behind shows up as growing RTT and
  irregular snapshot gaps, with no server instrumentation needed). Run it directly —
  `python3 -m spaceinvaders.loadtest --rooms 5 --players-per-room 5 --duration 10` — for ad hoc
  load numbers; `tests/test_loadtest.py` keeps a fast, small-scale version of it in the regular
  suite so a real regression (not just a unit-level one) gets caught.
- Requires the `websockets` package (`requirements-server.txt`); the offline core
  (`config`/`geometry`/`input`/`entities`/`world`/`engine`/`renderer`) stays stdlib-only.

## Electron desktop client (`electron-client/`)

A separate Node/Electron project (`electron-client/package.json`) that speaks `protocol.py`'s
JSON wire format over WebSocket — never Python FFI. `main.js` spawns a local `spaceinvaders.server`
child process for offline/local-co-op play and connects directly to a remote host:port for online
play; the renderer draws `snapshot()` on a `<canvas>`, sends `held`-intent-set `input` frames, and
mirrors the same **WASD (P1) / arrows (P2)** control scheme as `spaceinvaders/input.py`. See
`electron-client/README.md` for how to run it. Online play with a blank room-code field gets a
private auto-generated code client-side (so strangers aren't dropped into the shared `"default"`
room). The `turtle_app.py` client is unaffected and remains the offline/2p-local reference
implementation — the two frontends are independent consumers of the same **core** (`world`), but
only the Electron client speaks the **protocol**; the turtle client uses `engine.GameLoop`
in-process, so it is not a protocol consumer at all.

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
