<script>
  export let label     = '';
  export let value     = null;   // raw number | null
  export let unit      = '';
  export let color     = '#5b8dee';
  export let decimals  = 1;
  export let secondary = null;   // small sub-line string | null
  export let clickable = false;  // render as a <button> and forward on:click

  $: display = (value !== null && value !== undefined && isFinite(value))
    ? Number(value).toFixed(decimals)
    : '---';
</script>

{#if clickable}
  <button class="card clickable" on:click>
    <span class="label">{label}</span>
    <div class="row">
      <span class="num" style="color:{color}; text-shadow:0 0 28px {color}4d">{display}</span>
      <span class="unit">{unit}</span>
    </div>
    {#if secondary}
      <span class="secondary">{secondary}</span>
    {/if}
  </button>
{:else}
  <div class="card">
    <span class="label">{label}</span>
    <div class="row">
      <span class="num" style="color:{color}; text-shadow:0 0 28px {color}4d">{display}</span>
      <span class="unit">{unit}</span>
    </div>
    {#if secondary}
      <span class="secondary">{secondary}</span>
    {/if}
  </div>
{/if}

<style>
  .card {
    flex: 1;
    width: 100%;
    padding: 10px 18px 10px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    gap: 2px;
    border: none;
    border-bottom: 1px solid #2e3a58;
    background: #1a1f35;
    font: inherit;
    text-align: left;
    position: relative;
    overflow: hidden;
  }
  .card.clickable { cursor: pointer; transition: background .12s; }
  .card.clickable:active { background: #232a48; }
  .card::after {
    content: '';
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(
      0deg, transparent, transparent 3px,
      rgba(0,0,0,0.03) 3px, rgba(0,0,0,0.03) 4px
    );
    pointer-events: none;
  }
  .label {
    font-size: 12px;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: #7888b0;
    font-family: system-ui, sans-serif;
  }
  .row {
    display: flex;
    align-items: baseline;
    gap: 6px;
    line-height: 1;
  }
  .num {
    font-family: 'Courier New', Courier, monospace;
    font-size: 48px;
    font-weight: 700;
    letter-spacing: -.02em;
    transition: color .3s;
  }
  .unit {
    font-size: 15px;
    color: #7888b0;
    font-family: system-ui, sans-serif;
    padding-bottom: 3px;
  }
  .secondary {
    font-size: 13px;
    color: #7888b0;
    font-family: 'Courier New', Courier, monospace;
    margin-top: 2px;
  }
</style>
