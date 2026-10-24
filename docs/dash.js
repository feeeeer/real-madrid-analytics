// Mini-motor de datos de la web: carga los CSV de data/, calcula los derivados y avisa a la página cuando hay datos.
// Mantiene la misma interfaz que el cuadro de mando original (dash.data, dash.calc, dash.onData, dash.params...).
window.dash = (() => {
  const FUENTES = ['partidos', 'metricas_equipo', 'metricas_jugador', 'pases', 'tiros', 'rendimiento', 'historico', 'historico_alineaciones', 'escudos', 'ligas', 'titulos', 'alineaciones', 'competicion', 'incidencias', 'red_nodos', 'red_enlaces', 'acciones', 'proximos'];
  // nombres clásicos de las competiciones europeas en toda la web
  const NOMBRES = { 'Champions League': 'Copa de Europa', 'Liga de Campeones': 'Copa de Europa', 'Copa de Europa / Champions': 'Copa de Europa',
    'Liga Europa': 'Copa de la UEFA', 'Europa League': 'Copa de la UEFA' };
  const store = {}; // id -> {status, data, message}
  const calcs = {}; // id -> {inputs, fn}
  const subs = [];
  const DEFECTO = { capa: 'pases', capa_t: 'zonas', equipo: 'rm', tipos: ['progresivo', 'clave'], tiros_tipo: ['gol', 'parado', 'fuera', 'bloqueado'] };
  let params = { ...DEFECTO };
  try { params = { ...DEFECTO, ...JSON.parse(sessionStorage.getItem('rm-params') || '{}') }; } catch (e) { /* sin almacenamiento: parámetros por defecto */ }

  const avisar = () => subs.forEach((fn) => fn());
  const guardar = () => { try { sessionStorage.setItem('rm-params', JSON.stringify(params)); } catch (e) { /* nada */ } };

  // cada CSV se descarga la primera vez que alguna sección lo pide (el histórico de alineaciones pesa casi 2 MB)
  function cargar(id) {
    if (store[id]) return;
    store[id] = { status: 'loading', data: [] };
    d3.csv(`data/${id}.csv`, (r) => {
      for (const k of ['competicion', 'comp_hist']) if (r[k] in NOMBRES) r[k] = NOMBRES[r[k]];
      if (r.motivo) r.motivo = r.motivo.replace(/(\d)\.(\d)/g, '$1,$2');  // decimales en español en los textos del rendimiento
      return r;
    })
      .then((rows) => { store[id] = { status: 'ok', data: rows }; })
      .catch((e) => { store[id] = { status: 'error', data: [], message: String(e) }; })
      .finally(avisar);
  }

  function data(id) {
    const c = calcs[id];
    if (!c) {
      if (FUENTES.includes(id)) cargar(id);
      return store[id] || { status: 'missing', data: [] };
    }
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
