<script>
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import { sensorData, forceHistory, wsConnected, qcState, qcForceHistory } from './lib/stores.js';
  import { createReconnectingWS } from './lib/ws.js';
  import NavBar        from './components/NavBar.svelte';
  import Dashboard     from './pages/Dashboard.svelte';
  import ManualControl from './pages/ManualControl.svelte';
  import QualityCheck  from './pages/QualityCheck.svelte';
  import Settings      from './pages/Settings.svelte';

  const MAX_HISTORY = 200;
  const pages = [Dashboard, ManualControl, QualityCheck, Settings];
  let activePage = 0;
  let sensorWs = null;
  let qcWs = null;

  // ── QC WebSocket management ───────────────────────────────────────
  // Tracks $qcState.phase; opens/closes the QC stream WS regardless of
  // which page is visible. This keeps the session alive across navigation.
  $: {
    if ($qcState.phase === 'running' && !qcWs) {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      qcWs = createReconnectingWS(
        `${proto}//${location.host}/api/qc/stream`,
        { onMessage: handleQcMsg },
      );
    } else if ($qcState.phase !== 'running' && qcWs) {
      qcWs.close();
      qcWs = null;
    }
  }

  function handleQcMsg(msg) {
    const text = msg?.response ?? '';
    const up   = text.toUpperCase();

    if (up.includes('STOP_QUALITY_CHECK')) {
      qcState.update(s => ({ ...s, phase: 'done', statusMsg: '质检完毕' }));
      return;
    }
    if (up.includes('START_QUALITY_CHECK')) {
      qcState.update(s => ({ ...s, statusMsg: '正在挤出' }));
      return;
    }
    const m = text.match(/STATUS\s+(.+)/i);
    if (m) qcState.update(s => ({ ...s, statusMsg: m[1].trim() }));
  }

  // ── Sensor WebSocket ──────────────────────────────────────────────
  onMount(() => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    sensorWs = createReconnectingWS(`${proto}//${location.host}/ws/sensors`, {
      onOpen()  { wsConnected.set(true);  },
      onClose() { wsConnected.set(false); },
      onMessage(data) {
        sensorData.set(data);
        const f = data.extrusion_force_N;
        if (f !== null && f !== undefined && isFinite(f)) {
          forceHistory.update(h => {
            const n = [...h, f];
            return n.length > MAX_HISTORY ? n.slice(-MAX_HISTORY) : n;
          });
          // Accumulate QC-specific history while a session is running.
          // Using get() here is intentional: we need the current phase at
          // callback time without creating a reactive subscription.
          if (get(qcState).phase === 'running') {
            qcForceHistory.update(h => {
              const n = [...h, f];
              return n.length > MAX_HISTORY ? n.slice(-MAX_HISTORY) : n;
            });
          }
        }
      },
    });
  });

  onDestroy(() => {
    sensorWs?.close();
    qcWs?.close();
  });
</script>

<div class="shell">
  <main class="content">
    <svelte:component this={pages[activePage]} />
  </main>
  <NavBar active={activePage} on:nav={(e) => (activePage = e.detail)} />
</div>

<style>
  :global(*, *::before, *::after) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(html, body) {
    width: 800px; height: 480px;
    overflow: hidden;
    background: #0b0d14;
    color: #dce4f5;
    font-family: system-ui, -apple-system, sans-serif;
    -webkit-tap-highlight-color: transparent;
    user-select: none;
  }
  :global(button) { cursor: pointer; }

  .shell {
    width: 800px; height: 480px;
    display: flex;
    flex-direction: column;
    background-color: #0b0d14;
    background-image:
      linear-gradient(rgba(30, 34, 53, 0.55) 1px, transparent 1px),
      linear-gradient(90deg, rgba(30, 34, 53, 0.55) 1px, transparent 1px);
    background-size: 24px 24px;
  }
  .content { flex: 1; min-height: 0; overflow: hidden; }
</style>
