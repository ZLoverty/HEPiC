<script>
  import { createEventDispatcher } from 'svelte';
  import { wsConnected } from '../lib/stores.js';

  export let active = 0;
  const dispatch = createEventDispatcher();

  const tabs = [
    { label: '仪表盘' },
    { label: '手动控制' },
    { label: '质检模式' },
    { label: '设置' },
  ];
</script>

<nav>
  {#each tabs as tab, i}
    <button
      class="tab"
      class:active={active === i}
      on:click={() => dispatch('nav', i)}
    >
      <span class="icon" aria-hidden="true">
        {#if i === 0}
          <!-- dashboard: 4-square grid -->
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="14" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/>
          </svg>
        {:else if i === 1}
          <!-- manual: sliders -->
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <line x1="4" y1="8" x2="20" y2="8"/>
            <circle cx="15" cy="8" r="3" fill="var(--bg-nav)"/>
            <line x1="4" y1="16" x2="20" y2="16"/>
            <circle cx="9" cy="16" r="3" fill="var(--bg-nav)"/>
          </svg>
        {:else if i === 2}
          <!-- qc: circle + checkmark -->
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="9"/>
            <polyline points="8 12 11 15 16 9"/>
          </svg>
        {:else}
          <!-- settings: gear -->
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 2v2.5M12 19.5V22M4.22 4.22l1.77 1.77M18.01 18.01l1.77 1.77M2 12h2.5M19.5 12H22M4.22 19.78l1.77-1.77M18.01 5.99l1.77-1.77"/>
          </svg>
        {/if}
      </span>
      <span class="label">{tab.label}</span>
    </button>
  {/each}

  <!-- WebSocket connection indicator -->
  <div
    class="ws-dot"
    class:on={$wsConnected}
    title={$wsConnected ? '传感器已连接' : '传感器未连接'}
  />
</nav>

<style>
  :root { --bg-nav: #0a0c14; }

  nav {
    height: 64px;
    flex-shrink: 0;
    background: #0a0c14;
    border-top: 1px solid #1e2235;
    display: flex;
    position: relative;
  }
  .tab {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    color: #3d4560;
    background: none;
    border: none;
    border-top: 2px solid transparent;
    cursor: pointer;
    transition: color .15s, border-color .15s;
    padding: 0;
  }
  .tab:active  { opacity: .65; }
  .tab.active  { color: #5b8dee; border-top-color: #5b8dee; }
  .icon {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .icon svg { width: 100%; height: 100%; }
  .label {
    font-size: 11px;
    font-family: system-ui, sans-serif;
    letter-spacing: .02em;
  }
  .ws-dot {
    position: absolute;
    right: 10px;
    top: 9px;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #e5484d;
    transition: background .4s;
  }
  .ws-dot.on {
    background: #26bf6e;
    box-shadow: 0 0 7px #26bf6eaa;
  }
</style>
