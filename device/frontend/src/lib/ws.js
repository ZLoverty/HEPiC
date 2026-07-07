/**
 * Opens a WebSocket that automatically reconnects on close/error.
 * Returns a handle with a `close()` method.
 */
export function createReconnectingWS(url, { onMessage, onOpen, onClose } = {}) {
  let ws    = null;
  let timer = null;
  let alive = true;

  function connect() {
    if (!alive) return;
    try { ws = new WebSocket(url); }
    catch { reschedule(); return; }

    ws.onopen    = () => onOpen?.();
    ws.onmessage = (e) => { try { onMessage?.(JSON.parse(e.data)); } catch {} };
    ws.onerror   = () => {};
    ws.onclose   = () => { onClose?.(); reschedule(); };
  }

  function reschedule() {
    ws = null;
    if (alive) timer = setTimeout(connect, 2000);
  }

  connect();

  return {
    close() {
      alive = false;
      clearTimeout(timer);
      ws?.close();
      ws = null;
    },
  };
}
