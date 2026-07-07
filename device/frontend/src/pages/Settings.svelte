<script>
  import { wsConnected } from '../lib/stores.js';
  import { api } from '../lib/api.js';

  let klipperOk  = null;   // null=checking, true=ok, false=error
  let klipperMsg = '';

  async function checkKlipper() {
    klipperOk = null;
    try {
      const s = await api.klipper.status();
      klipperOk  = true;
      klipperMsg = `热端 ${s.hotend_temperature !== null ? Number(s.hotend_temperature).toFixed(1) : '---'} °C`;
    } catch (e) {
      klipperOk  = false;
      klipperMsg = String(e);
    }
  }

  checkKlipper();
</script>

<div class="layout">
  <div class="section">连接状态</div>

  <div class="row">
    <div class="dot" class:green={$wsConnected} class:red={!$wsConnected}/>
    <span class="name">传感器服务器</span>
    <span class="val" class:ok={$wsConnected} class:bad={!$wsConnected}>
      {$wsConnected ? '已连接' : '未连接'}
    </span>
  </div>

  <div class="row">
    <div
      class="dot"
      class:green={klipperOk === true}
      class:red={klipperOk === false}
      class:amber={klipperOk === null}
    />
    <span class="name">Klipper / Moonraker</span>
    <span class="val" class:ok={klipperOk === true} class:bad={klipperOk === false} class:muted={klipperOk === null}>
      {klipperOk === null ? '检测中...' : klipperOk ? `已连接 · ${klipperMsg}` : '未连接'}
    </span>
    <button class="refresh" on:click={checkKlipper}>刷新</button>
  </div>

  <div class="section" style="margin-top:20px">关于</div>
  <div class="info">
    <div class="info-row"><span>版本</span><span class="mono">v0.1.0</span></div>
    <div class="info-row"><span>系统</span><span class="mono">HEPiC Embedded</span></div>
    <div class="info-row"><span>后端</span><span class="mono">FastAPI + Klipper</span></div>
  </div>
</div>

<style>
  .layout {
    padding: 18px 24px;
    color: #dce4f5;
    font-family: system-ui, sans-serif;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .section {
    font-size: 10px;
    letter-spacing: .16em;
    text-transform: uppercase;
    color: #5a6380;
    margin-bottom: 4px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    background: #131623;
    border: 1px solid #1e2235;
    padding: 0 16px;
    height: 56px;
    border-radius: 2px;
  }
  .dot {
    width: 9px; height: 9px;
    border-radius: 50%;
    flex-shrink: 0;
    background: #3d4560;
    transition: background .4s;
  }
  .dot.green { background: #26bf6e; box-shadow: 0 0 8px #26bf6e88; }
  .dot.red   { background: #e5484d; }
  .dot.amber { background: #f5a623; box-shadow: 0 0 8px #f5a62388; }
  .name { flex: 1; font-size: 14px; }
  .val  { font-size: 13px; font-family: 'Courier New', Courier, monospace; }
  .ok   { color: #26bf6e; }
  .bad  { color: #e5484d; }
  .muted{ color: #5a6380; }
  .refresh {
    background: #1e2235;
    border: 1px solid #2e3352;
    color: #dce4f5;
    font-size: 13px;
    padding: 4px 12px;
    border-radius: 2px;
    cursor: pointer;
    height: 32px;
  }
  .refresh:active { background: #2e3352; }

  .info {
    background: #131623;
    border: 1px solid #1e2235;
    padding: 4px 16px;
    border-radius: 2px;
  }
  .info-row {
    display: flex;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid #1a1e30;
    font-size: 14px;
    color: #5a6380;
  }
  .info-row:last-child { border-bottom: none; }
  .mono { color: #dce4f5; font-family: 'Courier New', Courier, monospace; }
</style>
