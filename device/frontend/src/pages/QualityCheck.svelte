<script>
  import LineChart from '../components/LineChart.svelte';
  import { api } from '../lib/api.js';
  import { sensorData, qcState, qcForceHistory } from '../lib/stores.js';

  // ── Ephemeral UI state: material picker lists ─────────────────────
  // These are fetch results for the dropdowns, not session state.
  let families  = [];
  let piCodes   = [];
  let loadFam   = true;
  let loadCodes = false;
  let loadMat   = false;

  // ── Derived display values ────────────────────────────────────────
  $: fMin       = $qcState.material?.force_range?.[0] ?? null;
  $: fMax       = $qcState.material?.force_range?.[1] ?? null;
  $: curForce   = $sensorData.extrusion_force_N;
  $: forceColor = (() => {
    if (curForce === null || !isFinite(curForce) || fMin === null) return '#f5a623';
    if (curForce < fMin || curForce > fMax) return '#e5484d';
    return '#26bf6e';
  })();

  // ── Init: load family list; restore pi codes if family was already set ──
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
  // No WebSocket management here. App.svelte opens /api/qc/stream
  // when phase === 'running' and closes it when phase leaves 'running'.

  async function startQC() {
    if (!$qcState.family || !$qcState.piCode) return;
    qcForceHistory.set([]);
    qcState.update(s => ({ ...s, phase: 'running', statusMsg: '正在启动...' }));
    await api.qc.start($qcState.family, $qcState.piCode).catch(console.error);
  }

  async function abort() {
    qcState.update(s => ({ ...s, phase: 'idle', statusMsg: '' }));
    await api.klipper.emergencyStop().catch(console.error);
  }

  function finish() {
    qcState.update(s => ({ ...s, phase: 'idle', statusMsg: '' }));
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

    <div class="force-block">
      <div class="force-label">挤出力</div>
      <div class="force-num" style="color:{forceColor}; text-shadow:0 0 32px {forceColor}55">
        {curForce !== null && isFinite(curForce) ? Number(curForce).toFixed(2) : '---'}
      </div>
      <div class="force-unit">N</div>
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
  .divv { width: 1px; background: #1e2235; margin: 12px 0; }
  .col-title {
    font-size: 9px; letter-spacing: .14em; text-transform: uppercase;
    color: #5a6380; font-family: system-ui, sans-serif;
  }
  .chip-grid { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    height: 52px; min-width: 72px; padding: 0 14px;
    background: #131623; border: 1px solid #1e2235;
    color: #dce4f5; font-size: 14px;
    font-family: 'Courier New', Courier, monospace;
    border-radius: 2px; cursor: pointer;
    transition: background .1s, border-color .1s, color .1s;
  }
  .chip:active { background: #1a1e30; }
  .chip.sel { background: #0f1a38; border-color: #5b8dee; color: #5b8dee; }
  .muted { color: #3d4560; font-size: 13px; font-family: system-ui, sans-serif; }

  .mat-card {
    background: #0e1020; border: 1px solid #1e2235;
    padding: 10px 12px; display: flex; flex-direction: column; gap: 6px;
  }
  .mat-row {
    display: flex; justify-content: space-between;
    align-items: baseline; font-size: 12px;
  }
  .mk { color: #5a6380; font-family: system-ui, sans-serif; }
  .mv { color: #dce4f5; font-family: system-ui, sans-serif; }
  .mono   { font-family: 'Courier New', Courier, monospace !important; }
  .orange { color: #f97316 !important; }
  .blue   { color: #5b8dee  !important; }
  .amber  { color: #f5a623  !important; }

  .start-btn {
    margin-top: auto; height: 60px;
    background: #0b2016; border: 1px solid #26bf6e;
    color: #26bf6e; font-size: 20px; font-weight: 600;
    font-family: system-ui, sans-serif; letter-spacing: .04em;
    border-radius: 2px; cursor: pointer; transition: background .12s;
  }
  .start-btn:active { background: #26bf6e; color: #0b0d14; }

  /* ── Running / Done ──────────────────────────────────────── */
  .running { width: 100%; height: 100%; display: flex; }
  .force-col {
    width: 272px; flex-shrink: 0;
    border-right: 1px solid #1e2235;
    padding: 14px 16px;
    display: flex; flex-direction: column; gap: 4px;
  }
  .phase-badge {
    display: inline-flex; align-items: center;
    font-size: 10px; letter-spacing: .12em; text-transform: uppercase;
    color: #5b8dee; font-family: system-ui, sans-serif; gap: 6px;
  }
  .phase-badge::before {
    content: ''; display: inline-block; width: 7px; height: 7px;
    border-radius: 50%; background: #5b8dee; box-shadow: 0 0 7px #5b8deeaa;
  }
  .phase-badge.done { color: #26bf6e; }
  .phase-badge.done::before { background: #26bf6e; box-shadow: 0 0 7px #26bf6eaa; }
  .status-text {
    font-size: 12px; color: #5a6380;
    font-family: system-ui, sans-serif; min-height: 18px; margin-bottom: 4px;
  }
  .force-block { display: flex; flex-direction: column; gap: 0; margin: auto 0; }
  .force-label {
    font-size: 9px; letter-spacing: .16em; text-transform: uppercase;
    color: #5a6380; font-family: system-ui, sans-serif;
  }
  .force-num {
    font-family: 'Courier New', Courier, monospace;
    font-size: 76px; font-weight: 700; line-height: 1;
    transition: color .3s, text-shadow .3s;
  }
  .force-unit { font-size: 22px; color: #5a6380; font-family: system-ui, sans-serif; }
  .ref-range {
    font-size: 11px; color: #5a6380;
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
  .done-btn:active  { background: #26bf6e; color: #0b0d14; }
  .run-chart { flex: 1; min-width: 0; padding: 6px 6px 6px 2px; }
</style>
