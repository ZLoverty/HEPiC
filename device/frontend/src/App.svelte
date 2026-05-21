<script>
  import { onMount, onDestroy } from 'svelte';
  import { sensorData, forceHistory, wsConnected } from './lib/stores.js';
  import { createReconnectingWS } from './lib/ws.js';
  import NavBar       from './components/NavBar.svelte';
  import Dashboard    from './pages/Dashboard.svelte';
  import ManualControl from './pages/ManualControl.svelte';
  import QualityCheck  from './pages/QualityCheck.svelte';
  import Settings      from './pages/Settings.svelte';

  const MAX_HISTORY = 200;
  const pages = [Dashboard, ManualControl, QualityCheck, Settings];
  let activePage = 0;
  let ws = null;

  onMount(() => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = createReconnectingWS(`${proto}//${location.host}/ws/sensors`, {
      onOpen()  { wsConnected.set(true);  },
      onClose() { wsConnected.set(false); },
      onMessage(data) {
        sensorData.set(data);
        const f = data.extrusion_force_N;
        if (f !== null && f !== undefined && isFinite(f)) {
          forceHistory.update(h => {
            const next = [...h, f];
            return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next;
          });
        }
      },
    });
  });

  onDestroy(() => ws?.close());
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
    /* subtle grid-paper texture */
    background-color: #0b0d14;
    background-image:
      linear-gradient(rgba(30, 34, 53, 0.55) 1px, transparent 1px),
      linear-gradient(90deg, rgba(30, 34, 53, 0.55) 1px, transparent 1px);
    background-size: 24px 24px;
  }
  .content {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
</style>
