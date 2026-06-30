<script>
  import MetricCard from '../components/MetricCard.svelte';
  import LineChart  from '../components/LineChart.svelte';
  import { sensorData, forceHistory } from '../lib/stores.js';

  $: force    = $sensorData.extrusion_force_N;
  $: feedrate = $sensorData.measured_feedrate_mms;
  $: temp     = $sensorData.hotend_temperature;
  $: target   = $sensorData.target_temperature;
  $: tempSub  = target !== null ? `目标 ${Number(target).toFixed(0)} °C` : null;
</script>

<div class="layout">
  <!-- Left: 3 metric cards stacked -->
  <div class="metrics">
    <MetricCard label="挤出力"  value={force}    unit="N"    color="#f5a623" decimals={2} />
    <MetricCard label="进线速度" value={feedrate} unit="mm/s" color="#5b8dee" decimals={1} />
    <MetricCard label="热端温度" value={temp}     unit="°C"   color="#f97316" decimals={1} secondary={tempSub} />
  </div>

  <!-- Right: live force sparkline -->
  <div class="chart">
    <LineChart data={$forceHistory} color="#f5a623" title="挤出力历史" unit="N" />
  </div>
</div>

<style>
  .layout {
    width: 100%;
    height: 100%;
    display: flex;
  }
  .metrics {
    width: 258px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    border-right: 1px solid #252d48;
  }
  /* remove bottom border on last card */
  .metrics :global(.card:last-child) { border-bottom: none; }
  .chart {
    flex: 1;
    min-width: 0;
    padding: 4px 4px 4px 0;
  }
</style>
