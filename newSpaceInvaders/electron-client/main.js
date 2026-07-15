// Electron main process.
//
// Responsibilities:
//   - Create the BrowserWindow (contextIsolation ON, nodeIntegration OFF,
//     sandbox ON — the renderer never gets Node/Electron APIs directly, only
//     what preload.js explicitly exposes through contextBridge).
//   - OFFLINE play: spawn `python3 -m spaceinvaders.server --host 127.0.0.1
//     --port 0 --max-players <N>` as a child process, read the "PORT=<n>"
//     line the server prints as its first line of stdout (see
//     spaceinvaders/server.py:_run_forever), and hand that port back to the
//     renderer over IPC so it can open a WebSocket to it.
//   - ONLINE play needs no child process at all — the renderer just opens a
//     WebSocket straight to the host:port the user typed into the menu.
//   - Kill the spawned local server cleanly when the window closes or the
//     app quits, so we never leak a background python process.
'use strict';

const path = require('path');
const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('child_process');

// The Python package (`spaceinvaders/`) lives one directory up from this
// electron-client/ folder, at newSpaceInvaders/spaceinvaders. `python3 -m
// spaceinvaders.server` must be launched with newSpaceInvaders/ as cwd so
// the package import resolves.
const PROJECT_ROOT = path.join(__dirname, '..');
const PYTHON_BIN = process.env.SPACEINVADERS_PYTHON || 'python3';
const LOCAL_SERVER_START_TIMEOUT_MS = 10000;

let mainWindow = null;
let localServerProcess = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 800,
    minWidth: 700,
    minHeight: 600,
    backgroundColor: '#000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.setMenuBarVisibility(false);
  mainWindow.loadFile(path.join(__dirname, 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

/**
 * Spawn a local authoritative server on an ephemeral port and resolve with
 * the port once the "PORT=<n>" line shows up on its stdout. Resolves with
 * {ok:false, error} instead of rejecting so IPC callers get a plain object
 * back either way.
 */
function startLocalServer(maxPlayers) {
  return new Promise((resolve) => {
    // Only one local server at a time; replace any previous one.
    stopLocalServer();

    const args = [
      '-m', 'spaceinvaders.server',
      '--host', '127.0.0.1',
      '--port', '0',
      '--max-players', String(maxPlayers),
    ];

    let proc;
    try {
      proc = spawn(PYTHON_BIN, args, { cwd: PROJECT_ROOT });
    } catch (err) {
      resolve({ ok: false, error: `failed to spawn ${PYTHON_BIN}: ${err.message}` });
      return;
    }

    localServerProcess = proc;
    let resolved = false;
    let stdoutBuf = '';
    let stderrBuf = '';

    const finish = (result) => {
      if (resolved) return;
      resolved = true;
      clearTimeout(timeoutHandle);
      resolve(result);
    };

    proc.stdout.on('data', (chunk) => {
      stdoutBuf += chunk.toString();
      const match = stdoutBuf.match(/^PORT=(\d+)/m);
      if (match) {
        finish({ ok: true, port: parseInt(match[1], 10), pid: proc.pid });
      }
    });

    proc.stderr.on('data', (chunk) => {
      stderrBuf += chunk.toString();
    });

    proc.on('error', (err) => {
      finish({ ok: false, error: `local server process error: ${err.message}` });
    });

    proc.on('exit', (code, signal) => {
      if (localServerProcess === proc) localServerProcess = null;
      finish({
        ok: false,
        error: `local server exited before reporting a port (code=${code}, signal=${signal})\n${stderrBuf.slice(-800)}`,
      });
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('local-server:exit', { code, signal });
      }
    });

    const timeoutHandle = setTimeout(() => {
      finish({ ok: false, error: 'timed out waiting for local server to report its port' });
    }, LOCAL_SERVER_START_TIMEOUT_MS);
  });
}

function stopLocalServer() {
  if (localServerProcess) {
    try {
      localServerProcess.kill();
    } catch (err) {
      // process already gone; nothing to do.
    }
    localServerProcess = null;
  }
}

ipcMain.handle('local-server:start', async (_event, { maxPlayers }) => {
  const n = Number.isInteger(maxPlayers) ? maxPlayers : 2;
  return startLocalServer(Math.max(1, Math.min(5, n)));
});

ipcMain.handle('local-server:stop', async () => {
  stopLocalServer();
  return { ok: true };
});

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  stopLocalServer();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopLocalServer();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
