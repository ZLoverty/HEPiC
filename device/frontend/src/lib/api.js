async function req(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`);
  return r.json();
}

export const api = {
  klipper: {
    status:        ()            => req('GET',  '/api/klipper/status'),
    setTemp:       (temperature) => req('POST', '/api/klipper/temperature',    { temperature }),
    gcode:         (script)      => req('POST', '/api/klipper/gcode',          { script }),
    emergencyStop: ()            => req('POST', '/api/klipper/emergency_stop'),
    restart:       ()            => req('POST', '/api/klipper/restart'),
  },
  materials: {
    families: ()               => req('GET', '/api/materials/'),
    list:     (family)         => req('GET', `/api/materials/${encodeURIComponent(family)}`),
    get:      (family, piCode) => req('GET', `/api/materials/${encodeURIComponent(family)}/${encodeURIComponent(piCode)}`),
  },
  qc: {
    start: (family, pi_code) => req('POST', '/api/qc/start', { family, pi_code }),
  },
  system: {
    info: () => req('GET', '/api/system/info'),
  },
};
