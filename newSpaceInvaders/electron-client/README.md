# Space Invaders — Electron client

A thin Electron front-end for the authoritative Python game server
(`spaceinvaders/server.py`). All game logic lives server-side; this client
only sends `input` and draws whatever `snapshot` says.

## Running

```bash
cd newSpaceInvaders/electron-client
npm install
npm start
```

- **Offline modes** ("Um Jogador" / "2 Jogadores (Local)") spawn
  `python3 -m spaceinvaders.server --host 127.0.0.1 --port 0 --max-players <N>`
  as a child process from `main.js`, using `python3` on `PATH`. Override the
  interpreter with `SPACEINVADERS_PYTHON=/path/to/python3 npm start` if
  `python3` isn't the right binary on your system. The server prints
  `PORT=<n>` as its first stdout line (see `server.py:_run_forever`); main.js
  parses that line to learn the ephemeral port and hands a `ws://127.0.0.1:<port>`
  URL to the renderer. The child process is killed on window close and app
  quit (`window-all-closed` / `before-quit` in `main.js`), and also whenever
  you return to the menu.
- **Online mode** takes a `host:port` (e.g. `203.0.113.5:8765`) and an
  optional room code, and connects straight to it — no process is spawned.
  If you omit the port, `:8765` is assumed (the server's own CLI default).
  You can also paste a full `ws://` / `wss://` URL into the host field.

## Controls

Mirrors `spaceinvaders/input.py` exactly:

- **Player 1 (WASD):** W up, A left, S down, D right, Space fire.
- **Player 2 (arrows):** Arrow keys move, Enter fires.

In local co-op both key schemes are live at once. In single-player and
online modes only the WASD/Space scheme is bound (there's only one local
player, so there's no ambiguity about whose keys they are).

## Architecture notes

- `main.js` — Electron main process: creates the window, spawns/kills the
  local server child process, exposes that lifecycle over IPC.
- `preload.js` — context bridge (`contextIsolation: true`, `nodeIntegration:
  false`, `sandbox: true` — Electron's secure defaults are untouched).
  Exposes exactly two calls (`startLocalServer`, `stopLocalServer`) plus an
  exit-notification subscription; nothing else crosses into the renderer.
- `renderer.js` — menu, WebSocket client(s), input capture, and canvas
  rendering. Uses the **browser-native `WebSocket`** global directly (not
  the `ws` npm package) since the renderer already has that Web API without
  any extra bridging; see the comment at the top of the file. `ws` is
  therefore not a dependency in `package.json`.
- **Local 2-player** opens **two independent WebSocket connections** to the
  same local server/room — one per local player — exactly like two separate
  online clients would. This was simpler to get right than multiplexing two
  players' input over one connection, since the server already hands out
  one pid per connection. The WASD connection joins first and waits for its
  `welcome` before the arrow-keys connection joins, so pid assignment is
  deterministic (pid 0 = WASD, pid 1 = arrows).
- Rendering buffers the last several `snapshot` messages and renders
  ~120ms behind "now", interpolating positions between the two bracketing
  snapshots (snapshots broadcast at ~15Hz, so this smooths motion between
  them). Enemies/bullets only interpolate when the array length is
  unchanged between the two snapshots (a death or new bullet changes the
  count, at which point it just snaps to the newer snapshot); players
  always interpolate, matched by `pid`.
- Reconnection: on an unexpected close, each connection retries with
  exponential backoff (500ms → 8s, up to 6 attempts) and resends its saved
  `token` in `join` to reclaim the same pid, per the room's
  `RECONNECT_GRACE_SECONDS` window in `server.py`.

## Assumptions made beyond `protocol.py`'s docstring

The docstring documents message shapes precisely but is silent on a few
client-side choices, which were resolved as follows:

- **Which local player gets pid 0 in co-op.** The server hands out the
  first free pid per connection, in join order — so the client join order
  determines it, not the server. This client joins the WASD connection
  first and waits for its `welcome` before joining the arrow-keys
  connection, so pid 0 (labelled "P1" in the HUD) is reliably the WASD
  player, matching `input.py`'s `KEYMAP_P1` naming. This only holds for a
  freshly-spawned local room; it doesn't apply to online play where other
  clients may already hold low pids.
- **Render delay / interpolation window.** Not specified beyond "buffer ~2
  snapshots and interpolate"; 120ms was chosen as roughly 1.8x the ~66ms
  snapshot interval, enough slack to almost always have two real snapshots
  bracketing the render time without adding much input latency.
- **Default online port when the user omits one.** `protocol.py` doesn't
  address client UX; `8765` was used because it's `server.py`'s own
  `--port` default.
- **Which keymap a single online connection uses.** Only one scheme
  (WASD+Space) is bound for a lone local connection (single-player or
  online), since there's exactly one local player and no way to know in
  advance which pid the server will assign.
