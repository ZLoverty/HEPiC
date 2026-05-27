<script>
  export let data      = [];        // number[]
  export let color     = '#f5a623';
  export let maxPoints = 200;
  export let title     = '';
  export let unit      = '';

  const VW = 480, VH = 260;
  const P  = { l: 42, r: 10, t: 18, b: 22 };
  const IW = VW - P.l - P.r;
  const IH = VH - P.t - P.b;

  // stable gradient id per component instance
  const gid = 'g' + Math.random().toString(36).slice(2, 8);

  function niceRange(vals) {
    const clean = vals.filter(v => v !== null && isFinite(v));
    if (!clean.length) return { min: 0, max: 10 };
    let lo = Math.min(...clean), hi = Math.max(...clean);
    if (lo === hi) { lo -= 1; hi += 1; }
    const span = hi - lo;
    return { min: lo - span * .08, max: hi + span * .08 };
  }

  function niceTicks({ min, max }) {
    const span = max - min;
    if (span <= 0) return [min, max];
    const rough = span / 4;
    const mag   = Math.pow(10, Math.floor(Math.log10(rough)));
    const step  = [1, 2, 2.5, 5].map(s => s * mag).find(s => s >= rough) ?? mag;
    const out   = [];
    for (let v = Math.ceil(min / step) * step; v <= max + step * .01; v += step)
      out.push(+v.toFixed(10));
    return out;
  }

  function ty(v, { min, max }) { return P.t + IH - ((v - min) / (max - min)) * IH; }
  function tx(i, total)        { return P.l + ((maxPoints - total + i) / (maxPoints - 1)) * IW; }

  $: pts   = data.slice(-maxPoints);
  $: range = niceRange(pts);
  $: ticks = niceTicks(range);

  $: linePath = (() => {
    let d = '', first = true;
    for (let i = 0; i < pts.length; i++) {
      const v = pts[i];
      if (v === null || !isFinite(v)) continue;
      const x = tx(i, pts.length).toFixed(1);
      const y = ty(v, range).toFixed(1);
      d += first ? `M${x},${y}` : `L${x},${y}`;
      first = false;
    }
    return d;
  })();

  $: areaPath = (() => {
    if (!linePath) return '';
    const lx = tx(pts.length - 1, pts.length).toFixed(1);
    const fy = (P.t + IH).toFixed(1);
    const fx = tx(0, pts.length).toFixed(1);
    return `${linePath}L${lx},${fy}L${fx},${fy}Z`;
  })();

  // last valid point for the live dot
  $: lastIdx = (() => {
    for (let i = pts.length - 1; i >= 0; i--)
      if (pts[i] !== null && isFinite(pts[i])) return i;
    return -1;
  })();
  $: lastX = lastIdx >= 0 ? tx(lastIdx, pts.length) : null;
  $: lastY = lastIdx >= 0 ? ty(pts[lastIdx], range)  : null;
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
        <stop offset="0%"   stop-color={color} stop-opacity=".22"/>
        <stop offset="100%" stop-color={color} stop-opacity="0"/>
      </linearGradient>
    </defs>

    <!-- horizontal grid lines -->
    {#each ticks as v}
      {@const y = ty(v, range)}
      <line x1={P.l} y1={y} x2={VW - P.r} y2={y}
            stroke="#252a40" stroke-width="1" stroke-dasharray="3 5"/>
      <text x={P.l - 4} y={y + 4} text-anchor="end"
            fill="#3d4560" font-size="11" font-family="monospace">{v}</text>
    {/each}

    <!-- y-axis rule -->
    <line x1={P.l} y1={P.t} x2={P.l} y2={P.t + IH}
          stroke="#252a40" stroke-width="1"/>

    <!-- filled area -->
    {#if areaPath}
      <path d={areaPath} fill="url(#{gid})"/>
    {/if}

    <!-- main line -->
    {#if linePath}
      <path d={linePath} fill="none" stroke={color} stroke-width="2"
            stroke-linejoin="round" stroke-linecap="round"/>
    {/if}

    <!-- live dot with pulse ring -->
    {#if lastX !== null && lastY !== null}
      <circle cx={lastX} cy={lastY} r="8" fill={color} opacity=".18"/>
      <circle cx={lastX} cy={lastY} r="3.5" fill={color}/>
    {/if}

    <!-- empty state -->
    {#if pts.length < 2}
      <text x={VW/2} y={VH/2} text-anchor="middle" dominant-baseline="middle"
            fill="#252a40" font-size="14" font-family="monospace">等待数据...</text>
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
    font-size: 9px;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: #3d4560;
    padding: 6px 8px 0;
    font-family: system-ui, sans-serif;
    flex-shrink: 0;
  }
  svg { flex: 1; min-height: 0; }
</style>
