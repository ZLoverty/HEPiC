<script>
  import MetricCard from '../components/MetricCard.svelte';
  import LineChart  from '../components/LineChart.svelte';
  import { api } from '../lib/api.js';
  import { sensorData, forceHistory } from '../lib/stores.js';

  $: force    = $sensorData.extrusion_force_N;
  $: feedrate = $sensorData.measured_feedrate_mms;
  $: temp     = $sensorData.hotend_temperature;
  $: target   = $sensorData.target_temperature;
  $: tempSub  = target !== null ? `目标 ${Number(target).toFixed(0)} °C` : null;

  // Firmware enters "shutdown" after an emergency stop and stays unresponsive
  // until FIRMWARE_RESTART — same condition the App-level banner uses to show
  // its restart button, so extrude/retract/estop just disable rather than
  // duplicating restart logic locally.
  $: stopped = $sensorData.klippy_state === 'shutdown' || $sensorData.klippy_state === 'error';

  // Fixed extrusion speed: 3 mm/s, 5 mm per batch ≈ 1.67 s per batch.
  // Interval is 100 ms shorter than execution time so batches chain without gaps.
  const SPEED_MMS = 3;
  const BATCH_MM  = 5;
  const BATCH_MS  = Math.floor(BATCH_MM / SPEED_MMS * 1000) - 100; // 1567 ms

  let holdTimer = null;

  // ── Numpad state ──────────────────────────────────────────────────
  let numpadOpen  = false;
  let numpadInput = '';
  // True until the first keypress after opening: lets a digit overwrite the
  // prefilled default instead of appending to it, without touching normal
  // append/backspace behavior on every keypress after that.
  let numpadFresh = false;

  function openNumpad() {
    numpadInput = (target !== null && target !== undefined) ? String(Math.round(target)) : '200';
    numpadFresh = true;
    numpadOpen  = true;
  }

  function numpadKey(k) {
    if (k === '⌫') {
      numpadInput = numpadInput.slice(0, -1);
    } else if (numpadFresh) {
      numpadInput = k;
    } else if (numpadInput.length < 3) {
      numpadInput += k;
    }
    numpadFresh = false;
  }

  function confirmTemp() {
    const v = parseInt(numpadInput, 10);
    if (!isNaN(v) && v >= 20 && v <= 320) {
      api.klipper.setTemp(v).catch(console.error);
    }
    numpadOpen = false;
  }

  // ── Long-press extrude / retract ──────────────────────────────────
  function startHold(dir) {
    if (stopped) return;
    const f    = (SPEED_MMS * 60).toFixed(0);
    const send = () =>
      api.klipper.gcode(`M83\nG1 E${dir * BATCH_MM} F${f}\nM82`).catch(console.error);
    send();
    holdTimer = setInterval(send, BATCH_MS);
  }

  function endHold() {
    if (holdTimer !== null) {
      clearInterval(holdTimer);
      holdTimer = null;
    }
  }

  // ── Emergency stop ─────────────────────────────────────────────────
  async function estop() {
    endHold();
    await api.klipper.emergencyStop().catch(console.error);
  }
</script>

<div class="layout">
  <!-- Left: hold-to-extrude/retract, compressed live metrics, e-stop -->
  <div class="side">
    <div class="hold-btns">
      <button class="act extrude" disabled={stopped}
        on:pointerdown={() => startHold(1)}
        on:pointerup={endHold}
        on:pointercancel={endHold}>
        按住挤出
      </button>
      <button class="act retract" disabled={stopped}
        on:pointerdown={() => startHold(-1)}
        on:pointerup={endHold}
        on:pointercancel={endHold}>
        按住回抽
      </button>
    </div>

    <div class="metrics">
      <MetricCard label="挤出力"  value={force}    unit="N"    color="#f5a623" decimals={2} />
      <MetricCard label="进线速度" value={feedrate} unit="mm/s" color="#5b8dee" decimals={1} />
      <MetricCard label="热端温度" value={temp}     unit="°C"   color="#f97316" decimals={1}
        secondary={tempSub} clickable on:click={openNumpad} />
    </div>

    <button class="act estop" disabled={stopped} on:click={estop}>急&nbsp;停</button>
  </div>

  <!-- Right: live force sparkline -->
  <div class="chart">
    <LineChart data={$forceHistory} color="#f5a623" title="挤出力历史" unit="N" />
  </div>

  <!-- Numpad overlay -->
  {#if numpadOpen}
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="overlay" on:click|self={() => (numpadOpen = false)}>
      <div class="numpad">
        <div class="np-display">
          {numpadInput || '0'}<span class="np-unit">°C</span>
        </div>
        <div class="np-grid">
          {#each ['7','8','9','4','5','6','1','2','3','⌫','0','✓'] as k}
            <button
              class="np-key {k === '✓' ? 'np-confirm' : k === '⌫' ? 'np-back' : ''}"
              on:click={() => k === '✓' ? confirmTemp() : numpadKey(k)}>
              {k}
            </button>
          {/each}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .layout {
    position: relative;
    width: 100%;
    height: 100%;
    display: flex;
  }
  .side {
    width: 258px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    border-right: 1px solid #252d48;
  }
  .chart {
    flex: 1;
    min-width: 0;
    padding: 4px 4px 4px 0;
  }

  /* ── Hold-to-extrude / retract ── */
  .hold-btns {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    border-bottom: 1px solid #252d48;
  }

  /* ── Compressed metric cards ── */
  .metrics {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .metrics :global(.card) { padding: 6px 18px; }
  .metrics :global(.card .num) { font-size: 34px; }
  .metrics :global(.card .secondary) { font-size: 13px; }
  .metrics :global(.card:last-child) { border-bottom: none; }

  /* ── Action buttons (extrude / retract / estop) ── */
  .act {
    width: 100%;
    height: 40px;
    border-radius: 2px;
    font-size: 15px;
    font-weight: 600;
    font-family: system-ui, sans-serif;
    cursor: pointer;
    transition: opacity .1s, background .12s;
    border: 1px solid;
    border-radius: 0;
  }
  .act:active   { opacity: .68; }
  .act:disabled { opacity: .35; cursor: not-allowed; }

  .extrude { background: #0e2218; border-color: #26bf6e55; color: #26bf6e; }
  .extrude:active:not(:disabled) { background: #1a3a28; }

  .retract { background: #0e1528; border-color: #5b8dee55; color: #5b8dee; border-top: none; }
  .retract:active:not(:disabled) { background: #1a2442; }

  .estop {
    flex-shrink: 0;
    height: 46px;
    background: #22100e;
    border-color: #e5484d;
    color: #e5484d;
    font-size: 17px;
    letter-spacing: .08em;
    border-top: 1px solid #252d48;
  }
  .estop:active:not(:disabled) { background: #e5484d !important; color: #fff; opacity: 1 !important; }

  /* ── Numpad overlay ── */
  .overlay {
    position: absolute;
    inset: 0;
    background: rgba(7, 9, 16, .72);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
  }
  .numpad {
    background: #151b2e;
    border: 1px solid #252d48;
    border-radius: 4px;
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    width: 290px;
  }
  .np-display {
    font-family: 'Courier New', Courier, monospace;
    font-size: 52px;
    font-weight: 700;
    color: #eef2ff;
    text-align: right;
    padding: 0 6px;
    line-height: 1;
    border-bottom: 1px solid #252d48;
    padding-bottom: 12px;
  }
  .np-unit {
    font-size: 16px;
    color: #5a6380;
    margin-left: 4px;
  }
  .np-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }
  .np-key {
    height: 56px;
    background: #1a1f35;
    border: 1px solid #252d48;
    color: #eef2ff;
    font-size: 22px;
    font-family: 'Courier New', Courier, monospace;
    border-radius: 2px;
    cursor: pointer;
    transition: background .1s;
  }
  .np-key:active  { background: #252d48; }
  .np-back  { color: #e5484d; font-size: 18px; }
  .np-confirm {
    background: #0e2218;
    border-color: #26bf6e55;
    color: #26bf6e;
    font-size: 20px;
  }
  .np-confirm:active { background: #1a3a28; }
</style>
