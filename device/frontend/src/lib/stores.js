import { writable } from 'svelte/store';

export const sensorData = writable({
  extrusion_force_N:    null,
  measured_feedrate_mms: null,
  hotend_temperature:   null,
  target_temperature:   null,
  feedrate_mms:         null,
  klippy_state:         'unknown',
});

/** Last 200 extrusion-force readings for the global sparkline. */
export const forceHistory = writable(/** @type {number[]} */([]));

/** Whether the /ws/sensors WebSocket is currently connected. */
export const wsConnected = writable(false);

/**
 * QC session state. Lives at App level so it survives page navigation.
 * The WebSocket to /api/qc/stream is managed by App.svelte, not the QC page.
 */
export const qcState = writable({
  phase:    /** @type {'idle'|'running'|'done'} */ ('idle'),
  statusMsg: '',
  family:   /** @type {string|null} */ (null),
  piCode:   /** @type {string|null} */ (null),
  material: /** @type {object|null} */ (null),
  extrudeStartedAt: /** @type {number|null} */ (null),  // Date.now() when extrusion begins
  frozenForce: /** @type {number|null} */ (null),  // force snapshot at STOP_QUALITY_CHECK; held until "完成"
});

/** Force readings accumulated during the current QC session. */
export const qcForceHistory = writable(/** @type {number[]} */([]));

