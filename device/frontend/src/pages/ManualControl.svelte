<script>
  import { api } from '../lib/api.js';
  import { sensorData } from '../lib/stores.js';

  let targetTemp = 200;
  let feedrate   = 30;
  let busy       = false;

  async function adjustTemp(delta) {
    targetTemp = Math.max(20, Math.min(320, targetTemp + delta));
    api.klipper.setTemp(targetTemp).catch(console.error);
  }

  async function adjustFeedrate(delta) {
    feedrate = Math.max(1, Math.min(150, feedrate + delta));
  }

  async function extrude() {
    if (busy) return;
    busy = true;
    const f = (feedrate * 60).toFixed(0);
    await api.klipper.gcode(`M83\nG1 E50 F${f}\nM82`).catch(console.error);
    busy = false;
  }

  async function retract() {
    if (busy) return;
    busy = true;
    const f = (feedrate * 60).toFixed(0);
    await api.klipper.gcode(`M83\nG1 E-50 F${f}\nM82`).catch(console.error);
    busy = false;
  }

  async function estop() {
    await api.klipper.emergencyStop().catch(console.error);
  }
</script>

<div class="layout">
  <!-- Controls row -->
  <div class="controls">

    <!-- Temperature -->
    <div class="panel">
      <div class="panel-label">目标温度</div>
      <div class="big-num">{targetTemp}<span class="unit">°C</span></div>
      <div class="steps">
        {#each [-10, -1, 1, 10] as d}
          <button class="step-btn" on:click={() => adjustTemp(d)}>
            {d > 0 ? `+${d}` : d}
          </button>
        {/each}
      </div>
      <div class="actual">
        实测&nbsp;{$sensorData.hotend_temperature !== null
          ? Number($sensorData.hotend_temperature).toFixed(1) + ' °C'
          : '---'}
      </div>
    </div>

    <div class="vdiv" />

    <!-- Feedrate -->
    <div class="panel">
      <div class="panel-label">挤出速度</div>
      <div class="big-num">{feedrate}<span class="unit">mm/s</span></div>
      <div class="steps">
        {#each [-5, -1, 1, 5] as d}
          <button class="step-btn" on:click={() => adjustFeedrate(d)}>
            {d > 0 ? `+${d}` : d}
          </button>
        {/each}
      </div>
      <div class="actual">
        实测&nbsp;{$sensorData.measured_feedrate_mms !== null
          ? Number($sensorData.measured_feedrate_mms).toFixed(1) + ' mm/s'
          : '---'}
      </div>
    </div>
  </div>

  <!-- Actions row -->
  <div class="actions">
    <button class="act extrude" on:click={extrude} disabled={busy}>挤出 50mm</button>
    <button class="act retract" on:click={retract} disabled={busy}>退料 50mm</button>
    <button class="act estop"   on:click={estop}>急&nbsp;停</button>
  </div>
</div>

<style>
  .layout {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
  }
  .controls {
    flex: 1;
    display: flex;
    min-height: 0;
  }
  .panel {
    flex: 1;
    padding: 18px 28px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    justify-content: center;
  }
  .vdiv {
    width: 1px;
    background: #1e2235;
    margin: 16px 0;
  }
  .panel-label {
    font-size: 10px;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: #5a6380;
    font-family: system-ui, sans-serif;
  }
  .big-num {
    font-family: 'Courier New', Courier, monospace;
    font-size: 62px;
    font-weight: 700;
    color: #dce4f5;
    line-height: 1;
  }
  .unit {
    font-size: 18px;
    color: #5a6380;
    margin-left: 6px;
    font-family: system-ui, sans-serif;
  }
  .steps {
    display: flex;
    gap: 8px;
  }
  .step-btn {
    flex: 1;
    height: 58px;
    background: #131623;
    border: 1px solid #1e2235;
    color: #dce4f5;
    font-size: 17px;
    font-family: 'Courier New', Courier, monospace;
    border-radius: 2px;
    cursor: pointer;
    transition: background .1s, border-color .1s;
  }
  .step-btn:active {
    background: #1e2235;
    border-color: #5b8dee;
  }
  .actual {
    font-size: 12px;
    color: #5a6380;
    font-family: 'Courier New', Courier, monospace;
  }

  /* action row */
  .actions {
    height: 82px;
    border-top: 1px solid #1e2235;
    display: flex;
    gap: 10px;
    padding: 12px 16px;
    background: #0a0c14;
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
  .extrude:not(:disabled):active { background: #1a3a28; }

  .retract { background: #0e1528; border-color: #5b8dee55; color: #5b8dee; }
  .retract:not(:disabled):active { background: #1a2442; }

  .estop {
    flex: .6;
    background: #22100e;
    border-color: #e5484d;
    color: #e5484d;
    font-size: 20px;
    letter-spacing: .08em;
  }
  .estop:active { background: #e5484d !important; color: #fff; opacity: 1 !important; }
</style>
