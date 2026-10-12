// Mini-motor de datos de la web: carga los CSV de data/, calcula los derivados y avisa a la página cuando hay datos.
// Mantiene la misma interfaz que el cuadro de mando original (dash.data, dash.calc, dash.onData, dash.params...).
window.dash = (() => {
  const FUENTES = ['partidos', 'metricas_equipo', 'metricas_jugador', 'pases', 'tiros', 'rendimiento', 'historico', 'historico_alineaciones', 'escudos', 'ligas', 'titulos'];
  const store = {}; // id -> {status, data, message}
  const calcs = {}; // id -> {inputs, fn}
  const subs = [];
  const DEFECTO = { capa: 'pases', capa_t: 'pases', equipo: 'rm', tipos: ['completo', 'fallado', 'clave'], tiros_tipo: ['gol', 'parado', 'fuera', 'bloqueado'] };
  let params = { ...DEFECTO };
  try { params = { ...DEFECTO, ...JSON.parse(sessionStorage.getItem('rm-params') || '{}') }; } catch (e) { /* sin almacenamiento: parámetros por defecto */ }

  const avisar = () => subs.forEach((fn) => fn());
  const guardar = () => { try { sessionStorage.setItem('rm-params', JSON.stringify(params)); } catch (e) { /* nada */ } };

  for (const id of FUENTES) {
    store[id] = { status: 'loading', data: [] };
    d3.csv(`data/${id}.csv`)
      .then((rows) => { store[id] = { status: 'ok', data: rows }; })
      .catch((e) => { store[id] = { status: 'error', data: [], message: String(e) }; })
      .finally(avisar);
  }

  function data(id) {
    const c = calcs[id];
    if (!c) return store[id] || { status: 'missing', data: [] };
    const ins = c.inputs.map(data);
    const bad = ins.find((d) => d.status !== 'ok');
    if (bad) return { status: bad.status, data: [] };
    if (!c.cache) c.cache = { status: 'ok', data: c.fn(...ins.map((d) => d.data)) };
    return c.cache;
  }

  let ancho = window.innerWidth;
  window.addEventListener('resize', () => { if (Math.abs(window.innerWidth - ancho) > 20) { ancho = window.innerWidth; avisar(); } });

  return {
    data,
    calc: (id, def) => { calcs[id] = { ...def }; },
    onData: (fn) => { subs.push(fn); fn(); },
    params: () => params,
    setParams: (o) => { params = { ...params, ...o }; guardar(); avisar(); },
    resetParams: () => { params = { ...DEFECTO }; guardar(); avisar(); },
    setLink: (name) => history.replaceState(null, '', '#' + name),
    colors: ['var(--serie-rm)', 'var(--serie-rival)', 'var(--serie-clave)'],
  };
})();
