<script>
  import { onDestroy } from 'svelte';
  import LineChart from '../components/LineChart.svelte';
  import { api } from '../lib/api.js';
  import { sensorData, qcState, qcForceHistory } from '../lib/stores.js';

  // ── Ephemeral UI state: material picker lists ─────────────────────
  let families  = [];
  let piCodes   = [];
  let loadFam   = true;
  let loadCodes = false;
  let loadMat   = false;

  // ── Derived display values ────────────────────────────────────────
  $: fMin       = $qcState.material?.force_range?.[0] ?? null;
  $: fMax       = $qcState.material?.force_range?.[1] ?? null;
  $: liveTemp   = $sensorData.hotend_temperature;
  $: liveFeed   = $sensorData.measured_feedrate_mms;

  // Freeze the reading the instant the run finishes, so the inspector has
  // time to record it instead of watching it keep drifting toward zero.
  let frozenForce = null;
  $: if ($qcState.phase === 'done' && frozenForce === null) {
    frozenForce = $sensorData.extrusion_force_N;
  }
  $: if ($qcState.phase !== 'done') {
    frozenForce = null;
  }
  $: curForce   = $qcState.phase === 'done' ? frozenForce : $sensorData.extrusion_force_N;
  $: forceColor = (() => {
    if (curForce === null || !isFinite(curForce) || fMin === null) return '#f5a623';
    if (curForce < fMin || curForce > fMax) return '#e5484d';
    return '#26bf6e';
  })();

  // ── Progress tracking ─────────────────────────────────────────────
  // Extrude duration comes from material data (mirrors the gcode builder logic).
  $: extrudeDurationMs = (() => {
    const mat = $qcState.material;
    if (!mat?.speed) return 60000;
    const len = mat.quality_check_extrude_length_mm ?? (mat.speed * 60);
    return (len / mat.speed) * 1000;
  })();

  let tickProgress = 0;   // 0-1, updated by interval during extrusion
  let extrudeTimer = null;

  // Start/stop timer based on whether extrusion has begun.
  $: {
    if ($qcState.extrudeStartedAt && $qcState.phase === 'running') {
      if (!extrudeTimer) {
        extrudeTimer = setInterval(() => {
          const elapsed = Date.now() - $qcState.extrudeStartedAt;
          tickProgress  = Math.min(elapsed / extrudeDurationMs, 1);
        }, 250);
      }
    } else {
      clearInterval(extrudeTimer);
      extrudeTimer  = null;
      tickProgress  = 0;
    }
  }

  // Unified 0-1 progress value across all phases.
  $: qcProgress = (() => {
    if ($qcState.phase === 'idle') return 0;
    if ($qcState.phase === 'done') return 1;
    if ($qcState.extrudeStartedAt)
      return 0.30 + tickProgress * 0.68;   // 30 %→98 % during extrusion
    // Pre-extrusion: rough estimate from status message
    const msg = $qcState.statusMsg;
    if (msg.includes('归零')) return 0.18;
    if (msg.includes('加热')) return 0.05;
    return 0.02;
  })();

  $: qcPct          = Math.round(qcProgress * 100);
  $: isIndeterminate = $qcState.phase === 'running' && !$qcState.extrudeStartedAt
                       && $qcState.statusMsg.includes('加热');

  // Standard deviation over the 30 s rolling window stored in qcForceHistory.
  $: stdDev30s = (() => {
    const pts = $qcForceHistory.filter(v => v !== null && isFinite(v));
    if (pts.length < 2) return null;
    const mean = pts.reduce((a, b) => a + b, 0) / pts.length;
    const variance = pts.reduce((s, v) => s + (v - mean) ** 2, 0) / pts.length;
    return Math.sqrt(variance);
  })();

  onDestroy(() => { clearInterval(extrudeTimer); });

  // ── Init: load family list ────────────────────────────────────────
  api.materials.families()
    .then(d => { families = d.families ?? []; })
    .catch(console.error)
    .finally(() => { loadFam = false; });

  if ($qcState.family) {
    loadCodes = true;
    api.materials.list($qcState.family)
      .then(d => { piCodes = d.pi_codes ?? []; })
      .catch(console.error)
      .finally(() => { loadCodes = false; });
  }

  // ── Material picker actions ───────────────────────────────────────
  async function pickFamily(fam) {
    qcState.update(s => ({ ...s, family: fam, piCode: null, material: null }));
    piCodes = []; loadCodes = true;
    try   { piCodes = (await api.materials.list(fam)).pi_codes ?? []; }
    catch { piCodes = []; }
    finally { loadCodes = false; }
  }

  async function pickCode(code) {
    loadMat = true;
    try {
      const mat = await api.materials.get($qcState.family, code);
      qcState.update(s => ({ ...s, piCode: code, material: mat }));
    } catch {
      qcState.update(s => ({ ...s, piCode: code, material: null }));
    } finally { loadMat = false; }
  }

  // ── QC session actions ────────────────────────────────────────────
  async function startQC() {
    if (!$qcState.family || !$qcState.piCode) return;
    qcForceHistory.set([]);
    qcState.update(s => ({ ...s, phase: 'running', statusMsg: '正在启动...', extrudeStartedAt: null }));
    await api.qc.start($qcState.family, $qcState.piCode).catch(console.error);
  }

  async function abort() {
    clearInterval(extrudeTimer);
    extrudeTimer = null;
    qcState.update(s => ({ ...s, phase: 'idle', statusMsg: '', extrudeStartedAt: null }));
    await api.klipper.emergencyStop().catch(console.error);
  }

  function finish() {
    qcState.update(s => ({ ...s, phase: 'idle', statusMsg: '', extrudeStartedAt: null }));
  }
</script>

<!-- ═══════════════════════════════════ CONFIG ══════════════════════ -->
{#if $qcState.phase === 'idle'}
<div class="config">

  <div class="col">
    <div class="col-title">材料系列</div>
    <div class="chip-grid">
      {#if loadFam}
        <span class="muted">加载中...</span>
      {:else if families.length === 0}
        <span class="muted">无数据</span>
      {:else}
        {#each families as fam}
          <button
            class="chip" class:sel={$qcState.family === fam}
            on:click={() => pickFamily(fam)}
          >{fam}</button>
        {/each}
      {/if}
    </div>
  </div>

  <div class="divv"/>

  <div class="col">
    <div class="col-title">型号</div>
    <div class="chip-grid">
      {#if !$qcState.family}
        <span class="muted">请先选择系列</span>
      {:else if loadCodes}
        <span class="muted">加载中...</span>
      {:else}
        {#each piCodes as code}
          <button
            class="chip" class:sel={$qcState.piCode === code}
            on:click={() => pickCode(code)}
          >{code}</button>
        {/each}
      {/if}
    </div>
  </div>

  <div class="divv"/>

  <div class="confirm">
    <div class="col-title">确认</div>
    {#if loadMat}
      <span class="muted">加载中...</span>
    {:else if $qcState.material}
      <div class="mat-card">
        <div class="mat-row"><span class="mk">材料</span><span class="mv">{$qcState.material.name ?? $qcState.piCode}</span></div>
        <div class="mat-row"><span class="mk">型号</span><span class="mv mono">{$qcState.piCode}</span></div>
        <div class="mat-row"><span class="mk">温度</span><span class="mv mono orange">{$qcState.material.temperature} °C</span></div>
        <div class="mat-row"><span class="mk">速度</span><span class="mv mono blue">{$qcState.material.speed} mm/s</span></div>
        {#if $qcState.material.force_range}
          <div class="mat-row">
            <span class="mk">目标力</span>
            <span class="mv mono amber">{$qcState.material.force_range[0]}–{$qcState.material.force_range[1]} N</span>
          </div>
        {/if}
      </div>
      <button class="start-btn" on:click={startQC}>开始质检</button>
    {:else if $qcState.piCode}
      <span class="muted">无法获取材料信息</span>
    {:else}
      <span class="muted">请选择型号</span>
    {/if}
  </div>
</div>

<!-- ═══════════════════════════════════ RUNNING / DONE ══════════════ -->
{:else}
<div class="running">

  <div class="force-col">
    <div class="phase-badge" class:done={$qcState.phase === 'done'}>
      {$qcState.phase === 'done' ? '完成' : '运行中'}
    </div>
    <div class="status-text">{$qcState.statusMsg}</div>

    <div class="live-meta">
      <span class="lm-item"><span class="lm-dot temp"></span>{liveTemp !== null && isFinite(liveTemp) ? Number(liveTemp).toFixed(1) : '--'}&nbsp;°C</span>
      <span class="lm-item"><span class="lm-dot spd"></span>{liveFeed !== null && isFinite(liveFeed) ? Number(liveFeed).toFixed(1) : '--'}&nbsp;mm/s</span>
    </div>

    <!-- Progress bar -->
    <div class="prog-wrap">
      <div
        class="prog-bar"
        class:indeterminate={isIndeterminate}
        class:done={$qcState.phase === 'done'}
        style="width:{isIndeterminate ? 100 : qcPct}%"
      ></div>
      <span class="prog-pct" class:done={$qcState.phase === 'done'}>{qcPct}%</span>
    </div>

    <div class="force-block">
      <div class="force-main">
        <div class="force-label">挤出力</div>
        <div class="force-num" style="color:{forceColor}; text-shadow:0 0 32px {forceColor}55">
          {curForce !== null && isFinite(curForce) ? Number(curForce).toFixed(2) : '---'}
        </div>
      </div>
      <div class="force-std">
        <div class="std-num">
          ±{stdDev30s !== null ? stdDev30s.toFixed(3) : '---'}
        </div>
      </div>
    </div>

    {#if fMin !== null}
      <div class="ref-range">目标 {fMin}–{fMax} N</div>
    {/if}

    <div class="run-actions">
      {#if $qcState.phase === 'done'}
        <button class="done-btn" on:click={finish}>完成</button>
      {:else}
        <button class="abort-btn" on:click={abort}>中止</button>
      {/if}
    </div>
  </div>

  <div class="run-chart">
    <LineChart data={$qcForceHistory} color={forceColor} title="质检挤出力" unit="N" />
  </div>
</div>
{/if}

<style>
  /* ── Config ──────────────────────────────────────────────── */
  .config { width: 100%; height: 100%; display: flex; }
  .col {
    flex: 1; padding: 14px 16px;
    display: flex; flex-direction: column; gap: 10px; min-width: 0;
  }
  .confirm {
    flex: 1.15; padding: 14px 16px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .divv { width: 1px; background: #252d48; margin: 12px 0; }
  .col-title {
    font-size: 12px; letter-spacing: .12em; text-transform: uppercase;
    color: #7888b0; font-family: system-ui, sans-serif;
  }
  .chip-grid { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    height: 52px; min-width: 72px; padding: 0 14px;
    background: #1a1f35; border: 1px solid #252d48;
    color: #eef2ff; font-size: 14px;
    font-family: 'Courier New', Courier, monospace;
    border-radius: 2px; cursor: pointer;
    transition: background .1s, border-color .1s, color .1s;
  }
  .chip:active { background: #252d48; }
  .chip.sel { background: #0f1a38; border-color: #7aa5f4; color: #7aa5f4; }
  .muted { color: #5a6888; font-size: 13px; font-family: system-ui, sans-serif; }

  .mat-card {
    background: #131828; border: 1px solid #252d48;
    padding: 10px 12px; display: flex; flex-direction: column; gap: 6px;
  }
  .mat-row {
    display: flex; justify-content: space-between;
    align-items: baseline; font-size: 13px;
  }
  .mk { color: #7888b0; font-family: system-ui, sans-serif; }
  .mv { color: #eef2ff; font-family: system-ui, sans-serif; }
  .mono   { font-family: 'Courier New', Courier, monospace !important; }
  .orange { color: #f97316 !important; }
  .blue   { color: #7aa5f4  !important; }
  .amber  { color: #f5a623  !important; }

  .start-btn {
    margin-top: auto; height: 60px;
    background: #0b2016; border: 1px solid #26bf6e;
    color: #26bf6e; font-size: 20px; font-weight: 600;
    font-family: system-ui, sans-serif; letter-spacing: .04em;
    border-radius: 2px; cursor: pointer; transition: background .12s;
  }
  .start-btn:active { background: #26bf6e; color: #141824; }

  /* ── Running / Done ──────────────────────────────────────── */
  .running { width: 100%; height: 100%; display: flex; }
  .force-col {
    width: 272px; flex-shrink: 0;
    border-right: 1px solid #252d48;
    padding: 14px 16px;
    display: flex; flex-direction: column; gap: 4px;
  }
  .phase-badge {
    display: inline-flex; align-items: center;
    font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
    color: #7aa5f4; font-family: system-ui, sans-serif; gap: 6px;
  }
  .phase-badge::before {
    content: ''; display: inline-block; width: 7px; height: 7px;
    border-radius: 50%; background: #7aa5f4; box-shadow: 0 0 7px #7aa5f4aa;
  }
  .phase-badge.done { color: #26bf6e; }
  .phase-badge.done::before { background: #26bf6e; box-shadow: 0 0 7px #26bf6eaa; }

  .status-text {
    font-size: 13px; color: #7888b0;
    font-family: system-ui, sans-serif; min-height: 18px;
  }

  .live-meta {
    display: flex; gap: 14px; margin-bottom: 2px;
    font-size: 11px; color: #9aa8cc;
    font-family: 'Courier New', Courier, monospace;
  }
  .lm-item { display: flex; align-items: center; gap: 5px; }
  .lm-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
  .lm-dot.temp { background: #f97316; }
  .lm-dot.spd  { background: #7aa5f4; }

  /* ── Progress bar ─────────────────────────────────────── */
  .prog-wrap {
    position: relative;
    height: 5px;
    background: #1a1f35;
    border-radius: 3px;
    margin: 6px 0 14px;
    overflow: hidden;
  }
  .prog-bar {
    height: 100%;
    background: #7aa5f4;
    border-radius: 3px;
    transition: width .4s ease;
  }
  .prog-bar.done { background: #26bf6e; }

  @keyframes sweep {
    0%   { transform: translateX(-100%); }
    100% { transform: translateX(100%);  }
  }
  .prog-bar.indeterminate {
    background: linear-gradient(90deg, #1a2a50 30%, #7aa5f4 50%, #1a2a50 70%);
    background-size: 200% 100%;
    animation: sweep 1.6s ease-in-out infinite;
    width: 100% !important;
  }
  .prog-pct {
    position: absolute;
    right: 0;
    top: -20px;
    font-size: 12px;
    color: #7aa5f4;
    font-family: 'Courier New', Courier, monospace;
  }
  .prog-pct.done { color: #26bf6e; }

  .force-block {
    display: flex; flex-direction: row; gap: 0; margin: auto 0;
    align-items: flex-end;
  }
  .force-main { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .force-std  {
    display: flex; flex-direction: column; align-items: flex-end;
    padding-left: 12px; flex-shrink: 0;
  }
  .force-label {
    font-size: 12px; letter-spacing: .14em; text-transform: uppercase;
    color: #7888b0; font-family: system-ui, sans-serif;
  }
  .force-num {
    font-family: 'Courier New', Courier, monospace;
    font-size: 60px; font-weight: 700; line-height: 1;
    transition: color .3s, text-shadow .3s;
  }
  .std-num {
    font-family: 'Courier New', Courier, monospace;
    font-size: 20px; font-weight: 700; line-height: 1;
    color: #eef2ff;
  }
  .ref-range {
    font-size: 12px; color: #7888b0;
    font-family: 'Courier New', Courier, monospace; margin-top: 4px;
  }
  .run-actions { margin-top: auto; }
  .abort-btn, .done-btn {
    width: 100%; height: 54px; font-size: 17px; font-weight: 600;
    font-family: system-ui, sans-serif; letter-spacing: .08em;
    border-radius: 2px; cursor: pointer; transition: background .12s;
  }
  .abort-btn { background: #220e0e; border: 1px solid #e5484d; color: #e5484d; }
  .abort-btn:active { background: #e5484d; color: #fff; }
  .done-btn  { background: #0b2016; border: 1px solid #26bf6e; color: #26bf6e; }
  .done-btn:active  { background: #26bf6e; color: #141824; }
  .run-chart { flex: 1; min-width: 0; padding: 6px 6px 6px 2px; }
</style>
