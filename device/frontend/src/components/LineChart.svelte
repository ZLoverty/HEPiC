<script>
  export let data      = [];        // number[]
  export let color     = '#f5a623';
  export let maxPoints = 200;
  export let title     = '';
  export let unit      = '';
  export let hz        = 10;       // broadcast rate, used for x-axis time labels

  const VW = 480, VH = 260;
  const P  = { l: 46, r: 10, t: 18, b: 22 };
  const IW = VW - P.l - P.r;
  const IH = VH - P.t - P.b;

  const gid = 'g' + Math.random().toString(36).slice(2, 8);

  function niceRange(vals) {
    const clean = vals.filter(v => v !== null && isFinite(v));
    if (!clean.length) return { min: 0, max: 10 };
    let lo = Math.min(...clean), hi = Math.max(...clean);
    if (lo === hi) { lo -= 1; hi += 1; }
    const span = hi - lo;
    return { min: lo - span * .08, max: hi + span * .08 };
  }

  // Returns at most maxTicks nice tick values spanning [min, max].
  function niceTicks({ min, max }, maxTicks = 6) {
    const span = max - min;
    if (span <= 0) return [min, max];
    const rough = span / maxTicks;
    const mag   = Math.pow(10, Math.floor(Math.log10(rough)));
    const step  = [1, 2, 2.5, 5, 10].map(s => s * mag).find(s => s >= rough) ?? (mag * 10);
    const out   = [];
    for (let v = Math.ceil(min / step) * step; v <= max + step * .01; v += step)
      out.push(+v.toFixed(10));
    return out;
  }

  function ty(v, { min, max }) { return P.t + IH - ((v - min) / (max - min)) * IH; }

  // Left-to-right fill: point i of `total` points sits at a fixed column
  // spacing so the plot grows from the left edge. Once total >= maxPoints
  // the window slides and the spacing stays constant.
  function tx(i) { return P.l + (i / (maxPoints - 1)) * IW; }

  $: pts   = data.slice(-maxPoints);
  $: range = niceRange(pts);
  $: ticks = niceTicks(range);

  $: linePath = (() => {
    let d = '', first = true;
    for (let i = 0; i < pts.length; i++) {
      const v = pts[i];
      if (v === null || !isFinite(v)) continue;
      const x = tx(i).toFixed(1);
      const y = ty(v, range).toFixed(1);
      d += first ? `M${x},${y}` : `L${x},${y}`;
      first = false;
    }
    return d;
  })();

  $: areaPath = (() => {
    if (!linePath) return '';
    const lx = tx(pts.length - 1).toFixed(1);
    const fy = (P.t + IH).toFixed(1);
    const fx = tx(0).toFixed(1);
    return `${linePath}L${lx},${fy}L${fx},${fy}Z`;
  })();

  $: lastIdx = (() => {
    for (let i = pts.length - 1; i >= 0; i--)
      if (pts[i] !== null && isFinite(pts[i])) return i;
    return -1;
  })();
  $: lastX = lastIdx >= 0 ? tx(lastIdx)             : null;
  $: lastY = lastIdx >= 0 ? ty(pts[lastIdx], range)  : null;

  // Five evenly-spaced x-axis time labels spanning the full maxPoints window.
  const N_XTICKS = 5;
  $: xTicks = Array.from({ length: N_XTICKS }, (_, k) => {
    const idx     = Math.round(k * (maxPoints - 1) / (N_XTICKS - 1));
    const secsAgo = Math.round((maxPoints - 1 - idx) / hz);
    const label   = secsAgo === 0 ? '现在' : `-${secsAgo}s`;
    return { x: tx(idx), label };
  });
</script>

<div class="wrap">
  {#if title}
    <div class="title">{title}{unit ? ` (${unit})` : ''}</div>
  {/if}
  <svg
    viewBox="0 0 {VW} {VH}"
    preserveAspectRatio="none"
    style="width:100%;height:100%;display:block;flex:1"
  >
    <defs>
      <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%"   stop-color={color} stop-opacity=".25"/>
        <stop offset="100%" stop-color={color} stop-opacity="0"/>
      </linearGradient>
    </defs>

    <!-- horizontal grid lines + y-axis labels -->
    {#each ticks as v}
      {@const y = ty(v, range)}
      <line x1={P.l} y1={y} x2={VW - P.r} y2={y}
            stroke="#2d3655" stroke-width="1" stroke-dasharray="3 5"/>
      <text x={P.l - 4} y={y + 4} text-anchor="end"
            fill="#6a7590" font-size="14" font-family="monospace">{v}</text>
    {/each}

    <!-- y-axis rule -->
    <line x1={P.l} y1={P.t} x2={P.l} y2={P.t + IH}
          stroke="#2d3655" stroke-width="1"/>

    <!-- x-axis rule -->
    <line x1={P.l} y1={P.t + IH} x2={VW - P.r} y2={P.t + IH}
          stroke="#2d3655" stroke-width="1"/>

    <!-- x-axis time labels -->
    {#each xTicks as { x, label }}
      <line x1={x} y1={P.t + IH} x2={x} y2={P.t + IH + 4}
            stroke="#2d3655" stroke-width="1"/>
      <text x={x} y={VH - 2} text-anchor="middle"
            fill="#6a7590" font-size="13" font-family="monospace">{label}</text>
    {/each}

    <!-- filled area -->
    {#if areaPath}
      <path d={areaPath} fill="url(#{gid})"/>
    {/if}

    <!-- main line -->
    {#if linePath}
      <path d={linePath} fill="none" stroke={color} stroke-width="2.5"
            stroke-linejoin="round" stroke-linecap="round"/>
    {/if}

    <!-- live dot -->
    {#if lastX !== null && lastY !== null}
      <circle cx={lastX} cy={lastY} r="8" fill={color} opacity=".2"/>
      <circle cx={lastX} cy={lastY} r="3.5" fill={color}/>
    {/if}

    <!-- empty state -->
    {#if pts.length < 2}
      <text x={VW/2} y={VH/2} text-anchor="middle" dominant-baseline="middle"
            fill="#3a4570" font-size="14" font-family="monospace">等待数据...</text>
    {/if}
  </svg>
</div>

<style>
  .wrap {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .title {
    font-size: 13px;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: #6a7590;
    padding: 6px 8px 0;
    font-family: system-ui, sans-serif;
    flex-shrink: 0;
  }
  svg { flex: 1; min-height: 0; }
</style>
