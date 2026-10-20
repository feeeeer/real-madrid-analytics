(() => {
const RM = 'Real Madrid';
const $ = (s) => document.querySelector(s);
const N = (v) => (v === '' || v == null ? 0 : Number(v));
const enc = (s) => String(s).replace(/%/g, '%25').replace(/&/g, '%26').replace(/=/g, '%3D');
const el = (tag, attrs = {}, text) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
};
const markEl = (tag, src, field, where, text) => el(tag, { 'data-source': src, 'data-field': field, 'data-where': where }, text);
const ok = (...ids) => ids.every((id) => dash.data(id).status === 'ok');
const rows = (id) => (dash.data(id).status === 'ok' ? dash.data(id).data : []);
const C_RM = () => dash.colors[0];
const C_RIV = () => dash.colors[1];
const C_KEY = () => dash.colors[2];
const C_BAD = 'var(--cds-chart-status-critical)';

// ---------- Cálculos (visibles en Fuentes) ----------
dash.calc('informe', {
  inputs: ['metricas_equipo'],
  title: 'Informe vs media del Madrid',
  description: 'Cada métrica del Madrid en el partido frente a su media en los partidos de la misma fuente (StatsBomb u Opta); z en desviaciones típicas, positivo = mejor para el estilo del míster. Métricas que la fuente no tiene, fuera.',
  fn: (metricas_equipo) => {
    // signo: +1 más es mejor, -1 menos es mejor. Posesión y PPDA fuera: un bloque medio/bajo no se juzga por ellas.
    const M = { xg: 1, xg_contra: -1, tiros_puerta: 1, acierto_pase: 1, pases_progresivos: 1, presiones_campo_rival: 1,
      recuperaciones_campo_rival: 1, duelos_ganados_pct: 1, perdidas_peligrosas: -1, contrapresiones: 1, xg_contraataque: 1 };
    const out = [];
    const fuentes = [...new Set(metricas_equipo.map((r) => r.fuente))];
    for (const fuente of fuentes) {
      const rm = metricas_equipo.filter((r) => r.equipo === 'Real Madrid' && r.fuente === fuente);
      for (const [k, sign] of Object.entries(M)) {
        const rk = rm.filter((r) => r[k] !== '' && r[k] != null);
        if (rk.length < 3) continue;
        const v = rk.map((r) => Number(r[k]));
        const media = v.reduce((a, b) => a + b, 0) / v.length;
        const sd = Math.sqrt(v.reduce((a, b) => a + (b - media) ** 2, 0) / (v.length - 1)) || 1;
        rk.forEach((r, i) => out.push({ clave: r.match_id + '|' + k, match_id: r.match_id, metrica: k, valor: v[i],
          media: Math.round(media * 100) / 100, z: Math.round((sign * (v[i] - media) / sd) * 100) / 100 }));
      }
    }
    return out;
  },
});

dash.calc('jugadores_temporada', {
  inputs: ['metricas_jugador', 'partidos'],
  title: 'Plantilla por temporada',
  description: 'Suma por jugador del Madrid de sus partidos en cada competición y temporada; % de duelos = ganados / (ganados + perdidos).',
  fn: (metricas_jugador, partidos) => {
    const comp = Object.fromEntries(partidos.map((p) => [p.match_id, p.competicion + '|' + p.temporada]));
    const acc = {};
    for (const r of metricas_jugador) {
      if (r.equipo !== 'Real Madrid') continue;
      const t = comp[r.match_id];
      const k = t + '|' + r.jugador_id;
      const a = (acc[k] ??= { clave: k, temporada: t, jugador: r.jugador, pj: 0, minutos: 0, goles: 0, xg: 0, asistencias: 0, xa: 0,
        pases_progresivos: 0, recuperaciones: 0, dg: 0, dp: 0, perdidas_peligrosas: 0 });
      a.pj += 1; a.minutos += Number(r.minutos); a.goles += Number(r.goles); a.xg += Number(r.xg); a.conXg ||= r.xg !== '';
      a.asistencias += Number(r.asistencias); a.xa += Number(r.xa); a.pases_progresivos += Number(r.pases_progresivos);
      a.recuperaciones += Number(r.recuperaciones); a.dg += Number(r.duelos_ganados); a.dp += Number(r.duelos_perdidos);
      a.perdidas_peligrosas += Number(r.perdidas_peligrosas);
    }
    // sin xG (Champions y Copa: Understat solo cubre la Liga) se deja vacío, no 0
    return Object.values(acc).map(({ dg, dp, conXg, ...a }) => ({ ...a, xg: conXg ? Math.round(a.xg * 100) / 100 : '', xa: conXg ? Math.round(a.xa * 100) / 100 : '',
      duelos_pct: dg + dp ? Math.round((1000 * dg) / (dg + dp)) / 10 : 0 }));
  },
});

// ---------- Textos del informe (estilo Mourinho) ----------
const MET = {
  xg: { label: 'xG generado', fmt: 2,
    impacto: 'Dominamos sin herir: el equipo no fabrica ocasiones claras y el rival sale vivo del partido.',
    correccion: 'Tras robo, máximo dos pases verticales antes de buscar el remate. Extremos abiertos fijando a los laterales para liberar el carril central al 9.',
    explotar: 'Repetir el patrón que generó las ocasiones y cargar el área con cuatro hombres en cada llegada.',
    mensaje: '"Llegamos una y otra vez. Ahora quiero la misma fe para matar los partidos."' },
  xg_contra: { label: 'xG concedido', fmt: 2,
    impacto: 'El rival entra en nuestra área con demasiada facilidad. La solidez defensiva es innegociable.',
    correccion: 'Bajar el bloque cinco metros, cerrar el pasillo interior con el mediocentro y mantener vigilancias ofensivas 2+1 cuando atacamos.',
    explotar: 'El bloque está cerrado: los laterales pueden asumir más riesgo arriba porque la retaguardia aguanta.',
    mensaje: '"Esta portería es de todos. Nadie nos hace daño si estamos así de juntos."' },
  tiros_puerta: { label: 'Tiros a puerta', fmt: 0,
    impacto: 'Llegamos pero no obligamos al portero: decisiones malas en el último metro.',
    correccion: 'Sesión de finalización tras transición: tres contra dos con dos toques máximo y tiro.',
    explotar: 'El equipo pisa área con convicción: seguir buscando el disparo temprano.',
    mensaje: '"El portero rival se va a casa cansado. Así se gana."' },
  acierto_pase: { label: '% acierto de pase', fmt: 1,
    impacto: 'Perdemos demasiados balones simples y regalamos transiciones al rival.',
    correccion: 'Rondos de presión con un toque menos y apoyos más cercanos al poseedor; prohibido el pase horizontal en zona de riesgo.',
    explotar: 'Circulación limpia: permite atraer la presión y lanzar el contragolpe con el campo largo.',
    mensaje: '"Con el balón somos un reloj. Que el rival corra detrás."' },
  pases_progresivos: { label: 'Pases progresivos', fmt: 0,
    impacto: 'Circulamos sin avanzar: el rival se reorganiza antes de que lleguemos.',
    correccion: 'Mediocentro perfilado para el pase vertical a la primera; interiores atacando la espalda del pivote rival.',
    explotar: 'Rompemos líneas con facilidad: buscar antes al delantero de espaldas para descargar y correr.',
    mensaje: '"Cada pase hacia delante es una puñalada. Seguid así."' },
  presiones_campo_rival: { label: 'Presiones en campo rival', fmt: 0,
    impacto: 'El rival sale jugando cómodo: no hay agresividad en la primera línea.',
    correccion: 'Activar la presión solo en trampa (pase al lateral o pase atrás), con el 9 cerrando la línea de pase al pivote.',
    explotar: 'Las trampas de presión funcionan: robar arriba es media ocasión hecha.',
    mensaje: '"Hoy el rival no ha podido respirar. Esa intensidad es la nuestra."' },
  recuperaciones_campo_rival: { label: 'Recuperaciones en campo rival', fmt: 0,
    impacto: 'Robamos lejos de su portería: cada contraataque empieza a 60 metros.',
    correccion: 'Adelantar 10 metros la línea de presión en los momentos de pase atrás del rival.',
    explotar: 'Robamos arriba: que los extremos ataquen el espacio en cuanto se recupera.',
    mensaje: '"Robar ahí arriba es lo que hace un equipo campeón."' },
  duelos_ganados_pct: { label: '% duelos ganados', fmt: 1,
    impacto: 'Perdemos la batalla física. Sin duelos ganados no hay bloque que aguante.',
    correccion: 'Doblar al jugador que pierde los duelos con ayuda del interior; balón al espacio en lugar de al pie si el emparejamiento no nos favorece.',
    explotar: 'Ganamos el cuerpo a cuerpo: buscar segundas jugadas y balón directo al hombre fuerte.',
    mensaje: '"Hoy hemos sido hombres. Así se compite en este club."' },
  perdidas_peligrosas: { label: 'Pérdidas peligrosas', fmt: 0,
    impacto: 'Regalamos el balón en nuestro tercio: es exactamente cómo un rival nos mata en transición.',
    correccion: 'Regla clara en salida: ante presión, balón largo al 9 o al lateral contrario. Nadie conduce en nuestro tercio.',
    explotar: 'Salida limpia y segura: podemos invitar al rival a presionar para correr a su espalda.',
    mensaje: '"Ni un regalo atrás. Eso es madurez."' },
  contrapresiones: { label: 'Contrapresiones', fmt: 0,
    impacto: 'Tras perder el balón no reaccionamos: el rival sale limpio a la contra.',
    correccion: 'Regla de 5 segundos: los tres más cercanos al balón perdido presionan, el resto cierra centro.',
    explotar: 'La reacción tras pérdida es inmediata: el equipo está mentalmente en el partido.',
    mensaje: '"Perdemos el balón y en cinco segundos es nuestro otra vez. Eso es hambre."' },
  xg_contraataque: { label: 'xG en contraataque', fmt: 2,
    impacto: 'No castigamos al rival cuando se desordena: nuestra arma principal está apagada.',
    correccion: 'Automatismo de transición: primer pase al hombre libre por fuera, dos corredores al área y uno llegando de segunda línea.',
    explotar: 'La transición es letal: esperar en bloque medio y dejar que el rival se desordene.',
    mensaje: '"Que tengan el balón. Nosotros tenemos el contraataque."' },
};

const CMP = [
  ['goles', 'Goles', 0, 1], ['xg', 'xG', 2, 1], ['tiros', 'Tiros', 0, 1], ['tiros_puerta', 'Tiros a puerta', 0, 1],
  ['xg_contraataque', 'xG contraataque', 2, 1], ['posesion', 'Posesión (%)', 1, 0], ['acierto_pase', '% acierto pase', 1, 1],
  ['pases_progresivos', 'Pases progresivos', 0, 1], ['pases_ultimo_tercio', 'Pases al último tercio', 0, 1],
  ['ppda', 'PPDA', 1, 0], ['presiones_campo_rival', 'Presiones campo rival', 0, 1],
  ['recuperaciones_campo_rival', 'Recup. campo rival', 0, 1], ['contrapresiones', 'Contrapresiones', 0, 1],
  ['duelos_ganados_pct', '% duelos ganados', 1, 1], ['perdidas_peligrosas', 'Pérdidas peligrosas', 0, -1],
];

const RES = { Goal: 'Gol', Saved: 'Parada', 'Saved to Post': 'Parada al poste', 'Saved Off Target': 'Parada (fuera)', Blocked: 'Bloqueado',
  'Off T': 'Fuera', Wayward: 'Desviado', Post: 'Poste' };
const PAT = { 'Regular Play': 'Juego posicional', 'From Counter': 'Contraataque', 'From Corner': 'Córner', 'From Free Kick': 'Falta',
  'From Throw In': 'Saque de banda', 'From Goal Kick': 'Saque de puerta', 'From Keeper': 'Desde el portero', 'From Kick Off': 'Saque de centro', Other: 'Otro' };

// ---------- Tooltip ----------
function tooltip(box) {
  let t = box.querySelector(':scope > .rm-tip');
  if (!t) { t = el('div', { class: 'rm-tip', hidden: '' }); box.appendChild(t); }
  return {
    show(ev, title, lines) {
      t.replaceChildren(el('div', { class: 't' }, title), ...lines.map((l) => el('div', {}, l)));
      t.hidden = false;
      const b = box.getBoundingClientRect();
      const x = ev.clientX - b.left, y = ev.clientY - b.top;
      const w = t.offsetWidth, h = t.offsetHeight;
      t.style.left = Math.max(0, Math.min(b.width - w, x + 12)) + 'px';
      t.style.top = Math.max(0, y - h - 10 < 0 ? y + 14 : y - h - 10) + 'px';
    },
    hide() { t.hidden = true; },
  };
}

// ---------- Campo ----------
// resultado de Understat -> botón del filtro de tiros (el poste cuenta como fuera)
const TIPO_TIRO = { Goal: 'gol', Saved: 'parado', 'Saved to Post': 'parado', 'Saved Off Target': 'parado', 'Off T': 'fuera', Post: 'fuera', Blocked: 'bloqueado' };

function drawPitch(box, { capa, passes, shots, color, tipos, tiposTiro }) {
  box.querySelector('svg')?.remove();
  const half = capa === 'tiros';
  const vb = [-2, -2, 124, 84];
  const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', vb.join(' '))
    .attr('role', 'img').attr('aria-label', half ? 'Mapa de tiros' : 'Mapa de pases');
  const g = svg.append('g').attr('fill', 'none').style('stroke', 'var(--cds-chart-axis)').attr('stroke-width', 0.3).attr('opacity', 0.8);
  g.append('rect').attr('x', 0).attr('y', 0).attr('width', 120).attr('height', 80);
  g.append('line').attr('x1', 60).attr('x2', 60).attr('y1', 0).attr('y2', 80);
  g.append('circle').attr('cx', 60).attr('cy', 40).attr('r', 10);
  for (const [x0, dir] of [[0, 1], [120, -1]]) {
    g.append('rect').attr('x', dir > 0 ? x0 : x0 - 18).attr('y', 18).attr('width', 18).attr('height', 44);
    g.append('rect').attr('x', dir > 0 ? x0 : x0 - 6).attr('y', 30).attr('width', 6).attr('height', 20);
    g.append('rect').attr('x', dir > 0 ? x0 - 2 : x0).attr('y', 36).attr('width', 2).attr('height', 8);
    g.append('circle').attr('cx', x0 + dir * 12).attr('cy', 40).attr('r', 0.4).style('fill', 'var(--cds-chart-axis)');
    g.append('path').attr('d', d3.arc()({ innerRadius: 10, outerRadius: 10, startAngle: dir > 0 ? 0.65 : Math.PI + 0.65, endAngle: dir > 0 ? Math.PI - 0.65 : 2 * Math.PI - 0.65 }))
      .attr('transform', `translate(${x0 + dir * 12},40)`);
  }
  const tip = tooltip(box);
  const legend = [];
  if (!half) {
    const defs = svg.append('defs');
    const COL = { completo: color, fallado: C_BAD, clave: C_KEY() };
    for (const [k, c] of Object.entries(COL)) {
      defs.append('marker').attr('id', `arr-${box.id}-${k}`).attr('viewBox', '0 0 10 10').attr('refX', 9).attr('refY', 5)
        .attr('markerWidth', 4).attr('markerHeight', 4).attr('orient', 'auto')
        .append('path').attr('d', 'M0,0L10,5L0,10z').style('fill', c);
    }
    const ps = passes.filter((p) => tipos.includes(p.tipo));
    const op = ps.length > 800 ? 0.25 : ps.length > 250 ? 0.45 : 0.8;
    // los pases clave se dibujan encima
    ps.sort((a, b) => (a.tipo === 'clave') - (b.tipo === 'clave'));
    svg.append('g').selectAll('line').data(ps).join('line')
      .attr('x1', (d) => d.x).attr('y1', (d) => d.y).attr('x2', (d) => d.fin_x).attr('y2', (d) => d.fin_y)
      .style('stroke', (d) => COL[d.tipo]).attr('stroke-width', (d) => (d.tipo === 'clave' ? 0.55 : 0.35))
      .attr('stroke-linecap', 'round').attr('opacity', (d) => (d.tipo === 'clave' ? 1 : op))
      .attr('marker-end', (d) => `url(#arr-${box.id}-${d.tipo})`)
      .on('mouseenter', function (ev, d) {
        d3.select(this).attr('stroke-width', 1).attr('opacity', 1);
        tip.show(ev, `${d.jugador} · ${d.minuto}'`, [{ completo: 'Pase completado', fallado: 'Pase fallado', clave: 'Pase clave (acaba en tiro)' }[d.tipo]]);
      })
      .on('mouseleave', function (ev, d) {
        d3.select(this).attr('stroke-width', d.tipo === 'clave' ? 0.55 : 0.35).attr('opacity', d.tipo === 'clave' ? 1 : op);
        tip.hide();
      });
    legend.push(['completo', 'Completado', color], ['fallado', 'Fallado', C_BAD], ['clave', 'Pase clave', C_KEY()]);
  } else {
    const ss = shots.filter((d) => tiposTiro.includes(TIPO_TIRO[d.resultado])).sort((a, b) => (b.xg || 0) - (a.xg || 0));
    svg.append('g').selectAll('circle').data(ss).join('circle')
      .attr('cx', (d) => d.x).attr('cy', (d) => d.y).attr('r', (d) => (isNaN(d.xg) ? 2 : 0.7 + Math.sqrt(d.xg) * 4.5))
      .style('fill', (d) => (d.resultado === 'Goal' ? color : 'transparent')).style('stroke', color)
      .attr('stroke-width', 0.35).attr('fill-opacity', 0.85)
      .on('mouseenter', (ev, d) => tip.show(ev, `${d.jugador} · ${d.minuto}'`,
        [`${RES[d.resultado] || d.resultado}${isNaN(d.xg) ? '' : ` · xG ${d.xg.toFixed(2)}`}`, `${PAT[d.patron_juego] || d.patron_juego}${d.subtipo === 'Penalty' ? ' · Penalti' : ''}`]))
      .on('mouseleave', () => tip.hide());
    legend.push(['gol', 'Gol', color, 'dot'], ['no', 'Sin gol (círculo vacío)', 'transparent', 'dot']);
  }
  return legend;
}

function drawLegend(node, items) {
  node.replaceChildren(...items.map(([, label, c, shape]) => {
    const s = el('span');
    const i = el('i', { class: shape || '' });
    i.style.background = c;
    if (c === 'transparent') i.style.border = '1px solid currentColor';
    s.append(i, label);
    return s;
  }));
}

function segmented(id, onPick) {
  const box = $(id);
  box.addEventListener('click', (ev) => { const b = ev.target.closest('button'); if (b) onPick(b.dataset.v); });
  return (isOn) => box.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(isOn(b.dataset.v))));
}

// ---------- Estado / controles ----------
const P = () => dash.params();
const toggleTipo = (v) => {
  const t = new Set(P().tipos || []);
  t.has(v) ? t.delete(v) : t.add(v);
  dash.setParams({ tipos: [...t] });
};
const segCapa = segmented('#p-capa', (v) => dash.setParams({ capa: v }));
const segEquipo = segmented('#p-equipo', (v) => dash.setParams({ equipo: v, jugador: null }));
const segTipos = segmented('#p-tipos', toggleTipo);
const segCapaT = segmented('#t-capa', (v) => dash.setParams({ capa_t: v }));
const segTiposT = segmented('#t-tipos', toggleTipo);
const toggleTiro = (v) => {
  const t = new Set(P().tiros_tipo || []);
  t.has(v) ? t.delete(v) : t.add(v);
  dash.setParams({ tiros_tipo: [...t] });
};
const segTiros = segmented('#p-tiros', toggleTiro);
const segTirosT = segmented('#t-tiros', toggleTiro);

$('#sel-partido').addEventListener('change', (e) => dash.setParams({ partido: Number(e.target.value), jugador: null }));
$('#p-jugador').addEventListener('change', (e) => dash.setParams({ jugador: e.target.value }));  // '*' = todo el equipo
$('#sel-temporada').addEventListener('change', (e) => dash.setParams({ temporada: e.target.value, jugador_t: null }));
$('#t-jugador').addEventListener('change', (e) => dash.setParams({ jugador_t: e.target.value || null }));
$('#tabla-partido').addEventListener('click', (ev) => {
  const tr = ev.target.closest('tr[data-key]');
  if (!tr) return;
  const r = rows('metricas_jugador').find((x) => x.clave === tr.dataset.key);
  if (r) dash.setParams({ jugador: r.jugador, equipo: r.equipo === RM ? 'rm' : 'rival' });
});
$('#tabla-temporada').addEventListener('click', (ev) => {
  const th = ev.target.closest('th');
  if (th) { sortT = { k: th.dataset.field, asc: sortT.k === th.dataset.field ? !sortT.asc : false }; render(); return; }
  const tr = ev.target.closest('tr[data-key]');
  const r = tr && rows('jugadores_temporada').find((x) => x.clave === tr.dataset.key);
  if (r) dash.setParams({ jugador_t: r.jugador });
});
let sortT = { k: 'minutos', asc: false };
let sortR = { k: 'pj', asc: false };
$('#tabla-rivales').addEventListener('click', (ev) => {
  const th = ev.target.closest('th');
  if (th) { sortR = { k: th.dataset.field, asc: sortR.k === th.dataset.field ? !sortR.asc : th.dataset.field === 'rival' }; render(); }
});
$('#q-rival').addEventListener('input', () => render());
$('#q-partido').addEventListener('input', () => render());
$('#sel-comp').addEventListener('change', (e) => { dash.setParams({ comp: e.target.value }); });
let partidoHist = null;
$('#tabla-hist').addEventListener('click', (ev) => { const tr = ev.target.closest('tr[data-key]'); if (tr) { partidoHist = tr.dataset.key; render(); $('#alineacion').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } });
d3.json('data/estado.json').then((e) => { $('#estado').textContent = `Actualizado el ${new Date(e.actualizado).toLocaleString('es-ES', { dateStyle: 'long', timeStyle: 'short' })} · ${e.partidos} partidos analizados` + (e.fallos.length ? ` · sin actualizar: ${e.fallos.join(', ')}` : ''); }).catch(() => {});

// ---------- Pestañas ----------
const tabs = [...document.querySelectorAll('.rm-tab')];
function showTab(id, link = true) {
  for (const t of tabs) t.setAttribute('aria-selected', String(t.dataset.tab === id));
  for (const s of document.querySelectorAll('.rm-page')) s.hidden = s.id !== id;
  if (link) dash.setLink(id);
  render();
}
tabs.forEach((t) => t.addEventListener('click', () => showTab(t.dataset.tab)));

// ---------- Render ----------
// ---------- Escudos ----------
let escudosMap = null;
function escudo(nombre) {
  if (!escudosMap && dash.data('escudos').status === 'ok') escudosMap = new Map(rows('escudos').map((r) => [r.equipo, r.url]));
  const url = escudosMap && escudosMap.get(nombre);
  if (!url) return el('span', { class: 'esc esc-vacio', 'aria-hidden': 'true' });
  const img = el('img', { class: 'esc', src: url, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' });
  img.addEventListener('error', () => img.replaceWith(el('span', { class: 'esc esc-vacio', 'aria-hidden': 'true' })));
  return img;
}
// detras: el escudo a la derecha del nombre (equipo local en "LOCAL – VISITANTE")
const conEscudo = (nombre, tag = 'span', detras = false) => {
  const s = el(tag, { class: 'con-esc' });
  if (detras) s.append(nombre, escudo(nombre)); else s.append(escudo(nombre), nombre);
  return s;
};

// Modo claro / oscuro: por defecto el del sistema; el botón fija uno y se recuerda en este navegador
(() => {
  const b = $('#tema');
  const actual = () => document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const pintar = () => { const osc = actual() === 'dark'; b.textContent = osc ? '☀️' : '🌙'; b.title = osc ? 'Modo claro' : 'Modo oscuro'; };
  b.addEventListener('click', () => {
    const t = actual() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('rm-tema', t); } catch (e) { /* sin almacenamiento: solo esta visita */ }
    pintar();
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', pintar);
  pintar();
})();

const POS_ES = { Goalkeeper: 'Portero', Sweeper: 'Líbero', 'Centre-Back': 'Central', 'Left-Back': 'Lateral izquierdo', 'Right-Back': 'Lateral derecho',
  Defender: 'Defensa', 'Defensive Midfield': 'Mediocentro defensivo', 'Central Midfield': 'Mediocentro', 'Left Midfield': 'Interior izquierdo',
  'Right Midfield': 'Interior derecho', Midfield: 'Centrocampista', 'Attacking Midfield': 'Mediapunta', 'Left Winger': 'Extremo izquierdo',
  'Right Winger': 'Extremo derecho', 'Second Striker': 'Segundo delantero', 'Centre-Forward': 'Delantero centro', Attack: 'Delantero',
  GK: 'Portero', DF: 'Defensa', MF: 'Centrocampista', FW: 'Delantero' };

// Campo vertical con los titulares en su posición (px: 0 izquierda-1 derecha; py: 0 propia portería-1 rival)
function campito(titulares, color) {
  const W = 68, H = 105;
  const svg = d3.create('svg').attr('viewBox', `-2 -2 ${W + 4} ${H + 4}`).attr('class', 'campito').attr('role', 'img')
    .attr('aria-label', 'Titulares en el campo');
  const g = svg.append('g').attr('fill', 'none').style('stroke', 'var(--cds-chart-axis)').attr('stroke-width', 0.4);
  g.append('rect').attr('width', W).attr('height', H);
  g.append('line').attr('x1', 0).attr('x2', W).attr('y1', H / 2).attr('y2', H / 2);
  g.append('circle').attr('cx', W / 2).attr('cy', H / 2).attr('r', 9.15);
  for (const y0 of [0, H]) {
    const d = y0 ? -1 : 1;
    g.append('rect').attr('x', W / 2 - 20.15).attr('y', y0 ? H - 16.5 : 0).attr('width', 40.3).attr('height', 16.5);
    g.append('rect').attr('x', W / 2 - 9.15).attr('y', y0 ? H - 5.5 : 0).attr('width', 18.3).attr('height', 5.5);
    g.append('circle').attr('cx', W / 2).attr('cy', y0 + d * 11).attr('r', 0.5).style('fill', 'var(--cds-chart-axis)');
  }
  const pts = titulares.filter((j) => j.px !== '' && j.py !== '');
  const n = svg.append('g').selectAll('g').data(pts).join('g')
    .attr('transform', (j) => `translate(${N(j.px) * W},${(1 - N(j.py)) * H})`);
  n.append('circle').attr('r', 3.6).style('fill', color).style('stroke', 'var(--color-panel)').attr('stroke-width', 0.6);
  n.append('text').attr('text-anchor', 'middle').attr('dy', '1.15').style('fill', '#fff').style('font-size', '3.4px')
    .style('font-weight', '700').text((j) => j.dorsal);
  n.append('title').text((j) => `${j.dorsal} · ${j.jugador}`);
  return svg.node();
}

function fillTable(table, data, cols, keyOf, selKey) {
  const tb = table.querySelector('tbody');
  tb.replaceChildren(...data.map((r) => {
    const tr = el('tr', { 'data-key': keyOf(r) });
    if (selKey && keyOf(r) === selKey) tr.className = 'sel';
    for (const c of cols) tr.appendChild(el('td', {}, r[c]));
    return tr;
  }));
}

// Impacto de un jugador en el partido: goles y asistencias primero; luego lo que generó (xG, xA, pases clave, progresión)
// y lo que defendió (recuperaciones, duelos), restando las pérdidas en nuestro tercio. Sirve para ordenar, no es una nota oficial.
const impacto = (r) => N(r.goles) + 0.75 * N(r.asistencias) + 0.5 * (N(r.xg) + N(r.xa)) + 0.1 * N(r.pases_clave) + 0.02 * N(r.pases_progresivos)
  + 0.05 * N(r.recuperaciones) + 0.03 * N(r.duelos_ganados) - 0.1 * N(r.perdidas_peligrosas);
const resumenJugador = (r) => {
  const pl = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
  const partes = [];
  if (N(r.goles)) partes.push(pl(N(r.goles), 'gol', 'goles'));
  if (N(r.asistencias)) partes.push(pl(N(r.asistencias), 'asistencia', 'asistencias'));
  if (N(r.pases_clave)) partes.push(pl(N(r.pases_clave), 'pase clave', 'pases clave'));
  if (N(r.xg) + N(r.xa) >= 0.2) partes.push(`${N(r.xg).toFixed(2)} xG y ${N(r.xa).toFixed(2)} xA`);
  if (N(r.recuperaciones) >= 5) partes.push(`${r.recuperaciones} recuperaciones`);
  if (N(r.duelos_ganados) >= 5) partes.push(`${r.duelos_ganados} duelos ganados`);
  return partes.slice(0, 4).join(', ') || 'partido completo sin errores';
};

function renderPartido() {
  const partidos = rows('partidos');
  const sel = $('#sel-partido');
  const mid = Number(P().partido) || Number(rows('partidos').at(-1)?.match_id); // por defecto, el último partido
  if (partidos.length && (!sel.options.length || (sel.dataset.conHist !== '1' && ok('historico')))) {
    sel.replaceChildren();
    sel.dataset.conHist = ok('historico') ? '1' : '';
    const groups = d3.groups([...partidos].sort((a, b) => b.fecha.localeCompare(a.fecha)), (p) => `${p.competicion} ${p.temporada}`);
    for (const [label, ps] of groups) {
      const og = el('optgroup', { label });
      for (const p of ps) {
        // con los nombres del histórico ("Atletico Madrid", no "Atletico")
        const h = rows('historico').find((r) => r.fecha === p.fecha);
        const n = (x) => (!h || x === RM ? x : h.rival);
        og.appendChild(el('option', { value: p.match_id }, `${p.fecha} · ${n(p.local)} ${p.goles_local}–${p.goles_visitante} ${n(p.visitante)}`));
      }
      sel.appendChild(og);
    }
  }
  sel.value = String(mid);
  const p = partidos.find((x) => Number(x.match_id) === mid);
  const w = `match_id=${mid}`;
  // el mismo partido en el histórico: nombres de equipo, estadio y jornada con los que se ve el resto de la web
  const hp = p && rows('historico').find((r) => r.fecha === p.fecha);
  const nombre = (n) => (!hp ? n : n === RM ? RM : hp.rival);
  if (p) {
    $('#m-meta').textContent = [p.competicion === 'La Liga' ? 'LaLiga' : p.competicion, p.temporada.replace(/^(\d{4})\/\d{2}(\d{2})$/, '$1/$2'),
      hp && hp.ronda ? hp.ronda : '', p.fecha, hp && hp.estadio ? hp.estadio : ''].filter(Boolean).join(' · ');
    $('#m-score').replaceChildren(conEscudo(nombre(p.local)), markEl('b', 'partidos', 'goles_local', w, p.goles_local),
      el('span', {}, '–'), markEl('b', 'partidos', 'goles_visitante', w, p.goles_visitante), conEscudo(nombre(p.visitante), 'span', true));
    // goleadores: los tiros que acabaron en gol (Understat); los goles en propia puerta no son tiros, salen como "(p.p.)"
    const goles = rows('tiros').filter((t) => Number(t.match_id) === mid && t.resultado === 'Goal').sort((a, b) => N(a.minuto) - N(b.minuto));
    const lista = (eq) => goles.filter((t) => t.equipo === eq).map((t) => `${t.jugador} ${t.minuto}'${t.subtipo === 'Penalty' ? ' (pen.)' : ''}`);
    const linea = (eq, marcados) => {
      const l = lista(eq);
      for (let i = l.length; i < marcados; i++) l.push('(p.p.)');
      return l.length ? `⚽ ${nombre(eq)}: ${l.join(' · ')}` : '';
    };
    const gl = linea(p.local, N(p.goles_local)), gv = linea(p.visitante, N(p.goles_visitante));
    $('#m-goles').replaceChildren(...[gl, gv].filter(Boolean).map((t) => el('p', {}, t)));
    $('#m-coach').replaceChildren('Entrenador del Madrid: ', markEl('span', 'partidos', 'entrenador_rm', w, p.entrenador_rm));
  }

  // Comparativa
  const me = rows('metricas_equipo');
  const a = me.find((r) => Number(r.match_id) === mid && r.equipo === RM);
  const b = me.find((r) => Number(r.match_id) === mid && r.equipo !== RM);
  const cmp = $('#cmp');
  cmp.replaceChildren();
  if (a && b) {
    const wa = `clave=${enc(a.clave)}`, wb = `clave=${enc(b.clave)}`;
    cmp.append(el('span', { class: 'v head' }, 'RM'), el('span'), el('span', { class: 'lab head' }, ''), el('span'), el('span', { class: 'v r head' }, nombre(b.equipo)));
    for (const [k, label, dec, dir] of CMP) {
      if (a[k] === '' && b[k] === '') continue; // Opta no registra presiones
      const va = N(a[k]), vb = N(b[k]), mx = Math.max(va, vb) || 1;
      const better = dir === 0 || va === vb ? 0 : (va > vb) === (dir > 0) ? 1 : -1;
      const barA = el('span', { class: 'bar bl' }), barB = el('span', { class: 'bar br' });
      barA.style.width = `${(100 * va) / mx}%`; barB.style.width = `${(100 * vb) / mx}%`;
      barA.style.background = C_RM(); barB.style.background = C_RIV();
      barA.style.opacity = better < 0 ? 0.45 : 1; barB.style.opacity = better > 0 ? 0.45 : 1;
      const fmt = (v) => (v === '' ? '—' : N(v).toFixed(dec));
      const ta = markEl('span', 'metricas_equipo', k, wa, fmt(a[k])), tb = markEl('span', 'metricas_equipo', k, wb, fmt(b[k]));
      ta.className = 'v'; tb.className = 'v r';
      cmp.append(ta, barA, el('span', { class: 'lab' }, label), barB, tb);
    }
  }

  // Informe para el míster
  const rep = $('#rep');
  rep.replaceChildren();
  const inf = rows('informe').filter((r) => Number(r.match_id) === mid);
  const jug = rows('metricas_jugador').filter((r) => Number(r.match_id) === mid && r.equipo === RM && N(r.minutos) > 0);
  if (inf.length && a && b && p) {
    const sorted = [...inf].sort((x, y) => x.z - y.z);
    const neg = sorted.filter((r) => r.z < -0.5).slice(0, 2);
    const pos = sorted.filter((r) => r.z > 0.5).reverse().slice(0, 2);
    const gRM = N(a.goles), gR = N(b.goles), dxg = N(a.xg) - N(a.xg_contra), conXg = a.xg !== '';
    const res = gRM > gR ? 'victoria' : gRM === gR ? 'empate' : 'derrota';
    const fmt = (r) => Number(r.valor).toFixed(MET[r.metrica].fmt);

    rep.append(el('h3', {}, '1. Radiografía general'));
    const rad = el('p', { class: 'item' });
    rad.append(`${res[0].toUpperCase() + res.slice(1)} `, markEl('b', 'metricas_equipo', 'goles', `clave=${enc(a.clave)}`, a.goles), '–',
      markEl('b', 'metricas_equipo', 'goles', `clave=${enc(b.clave)}`, b.goles), ` ante ${nombre(b.equipo)}. `);
    if (conXg) rad.append('xG ', markEl('b', 'metricas_equipo', 'xg', `clave=${enc(a.clave)}`, a.xg),
      ' a favor y ', markEl('b', 'metricas_equipo', 'xg_contra', `clave=${enc(a.clave)}`, a.xg_contra), ' en contra: ',
      dxg > 0.5 ? 'fuimos mejores en ocasiones.' : dxg < -0.5 ? 'el rival generó más que nosotros.' : 'partido muy igualado en ocasiones.',
      gRM > gR && dxg < 0 ? ' El marcador nos favoreció más que el juego.' : gRM < gR && dxg > 0 ? ' El juego mereció más que el marcador.' : '');
    else rad.append('Tiros a puerta ', markEl('b', 'metricas_equipo', 'tiros_puerta', `clave=${enc(a.clave)}`, a.tiros_puerta), ' a ',
      markEl('b', 'metricas_equipo', 'tiros_puerta', `clave=${enc(b.clave)}`, b.tiros_puerta), ' (en esta competición no hay xG: Understat solo cubre la Liga).');
    rep.append(rad);

    const block = (r, bad) => {
      const m = MET[r.metrica];
      const it = el('div', { class: 'item ' + (bad ? 'bad' : 'good') });
      const dato = el('p');
      dato.append(el('span', { class: 'k' }, 'El dato: '), `${m.label} `, markEl('b', 'informe', 'valor', `clave=${enc(r.clave)}`, fmt(r)),
        ' frente a una media de ', markEl('b', 'informe', 'media', `clave=${enc(r.clave)}`, r.media), '.');
      it.append(dato);
      if (bad) {
        it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'El impacto: '), m.impacto);
        it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'Corrección: '), m.correccion);
      } else {
        it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'Cómo explotarlo: '), m.explotar);
        it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'Mensaje al grupo: '), m.mensaje);
      }
      return it;
    };

    rep.append(el('h3', {}, '2. 🚨 Alertas rojas y plan de choque'));
    if (neg.length) neg.forEach((r) => rep.append(block(r, true)));
    else rep.append(el('p', { class: 'item' }, 'Ninguna métrica colectiva claramente por debajo de lo habitual.'));
    const peor = [...jug].filter((r) => r.posicion !== 'GK').sort((x, y) => N(y.perdidas_peligrosas) - N(x.perdidas_peligrosas))[0];
    if (peor && N(peor.perdidas_peligrosas) >= 3) {
      const it = el('div', { class: 'item bad' });
      it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'Jugador señalado: '), `${peor.jugador}, `,
        markEl('b', 'metricas_jugador', 'perdidas_peligrosas', `clave=${enc(peor.clave)}`, peor.perdidas_peligrosas), ' pérdidas peligrosas en nuestro tercio.');
      it.append(el('p', {}, `Míster, a este hay que tocarle el orgullo en privado y con el vídeo delante: una pérdida más ahí y nos cuesta un partido. Si se repite, banquillo.`));
      rep.append(it);
    }

    rep.append(el('h3', {}, '3. 🛡️ Puntos fuertes y potenciación'));
    if (pos.length) pos.forEach((r) => rep.append(block(r, false)));
    else rep.append(el('p', { class: 'item' }, 'Ninguna métrica colectiva claramente por encima de lo habitual.'));
    const mejor = [...jug].sort((x, y) => impacto(y) - impacto(x))[0];
    if (mejor && impacto(mejor) > 0.5) {
      const it = el('div', { class: 'item good' });
      it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'Jugador a potenciar: '), `${mejor.jugador}: `, el('b', {}, resumenJugador(mejor)), '.');
      it.append(el('p', {}, 'Míster, a este hay que reconocérselo en público delante del grupo: que el resto vea que el que genera, juega.'));
      rep.append(it);
    }

    rep.append(el('h3', {}, '4. Veredicto para el próximo partido'));
    const v = !conXg ? { victoria: 'Victoria. Mantener el once; rotar solo por carga física.',
        empate: 'Empate. Mantener la estructura y ajustar los duelos individuales que se perdieron.',
        derrota: 'Derrota. Lunes, vídeo de las pérdidas y los duelos perdidos; revisar la titularidad de los señalados.' }[res]
      : res === 'victoria' && dxg > 0.5 ? 'Victoria merecida. Repetir once; rotar solo por carga física.'
      : res === 'victoria' ? 'Victoria por encima del juego. Lunes, vídeo de las ocasiones concedidas antes de que el marcador deje de perdonar.'
      : dxg > 0.5 ? 'El plan funcionó; faltó pegada. No tocar el sistema: sesión extra de finalización en transición.'
      : dxg < -0.5 ? 'Resultado justo y preocupante. Bloque más bajo y salida en transición; revisar la titularidad de los señalados.'
      : 'Partido de detalles. Mantener la estructura y ajustar los duelos individuales que se perdieron.';
    rep.append(el('p', { class: 'rm-verdict' }, v + (mejor ? ` Titular seguro: ${mejor.jugador}.` : '')));
  }

  // Mapa
  const equipoSel = P().equipo === 'rival' ? (b ? b.equipo : '') : RM;
  segCapa((v) => v === (P().capa || 'pases'));
  segEquipo((v) => v === (P().equipo || 'rm'));
  segTipos((v) => (P().tipos || []).includes(v));
  $('#p-tipos').hidden = (P().capa || 'pases') !== 'pases';
  segTiros((v) => (P().tiros_tipo || []).includes(v));
  $('#p-tiros').hidden = !$('#p-tipos').hidden;
  $('#p-equipo').querySelector('[data-v=rival]').textContent = b ? nombre(b.equipo) : 'Rival';
  const js = rows('metricas_jugador').filter((r) => Number(r.match_id) === mid && r.equipo === equipoSel && N(r.minutos) > 0)
    .sort((x, y) => N(y.minutos) - N(x.minutos));
  const pj = $('#p-jugador');
  pj.replaceChildren(el('option', { value: '*' }, 'Todo el equipo'), ...js.map((r) => el('option', { value: r.jugador }, r.jugador)));
  // sin elegir: el que más pases dio (con los 400 pases del equipo el mapa no se lee)
  const masPases = [...js].sort((x, y) => N(y.pases) - N(x.pases))[0];
  const jugSel = P().jugador && (P().jugador === '*' || js.some((r) => r.jugador === P().jugador)) ? P().jugador : masPases?.jugador || '*';
  pj.value = jugSel;
  const color = equipoSel === RM ? C_RM() : C_RIV();
  const filt = (r) => Number(r.match_id) === mid && r.equipo === equipoSel && (jugSel === '*' || r.jugador === jugSel);
  if (ok('pases', 'tiros')) {
    const legend = drawPitch($('#pitch-partido'), {
      capa: P().capa || 'pases', color, tipos: P().tipos || [], tiposTiro: P().tiros_tipo || [],
      passes: rows('pases').filter(filt).map((r) => ({ ...r, x: N(r.x), y: N(r.y), fin_x: N(r.fin_x), fin_y: N(r.fin_y) })),
      shots: rows('tiros').filter(filt).map((r) => ({ ...r, x: N(r.x), y: N(r.y), xg: r.xg === '' ? NaN : N(r.xg) })),
    });
    drawLegend($('#legend-partido'), legend);
  }

  // xG acumulado
  drawXgLine($('#xgline'), rows('tiros').filter((r) => Number(r.match_id) === mid), p, b);

  // Tabla jugadores
  const tab = rows('metricas_jugador').filter((r) => Number(r.match_id) === mid && r.equipo === equipoSel && N(r.minutos) > 0)
    .sort((x, y) => N(y.titular) - N(x.titular) || N(y.minutos) - N(x.minutos));
  const sel2 = tab.find((r) => r.jugador === jugSel);
  const vista = tab.map((r) => ({ ...r, xg: r.xg === '' ? '—' : N(r.xg).toFixed(2), xa: r.xa === '' ? '—' : N(r.xa).toFixed(2), acierto_pase: r.acierto_pase === '' ? '—' : N(r.acierto_pase).toFixed(1),
    duelos: `${N(r.duelos_ganados)}/${N(r.duelos_ganados) + N(r.duelos_perdidos)}`, impacto: impacto(r).toFixed(2) }));
  fillTable($('#tabla-partido'), vista, ['jugador', 'minutos', 'goles', 'asistencias', 'xg', 'xa', 'pases_clave', 'acierto_pase', 'pases_progresivos', 'regates',
    'recuperaciones', 'duelos', 'perdidas_peligrosas', 'impacto'], (r) => r.clave, sel2 && sel2.clave);

  const tk = $('#takeaway');
  if (p && a && a.xg === '') tk.replaceChildren(`${nombre(p.local)} – ${nombre(p.visitante)} (${p.fecha}): ${p.competicion}, sin xG.`);
  else if (p && a) {
    const wa = `clave=${enc(a.clave)}`;
    tk.replaceChildren(`${nombre(p.local)} – ${nombre(p.visitante)} (${p.fecha}): xG `, markEl('b', 'metricas_equipo', 'xg', wa, a.xg),
      ' del Madrid frente a ', markEl('b', 'metricas_equipo', 'xg_contra', wa, a.xg_contra), ' del rival.');
  }
}

function drawXgLine(box, shots, p, b) {
  box.querySelector('svg')?.remove();
  box.querySelector('.sin-xg')?.remove();
  if (!p || !b || dash.data('tiros').status !== 'ok') return;
  if (shots.length && shots.every((s) => s.xg === '')) return box.prepend(el('p', { class: 'sin-xg' }, 'Sin xG en esta competición: Understat solo cubre la Liga.'));
  const W = Math.max(280, box.clientWidth), H = 220, m = { t: 12, r: 118, b: 26, l: 34 };
  const maxMin = Math.max(95, d3.max(shots, (s) => N(s.minuto)) || 0);
  const series = [RM, b.equipo].map((team) => {
    let acc = 0;
    const pts = [{ minuto: 0, xg: 0 }];
    for (const s of shots.filter((s) => s.equipo === team).sort((x, y) => N(x.minuto) - N(y.minuto))) {
      acc += N(s.xg);
      pts.push({ minuto: N(s.minuto), xg: acc, s });
    }
    pts.push({ minuto: maxMin, xg: acc });
    return { team, pts, color: team === RM ? C_RM() : C_RIV() };
  });
  const x = d3.scaleLinear([0, maxMin], [m.l, W - m.r]);
  const y = d3.scaleLinear([0, Math.max(1, d3.max(series, (s) => s.pts.at(-1).xg))], [H - m.b, m.t]).nice();
  const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
  svg.append('g').attr('transform', `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(W < 400 ? 4 : 8).tickFormat((d) => d + "'"))
    .attr('font-size', null).attr('font-family', null).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'))
    .call((g) => g.selectAll('line,path').style('stroke', 'var(--cds-chart-axis)'));
  svg.append('g').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(W - m.l - m.r)))
    .attr('font-size', null).attr('font-family', null).call((g) => g.select('.domain').remove())
    .call((g) => g.selectAll('line').style('stroke', 'var(--cds-chart-grid)')).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'));
  svg.append('line').attr('x1', x(45)).attr('x2', x(45)).attr('y1', m.t).attr('y2', H - m.b).style('stroke', 'var(--cds-chart-reference)').attr('stroke-dasharray', '3 3');
  const tip = tooltip(box);
  const labels = [];
  for (const s of series) {
    svg.append('path').datum(s.pts).attr('fill', 'none').style('stroke', s.color).attr('stroke-width', 2).attr('stroke-linejoin', 'round').attr('stroke-linecap', 'round')
      .attr('d', d3.line().x((d) => x(d.minuto)).y((d) => y(d.xg)).curve(d3.curveStepAfter));
    svg.append('g').selectAll('circle').data(s.pts.filter((d) => d.s)).join('circle')
      .attr('cx', (d) => x(d.minuto)).attr('cy', (d) => y(d.xg)).attr('r', (d) => (d.s.resultado === 'Goal' ? 5 : 2.5))
      .style('fill', (d) => (d.s.resultado === 'Goal' ? s.color : 'var(--color-panel)')).style('stroke', s.color).attr('stroke-width', 1.5)
      .on('mouseenter', (ev, d) => tip.show(ev, `${d.s.minuto}' · ${d.s.jugador}`, [`${RES[d.s.resultado] || d.s.resultado} · xG ${N(d.s.xg).toFixed(2)}`, `Acumulado ${d.xg.toFixed(2)}`]))
      .on('mouseleave', () => tip.hide());
    labels.push({ y: y(s.pts.at(-1).xg), text: `${s.team.slice(0, 11)} ${s.pts.at(-1).xg.toFixed(2)}`, color: s.color });
  }
  labels.sort((p1, p2) => p1.y - p2.y);
  if (labels.length === 2 && labels[1].y - labels[0].y < 14) labels[1].y = labels[0].y + 14;
  for (const l of labels) svg.append('text').attr('x', W - m.r + 6).attr('y', l.y + 4).style('fill', l.color).style('font-size', 'var(--cds-font-size-caption)').text(l.text);
}

function renderTemporada() {
  const partidos = rows('partidos');
  const sel = $('#sel-temporada');
  if (partidos.length && (!sel.options.length || (sel.dataset.conHist !== '1' && ok('historico')))) {
    sel.replaceChildren();
    sel.dataset.conHist = ok('historico') ? '1' : '';
    const keys = d3.groups([...partidos].sort((a, b) => b.fecha.localeCompare(a.fecha)), (p) => p.competicion + '|' + p.temporada).map(([k]) => k);
    keys.forEach((k) => sel.appendChild(el('option', { value: k }, k.replace('|', ' '))));
  }
  const key = P().temporada || (partidos.length ? partidos.at(-1).competicion + '|' + partidos.at(-1).temporada : '');
  sel.value = key;
  const ids = new Set(partidos.filter((p) => p.competicion + '|' + p.temporada === key).map((p) => p.match_id));
  const byId = Object.fromEntries(partidos.map((p) => [p.match_id, p]));

  // xG por partido
  const box = $('#xgseason');
  box.querySelector('svg')?.remove();
  box.querySelector('.sin-xg')?.remove();
  const ms = rows('metricas_equipo').filter((r) => r.equipo === RM && ids.has(r.match_id))
    .map((r) => ({ ...r, p: byId[r.match_id] })).sort((a, b) => a.p.fecha.localeCompare(b.p.fecha));
  if (ms.length && ms.every((d) => d.xg === '')) box.prepend(el('p', { class: 'sin-xg' }, 'Sin xG en esta competición: Understat solo cubre la Liga.'));
  else if (ms.length) {
    const W = Math.max(280, box.clientWidth), H = 240, m = { t: 14, r: 96, b: 26, l: 34 };
    const x = d3.scalePoint(ms.map((d) => d.match_id), [m.l, W - m.r]).padding(0.3);
    const y = d3.scaleLinear([0, d3.max(ms, (d) => Math.max(N(d.xg), N(d.xg_contra)))], [H - m.b, m.t]).nice();
    const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    svg.append('g').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(W - m.l - m.r)))
      .attr('font-size', null).attr('font-family', null).call((g) => g.select('.domain').remove())
      .call((g) => g.selectAll('line').style('stroke', 'var(--cds-chart-grid)')).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'));
    const step = Math.ceil(ms.length / (W < 500 ? 5 : 10));
    svg.append('g').attr('transform', `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).tickValues(ms.filter((_, i) => i % step === 0).map((d) => d.match_id)).tickFormat((id) => byId[id].fecha.slice(2, 7)))
      .attr('font-size', null).attr('font-family', null).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'))
      .call((g) => g.selectAll('line,path').style('stroke', 'var(--cds-chart-axis)'));
    const lines = [['xg', 'xG a favor', C_RM()], ['xg_contra', 'xG en contra', C_BAD]];
    for (const [k, , c] of lines) {
      svg.append('path').datum(ms).attr('fill', 'none').style('stroke', c).attr('stroke-width', 2).attr('stroke-linejoin', 'round').attr('stroke-linecap', 'round')
        .attr('d', d3.line().x((d) => x(d.match_id)).y((d) => y(N(d[k]))));
    }
    const resCol = (d) => (N(d.goles) > N(d.p.goles_local) + N(d.p.goles_visitante) - N(d.goles) ? 'var(--color-ok)'
      : N(d.goles) * 2 === N(d.p.goles_local) + N(d.p.goles_visitante) ? 'var(--cds-chart-muted)' : C_BAD);
    const tip = tooltip(box);
    svg.append('g').selectAll('circle').data(ms).join('circle').attr('cx', (d) => x(d.match_id)).attr('cy', (d) => y(N(d.xg))).attr('r', 4)
      .style('fill', resCol).style('stroke', 'var(--color-panel)').attr('stroke-width', 1.5)
      .on('mouseenter', (ev, d) => tip.show(ev, `${d.p.fecha} · ${d.p.local} ${d.p.goles_local}–${d.p.goles_visitante} ${d.p.visitante}`,
        [`xG a favor ${d.xg}`, `xG en contra ${d.xg_contra}`, 'Pulsa para abrir el post-partido']))
      .on('mouseleave', () => tip.hide())
      .on('click', (ev, d) => { dash.setParams({ partido: Number(d.match_id), jugador: null }); showTab('partido'); });
    const last = ms.at(-1);
    const ends = lines.map(([k, label, c]) => ({ y: y(N(last[k])), text: label, c })).sort((a, b) => a.y - b.y);
    if (ends[1].y - ends[0].y < 14) ends[1].y = ends[0].y + 14;
    for (const e of ends) svg.append('text').attr('x', W - m.r + 8).attr('y', e.y + 4).style('fill', e.c).style('font-size', 'var(--cds-font-size-caption)').text(e.text);
  }

  // Tabla plantilla
  const jt = rows('jugadores_temporada').filter((r) => r.temporada === key);
  const sk = sortT.k;
  jt.sort((a, b) => (sk === 'jugador' ? a.jugador.localeCompare(b.jugador) : N(a[sk]) - N(b[sk])) * (sortT.asc ? 1 : -1));
  document.querySelectorAll('#tabla-temporada th').forEach((th) => th.setAttribute('aria-sort', th.dataset.field === sk ? (sortT.asc ? 'ascending' : 'descending') : 'none'));
  const selT = jt.find((r) => r.jugador === P().jugador_t);
  fillTable($('#tabla-temporada'), jt, ['jugador', 'pj', 'minutos', 'goles', 'xg', 'asistencias', 'xa', 'pases_progresivos', 'recuperaciones', 'duelos_pct', 'perdidas_peligrosas'],
    (r) => r.clave, selT && selT.clave);

  // Mapa de temporada
  const tj = $('#t-jugador');
  const byMin = [...jt].sort((a, b) => b.minutos - a.minutos);
  tj.replaceChildren(...byMin.map((r) => el('option', { value: r.jugador }, r.jugador)));
  const jugador = byMin.some((r) => r.jugador === P().jugador_t) ? P().jugador_t : byMin[0]?.jugador;
  tj.value = jugador || '';
  segCapaT((v) => v === (P().capa_t || 'pases'));
  segTiposT((v) => (P().tipos || []).includes(v));
  $('#t-tipos').hidden = (P().capa_t || 'pases') !== 'pases';
  segTirosT((v) => (P().tiros_tipo || []).includes(v));
  $('#t-tiros').hidden = !$('#t-tipos').hidden;
  if (ok('pases', 'tiros') && jugador) {
    const filt = (r) => ids.has(r.match_id) && r.equipo === RM && r.jugador === jugador;
    const legend = drawPitch($('#pitch-temporada'), {
      capa: P().capa_t || 'pases', color: C_RM(), tipos: P().tipos || [], tiposTiro: P().tiros_tipo || [],
      passes: rows('pases').filter(filt).map((r) => ({ ...r, x: N(r.x), y: N(r.y), fin_x: N(r.fin_x), fin_y: N(r.fin_y) })),
      shots: rows('tiros').filter(filt).map((r) => ({ ...r, x: N(r.x), y: N(r.y), xg: r.xg === '' ? NaN : N(r.xg) })),
    });
    drawLegend($('#legend-temporada'), legend);
  }
}

function balance(rs) {
  const v = rs.filter((r) => r.resultado === 'V').length, e = rs.filter((r) => r.resultado === 'E').length;
  return { pj: rs.length, v, e, d: rs.length - v - e, gf: d3.sum(rs, (r) => N(r.goles_rm)), gc: d3.sum(rs, (r) => N(r.goles_rival)),
    pct_v: rs.length ? Math.round((1000 * v) / rs.length) / 10 : 0 };
}

function renderHistorico() {
  const todos = rows('historico');
  const sel = $('#sel-comp');
  if (todos.length && sel.options.length < 2) {
    const comps = d3.rollups(todos, (v) => v.length, (r) => r.competicion).sort((a, b) => b[1] - a[1]);
    sel.replaceChildren(el('option', { value: '' }, 'Todas'), ...comps.map(([c, n]) => el('option', { value: c }, `${c} (${n})`)));
  }
  const comp = P().comp || '';
  sel.value = comp;
  const hs = todos.filter((r) => !comp || r.competicion === comp);
  const t = balance(hs);
  for (const k of ['pj', 'v', 'gf', 'gc']) $(`#k-${k}`).textContent = hs.length ? d3.format(',')(t[k]).replace(/,/g, '.') : '—';
  $('#k-pct').textContent = hs.length ? `${t.pct_v}%` : '—';

  // % de victorias por temporada
  const box = $('#histline');
  box.querySelector('svg')?.remove();
  const ts = d3.groups(hs, (r) => r.temporada).map(([temporada, rs]) => ({ temporada, year: Number(temporada.slice(0, 4)), ...balance(rs) }))
    .sort((a, b) => a.year - b.year);
  $('#hist-rango').textContent = ts.length ? `De ${ts[0].temporada} a ${ts.at(-1).temporada}. Pasa el ratón para ver el balance.` : '';
  if (ts.length > 1) {
    const W = Math.max(280, box.clientWidth), H = 240, m = { t: 12, r: 16, b: 26, l: 48 };
    const x = d3.scaleLinear(d3.extent(ts, (d) => d.year), [m.l, W - m.r]);
    const y = d3.scaleLinear([0, 100], [H - m.b, m.t]);
    const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    svg.append('g').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)).tickFormat((d) => d + '%'))
      .attr('font-size', null).attr('font-family', null).call((g) => g.select('.domain').remove())
      .call((g) => g.selectAll('line').style('stroke', 'var(--cds-chart-grid)')).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'));
    svg.append('g').attr('transform', `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(W < 500 ? 4 : 9).tickFormat(d3.format('d')))
      .attr('font-size', null).attr('font-family', null).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'))
      .call((g) => g.selectAll('line,path').style('stroke', 'var(--cds-chart-axis)'));
    const ln = d3.line().x((d) => x(d.year)).y((d) => y(d.pct_v));
    // un tramo por cada racha de temporadas seguidas (sin Liga en 1936–39, sin Copa de Europa antes de 1955...)
    const segs = [];
    for (const d of ts) { if (!segs.length || d.year - segs.at(-1).at(-1).year > 1) segs.push([]); segs.at(-1).push(d); }
    for (const sg of segs) svg.append('path').datum(sg).attr('fill', 'none').style('stroke', C_RM()).attr('stroke-width', 2).attr('stroke-linejoin', 'round').attr('stroke-linecap', 'round').attr('d', ln);
    const tip = tooltip(box);
    const dot = svg.append('circle').attr('r', 4).style('fill', C_RM()).attr('visibility', 'hidden');
    svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', W - m.l - m.r).attr('height', H - m.t - m.b).attr('fill', 'transparent')
      .on('mousemove', (ev) => {
        const yr = x.invert(d3.pointer(ev)[0]);
        const d = ts[d3.minIndex(ts, (q) => Math.abs(q.year - yr))];
        dot.attr('cx', x(d.year)).attr('cy', y(d.pct_v)).attr('visibility', 'visible');
        tip.show(ev, d.temporada, [`${d.pct_v}% victorias`, `${d.v}V ${d.e}E ${d.d}D · ${d.gf}–${d.gc} goles`]);
      })
      .on('mouseleave', () => { dot.attr('visibility', 'hidden'); tip.hide(); });
  }

  // Rivales
  const q = $('#q-rival').value.trim().toLowerCase();
  const rv = d3.groups(hs, (r) => r.rival).map(([rival, rs]) => ({ rival, ...balance(rs) })).filter((r) => !q || r.rival.toLowerCase().includes(q));
  rv.sort((a, b) => (sortR.k === 'rival' ? a.rival.localeCompare(b.rival) : a[sortR.k] - b[sortR.k]) * (sortR.asc ? 1 : -1));
  document.querySelectorAll('#tabla-rivales th').forEach((th) => th.setAttribute('aria-sort', th.dataset.field === sortR.k ? (sortR.asc ? 'ascending' : 'descending') : 'none'));
  fillTable($('#tabla-rivales'), rv, ['rival', 'pj', 'v', 'e', 'd', 'gf', 'gc', 'pct_v'], (r) => r.rival);
  $('#tabla-rivales tbody').querySelectorAll('tr').forEach((tr, i) => tr.firstChild.replaceChildren(conEscudo(rv[i].rival)));

  // Todos los partidos (los más recientes primero)
  const qp = $('#q-partido').value.trim().toLowerCase();
  const MAX = 400;
  const ps = hs.filter((r) => !qp || `${r.fecha} ${r.temporada} ${r.local} ${r.visitante} ${r.competicion} ${r.estadio}`.toLowerCase().includes(qp))
    .sort((a, b) => b.fecha.localeCompare(a.fecha));
  const conAl = new Set(rows('historico_alineaciones').map((r) => r.partido_id));
  const tb = $('#tabla-hist tbody');
  tb.replaceChildren(...ps.slice(0, MAX).map((r) => {
    const tr = el('tr', { 'data-key': r.partido_id || '' });
    if (r.partido_id && r.partido_id === partidoHist) tr.className = 'sel';
    const local = el('td', { class: 'loc' }), visitante = el('td', { class: 'vis' });
    local.append(conEscudo(r.local, 'span', true));
    visitante.append(conEscudo(r.visitante));
    tr.append(el('td', {}, r.fecha), el('td', {}, r.competicion), local, el('td', { class: 'sep' }, '–'), visitante, el('td', { class: 'estadio' }, r.estadio || '—'),
      el('td', {}, `${r.goles_local}–${r.goles_visitante}${r.penaltis ? ` (${r.penaltis.replace('-', '–')} pen.)` : ''}${conAl.has(r.partido_id) ? ' 👥' : ''}`));
    tr.lastChild.style.color = r.resultado === 'V' ? 'var(--color-ok)' : r.resultado === 'D' ? C_BAD : '';
    return tr;
  }));
  $('#hist-nota').textContent = `${ps.length} partidos${ps.length > MAX ? `; se muestran los ${MAX} más recientes, usa el buscador para el resto` : ''}. Pulsa un partido para ver su ficha (ronda, goleadores y, si hay 👥, alineaciones).`;

  // Ficha del partido elegido
  const p = todos.find((r) => r.partido_id === partidoHist);
  $('#alineacion').hidden = !p;
  if (p) pintarFicha($('#alineacion'), p, 'h2');
}

// Ficha de un partido (resultado, ronda, goleadores y alineaciones): se usa en Histórico y en Títulos
function pintarFicha(cont, p, tagTitulo = 'h3') {
  const al = rows('historico_alineaciones').filter((r) => r.partido_id === p.partido_id);
  const titulo = el(tagTitulo, { class: 'ficha-titulo' });
  titulo.append(`${p.fecha} · ${p.competicion}${p.ronda ? ` (${p.ronda})` : ''} · `, conEscudo(p.local),
    ` ${p.goles_local}–${p.goles_visitante}${p.penaltis ? ` (${p.penaltis.replace('-', '–')} pen.)` : ''} `,
    conEscudo(p.visitante), p.estadio ? ` · ${p.estadio}` : '');
  // goleadores de cada equipo (Wikipedia; no siempre están)
  const gol = el('div', { class: 'ficha-goles' });
  for (const [eq, g] of [[p.local, p.goleadores_local], [p.visitante, p.goleadores_visitante]]) {
    if (g) gol.append(el('p', {}, `⚽ ${eq}: ${g.split('; ').map((x) => x.replace(/ ([\d+,]+)/, " $1'").replace(/,(\d)/g, "', $1")).join(' · ')}`));
  }
  if (!gol.childNodes.length) gol.append(el('p', { class: 'rm-sub' }, al.length ? 'Sin goleadores en las fuentes.' : 'Sin goleadores ni alineaciones en las fuentes para este partido.'));
  else if (!al.length) gol.append(el('p', { class: 'rm-sub' }, 'Sin alineaciones en las fuentes para este partido.'));
  const porDorsal = (a, b) => (a.dorsal === '' ? 999 : N(a.dorsal)) - (b.dorsal === '' ? 999 : N(b.dorsal));
  // primero el local, luego el visitante
  const equipos = d3.groups(al, (r) => r.equipo).sort(([a], [b]) => (b === p.local) - (a === p.local));
  const grid = el('div', { class: 'rm-grid' });
  grid.append(...equipos.map(([equipo, js]) => {
    const c = el('div', { class: 'rm-lineup' });
    c.append(conEscudo(equipo, 'h3'));
    const cuerpo = el('div', { class: 'al-cuerpo' });
    const lista = el('div', { class: 'al-lista' });
    const tit = js.filter((j) => j.titular === '1').sort(porDorsal);
    for (const [nombre, grupo] of [['Titulares', tit], ['Suplentes', js.filter((j) => j.titular !== '1').sort(porDorsal)]]) {
      if (!grupo.length) continue;
      lista.append(el('p', { class: 'rm-sub' }, nombre));
      for (const j of grupo) {
        const fila = el('div', { class: 'al-fila' });
        fila.append(el('span', { class: 'al-dorsal' }, j.dorsal || ''), el('span', {}, j.jugador),
          j.posicion ? el('span', { class: 'al-pos' }, POS_ES[j.posicion] || j.posicion) : '');
        lista.append(fila);
      }
    }
    cuerpo.append(lista);
    if (tit.some((j) => j.px !== '')) cuerpo.append(campito(tit, equipo === RM ? C_RM() : C_RIV()));
    c.append(cuerpo);
    return c;
  }));
  cont.replaceChildren(titulo, gol, grid);
}

// ---------- Títulos ----------
let titSel = null;
$('#tit-lista').addEventListener('click', (ev) => { const b = ev.target.closest('button[data-key]'); if (b) { titSel = b.dataset.key; fichaTit = null; render(); $('#tit-detalle').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } });
// la ficha del partido se abre justo debajo de su fila (otro clic la cierra)
let fichaTit = null;
$('#tit-tabla').addEventListener('click', (ev) => {
  const tr = ev.target.closest('tr[data-key]');
  if (!tr || !tr.dataset.key) return;
  fichaTit = fichaTit === tr.dataset.key ? null : tr.dataset.key;
  render();
});
const esRM = (n) => /^(Real )?Madrid( CF| FC)?$/.test(n.trim());

function renderTitulos() {
  const ts = rows('titulos');
  if (!ts.length) return;
  const camp = ts.filter((t) => t.tipo === 'Campeón');
  const n = (f) => camp.filter(f).length;
  const kpis = [['Títulos oficiales', n((t) => t.grupo === 'Nacional' || t.grupo === 'Internacional')], ['Ligas', n((t) => t.comp_hist === 'LaLiga')],
    ['Copas de Europa', n((t) => t.comp_hist === 'Copa de Europa / Champions')], ['Copas del Rey', n((t) => t.comp_hist === 'Copa del Rey')],
    ['Mundiales de clubes', n((t) => ['Copa Intercontinental', 'Mundial de Clubes', 'Copa Intercontinental de la FIFA'].includes(t.comp_hist))]];
  $('#tit-kpis').replaceChildren(...kpis.map(([l, v]) => { const c = el('div', { class: 'rm-card rm-kpi' }); c.append(el('p', { class: 'rm-sub' }, l), el('p', { class: 'n' }, v)); return c; }));

  const lista = [];
  for (const grupo of ['Nacional', 'Internacional', 'Regional', 'Otros']) {
    const gs = d3.groups(ts.filter((t) => t.grupo === grupo), (t) => t.competicion);
    if (!gs.length) continue;
    const caja = el('section', { class: 'rm-card tit-grupo' });
    const cab = el('header');
    const ng = ts.filter((t) => t.grupo === grupo && t.tipo === 'Campeón').length;
    cab.append(el('h2', {}, { Nacional: 'Títulos nacionales', Internacional: 'Títulos internacionales', Regional: 'Títulos regionales', Otros: 'Otros torneos (no oficiales)' }[grupo]),
      el('span', { class: 'n' }, `${ng} ${ng === 1 ? 'título' : 'títulos'}`));
    caja.append(cab);
    lista.push(caja);
    for (const [comp, xs] of gs) {
      const fila = el('div', { class: 'tit-comp' });
      const cab = el('div');
      const nt = xs.filter((t) => t.tipo === 'Campeón').length, ns = xs.length - nt;
      cab.append(el('h3', {}, comp), el('p', { class: 'n' }, nt), el('p', { class: 'rm-sub' }, `${nt === 1 ? 'título' : 'títulos'}${ns ? ` · ${ns} ${ns === 1 ? 'vez' : 'veces'} subcampeón` : ''}`));
      const anios = el('div', { class: 'tit-anios' });
      for (const t of [...xs].sort((a, b) => a.etiqueta.slice(0, 4).localeCompare(b.etiqueta.slice(0, 4)))) {
        const key = `${t.competicion}|${t.tipo}|${t.etiqueta}`;
        const b = el('button', { type: 'button', 'data-key': key, 'aria-pressed': String(key === titSel), class: t.tipo === 'Campeón' ? '' : 'sub',
          title: `${t.tipo} · ${t.temporada && (t.comp_hist === 'LaLiga' || t.hasta) ? t.temporada : 'sin partidos en la base'}` }, t.etiqueta);
        if (t.comp_hist === 'LaLiga' ? !t.temporada : !t.hasta) b.disabled = true;
        anios.append(b);
      }
      fila.append(cab, anios);
      caja.append(fila);
    }
  }
  $('#tit-lista').replaceChildren(...lista);

  const t = ts.find((x) => `${x.competicion}|${x.tipo}|${x.etiqueta}` === titSel);
  $('#tit-detalle').hidden = !t;
  if (!t) return;
  $('#tit-titulo').textContent = `${t.tipo === 'Campeón' ? '🏆 Campeón' : 'Subcampeón'} · ${t.competicion} ${t.etiqueta}`;
  const wrap = $('#tit-tabla');
  if (t.comp_hist === 'LaLiga') {
    const tabla = rows('ligas').filter((r) => r.temporada === t.temporada).sort((a, b) => N(a.pos) - N(b.pos));
    const yo = tabla.find((r) => esRM(r.equipo));
    const otro = tabla.find((r) => r !== yo && (t.tipo === 'Campeón' ? r.pos === '2' : r.pos === '1'));
    $('#tit-resumen').textContent = yo ? `Temporada ${t.temporada}: ${yo.pts} puntos (${yo.g}V ${yo.e}E ${yo.p}D, ${yo.gf}–${yo.gc} goles)` +
      (otro ? `; ${t.tipo === 'Campeón' ? 'el segundo' : 'el campeón'}, ${otro.equipo}, con ${otro.pts}.` : '.') : `Temporada ${t.temporada}.`;
    const tb = el('table'); const th = el('thead'); const hr = el('tr');
    for (const h of ['Pos', 'Equipo', 'PJ', 'G', 'E', 'P', 'GF', 'GC', 'Pts']) hr.append(el('th', {}, h));
    th.append(hr); const bd = el('tbody');
    for (const r of tabla) {
      const tr = el('tr', esRM(r.equipo) ? { class: 'rm-fila' } : {});
      for (const c of ['pos', 'equipo', 'pj', 'g', 'e', 'p', 'gf', 'gc', 'pts']) tr.append(el('td', {}, r[c]));
      bd.append(tr);
    }
    tb.append(th, bd); wrap.replaceChildren(tb);
    return;
  }
  // la edición: los partidos de esa competición hasta su final (desde/hasta los calcula historico.py)
  const ps = rows('historico').filter((r) => r.competicion === t.comp_hist && r.fecha >= t.desde && r.fecha <= t.hasta).sort((a, b) => a.fecha.localeCompare(b.fecha));
  const b = balance(ps);
  $('#tit-resumen').textContent = `${ps.length} partidos en la base: ${b.v}V ${b.e}E ${b.d}D, ${b.gf}–${b.gc} goles. Pulsa un partido para ver su ficha aquí mismo.`;
  const tb = el('table'); const th = el('thead'); const hr = el('tr');
  for (const [h, a] of [['Fecha'], ['Ronda'], ['Partido', 3], ['Resultado'], ['Estadio']]) hr.append(el('th', a ? { colspan: a, class: 'partido' } : {}, h));
  th.append(hr); const bd = el('tbody');
  for (const r of ps) {
    const tr = el('tr', { 'data-key': r.partido_id });
    const loc = el('td', { class: 'loc' }), vis = el('td', { class: 'vis' });
    loc.append(conEscudo(r.local, 'span', true)); vis.append(conEscudo(r.visitante));
    tr.append(el('td', {}, r.fecha), el('td', {}, r.ronda || '—'), loc, el('td', { class: 'sep' }, '–'), vis,
      el('td', {}, `${r.goles_local}–${r.goles_visitante}${r.penaltis ? ` (${r.penaltis.replace('-', '–')} pen.)` : ''}`), el('td', { class: 'estadio' }, r.estadio || '—'));
    tr.children[5].style.color = r.resultado === 'V' ? 'var(--color-ok)' : r.resultado === 'D' ? C_BAD : '';
    bd.append(tr);
    if (r.partido_id === fichaTit) {
      tr.className = 'sel';
      const td = el('td', { colspan: 7, class: 'ficha-celda' });
      const caja = el('div', { class: 'ficha' });
      pintarFicha(caja, r);
      td.append(caja);
      const fila = el('tr', { class: 'ficha-fila' });
      fila.append(td);
      bd.append(fila);
    }
  }
  tb.append(th, bd); tb.id = 'tabla-titulo'; wrap.replaceChildren(tb);
}

// ---------- Rendimiento frente a lo esperado ----------
const VER_COL = { 'Por debajo': C_BAD, 'Por encima': 'var(--color-ok)', 'En línea': 'var(--cds-chart-muted)' };
let sortRen = { k: 'veredicto', asc: true };
$('#tabla-rendimiento').addEventListener('click', (ev) => {
  const th = ev.target.closest('th');
  if (th) { sortRen = { k: th.dataset.field, asc: sortRen.k === th.dataset.field ? !sortRen.asc : ['jugador', 'puesto', 'veredicto'].includes(th.dataset.field) }; render(); }
});
const consejo = (m) => m.includes('remata por debajo')
  ? 'Míster, a este hay que arroparlo en privado: genera las ocasiones, el gol llegará. Sesión extra de finalización tras transición, sin presión pública.'
  : m.includes('asistencia')
    ? 'Sus pases merecen más: el problema está en quien remata. Más hombres pisando área cuando él tenga el balón.'
    : m.includes('pérdidas')
      ? 'Míster, a este hay que tocarle el orgullo con el vídeo delante: en nuestro tercio, balón seguro o fuera. Una más y nos cuesta un partido.'
      : 'Percentil bajo para su puesto: revisar su rol antes que su actitud.';

function renderRendimiento() {
  const rs = rows('rendimiento').map((r) => ({ ...r, xg: N(r.xg), goles: N(r.goles) }));
  // Gráfico goles frente a xG
  const box = $('#ren-scatter');
  box.querySelector('svg')?.remove();
  if (rs.length) {
    const W = Math.max(280, box.clientWidth), H = 300, m = { t: 14, r: 16, b: 34, l: 40 };
    const mx = Math.ceil(Math.max(d3.max(rs, (d) => d.xg), d3.max(rs, (d) => d.goles)) + 0.5);
    const x = d3.scaleLinear([0, mx], [m.l, W - m.r]), y = d3.scaleLinear([0, mx], [H - m.b, m.t]);
    const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    svg.append('g').attr('transform', `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(5))
      .attr('font-size', null).attr('font-family', null).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'))
      .call((g) => g.selectAll('line,path').style('stroke', 'var(--cds-chart-axis)'));
    svg.append('g').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)))
      .attr('font-size', null).attr('font-family', null).call((g) => g.select('.domain').remove())
      .call((g) => g.selectAll('line').style('stroke', 'var(--cds-chart-grid)')).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'));
    svg.append('line').attr('x1', x(0)).attr('y1', y(0)).attr('x2', x(mx)).attr('y2', y(mx)).style('stroke', 'var(--cds-chart-reference)').attr('stroke-dasharray', '4 4');
    svg.append('text').attr('x', x(mx) - 4).attr('y', y(mx) + 14).attr('text-anchor', 'end').style('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text('goles = xG');
    svg.append('text').attr('x', W - m.r).attr('y', H - 4).attr('text-anchor', 'end').style('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text('xG (calidad de sus ocasiones)');
    svg.append('text').attr('x', m.l).attr('y', m.t - 2).style('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text('Goles');
    const tip = tooltip(box);
    const pts = rs.filter((d) => d.xg > 0 || d.goles > 0);
    svg.append('g').selectAll('circle').data(pts).join('circle').attr('cx', (d) => x(d.xg)).attr('cy', (d) => y(d.goles)).attr('r', 6)
      .style('fill', (d) => VER_COL[d.veredicto]).style('stroke', 'var(--color-panel)').attr('stroke-width', 1.5)
      .on('mouseenter', (ev, d) => tip.show(ev, d.jugador, [`${d.goles} goles con ${d.xg.toFixed(2)} xG`, d.veredicto]))
      .on('mouseleave', () => tip.hide());
    svg.append('g').selectAll('text').data(pts.filter((d) => Math.abs(d.goles - d.xg) >= 0.9 || d.xg >= 2)).join('text')
      .attr('x', (d) => x(d.xg) + 9).attr('y', (d) => y(d.goles) + 4).style('fill', 'var(--color-fg)').style('font-size', 'var(--cds-font-size-caption)')
      .text((d) => d.jugador.split(' ').slice(-1)[0]);
  }
  // Alertas
  const al = $('#ren-alertas');
  al.replaceChildren(...rs.filter((r) => r.veredicto === 'Por debajo').sort((a, b) => N(b.minutos) - N(a.minutos)).map((r) => {
    const it = el('div', { class: 'item bad' });
    const w = `jugador=${enc(r.jugador)}`;
    it.append(el('p')); it.lastChild.append(markEl('b', 'rendimiento', 'jugador', w, r.jugador), ` · ${r.puesto} · `, markEl('span', 'rendimiento', 'minutos', w, r.minutos), ' min');
    it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'El dato: '), markEl('span', 'rendimiento', 'motivo', w, r.motivo), '.');
    it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'Cómo tratarlo: '), consejo(r.motivo));
    return it;
  }));
  // Tabla
  const sk = sortRen.k, ord = { 'Por debajo': 0, 'En línea': 1, 'Por encima': 2 };
  const txt = ['jugador', 'puesto'].includes(sk);
  rs.sort((a, b) => (sk === 'veredicto' ? ord[a.veredicto] - ord[b.veredicto] || N(b.minutos) - N(a.minutos)
    : txt ? String(a[sk]).localeCompare(String(b[sk])) : N(a[sk]) - N(b[sk])) * (sortRen.asc || sk === 'veredicto' ? 1 : -1));
  document.querySelectorAll('#tabla-rendimiento th').forEach((th) => th.setAttribute('aria-sort', th.dataset.field === sk ? (sortRen.asc ? 'ascending' : 'descending') : 'none'));
  fillTable($('#tabla-rendimiento'), rs, ['jugador', 'puesto', 'minutos', 'goles', 'xg', 'g_menos_xg', 'asistencias', 'xa', 'a_menos_xa',
    'pct_rol', 'acierto_pase', 'prog90', 'recup90', 'duelos_pct', 'perdidas90', 'veredicto'], (r) => r.jugador);
  $('#tabla-rendimiento tbody').querySelectorAll('tr').forEach((tr, i) => { tr.lastChild.style.color = VER_COL[rs[i].veredicto]; });
}

function render() {
  const tab = document.querySelector('.rm-page:not([hidden])')?.id;
  if (tab === 'partido') renderPartido();
  else if (tab === 'temporada') renderTemporada();
  else if (tab === 'historico') renderHistorico();
  else if (tab === 'rendimiento') renderRendimiento();
  else if (tab === 'titulos') renderTitulos();
}

dash.onData(render);
const named = location.hash.slice(1);
if (['partido', 'temporada', 'historico', 'rendimiento', 'titulos'].includes(named)) showTab(named, false);
})();
