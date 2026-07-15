// Minimal, safe context bridge. contextIsolation is ON and nodeIntegration
// is OFF in main.js (Electron's secure defaults are left untouched); this is
// the only surface the renderer gets into the main process, and it exposes
// nothing beyond "start/stop the local offline server" + its exit event.
//
// The renderer's WebSocket client itself does NOT go through this bridge —
// it uses the browser-native `WebSocket` global directly (see renderer.js
// for why). This bridge only concerns the child-process lifecycle for
// offline play, which requires Node's child_process and must live in main.
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('spaceInvaders', {
  /**
   * Ask main to spawn a local `python3 -m spaceinvaders.server` on an
   * ephemeral port. Resolves { ok: true, port } or { ok: false, error }.
   */
  startLocalServer: (maxPlayers) => ipcRenderer.invoke('local-server:start', { maxPlayers }),

  /** Ask main to kill the currently-running local server, if any. */
  stopLocalServer: () => ipcRenderer.invoke('local-server:stop'),

  /** Subscribe to unexpected local server exits (e.g. python crashed). */
  onLocalServerExit: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('local-server:exit', listener);
    return () => ipcRenderer.removeListener('local-server:exit', listener);
  },
});
