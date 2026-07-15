// Renderer process script (loaded as a plain <script src="renderer.js">,
// no bundler). Runs with contextIsolation on / nodeIntegration off; the only
// bridge into the main process is `window.spaceInvaders` from preload.js.
//
// WEBSOCKET CHOICE: this file uses the browser-native `WebSocket` global
// directly (a Web Platform API available in the sandboxed renderer, not a
// Node API) rather than the npm `ws` package. That keeps the renderer
// exactly as sandboxed as a normal web page — no extra bridging needed to
// reach a WebSocket client — and `ws` is not listed as a dependency in
// package.json because of this choice. See preload.js for the corresponding
// note on the context bridge.
//
// LOCAL 2-PLAYER CHOICE: per the task's documented options, this client
// opens TWO independent WebSocket connections for local co-op (one per
// local player, exactly like two separate online clients pointed at the
// same local server/room) rather than multiplexing both players' input
// over a single connection. This is the simpler-to-get-correct option: the
// server already assigns one pid per connection, so two connections just
// works with zero server-side changes, and each local player naturally
// gets their own reconnect/token lifecycle.
'use strict';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CANVAS_W = 640;
const CANVAS_H = 680;

// Fallback sizes, only used for the brief window before a `welcome` message
// has supplied the room's real cfg. Mirrors spaceinvaders/config.py defaults.
const DEFAULT_CFG = {
  player_w: 20, player_h: 20,
  enemy_w: 24, enemy_h: 20,
  bullet_w: 4, bullet_h: 12,
};

// Physical-key -> Intent name, mirroring spaceinvaders/input.py exactly.
// KeyboardEvent.code is used (not .key) so the mapping is layout-independent.
const KEYMAP_P1 = { KeyW: 'UP', KeyA: 'LEFT', KeyS: 'DOWN', KeyD: 'RIGHT', Space: 'FIRE' };
const KEYMAP_P2 = { ArrowUp: 'UP', ArrowLeft: 'LEFT', ArrowDown: 'DOWN', ArrowRight: 'RIGHT', Enter: 'FIRE' };

const PLAYER_COLORS = ['#00e5ff', '#3d5aff', '#ff4de3', '#caff33', '#ffa53d'];
const ENEMY_COLOR = '#ff3b3b';
const PLAYER_BULLET_COLOR = '#ffe14d';
const ENEMY_BULLET_COLOR = '#ff9d3f';

const INPUT_SEND_INTERVAL_MS = 33;     // ~30/s, matches the sim tick rate
const RENDER_DELAY_MS = 120;           // render slightly behind "now" so we
                                        // always have two real snapshots to
                                        // interpolate between (snapshots
                                        // arrive ~every 66ms at 15Hz)
const MAX_RECONNECT_ATTEMPTS = 6;
const SNAPSHOT_BUFFER_MAX = 8;

// ---------------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------------

const screens = {
  menu: document.getElementById('screen-menu'),
  online: document.getElementById('screen-online'),
  game: document.getElementById('screen-game'),
};
const menuError = document.getElementById('menu-error');
const onlineError = document.getElementById('online-error');
const hudPlayers = document.getElementById('hud-players');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const overlayMessage = document.getElementById('overlay-message');
const canvas = document.getElementById('game-canvas');
const ctx = canvas.getContext('2d');

let inGame = false;

function showScreen(name) {
  for (const key of Object.keys(screens)) {
    screens[key].classList.toggle('hidden', key !== name);
  }
  inGame = name === 'game';
}

// ---------------------------------------------------------------------------
// Connection — one WebSocket + join/reconnect/input-send lifecycle.
// ---------------------------------------------------------------------------

class Connection {
  constructor({ url, room, keymap, label, onSnapshot, onWelcome, onPresence, onStatus, onError }) {
    this.url = url;
    this.room = room || null;
    this.keymap = keymap;
    this.label = label || null;

    this.onSnapshot = onSnapshot || (() => {});
    this.onWelcome = onWelcome || (() => {});
    this.onPresence = onPresence || (() => {});
    this.onStatus = onStatus || (() => {});
    this.onError = onError || (() => {});

    this.ws = null;
    this.pid = null;
    this.token = null;
    this.held = new Set();
    this.status = 'connecting';
    this.reconnectAttempts = 0;
    this.closedByUser = false;
    this._inputTimer = null;
    this._reconnectTimer = null;
    this._welcomeWaiters = [];
  }

  connect() {
    this.closedByUser = false;
    this._setStatus(this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting');

    let ws;
    try {
      ws = new WebSocket(this.url);
    } catch (err) {
      this._setStatus('disconnected');
      this.onError(`URL de conexão inválida: ${this.url}`);
      return;
    }
    this.ws = ws;

    ws.addEventListener('open', () => {
      this._send({ type: 'join', name: this.label, token: this.token, room: this.room });
    });

    ws.addEventListener('message', (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (err) {
        return; // malformed frame; ignore rather than crash the client
      }
      this._handleMessage(msg);
    });

    ws.addEventListener('close', () => {
      this._stopInputTimer();
      if (this.closedByUser) {
        this._setStatus('disconnected');
        return;
      }
      this._scheduleReconnect();
    });

    // 'error' events are always followed by 'close' on browser WebSockets;
    // reconnect logic lives in the close handler, nothing extra needed here.
    ws.addEventListener('error', () => {});
  }

  /**
   * Resolves with this connection's pid once a welcome has been received, or
   * rejects if the connection gives up before ever completing a handshake
   * (see _scheduleReconnect()'s exhausted-attempts branch) — without this,
   * a caller doing `await conn.waitForWelcome()` would hang forever on a
   * connection that never manages to join.
   */
  waitForWelcome() {
    if (this.pid !== null) return Promise.resolve(this.pid);
    return new Promise((resolve, reject) => this._welcomeWaiters.push({ resolve, reject }));
  }

  _settleWelcomeWaiters(pid, error) {
    const waiters = this._welcomeWaiters.splice(0);
    for (const { resolve, reject } of waiters) {
      if (error) reject(error);
      else resolve(pid);
    }
  }

  disconnect() {
    this.closedByUser = true;
    this._stopInputTimer();
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.ws) {
      try { this.ws.close(); } catch (err) { /* already closed */ }
      this.ws = null;
    }
    this._settleWelcomeWaiters(null, new Error('connection closed before joining'));
  }

  _handleMessage(msg) {
    switch (msg.type) {
      case 'welcome':
        this.pid = msg.pid;
        this.token = msg.token;
        this.reconnectAttempts = 0;
        this._setStatus('connected');
        this._startInputTimer();
        this.onWelcome(msg, this);
        this._settleWelcomeWaiters(this.pid, null);
        break;
      case 'snapshot':
        this.onSnapshot(msg, this);
        break;
      case 'player_joined':
      case 'player_left':
        this.onPresence(msg, this);
        break;
      case 'pong':
        break;
      case 'error':
        this.onError(msg.message);
        break;
      default:
        break;
    }
  }

  _scheduleReconnect() {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this._setStatus('disconnected');
      const message = 'Conexão perdida — número máximo de tentativas de reconexão atingido.';
      this.onError(message);
      this._settleWelcomeWaiters(null, new Error(message));
      return;
    }
    this._setStatus('reconnecting');
    const delay = Math.min(8000, 500 * (2 ** this.reconnectAttempts));
    this.reconnectAttempts += 1;
    this._reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  _startInputTimer() {
    this._stopInputTimer();
    this._inputTimer = setInterval(() => {
      this._send({ type: 'input', held: Array.from(this.held) });
    }, INPUT_SEND_INTERVAL_MS);
  }

  _stopInputTimer() {
    if (this._inputTimer) {
      clearInterval(this._inputTimer);
      this._inputTimer = null;
    }
  }

  _send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  _setStatus(status) {
    this.status = status;
    this.onStatus(status, this);
  }
}

// ---------------------------------------------------------------------------
// Game session state
// ---------------------------------------------------------------------------

let activeConnections = [];   // Connections whose keymaps receive keyboard input
let primaryConnection = null; // Connection whose snapshot stream drives rendering
let usingLocalServer = false; // whether main.js spawned a child python process for this session
let cfg = DEFAULT_CFG;
let snapshotBuffer = [];      // [{recvTime, data}], oldest first
let unsubscribeLocalExit = null;
let lastHudKey = null;        // dirty-check guard for updateHud(), reset per session

function resetGameState() {
  activeConnections = [];
  primaryConnection = null;
  cfg = DEFAULT_CFG;
  snapshotBuffer = [];
  lastHudKey = null;
  overlayMessage.classList.add('hidden');
  hudPlayers.innerHTML = '';
}

function pushSnapshot(msg) {
  snapshotBuffer.push({ recvTime: performance.now(), data: msg });
  if (snapshotBuffer.length > SNAPSHOT_BUFFER_MAX) snapshotBuffer.shift();
}

// ---------------------------------------------------------------------------
// Status UI
// ---------------------------------------------------------------------------

const STATUS_PRIORITY = { disconnected: 3, reconnecting: 2, connecting: 1, connected: 0 };
const STATUS_LABELS = {
  connected: 'conectado',
  connecting: 'conectando…',
  reconnecting: 'reconectando…',
  disconnected: 'desconectado',
};

function refreshStatusUI() {
  if (activeConnections.length === 0) return;
  let worst = 'connected';
  for (const conn of activeConnections) {
    if (STATUS_PRIORITY[conn.status] > STATUS_PRIORITY[worst]) worst = conn.status;
  }
  statusDot.className = `status-dot status-${worst}`;
  statusText.textContent = STATUS_LABELS[worst];
}

// ---------------------------------------------------------------------------
// Input handling
// ---------------------------------------------------------------------------

const GAME_KEY_CODES = new Set([
  ...Object.keys(KEYMAP_P1),
  ...Object.keys(KEYMAP_P2),
]);

document.addEventListener('keydown', (event) => {
  if (!inGame || activeConnections.length === 0) return;
  if (!GAME_KEY_CODES.has(event.code)) return;
  event.preventDefault();
  for (const conn of activeConnections) {
    const intent = conn.keymap[event.code];
    if (intent) conn.held.add(intent);
  }
});

document.addEventListener('keyup', (event) => {
  if (!GAME_KEY_CODES.has(event.code)) return;
  event.preventDefault();
  for (const conn of activeConnections) {
    const intent = conn.keymap[event.code];
    if (intent) conn.held.delete(intent);
  }
});

// Clear held keys if the window loses focus, so a key stuck "held" by an
// Alt-Tab away doesn't leave a ship drifting forever.
window.addEventListener('blur', () => {
  for (const conn of activeConnections) conn.held.clear();
});

// ---------------------------------------------------------------------------
// Rendering — interpolated between the last two buffered snapshots.
// ---------------------------------------------------------------------------

function worldToCanvas(x, y) {
  return [CANVAS_W / 2 + x, CANVAS_H / 2 - y];
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

/** Find/interpolate the snapshot to render at `renderTime` (performance.now()-scale). */
function sampleSnapshot(renderTime) {
  const buf = snapshotBuffer;
  if (buf.length === 0) return null;
  if (buf.length === 1 || renderTime <= buf[0].recvTime) return buf[0].data;
  const last = buf[buf.length - 1];
  if (renderTime >= last.recvTime) return last.data;

  for (let i = 0; i < buf.length - 1; i++) {
    const s0 = buf[i];
    const s1 = buf[i + 1];
    if (renderTime >= s0.recvTime && renderTime <= s1.recvTime) {
      const span = s1.recvTime - s0.recvTime;
      const t = span > 0 ? (renderTime - s0.recvTime) / span : 1;
      return interpolate(s0.data, s1.data, t);
    }
  }
  return last.data;
}

/**
 * Blend two snapshots. Players are matched by pid (stable across frames).
 * Enemies/bullets are matched by array index only when both arrays have the
 * same length (formation moves together; an enemy dying or a bullet
 * spawning/expiring changes the array length, at which point we just snap to
 * the newer snapshot for that list rather than guessing correspondence).
 * Discrete fields (alive/lives/score/state/kind) always come from the newer
 * snapshot — only positions are interpolated.
 */
function interpolate(s0, s1, t) {
  const playersByPid = new Map(s0.players.map((p) => [p.pid, p]));
  const players = s1.players.map((p1) => {
    const p0 = playersByPid.get(p1.pid);
    if (!p0) return p1;
    return { ...p1, x: lerp(p0.x, p1.x, t), y: lerp(p0.y, p1.y, t) };
  });

  const enemies = s0.enemies.length === s1.enemies.length
    ? s1.enemies.map((e1, i) => ({ x: lerp(s0.enemies[i].x, e1.x, t), y: lerp(s0.enemies[i].y, e1.y, t) }))
    : s1.enemies;

  const bullets = s0.bullets.length === s1.bullets.length
    ? s1.bullets.map((b1, i) => ({
        x: lerp(s0.bullets[i].x, b1.x, t),
        y: lerp(s0.bullets[i].y, b1.y, t),
        kind: b1.kind,
      }))
    : s1.bullets;

  return { state: s1.state, players, enemies, bullets };
}

function drawPlayer(p, pid) {
  if (!p.alive) return;
  const color = PLAYER_COLORS[pid % PLAYER_COLORS.length];
  const w = cfg.player_w, h = cfg.player_h;
  const [cx, cy] = worldToCanvas(p.x, p.y);
  ctx.fillStyle = color;
  // Ship body.
  ctx.fillRect(cx - w / 2, cy - h / 2, w, h);
  // Small nose pointing "up" on screen (toward the enemies) for legibility.
  ctx.beginPath();
  ctx.moveTo(cx, cy - h / 2 - 6);
  ctx.lineTo(cx - w / 3, cy - h / 2);
  ctx.lineTo(cx + w / 3, cy - h / 2);
  ctx.closePath();
  ctx.fill();
}

function drawEnemy(e) {
  const w = cfg.enemy_w, h = cfg.enemy_h;
  const [cx, cy] = worldToCanvas(e.x, e.y);
  ctx.fillStyle = ENEMY_COLOR;
  ctx.beginPath();
  ctx.moveTo(cx - w / 2, cy - h / 2);
  ctx.lineTo(cx + w / 2, cy - h / 2);
  ctx.lineTo(cx, cy + h / 2);
  ctx.closePath();
  ctx.fill();
}

function drawBullet(b) {
  const w = cfg.bullet_w, h = cfg.bullet_h;
  const [cx, cy] = worldToCanvas(b.x, b.y);
  ctx.fillStyle = b.kind === 'player' ? PLAYER_BULLET_COLOR : ENEMY_BULLET_COLOR;
  ctx.fillRect(cx - w / 2, cy - h / 2, w, h);
}

function drawFrame(frame) {
  ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

  for (const e of frame.enemies) drawEnemy(e);
  for (const b of frame.bullets) drawBullet(b);
  for (const p of frame.players) drawPlayer(p, p.pid);

  updateHud(frame);
}

function updateHud(frame) {
  // Snapshots (and the score/lives/alive fields driving the HUD) only change
  // at the server's ~15Hz broadcast rate, but this is called every rAF tick
  // (~60Hz) — skip the DOM rebuild entirely when nothing HUD-relevant changed
  // since the last call.
  const sorted = [...frame.players].sort((a, b) => a.pid - b.pid);
  const key = sorted.map((p) => `${p.pid}:${p.score}:${p.lives}:${p.alive}`).join('|');
  if (key !== lastHudKey) {
    lastHudKey = key;
    hudPlayers.innerHTML = '';
    for (const p of sorted) {
      const span = document.createElement('span');
      span.className = 'hud-player';
      span.style.color = PLAYER_COLORS[p.pid % PLAYER_COLORS.length];
      span.textContent = `P${p.pid + 1}  pontos ${p.score}  vidas ${p.lives}${p.alive ? '' : ' (destruído)'}`;
      hudPlayers.appendChild(span);
    }
  }

  if (frame.state === 'RUNNING') {
    overlayMessage.classList.add('hidden');
  } else {
    overlayMessage.classList.remove('hidden');
    if (frame.state === 'WON') {
      overlayMessage.textContent = 'VOCÊ VENCEU!';
      overlayMessage.style.color = '#4bff4b';
    } else {
      overlayMessage.textContent = 'FIM DE JOGO';
      overlayMessage.style.color = '#ff3b3b';
    }
  }
}

function renderLoop() {
  requestAnimationFrame(renderLoop);
  refreshStatusUI();
  if (!inGame) return;
  const renderTime = performance.now() - RENDER_DELAY_MS;
  const frame = sampleSnapshot(renderTime);
  if (frame) drawFrame(frame);
}
requestAnimationFrame(renderLoop);

// ---------------------------------------------------------------------------
// Session teardown
// ---------------------------------------------------------------------------

async function teardownGame() {
  for (const conn of activeConnections) conn.disconnect();
  if (usingLocalServer && window.spaceInvaders) {
    try { await window.spaceInvaders.stopLocalServer(); } catch (err) { /* best effort */ }
  }
  usingLocalServer = false;
  resetGameState();
}

// ---------------------------------------------------------------------------
// Starting a game
// ---------------------------------------------------------------------------

function makeConnectionCallbacks() {
  return {
    onSnapshot: (msg, conn) => {
      if (conn === primaryConnection) pushSnapshot(msg);
    },
    onWelcome: (msg) => {
      cfg = msg.cfg || DEFAULT_CFG;
    },
    onPresence: () => {},
    onStatus: () => refreshStatusUI(),
    onError: (message) => {
      console.error('[spaceinvaders] server error:', message);
    },
  };
}

/** Local play (single or co-op): spawn a local server, then connect. */
async function startLocalGame(numLocalPlayers) {
  resetGameState();
  showScreen('game');
  statusText.textContent = 'iniciando servidor local…';
  statusDot.className = 'status-dot status-connecting';

  const result = await window.spaceInvaders.startLocalServer(numLocalPlayers);
  if (!result || !result.ok) {
    showScreen('menu');
    setMenuError(`Falha ao iniciar servidor local:\n${result ? result.error : 'IPC indisponível'}`);
    return;
  }
  usingLocalServer = true;
  const url = `ws://127.0.0.1:${result.port}`;

  const callbacks = makeConnectionCallbacks();
  const connA = new Connection({ url, room: null, keymap: KEYMAP_P1, label: 'P1', ...callbacks });
  connA.connect();
  try {
    await connA.waitForWelcome();
  } catch (err) {
    connA.disconnect();
    await teardownGame();
    showScreen('menu');
    setMenuError('Não foi possível conectar ao servidor local. Tente novamente.');
    return;
  }
  primaryConnection = connA;
  activeConnections = [connA];

  if (numLocalPlayers === 2) {
    // Join sequentially and wait for connA's welcome first (above) so the
    // server — which assigns the first free pid per connection, in join
    // order — deterministically hands pid 0 to the WASD player and pid 1 to
    // the arrow-keys player, matching spaceinvaders/input.py's convention.
    const connB = new Connection({ url, room: null, keymap: KEYMAP_P2, label: 'P2', ...callbacks });
    connB.connect();
    try {
      await connB.waitForWelcome();
    } catch (err) {
      await teardownGame();
      showScreen('menu');
      setMenuError('Não foi possível conectar o Jogador 2 ao servidor local. Tente novamente.');
      return;
    }
    activeConnections = [connA, connB];
  }

  refreshStatusUI();
}

/**
 * Mint a room code for online play when the user leaves the field blank.
 * The server defaults an omitted room to its own shared "default" room
 * (see spaceinvaders/server.py) — fine for local co-op, where both local
 * connections rely on that same implicit sharing against a private,
 * freshly-spawned local server, but wrong for online play against a public
 * host: two strangers who both leave the field blank would otherwise be
 * silently placed in the same room. Minting a private code here means
 * "blank" always means "just for me" for online play specifically.
 */
function generatePrivateRoomCode() {
  return `solo-${Math.random().toString(36).slice(2, 10)}`;
}

/** Online play: connect to a user-supplied host:port, single local player. */
function startOnlineGame(hostPort, room) {
  resetGameState();
  showScreen('game');

  let url = hostPort.trim();
  if (!/^wss?:\/\//i.test(url)) {
    if (!url.includes(':')) url = `${url}:8765`; // 8765 matches server.py's CLI default
    url = `ws://${url}`;
  }

  const roomCode = room || generatePrivateRoomCode();
  const callbacks = makeConnectionCallbacks();
  // A single local player online always uses the WASD+Space (P1) scheme,
  // regardless of which pid the server ends up assigning — with only one
  // local connection there's no ambiguity about whose keys these are.
  const conn = new Connection({ url, room: roomCode, keymap: KEYMAP_P1, label: 'Jogador', ...callbacks });
  primaryConnection = conn;
  activeConnections = [conn];
  conn.connect();
  refreshStatusUI();
}

function setMenuError(text) {
  menuError.textContent = text || '';
}

function setOnlineError(text) {
  onlineError.textContent = text || '';
}

// ---------------------------------------------------------------------------
// Menu wiring
// ---------------------------------------------------------------------------

document.getElementById('btn-single').addEventListener('click', () => {
  setMenuError('');
  startLocalGame(1);
});

document.getElementById('btn-coop').addEventListener('click', () => {
  setMenuError('');
  startLocalGame(2);
});

document.getElementById('btn-online').addEventListener('click', () => {
  setOnlineError('');
  showScreen('online');
});

document.getElementById('btn-online-back').addEventListener('click', () => {
  showScreen('menu');
});

document.getElementById('form-online').addEventListener('submit', (event) => {
  event.preventDefault();
  const host = document.getElementById('input-host').value.trim();
  const room = document.getElementById('input-room').value.trim();
  if (!host) {
    setOnlineError('Informe o endereço do servidor (host:porta).');
    return;
  }
  setOnlineError('');
  startOnlineGame(host, room);
});

document.getElementById('btn-back-to-menu').addEventListener('click', async () => {
  await teardownGame();
  showScreen('menu');
});

if (window.spaceInvaders) {
  unsubscribeLocalExit = window.spaceInvaders.onLocalServerExit(({ code, signal }) => {
    console.error(`[spaceinvaders] local server exited unexpectedly (code=${code}, signal=${signal})`);
  });
}

window.addEventListener('beforeunload', () => {
  for (const conn of activeConnections) conn.disconnect();
  if (usingLocalServer && window.spaceInvaders) {
    // Fire-and-forget — the page is unloading, we can't await this, but
    // main.js also kills the child on window-all-closed/before-quit as a
    // backstop in case this IPC call doesn't land in time.
    window.spaceInvaders.stopLocalServer();
  }
});

showScreen('menu');
