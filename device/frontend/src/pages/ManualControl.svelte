<script>
  import { api } from '../lib/api.js';
  import { sensorData } from '../lib/stores.js';

  // Fixed extrusion speed: 3 mm/s, 5 mm per batch ≈ 1.67 s per batch.
  // Interval is 100 ms shorter than execution time so batches chain without gaps.
  const SPEED_MMS   = 3;
  const BATCH_MM    = 5;
  const BATCH_MS    = Math.floor(BATCH_MM / SPEED_MMS * 1000) - 100; // 1567 ms

  let targetTemp = 200;
  let stopped    = false;
  let holdTimer  = null;

  // ── Numpad state ──────────────────────────────────────────────────
  let numpadOpen  = false;
  let numpadInput = '';

  function openNumpad() {
    numpadInput = String(targetTemp);
    numpadOpen  = true;
  }

  function numpadKey(k) {
    if (k === '⌫') {
      numpadInput = numpadInput.slice(0, -1);
    } else if (numpadInput.length < 3) {
      numpadInput += k;
    }
  }

  function confirmTemp() {
    const v = parseInt(numpadInput, 10);
    if (!isNaN(v) && v >= 20 && v <= 320) {
      targetTemp = v;
      api.klipper.setTemp(targetTemp).catch(console.error);
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

  // ── Emergency stop / restart ──────────────────────────────────────
  async function estop() {
    endHold();
    await api.klipper.emergencyStop().catch(console.error);
    stopped = true;
  }

  async function restart() {
    await api.klipper.restart().catch(console.error);
    stopped = false;
  }
</script>

<div class="layout">

  <!-- Temperature panel (full width, tap to set) -->
  <button class="panel" on:click={openNumpad}>
    <div class="panel-label">目标温度&nbsp;·&nbsp;点击设置</div>
    <div class="big-num">{targetTemp}<span class="unit">°C</span></div>
    <div class="actual-row">
      <span class="actual-item">
        热端&nbsp;{$sensorData.hotend_temperature !== null
          ? Number($sensorData.hotend_temperature).toFixed(1) + ' °C'
          : '---'}
      </span>
      <span class="actual-sep">·</span>
      <span class="actual-item">
        速度&nbsp;{$sensorData.measured_feedrate_mms !== null && isFinite($sensorData.measured_feedrate_mms)
          ? Number($sensorData.measured_feedrate_mms).toFixed(1) + ' mm/s'
          : '---'}
      </span>
    </div>
  </button>

  <!-- Actions row -->
  <div class="actions">
    {#if stopped}
      <button class="act restart" on:click={restart}>固件重启</button>
    {:else}
      <button class="act extrude"
        on:pointerdown={() => startHold(1)}
        on:pointerup={endHold}
        on:pointercancel={endHold}>
        按住挤出
      </button>
      <button class="act retract"
        on:pointerdown={() => startHold(-1)}
        on:pointerup={endHold}
        on:pointercancel={endHold}>
        按住回抽
      </button>
    {/if}
    <button class="act estop" on:click={estop}>急&nbsp;停</button>
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
    flex-direction: column;
  }

  /* ── Temperature panel ── */
  .panel {
    flex: 1;
    min-height: 0;
    width: 100%;
    padding: 24px 36px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    justify-content: center;
    align-items: flex-start;
    background: transparent;
    border: none;
    cursor: pointer;
    text-align: left;
    transition: background .12s;
  }
  .panel:active { background: rgba(91,141,238,.06); }

  .panel-label {
    font-size: 12px;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: #7888b0;
    font-family: system-ui, sans-serif;
  }
  .big-num {
    font-family: 'Courier New', Courier, monospace;
    font-size: 72px;
    font-weight: 700;
    color: #eef2ff;
    line-height: 1;
  }
  .unit {
    font-size: 20px;
    color: #7888b0;
    margin-left: 8px;
    font-family: system-ui, sans-serif;
  }
  .actual-row {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 14px;
    color: #7888b0;
    font-family: 'Courier New', Courier, monospace;
  }
  .actual-sep { color: #3a4460; }

  /* ── Actions row ── */
  .actions {
    height: 82px;
    border-top: 1px solid #252d48;
    display: flex;
    gap: 10px;
    padding: 12px 16px;
    background: #0f1220;
  }
  .act {
    flex: 1;
    height: 58px;
    border-radius: 2px;
    font-size: 18px;
    font-weight: 600;
    font-family: system-ui, sans-serif;
    cursor: pointer;
    transition: opacity .1s, background .12s;
    border: 1px solid;
  }
  .act:active   { opacity: .68; }
  .act:disabled { opacity: .35; cursor: not-allowed; }

  .extrude { background: #0e2218; border-color: #26bf6e55; color: #26bf6e; }
  .extrude:active { background: #1a3a28; }

  .retract { background: #0e1528; border-color: #5b8dee55; color: #5b8dee; }
  .retract:active { background: #1a2442; }

  .restart {
    background: #1a1408;
    border-color: #f0a82555;
    color: #f0a825;
    font-size: 18px;
  }
  .restart:active { background: #2c2010; }

  .estop {
    flex: .6;
    background: #22100e;
    border-color: #e5484d;
    color: #e5484d;
    font-size: 20px;
    letter-spacing: .08em;
  }
  .estop:active { background: #e5484d !important; color: #fff; opacity: 1 !important; }

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
