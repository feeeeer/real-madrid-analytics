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
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const fechaEs = (iso, anio = true) => { const [y, m, d] = String(iso).split('-'); return `${Number(d)} ${MESES[m - 1]}${anio ? ' ' + y : ''}`; };
const markEl = (tag, src, field, where, text) => el(tag, { 'data-source': src, 'data-field': field, 'data-where': where }, text);
const ok = (...ids) => ids.every((id) => dash.data(id).status === 'ok');
const rows = (id) => (dash.data(id).status === 'ok' ? dash.data(id).data : []);
const C_RM = () => dash.colors[0];
const C_RIV = () => dash.colors[1];
const C_KEY = () => dash.colors[2];
const C_BAD = 'var(--cds-chart-status-critical)';

// ---------- Movimiento ----------
const EASE_OUT = 'cubic-bezier(0.23, 1, 0.32, 1)', EASE_MOVER = 'cubic-bezier(0.77, 0, 0.175, 1)';
const sinMovimiento = matchMedia('(prefers-reduced-motion: reduce)');
// animación de entrada que solo se ve la primera vez que aparece "clave"; si se repinta a mitad (llega otro CSV), sigue por donde iba
const inicios = new Map();
function entrada(clave, nodo, frames, opts) {
  if (!nodo || sinMovimiento.matches || !nodo.getClientRects().length) return;  // oculto: aún no lo ha visto nadie
  const ahora = performance.now();
  if (!inicios.has(clave)) inicios.set(clave, ahora);
  const pasado = ahora - inicios.get(clave);
  if (pasado > opts.duration + (opts.delay || 0)) return;
  nodo.animate(frames, { fill: 'backwards', ...opts }).currentTime = pasado;
}
// indicador que se desliza bajo la pestaña elegida
function moverIndicador(cont) {
  const sel = cont.querySelector('[aria-selected="true"]');
  let ind = cont.querySelector('.indicador');
  if (!sel || !sel.offsetWidth) return;
  const nuevo = !ind;
  if (nuevo) { ind = el('span', { class: 'indicador', 'aria-hidden': 'true' }); cont.prepend(ind); ind.style.transition = 'none'; }
  Object.assign(ind.style, { width: `${sel.offsetWidth}px`, height: `${sel.offsetHeight}px`, transform: `translate(${sel.offsetLeft}px, ${sel.offsetTop}px)` });
  if (nuevo) requestAnimationFrame(() => { ind.style.transition = ''; });
}
// las tarjetas visibles entran escalonadas, como mucho 8 pasos para no hacer esperar
const escalonar = (pag) => [...pag.querySelectorAll('.rm-card')].filter((c) => c.offsetParent).forEach((c, i) => c.style.setProperty('--i', Math.min(i, 8)));
// difumina el borde de lo que tiene más contenido por ver con scroll
const pistaScroll = (e) => {
  e.classList.toggle('mas-abajo', e.scrollHeight - e.scrollTop - e.clientHeight > 2);
  e.classList.toggle('mas-dcha', e.scrollWidth - e.scrollLeft - e.clientWidth > 2);
};
const CON_SCROLL = '.rm-tablewrap, .menu, .sub-tabs';
document.addEventListener('scroll', (ev) => { if (ev.target.matches?.(CON_SCROLL)) pistaScroll(ev.target); }, true);

// ---------- Cálculos (visibles en Fuentes) ----------
dash.calc('informe', {
  inputs: ['metricas_equipo', 'partidos'],
  title: 'Informe vs partidos anteriores',
  description: 'Cada métrica del Madrid en el partido frente a su media en los partidos anteriores que la tienen (mínimo 3); z en desviaciones típicas, positivo = mejor para el estilo del míster. Métricas que la fuente no tiene, fuera.',
  fn: (metricas_equipo, partidos) => {
    const fecha = Object.fromEntries(partidos.map((p) => [p.match_id, p.fecha]));
    // signo: +1 más es mejor, -1 menos es mejor. Posesión y PPDA fuera: un bloque medio/bajo no se juzga por ellas.
    const M = { xg: 1, xg_contra: -1, tiros_puerta: 1, acierto_pase: 1, pases_progresivos: 1, presiones_campo_rival: 1,
      recuperaciones_campo_rival: 1, duelos_ganados_pct: 1, perdidas_peligrosas: -1, contrapresiones: 1, xg_contraataque: 1 };
    const out = [];
    // todas las fuentes juntas (Opta y ESPN): cada métrica solo con los partidos que la tienen
    {
      const rm = metricas_equipo.filter((r) => r.equipo === 'Real Madrid');
      for (const [k, sign] of Object.entries(M)) {
        const rk = rm.filter((r) => r[k] !== '' && r[k] != null);
        for (const r of rk) {
          const v = rk.filter((x) => fecha[x.match_id] < fecha[r.match_id]).map((x) => Number(x[k]));
          if (v.length < 3) continue;
          const media = v.reduce((a, b) => a + b, 0) / v.length;
          const sd = Math.sqrt(v.reduce((a, b) => a + (b - media) ** 2, 0) / (v.length - 1)) || 1;
          out.push({ clave: r.match_id + '|' + k, match_id: r.match_id, metrica: k, valor: Number(r[k]), previos: v.length,
            media: Math.round(media * 100) / 100, z: Math.round((sign * (Number(r[k]) - media) / sd) * 100) / 100 });
        }
      }
    }
    return out;
  },
});

const TODAS = 'Todas las competiciones';
dash.calc('jugadores_temporada', {
  inputs: ['metricas_jugador', 'partidos'],
  title: 'Plantilla por temporada',
  description: 'Suma por jugador del Madrid de sus partidos en cada competición y temporada, y en todas juntas; % de duelos = ganados / (ganados + perdidos). xG y xA solo de la Liga.',
  fn: (metricas_jugador, partidos) => {
    const comp = Object.fromEntries(partidos.map((p) => [p.match_id, p.competicion + '|' + p.temporada]));
    const acc = {};
    for (const r of metricas_jugador) {
      if (r.equipo !== 'Real Madrid') continue;
      const tc = comp[r.match_id];
      for (const t of [tc, TODAS + '|' + tc.split('|')[1]]) {
      const k = t + '|' + r.jugador_id;
      const a = (acc[k] ??= { clave: k, temporada: t, jugador: r.jugador, pj: 0, minutos: 0, goles: 0, xg: 0, asistencias: 0, xa: 0,
        pases_progresivos: 0, recuperaciones: 0, dg: 0, dp: 0, perdidas_peligrosas: 0 });
      a.pj += 1; a.minutos += Number(r.minutos); a.goles += Number(r.goles); a.xg += Number(r.xg); a.conXg ||= r.xg !== '';
      a.asistencias += Number(r.asistencias); a.xa += Number(r.xa); a.pases_progresivos += Number(r.pases_progresivos);
      a.recuperaciones += Number(r.recuperaciones); a.dg += Number(r.duelos_ganados); a.dp += Number(r.duelos_perdidos);
      a.perdidas_peligrosas += Number(r.perdidas_peligrosas);
      }
    }
    // sin xG (Champions y Copa: Understat solo cubre la Liga) se deja vacío, no 0
    return Object.values(acc).map(({ dg, dp, conXg, ...a }) => ({ ...a, xg: conXg ? Math.round(a.xg * 100) / 100 : '', xa: conXg ? Math.round(a.xa * 100) / 100 : '',
      duelos_pct: dg + dp ? Math.round((1000 * dg) / (dg + dp)) / 10 : 0 }));
  },
});

// Cada jugador del Madrid en el partido frente a sus partidos anteriores (por 90 min; métricas Opta, válidas en todas las competiciones)
const FORMA = [['goles', ['gol', 'goles'], 1], ['asistencias', ['asistencia', 'asistencias'], 1], ['pases_clave', ['pase clave', 'pases clave'], 1],
  ['pases_progresivos', ['pase progresivo', 'pases progresivos'], 1], ['regates', ['regate', 'regates'], 1], ['recuperaciones', ['recuperación', 'recuperaciones'], 1],
  ['duelos_ganados', ['duelo ganado', 'duelos ganados'], 1], ['perdidas_peligrosas', ['pérdida peligrosa', 'pérdidas peligrosas'], -1]];
function formaJugadores(mid, fecha, jug) {
  const p90 = (r, k) => (N(r[k]) * 90) / N(r.minutos);
  const out = [];
  // solo partidos con eventos Opta (los que aún solo tienen datos de ESPN no traen pases, duelos ni recuperaciones)
  for (const r of jug.filter((r) => Number(r.match_id) === mid && r.equipo === RM && r.posicion !== 'GK' && N(r.minutos) >= 45 && r.pases !== '')) {
    // shortcut: mínimo 30 min por partido previo y 3 partidos; con pocas jornadas la media aún se mueve mucho
    const prev = jug.filter((x) => x.jugador_id === r.jugador_id && x.equipo === RM && N(x.minutos) >= 30 && x.pases !== '' && fecha[x.match_id] < fecha[r.match_id]);
    if (prev.length < 3) continue;
    const ms = FORMA.map(([k, label, sign]) => {
      const v = prev.map((x) => p90(x, k)), media = d3.mean(v), sd = Math.max(d3.deviation(v) || 0, 0.5);
      return { label, valor: N(r[k]), esperado: (media * N(r.minutos)) / 90, z: (sign * (p90(r, k) - media)) / sd };
    });
    out.push({ r, prev: prev.length, score: d3.mean(ms, (m) => m.z), ms });
  }
  return out;
}
const lineaForma = (f, arriba) => {
  const top = [...f.ms].sort((a, b) => (arriba ? b.z - a.z : a.z - b.z)).filter((m) => (arriba ? m.z > 0.5 : m.z < -0.5)).slice(0, 3);
  return `${f.r.jugador} (${f.r.minutos}'): ` + top.map((m) => `${m.valor} ${m.label[m.valor === 1 ? 0 : 1]} (suele ${m.esperado.toFixed(1)})`).join(' · ');
};

// ---------- Textos del informe (estilo Mourinho) ----------
const MET = {
  xg: { label: 'xG generado', fmt: 2,
    impacto: 'Dominamos sin herir: el equipo no fabrica ocasiones claras y el rival sale vivo del partido.',
    bien: 'El equipo fabricó más ocasiones de calidad que de costumbre.' },
  xg_contra: { label: 'xG concedido', fmt: 2,
    impacto: 'El rival entra en nuestra área con demasiada facilidad. La solidez defensiva es innegociable.',
    bien: 'El rival apenas encontró ocasiones claras: el bloque estuvo cerrado.' },
  tiros_puerta: { label: 'Tiros a puerta', fmt: 0,
    impacto: 'Llegamos pero no obligamos al portero: decisiones malas en el último metro.',
    bien: 'Más disparos entre los tres palos: obligamos al portero rival a intervenir.' },
  acierto_pase: { label: '% acierto de pase', fmt: 1,
    impacto: 'Perdemos demasiados balones simples y regalamos transiciones al rival.',
    bien: 'Circulación más limpia de lo habitual: menos balones regalados.' },
  pases_progresivos: { label: 'Pases progresivos', fmt: 0,
    impacto: 'Circulamos sin avanzar: el rival se reorganiza antes de que lleguemos.',
    bien: 'Rompimos líneas más que de costumbre y llegamos antes al último tercio.' },
  presiones_campo_rival: { label: 'Presiones en campo rival', fmt: 0,
    impacto: 'El rival sale jugando cómodo: no hay agresividad en la primera línea.',
    bien: 'Más presión arriba de lo habitual: el rival no salió cómodo.' },
  recuperaciones_campo_rival: { label: 'Recuperaciones en campo rival', fmt: 0,
    impacto: 'Robamos lejos de su portería: cada contraataque empieza a 60 metros.',
    bien: 'Robamos más cerca de su portería: los contraataques empiezan más cerca del gol.' },
  duelos_ganados_pct: { label: '% duelos ganados', fmt: 1,
    impacto: 'Perdemos la batalla física. Sin duelos ganados no hay bloque que aguante.',
    bien: 'Ganamos el cuerpo a cuerpo más que en otros partidos.' },
  perdidas_peligrosas: { label: 'Pérdidas peligrosas', fmt: 0,
    impacto: 'Regalamos el balón en nuestro tercio: es exactamente cómo un rival nos mata en transición.',
    bien: 'Menos balones perdidos en nuestro tercio: menos transiciones regaladas.' },
  contrapresiones: { label: 'Contrapresiones', fmt: 0,
    impacto: 'Tras perder el balón no reaccionamos: el rival sale limpio a la contra.',
    bien: 'Reaccionamos mejor tras pérdida: el rival salió menos limpio a la contra.' },
  xg_contraataque: { label: 'xG en contraataque', fmt: 2,
    impacto: 'No castigamos al rival cuando se desordena: nuestra arma principal está apagada.',
    bien: 'Las transiciones generaron más peligro de lo habitual.' },
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

function drawPitch(box, { capa, passes, shots, color, tipos, tiposTiro, acciones = [], red = null }) {
  box.querySelector('svg')?.remove();
  const half = capa === 'tiros';
  // pase progresivo = completado que avanza 15 m o más (misma definición que procesar.py)
  passes = passes.map((p) => ({ ...p, tipo: p.tipo === 'completo' && p.fin_x - p.x >= 15 ? 'progresivo' : p.tipo }));
  const vb = half ? [56, -2, 66, 84] : [-2, -2, 124, 84];  // tiros: solo el medio campo de ataque
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
  if (capa === 'red' && red) {
    // red de pases: cada jugador en su posición media; la línea engorda con los pases entre los dos (mínimo 3)
    const pos = new Map(red.nodos.map((n) => [n.jugador, n]));
    const ens = red.enlaces.filter((e) => N(e.n) >= 3 && pos.has(e.de) && pos.has(e.a));
    const maxN = d3.max(ens, (e) => N(e.n)) || 1;
    svg.append('g').selectAll('line').data(ens).join('line')
      .attr('x1', (e) => pos.get(e.de).x).attr('y1', (e) => pos.get(e.de).y).attr('x2', (e) => pos.get(e.a).x).attr('y2', (e) => pos.get(e.a).y)
      .style('stroke', color).attr('stroke-width', (e) => 0.3 + 1.8 * (N(e.n) / maxN)).attr('opacity', (e) => 0.25 + 0.6 * (N(e.n) / maxN)).attr('stroke-linecap', 'round')
      .on('mouseenter', (ev, e) => tip.show(ev, `${e.de} → ${e.a}`, [`${e.n} pases`])).on('mouseleave', () => tip.hide());
    const maxP = d3.max(red.nodos, (n) => N(n.pases)) || 1;
    const nodos = svg.append('g').selectAll('g').data(red.nodos.filter((n) => N(n.toques) >= 15)).join('g').attr('transform', (n) => `translate(${n.x},${n.y})`);
    nodos.append('circle').attr('r', (n) => 1.6 + 2.4 * Math.sqrt(N(n.pases) / maxP)).style('fill', color).style('stroke', 'var(--color-panel)').attr('stroke-width', 0.4)
      .on('mouseenter', (ev, n) => tip.show(ev, n.jugador, [`${n.pases} pases completados a compañeros`, `${n.toques} toques`])).on('mouseleave', () => tip.hide());
    nodos.append('text').attr('y', -4.6).attr('text-anchor', 'middle').style('fill', 'var(--color-fg)').style('font-size', '2.6px').style('pointer-events', 'none')
      .text((n) => n.jugador.split(' ').at(-1));
    legend.push(['n', 'Círculo: posición media (tamaño = pases)', color, 'dot'], ['l', 'Línea: pases entre los dos (3 o más)', color]);
  } else if (capa === 'acciones') {
    // dónde roba (círculo verde) y dónde pierde el balón (aspa roja; rellena si fue en nuestro tercio)
    const rec = acciones.filter((a) => a.tipo === 'recuperacion'), per = acciones.filter((a) => a.tipo === 'perdida');
    svg.append('g').selectAll('circle').data(rec).join('circle').attr('cx', (a) => a.x).attr('cy', (a) => a.y).attr('r', 1.3)
      .style('fill', 'var(--color-ok)').attr('opacity', 0.85)
      .on('mouseenter', (ev, a) => tip.show(ev, `${a.jugador} · ${a.minuto}'`, ['Recuperación'])).on('mouseleave', () => tip.hide());
    svg.append('g').selectAll('path').data(per).join('path').attr('d', d3.symbol(d3.symbolCross, 9))
      .attr('transform', (a) => `translate(${a.x},${a.y}) rotate(45)`).style('fill', C_BAD).attr('opacity', (a) => (a.peligrosa === '1' ? 1 : 0.55))
      .on('mouseenter', (ev, a) => tip.show(ev, `${a.jugador} · ${a.minuto}'`, [a.peligrosa === '1' ? 'Pérdida peligrosa (en nuestro tercio)' : 'Pérdida'])).on('mouseleave', () => tip.hide());
    legend.push(['r', `Recuperaciones (${rec.length})`, 'var(--color-ok)', 'dot'], ['p', `Pérdidas (${per.length}; ${per.filter((a) => a.peligrosa === '1').length} peligrosas)`, C_BAD, 'dot']);
  } else if (capa === 'zonas') {
    // dónde participa: origen de sus pases, sus tiros, recuperaciones y pérdidas, en celdas de 10 × 10 m
    const n = d3.rollup([...passes, ...shots, ...acciones], (v) => v.length, (d) => Math.min(11, Math.floor(d.x / 10)), (d) => Math.min(7, Math.floor(d.y / 10)));
    const celdas = [...n].flatMap(([cx, m]) => [...m].map(([cy, v]) => ({ cx, cy, v })));
    const max = d3.max(celdas, (c) => c.v) || 1;
    svg.insert('g', ':first-child').selectAll('rect').data(celdas).join('rect')
      .attr('x', (c) => c.cx * 10).attr('y', (c) => c.cy * 10).attr('width', 10).attr('height', 10)
      .style('fill', color).attr('opacity', (c) => 0.08 + 0.72 * (c.v / max))
      .on('mouseenter', (ev, c) => tip.show(ev, `${c.v} acciones`, ['Pases que salen de esta zona y tiros']))
      .on('mouseleave', () => tip.hide());
    legend.push(['poco', 'Pocas acciones', color, 'dot0'], ['mucho', 'Muchas acciones', color]);
  } else if (!half) {
    const defs = svg.append('defs');
    const COL = { progresivo: color, completo: 'var(--cds-chart-muted)', fallado: C_BAD, clave: C_KEY() };
    for (const [k, c] of Object.entries(COL)) {
      defs.append('marker').attr('id', `arr-${box.id}-${k}`).attr('viewBox', '0 0 10 10').attr('refX', 9).attr('refY', 5)
        .attr('markerWidth', 4).attr('markerHeight', 4).attr('orient', 'auto')
        .append('path').attr('d', 'M0,0L10,5L0,10z').style('fill', c);
    }
    const ps = passes.filter((p) => tipos.includes(p.tipo));
    const op = ps.length > 800 ? 0.25 : ps.length > 250 ? 0.45 : 0.8;
    // los pases clave se dibujan encima
    const capaDe = { completo: 0, fallado: 1, progresivo: 2, clave: 3 };
    ps.sort((a, b) => capaDe[a.tipo] - capaDe[b.tipo]);
    svg.append('g').selectAll('line').data(ps).join('line')
      .attr('x1', (d) => d.x).attr('y1', (d) => d.y).attr('x2', (d) => d.fin_x).attr('y2', (d) => d.fin_y)
      .style('stroke', (d) => COL[d.tipo]).attr('stroke-width', (d) => (d.tipo === 'clave' ? 0.55 : 0.35))
      .attr('stroke-linecap', 'round').attr('opacity', (d) => (d.tipo === 'clave' ? 1 : op))
      .attr('marker-end', (d) => `url(#arr-${box.id}-${d.tipo})`)
      .on('mouseenter', function (ev, d) {
        d3.select(this).attr('stroke-width', 1).attr('opacity', 1);
        tip.show(ev, `${d.jugador} · ${d.minuto}'`, [{ progresivo: 'Pase progresivo (avanza 15 m o más)', completo: 'Pase completado', fallado: 'Pase fallado', clave: 'Pase clave (acaba en tiro)' }[d.tipo]]);
      })
      .on('mouseleave', function (ev, d) {
        d3.select(this).attr('stroke-width', d.tipo === 'clave' ? 0.55 : 0.35).attr('opacity', d.tipo === 'clave' ? 1 : op);
        tip.hide();
      });
    legend.push(['progresivo', 'Progresivo', color], ['completo', 'Otro completado', 'var(--cds-chart-muted)'], ['fallado', 'Fallado', C_BAD], ['clave', 'Pase clave', C_KEY()]);
  } else {
    const ss = shots.filter((d) => tiposTiro.includes(TIPO_TIRO[d.resultado])).sort((a, b) => (b.xg || 0) - (a.xg || 0));
    const esc = ss.length > 60 ? 0.6 : 1;  // una temporada entera: círculos más pequeños para que no se tapen
    svg.append('g').selectAll('circle').data(ss).join('circle')
      .attr('cx', (d) => d.x).attr('cy', (d) => d.y).attr('r', (d) => esc * (isNaN(d.xg) ? 2 : 0.7 + Math.sqrt(d.xg) * 4.5))
      .style('fill', (d) => (d.resultado === 'Goal' ? color : 'transparent')).style('stroke', color)
      .attr('stroke-width', 0.3).attr('fill-opacity', ss.length > 60 ? 0.55 : 0.85).attr('stroke-opacity', ss.length > 60 ? 0.6 : 1)
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
    if (shape === 'dot0') i.style.opacity = 0.2;
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
$('#p-sub').addEventListener('click', (ev) => { const bt = ev.target.closest('button'); if (bt) dash.setParams({ sub_p: bt.dataset.v }); });
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
const segRT = segmented('#r-tiros', (v) => dash.setParams({ tiros_r: v }));

$('#sel-partido').addEventListener('change', (e) => dash.setParams({ partido: Number(e.target.value), jugador: null }));
$('#p-jugador').addEventListener('change', (e) => dash.setParams({ jugador: e.target.value }));  // '*' = todo el equipo
$('#sel-temporada').addEventListener('change', (e) => dash.setParams({ temporada: e.target.value, jugador_t: null }));
$('#t-jugador').addEventListener('change', (e) => dash.setParams({ jugador_t: e.target.value || null }));
$('#f-jugador').addEventListener('change', (e) => dash.setParams({ jugador_t: e.target.value || null }));
$('#f-comparar').addEventListener('change', (e) => dash.setParams({ comparar: e.target.value || null }));
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
d3.json('data/estado.json').then((e) => { $('#estado').textContent = `Actualizado ${new Date(e.actualizado).toLocaleString('es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · ${e.partidos} partidos` + (e.fallos.length ? ` · ⚠ sin actualizar: ${e.fallos.join(', ')}` : ''); }).catch(() => {});

// ---------- Pestañas ----------
const tabs = [...document.querySelectorAll('.rm-tab')];
function showTab(id, link = true) {
  for (const t of tabs) t.setAttribute('aria-selected', String(t.dataset.tab === id));
  for (const s of document.querySelectorAll('.rm-page')) s.hidden = s.id !== id;
  const t = tabs.find((x) => x.dataset.tab === id);
  $('#pag-titulo').textContent = t.dataset.titulo;
  document.title = `${t.dataset.titulo} · Real Madrid Analytics`;
  // cada filtro de la barra solo en las secciones a las que afecta
  for (const f of document.querySelectorAll('.filtros [data-en]')) f.hidden = !f.dataset.en.split(' ').includes(id);
  escalonar($(`#${id}`));
  if (link) scrollTo(0, 0);
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

// Cabecera de un partido: fecha y estadio a la izquierda; equipos, marcador y goleadores de cada uno debajo de su equipo
function marcadorFicha({ fecha, estadio, meta, local, visitante, gl, gv, penaltis, golesL = [], golesV = [] }) {
  const caja = el('div', { class: 'mf' });
  const cuando = el('div', { class: 'mf-cuando' });
  cuando.append(el('b', {}, fechaEs(fecha)), el('span', {}, estadio || 'Estadio sin datos'));
  if (meta) cuando.append(el('span', { class: 'mf-meta' }, meta));
  const equipo = (nombre, goles, lado) => {
    const d = el('div', { class: `mf-eq mf-${lado}` });
    d.append(conEscudo(nombre, 'div', lado === 'l'));
    // con muchos goles, en línea para que no se estire la cabecera
    const ul = el('ul', { class: 'mf-goles' + (goles.length > 4 ? ' en-linea' : '') });
    goles.forEach((g) => ul.append(el('li', {}, g)));
    d.append(ul);
    return d;
  };
  const res = el('div', { class: 'mf-res' });
  res.append(el('b', {}, `${gl} – ${gv}`));
  if (penaltis) res.append(el('small', {}, `${penaltis.replace('-', '–')} pen.`));
  caja.append(cuando, equipo(local, golesL, 'l'), res, equipo(visitante, golesV, 'v'));
  return caja;
}
const golesWiki = (g) => (g ? g.split('; ').map((x) => x.replace(/ ([\d+,]+)/, " $1'").replace(/,(\d)/g, "', $1")) : []);

// Modo claro / oscuro: por defecto el del sistema; el botón fija uno y se recuerda en este navegador
(() => {
  const b = $('#tema');
  const actual = () => document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const pintar = () => { const osc = actual() === 'dark'; b.textContent = osc ? '☀️ Modo claro' : '🌙 Modo oscuro'; b.title = osc ? 'Modo claro' : 'Modo oscuro'; };
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
    const tr = el('tr', { 'data-key': keyOf(r), tabindex: '0' });
    if (selKey && keyOf(r) === selKey) tr.className = 'sel';
    for (const c of cols) tr.appendChild(el('td', {}, r[c]));
    return tr;
  }));
}

// Impacto de un jugador en el partido: goles y asistencias primero; luego lo que generó (xG, xA, pases clave, progresión)
// y lo que defendió (recuperaciones, duelos), restando las pérdidas en nuestro tercio. Sirve para ordenar, no es una nota oficial.
const impacto = (r) => N(r.goles) + 0.75 * N(r.asistencias) + 0.5 * (N(r.xg) + N(r.xa)) + 0.1 * N(r.pases_clave) + 0.02 * N(r.pases_progresivos)
  + 0.05 * N(r.recuperaciones) + 0.03 * N(r.duelos_ganados) - 0.1 * N(r.perdidas_peligrosas);

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
        og.appendChild(el('option', { value: p.match_id }, `${fechaEs(p.fecha, false)} · ${n(p.local)} ${p.goles_local}–${p.goles_visitante} ${n(p.visitante)}`));
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
    // goleadores: los tiros que acabaron en gol (Understat); los goles en propia puerta no son tiros, salen como "(p.p.)"
    // goleadores de las incidencias (WhoScored o ESPN: incluyen penaltis y goles en propia puerta); si no hay, de los tiros
    const inc = rows('incidencias').filter((r) => Number(r.match_id) === mid && ['gol', 'penalti', 'gol_pp'].includes(r.tipo));
    const goles = inc.length ? inc.map((r) => ({ equipo: r.equipo, txt: `${r.jugador} ${r.minuto}'${r.tipo === 'penalti' ? ' (pen.)' : r.tipo === 'gol_pp' ? ' (p.p.)' : ''}`, m: N(r.orden) }))
      : rows('tiros').filter((t) => Number(t.match_id) === mid && t.resultado === 'Goal')
        .map((t) => ({ equipo: t.equipo, txt: `${t.jugador} ${t.minuto}'${t.subtipo === 'Penalty' ? ' (pen.)' : ''}`, m: N(t.minuto) }));
    const lista = (eq) => goles.filter((g) => g.equipo === eq).sort((a, b) => a.m - b.m).map((g) => g.txt);
    const conPP = (eq, marcados) => {
      const l = lista(eq);
      for (let i = l.length; i < marcados; i++) l.push('(p.p.)');
      return l;
    };
    const meta = [p.competicion === 'La Liga' ? 'LaLiga' : p.competicion, p.temporada.replace(/^(\d{4})\/\d{2}(\d{2})$/, '$1/$2'), hp && hp.ronda ? hp.ronda : ''].filter(Boolean).join(' · ');
    $('#m-ficha').replaceChildren(marcadorFicha({ fecha: p.fecha, estadio: hp && hp.estadio, meta, local: nombre(p.local), visitante: nombre(p.visitante),
      gl: p.goles_local, gv: p.goles_visitante, golesL: conPP(p.local, N(p.goles_local)), golesV: conPP(p.visitante, N(p.goles_visitante)) }));
    entrada('marcador', $('#m-ficha .mf-res'), [{ opacity: 0, transform: 'translateY(4px) scale(0.97)' }, { opacity: 1, transform: 'none' }], { duration: 400, delay: 120, easing: EASE_OUT });
    $('#m-coach').replaceChildren('Entrenador del Madrid: ', markEl('span', 'partidos', 'entrenador_rm', w, p.entrenador_rm));
  }

  // Apartados del partido (Resumen, Estadísticas, Mapas, Jugadores, Alineaciones)
  const sub = P().sub_p || 'resumen';
  document.querySelectorAll('#partido [data-sub]').forEach((d) => d.classList.toggle('sub-oculto', d.dataset.sub !== sub));
  document.querySelectorAll('#p-sub button').forEach((bt) => bt.setAttribute('aria-selected', String(bt.dataset.v === sub)));
  moverIndicador($('#p-sub'));
  escalonar($('#partido'));
  // anterior / siguiente
  const orden = [...partidos].sort((x, y) => x.fecha.localeCompare(y.fecha)), pos = orden.findIndex((x) => Number(x.match_id) === mid);
  $('#p-ant').disabled = pos <= 0; $('#p-sig').disabled = pos < 0 || pos >= orden.length - 1;
  $('#p-ant').onclick = () => pos > 0 && dash.setParams({ partido: Number(orden[pos - 1].match_id), jugador: null });
  $('#p-sig').onclick = () => pos < orden.length - 1 && dash.setParams({ partido: Number(orden[pos + 1].match_id), jugador: null });
  // partido aún sin eventos Opta (el Mac no lo ha descargado): datos básicos de ESPN y Understat
  const soloEspn = rows('metricas_equipo').some((r) => Number(r.match_id) === mid && r.fuente === 'ESPN');
  $('#p-aviso').hidden = !soloEspn;
  $('#momentum').hidden = soloEspn;
  // línea de tiempo: goles, tarjetas y cambios; arriba el local, abajo el visitante
  if (p && ok('incidencias')) drawLinea($('#m-linea'), rows('incidencias').filter((r) => Number(r.match_id) === mid), p, nombre);

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
      // la primera vez, cada barra crece desde el centro hacia fuera
      const fila = cmp.querySelectorAll('.bar').length / 2;
      for (const [bar, origen] of [[barA, 'right'], [barB, 'left']]) {
        bar.style.transformOrigin = origen;
        entrada('cmp', bar, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: 500, delay: 100 + fila * 30, easing: EASE_OUT });
      }
    }
  }

  // Informe para el míster
  const rep = $('#rep');
  rep.replaceChildren();
  const inf = rows('informe').filter((r) => Number(r.match_id) === mid);
  const jug = rows('metricas_jugador').filter((r) => Number(r.match_id) === mid && r.equipo === RM && N(r.minutos) > 0);
  if (a && b && p) {
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
        ' frente a una media de ', markEl('b', 'informe', 'media', `clave=${enc(r.clave)}`, r.media), ` en los ${r.previos} partidos anteriores.`);
      it.append(dato);
      it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'El impacto: '), bad ? m.impacto : m.bien);
      return it;
    };

    rep.append(el('h3', {}, '2. 🚨 Alertas rojas: el equipo peor que en sus partidos anteriores'));
    if (neg.length) neg.forEach((r) => rep.append(block(r, true)));
    else rep.append(el('p', { class: 'item' }, inf.length ? 'Ninguna métrica colectiva claramente por debajo de lo habitual.' : 'Aún no hay 3 partidos anteriores para comparar.'));
    rep.append(el('h3', {}, '3. 🛡️ Puntos fuertes: el equipo mejor que en sus partidos anteriores'));
    if (pos.length) pos.forEach((r) => rep.append(block(r, false)));
    else rep.append(el('p', { class: 'item' }, inf.length ? 'Ninguna métrica colectiva claramente por encima de lo habitual.' : 'Aún no hay 3 partidos anteriores para comparar.'));

    rep.append(el('h3', {}, '4. Jugadores frente a sus partidos anteriores'));
    const forma = formaJugadores(mid, Object.fromEntries(partidos.map((x) => [x.match_id, x.fecha])), rows('metricas_jugador'));
    const arriba = forma.filter((f) => f.score >= 0.3).sort((x, y) => y.score - x.score);
    const abajo = forma.filter((f) => f.score <= -0.3).sort((x, y) => x.score - y.score);
    if (!forma.length) rep.append(el('p', { class: 'item' }, 'Aún no hay 3 partidos anteriores con minutos para comparar a ningún jugador.'));
    else {
      for (const [lista, bien, titulo] of [[arriba, true, 'Por encima de lo suyo'], [abajo, false, 'Por debajo de lo suyo']]) {
        const it = el('div', { class: 'item ' + (bien ? 'good' : 'bad') });
        it.append(el('p', {}, '')); it.lastChild.append(el('span', { class: 'k' }, titulo + ': '), lista.length ? '' : 'nadie claramente.');
        lista.forEach((f) => it.append(el('p', {}, lineaForma(f, bien))));
        rep.append(it);
      }
      const resto = forma.length - arriba.length - abajo.length;
      if (resto) rep.append(el('p', { class: 'item' }, `${resto} jugador${resto > 1 ? 'es' : ''} en su línea habitual. Entre paréntesis, lo que suele dar en esos minutos.`));
    }

    rep.append(el('h3', {}, '5. Veredicto para el próximo partido'));
    const v = !conXg ? { victoria: 'Victoria. Mantener el once; rotar solo por carga física.',
        empate: 'Empate. Mantener la estructura y ajustar los duelos individuales que se perdieron.',
        derrota: 'Derrota. Lunes, vídeo de las pérdidas y los duelos perdidos; revisar la titularidad de los señalados.' }[res]
      : res === 'victoria' && dxg > 0.5 ? 'Victoria merecida. Repetir once; rotar solo por carga física.'
      : res === 'victoria' ? 'Victoria por encima del juego. Lunes, vídeo de las ocasiones concedidas antes de que el marcador deje de perdonar.'
      : dxg > 0.5 ? 'El plan funcionó; faltó pegada. No tocar el sistema: sesión extra de finalización en transición.'
      : dxg < -0.5 ? 'Resultado justo y preocupante. Bloque más bajo y salida en transición; revisar la titularidad de los señalados.'
      : 'Partido de detalles. Mantener la estructura y ajustar los duelos individuales que se perdieron.';
    rep.append(el('p', { class: 'rm-verdict' }, v));
  }

  // Mapa
  const equipoSel = P().equipo === 'rival' ? (b ? b.equipo : '') : RM;
  const capa = P().capa || 'pases';
  segCapa((v) => v === capa);
  segEquipo((v) => v === (P().equipo || 'rm'));
  segTipos((v) => (P().tipos || []).includes(v));
  $('#p-tipos').hidden = capa !== 'pases';
  segTiros((v) => (P().tiros_tipo || []).includes(v));
  $('#p-tiros').hidden = capa !== 'tiros';
  $('#p-jugador').parentElement.hidden = capa === 'red';  // la red de pases es de todo el equipo
  $('#p-equipo').querySelector('[data-v=rival]').textContent = b ? nombre(b.equipo) : 'Rival';
  const js = rows('metricas_jugador').filter((r) => Number(r.match_id) === mid && r.equipo === equipoSel && N(r.minutos) > 0)
    .sort((x, y) => N(y.minutos) - N(x.minutos));
  const pj = $('#p-jugador');
  pj.replaceChildren(el('option', { value: '*' }, 'Todo el equipo'), ...js.map((r) => el('option', { value: r.jugador }, r.jugador)));
  // sin elegir: el que más pases dio (con los 400 pases del equipo el mapa no se lee)
  const masPases = [...js].filter((r) => r.posicion !== 'GK').sort((x, y) => N(y.pases) - N(x.pases))[0];
  const jugSel = P().jugador && (P().jugador === '*' || js.some((r) => r.jugador === P().jugador)) ? P().jugador : masPases?.jugador || '*';
  pj.value = jugSel;
  const color = equipoSel === RM ? C_RM() : C_RIV();
  const filt = (r) => Number(r.match_id) === mid && r.equipo === equipoSel && (jugSel === '*' || r.jugador === jugSel);
  const delEquipo = (r) => Number(r.match_id) === mid && r.equipo === equipoSel;
  if (ok('pases', 'tiros') && (capa !== 'red' || ok('red_nodos', 'red_enlaces')) && (!['acciones', 'zonas'].includes(capa) || ok('acciones'))) {
    const xy = (r) => ({ ...r, x: N(r.x), y: N(r.y) });
    const legend = drawPitch($('#pitch-partido'), {
      capa, color, tipos: P().tipos || [], tiposTiro: P().tiros_tipo || [],
      passes: rows('pases').filter(filt).map((r) => ({ ...xy(r), fin_x: N(r.fin_x), fin_y: N(r.fin_y) })),
      shots: rows('tiros').filter(filt).map((r) => ({ ...xy(r), xg: r.xg === '' ? NaN : N(r.xg) })),
      acciones: capa === 'acciones' || capa === 'zonas' ? rows('acciones').filter(filt).map(xy) : [],
      red: capa === 'red' ? { nodos: rows('red_nodos').filter(delEquipo).map(xy), enlaces: rows('red_enlaces').filter(delEquipo) } : null,
    });
    drawLegend($('#legend-partido'), legend);
  }

  // xG acumulado
  // sin xG (Champions, Copa) ese hueco muestra la jornada y la clasificación de la competición
  const conXgP = !a || a.xg !== '';
  $('#xg-timeline').hidden = !conXgP;
  if (p && ok('pases', 'tiros', 'incidencias')) drawMomentum($('#momline'), rows('pases').filter((r) => Number(r.match_id) === mid), rows('tiros').filter((r) => Number(r.match_id) === mid),
    rows('incidencias').filter((r) => Number(r.match_id) === mid), p, nombre);
  if (conXgP) drawXgLine($('#xgline'), rows('tiros').filter((r) => Number(r.match_id) === mid), p, b);
  if (p) pintarJornada($('#jornada'), p);

  // Alineaciones
  const alP = rows('alineaciones').filter((r) => Number(r.match_id) === mid).map((r) => ({ ...r, equipo: nombre(r.equipo) }));
  $('#al-partido').replaceChildren(alP.length ? alineacionesEl(alP, nombre(p.local)) : el('p', { class: 'rm-sub' }, 'Sin alineaciones para este partido.'));

  // Tabla jugadores
  const tab = rows('metricas_jugador').filter((r) => Number(r.match_id) === mid && r.equipo === equipoSel && N(r.minutos) > 0)
    .sort((x, y) => N(y.titular) - N(x.titular) || N(y.minutos) - N(x.minutos));
  const sel2 = tab.find((r) => r.jugador === jugSel);
  const formaDe = Object.fromEntries(formaJugadores(mid, Object.fromEntries(partidos.map((x) => [x.match_id, x.fecha])), rows('metricas_jugador'))
    .map((f) => [f.r.jugador, f.score]));
  const flecha = (v) => (v == null ? '—' : `${v >= 0.3 ? '▲' : v <= -0.3 ? '▼' : '='} ${(Math.round(v * 10) / 10 || 0).toFixed(1)}`);
  const vista = tab.map((r) => ({ ...r, forma: equipoSel === RM ? flecha(formaDe[r.jugador]) : '—', xg: r.xg === '' ? '—' : N(r.xg).toFixed(2), xa: r.xa === '' ? '—' : N(r.xa).toFixed(2), acierto_pase: r.acierto_pase === '' ? '—' : N(r.acierto_pase).toFixed(1),
    duelos: `${N(r.duelos_ganados)}/${N(r.duelos_ganados) + N(r.duelos_perdidos)}`, impacto: impacto(r).toFixed(2) }));
  fillTable($('#tabla-partido'), vista, ['jugador', 'minutos', 'goles', 'asistencias', 'xg', 'xa', 'pases_clave', 'acierto_pase', 'pases_progresivos', 'regates',
    'recuperaciones', 'duelos', 'perdidas_peligrosas', 'forma', 'impacto'], (r) => r.clave, sel2 && sel2.clave);

}

const ICONO = { gol: '⚽', penalti: '⚽', gol_pp: '⚽', amarilla: '🟨', segunda_amarilla: '🟨🟥', roja: '🟥', cambio: '⇄' };
function drawLinea(box, inc, p, nombre) {
  box.replaceChildren();
  const W = Math.max(300, box.clientWidth), H = 92, m = { l: 10, r: 10 }, yc = H / 2;
  const fin = Math.max(90, d3.max(inc, (r) => N(r.orden)) || 0);
  const x = d3.scaleLinear([0, fin], [m.l, W - m.r]);
  const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img')
    .attr('aria-label', 'Línea de tiempo: ' + inc.map((r) => `${r.minuto}' ${r.tipo.replace('_', ' ')} ${r.jugador}`).join(', '));
  svg.append('line').attr('x1', x(0)).attr('x2', x(fin)).attr('y1', yc).attr('y2', yc).attr('class', 'mc-eje');
  for (const t of [0, 45, 90]) {
    svg.append('line').attr('x1', x(t)).attr('x2', x(t)).attr('y1', yc - 4).attr('y2', yc + 4).attr('class', 'mc-eje');
    svg.append('text').attr('x', x(t)).attr('y', yc + 3.5).attr('dx', t === 0 ? 4 : t === 90 ? -4 : 0).attr('text-anchor', t === 0 ? 'start' : t === 90 ? 'end' : 'middle')
      .attr('class', 'mc-min').attr('dy', -8).text(`${t}'`);
  }
  const tip = tooltip(box);
  // apilado: si un icono cae a menos de 16 px de otro de su lado, sube (o baja) un piso; en orden de minuto
  const ultimoX = { true: [], false: [] };
  [...inc].sort((a, b) => N(a.orden) - N(b.orden)).forEach((r, i) => {
    const arriba = r.equipo === p.local, xx = x(N(r.orden)), pisos = ultimoX[arriba];
    let piso = pisos.findIndex((x0) => xx - x0 >= 16);
    if (piso < 0) piso = pisos.length;
    pisos[piso] = xx;
    const yy = arriba ? yc - 16 - 15 * piso : yc + 22 + 15 * piso;
    const txt = r.tipo === 'cambio' ? `Entra ${r.jugador} · sale ${r.sale}` : `${r.jugador}${r.tipo === 'penalti' ? ' (penalti)' : r.tipo === 'gol_pp' ? ' (en propia puerta)' : ''}`;
    const ico = svg.append('text').attr('x', xx).attr('y', yy).attr('text-anchor', 'middle').attr('class', `mc-ico ${r.tipo}`).text(ICONO[r.tipo] || '•')
      .on('mouseenter', (ev) => tip.show(ev, `${r.minuto}' · ${nombre(r.equipo)}`, [txt])).on('mouseleave', () => tip.hide());
    entrada('linea', ico.node(), [{ opacity: 0, transform: `translateY(${arriba ? 4 : -4}px)` }, { opacity: 1, transform: 'none' }], { duration: 250, delay: 300 + i * 40, easing: EASE_OUT });
  });
}

// Momentum: quién empujaba en cada tramo de 5 minutos (pases completados que llegan al último tercio + tiros × 3)
function drawMomentum(box, pases, tiros, inc, p, nombre) {
  box.querySelector('svg')?.remove();
  const W = Math.max(280, box.clientWidth), H = 200, m = { t: 14, r: 10, b: 24, l: 10 };
  const fin = Math.max(90, d3.max(pases, (r) => N(r.minuto)) || 0), tramos = d3.range(0, fin, 5);
  const val = (eq, t0) => pases.filter((r) => r.equipo === eq && r.tipo !== 'fallado' && N(r.fin_x) >= 80 && N(r.minuto) >= t0 && N(r.minuto) < t0 + 5).length
    + 3 * tiros.filter((r) => r.equipo === eq && N(r.minuto) >= t0 && N(r.minuto) < t0 + 5).length;
  const d = tramos.map((t0) => ({ t0, v: val(p.local, t0) - val(p.visitante, t0) }));
  const lim = Math.max(5, d3.max(d, (r) => Math.abs(r.v)));
  const x = d3.scaleBand(tramos, [m.l, W - m.r]).padding(0.12), y = d3.scaleLinear([-lim, lim], [H - m.b, m.t]);
  const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img')
    .attr('aria-label', `Momentum: ${d.filter((r) => r.v > 0).length} tramos de 5 minutos a favor de ${nombre(p.local)} y ${d.filter((r) => r.v < 0).length} de ${nombre(p.visitante)}`);
  const colLocal = p.local === RM ? C_RM() : C_RIV(), colVis = p.local === RM ? C_RIV() : C_RM();
  const tip = tooltip(box);
  svg.append('g').selectAll('rect').data(d).join('rect').attr('x', (r) => x(r.t0)).attr('width', x.bandwidth())
    .attr('y', (r) => y(Math.max(0, r.v))).attr('height', (r) => Math.abs(y(r.v) - y(0))).attr('rx', 2)
    .style('fill', (r) => (r.v >= 0 ? colLocal : colVis)).attr('opacity', 0.85)
    .on('mouseenter', (ev, r) => tip.show(ev, `Minutos ${r.t0}–${r.t0 + 5}`, [r.v === 0 ? 'Igualado' : `Domina ${nombre(r.v > 0 ? p.local : p.visitante)}`]))
    .on('mouseleave', () => tip.hide());
  svg.append('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y(0)).attr('y2', y(0)).style('stroke', 'var(--cds-chart-reference)');
  svg.append('line').attr('x1', x(45)).attr('x2', x(45)).attr('y1', m.t).attr('y2', H - m.b).style('stroke', 'var(--cds-chart-reference)').attr('stroke-dasharray', '3 3');
  for (const t of [0, 15, 30, 45, 60, 75, 90].filter((t) => x(t) != null))
    svg.append('text').attr('x', x(t)).attr('y', H - 6).style('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text(`${t}'`);
  // goles encima de su tramo
  for (const g of inc.filter((r) => ['gol', 'penalti', 'gol_pp'].includes(r.tipo))) {
    const t0 = Math.min(tramos.at(-1), Math.floor(N(g.minuto) / 5) * 5), arriba = g.equipo === p.local;
    svg.append('text').attr('x', x(t0) + x.bandwidth() / 2).attr('y', arriba ? m.t - 2 : H - m.b + 12).attr('text-anchor', 'middle').style('font-size', '11px').text('⚽')
      .append('title').text(`${g.minuto}' ${g.jugador}`);
  }
  drawLegend($('#mom-ley'), [['l', `Domina ${nombre(p.local)}`, colLocal], ['v', `Domina ${nombre(p.visitante)}`, colVis]]);
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

// "Real Sociedad" -> SOC, "Rayo Vallecano" -> RAY: tres letras del nombre sin prefijos de club
const abrev = (n) => (String(n).replace(/\b(Real|Club|CF|FC|CD|RCD|UD|SD|AS|SSC|AC|Deportivo|de|Atlético de)\b/gi, ' ').trim().split(/\s+/)[0] || String(n))
  .normalize('NFD').replace(/[\u0300-\u036f]/g, '').slice(0, 3).toUpperCase();

function renderTemporada() {
  const partidos = rows('partidos');
  const sel = $('#sel-temporada');
  if (partidos.length && (!sel.options.length || (sel.dataset.conHist !== '1' && ok('historico')))) {
    sel.replaceChildren();
    sel.dataset.conHist = ok('historico') ? '1' : '';
    for (const [temp, ps] of d3.groups([...partidos].sort((a, b) => b.fecha.localeCompare(a.fecha)), (p) => p.temporada)) {
      const og = el('optgroup', { label: temp });
      [TODAS, ...new Set(ps.map((p) => p.competicion))].forEach((c) => og.appendChild(el('option', { value: c + '|' + temp }, c)));
      sel.appendChild(og);
    }
  }
  const key = claveSel();
  sel.value = key;
  const [compSel, tempSel] = key.split('|');
  const enKey = (p) => p.temporada === tempSel && (compSel === TODAS || p.competicion === compSel);
  const ids = new Set(partidos.filter(enKey).map((p) => p.match_id));

  // Resumen
  const ps = partidos.filter(enKey);
  const gl = (p) => (p.local === RM ? [N(p.goles_local), N(p.goles_visitante)] : [N(p.goles_visitante), N(p.goles_local)]);
  const v = ps.filter((p) => gl(p)[0] > gl(p)[1]).length, e = ps.filter((p) => gl(p)[0] === gl(p)[1]).length;
  const meq = rows('metricas_equipo').filter((r) => r.equipo === RM && ids.has(r.match_id) && r.xg !== '');
  const kpis = [['Partidos', ps.length], ['Victorias · empates · derrotas', `${v} · ${e} · ${ps.length - v - e}`],
    ['Goles a favor – en contra', `${d3.sum(ps, (p) => gl(p)[0])} – ${d3.sum(ps, (p) => gl(p)[1])}`]];
  if (meq.length) kpis.push([`xG a favor – en contra${meq.length < ps.length ? ' (solo Liga)' : ''}`, `${d3.sum(meq, (r) => N(r.xg)).toFixed(1)} – ${d3.sum(meq, (r) => N(r.xg_contra)).toFixed(1)}`]);
  if (compSel === 'La Liga' && ps.length) kpis.push(['Puntos por partido', ((3 * v + e) / ps.length).toFixed(2)]);
  $('#t-kpis').replaceChildren(...kpis.map(([l, val]) => { const c = el('div', { class: 'rm-card rm-kpi' }); c.append(el('p', { class: 'rm-sub' }, l), el('p', { class: 'n' }, val)); return c; }));
  const byId = Object.fromEntries(partidos.map((p) => [p.match_id, p]));

  // Líderes de la plantilla
  const gk = new Set(rows('metricas_jugador').filter((r) => r.posicion === 'GK').map((r) => r.jugador));
  const jtSel = rows('jugadores_temporada').filter((r) => r.temporada === key && !gk.has(r.jugador));  // porteros fuera: sus saques inflan los pases
  $('#t-lideres').replaceChildren(...[['goles', 'Goles'], ['asistencias', 'Asistencias'], ['pases_progresivos', 'Pases progresivos'], ['recuperaciones', 'Recuperaciones']].map(([k, label]) => {
    const caja = el('div');
    const ol = el('ol');
    for (const r of [...jtSel].sort((a, b) => N(b[k]) - N(a[k])).slice(0, 3)) {
      const li = el('li', { tabindex: '0' });
      li.append(el('span', {}, r.jugador), el('b', {}, r[k]));
      const abrir = () => { dash.setParams({ jugador_t: r.jugador }); showTab('jugadores'); };
      li.addEventListener('click', abrir);
      li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') abrir(); });
      ol.append(li);
    }
    caja.append(el('h3', {}, label), ol);
    return caja;
  }));

  // Perfil del equipo: media por partido, Madrid frente a rivales
  const me = rows('metricas_equipo').filter((r) => ids.has(r.match_id));
  const media = (rs, k) => { const v = rs.filter((r) => r[k] !== '').map((r) => N(r[k])); return v.length ? d3.mean(v) : NaN; };
  $('#t-perfil tbody').replaceChildren(...[['tiros', 'Tiros', 1], ['tiros_puerta', 'Tiros a puerta', 1], ['xg', 'xG (solo Liga)', 2], ['posesion', 'Posesión (%)', 1],
    ['acierto_pase', '% acierto de pase', 1], ['pases_progresivos', 'Pases progresivos', 1], ['ppda', 'PPDA', 1],
    ['recuperaciones_campo_rival', 'Recuperaciones en campo rival', 1], ['duelos_ganados_pct', '% duelos ganados', 1], ['perdidas_peligrosas', 'Pérdidas peligrosas', 1]]
    .map(([k, label, dec]) => {
      const tr = el('tr');
      const f = (v) => (isNaN(v) ? '—' : v.toFixed(dec));
      tr.append(el('td', {}, label), el('td', {}, f(media(me.filter((r) => r.equipo === RM), k))), el('td', {}, f(media(me.filter((r) => r.equipo !== RM), k))));
      return tr;
    }));

  // Clasificaciones
  pintarClasificaciones($('#t-clasif'), compSel === TODAS ? [...new Set(ps.map((p) => p.competicion))] : [compSel]);

  // Mapa de tiros de la temporada: a favor o en contra, con su desglose por origen
  const lado = P().tiros_r || 'favor';
  segRT((v) => v === lado);
  const tt = rows('tiros').filter((r) => ids.has(r.match_id) && (lado === 'favor' ? r.equipo === RM : r.equipo !== RM))
    .map((r) => ({ ...r, x: N(r.x), y: N(r.y), xg: r.xg === '' ? NaN : N(r.xg) }));
  drawLegend($('#legend-resumen'), drawPitch($('#pitch-resumen'), { capa: 'tiros', color: lado === 'favor' ? C_RM() : C_RIV(), passes: [], shots: tt, tipos: [],
    tiposTiro: [...new Set(Object.values(TIPO_TIRO))] }));
  const gol = (v) => v.filter((r) => r.resultado === 'Goal').length;
  const xgS = (v) => (v.some((r) => !isNaN(r.xg)) ? d3.sum(v, (r) => r.xg || 0).toFixed(1) : '—');
  const pctG = (v) => (v.length ? `${Math.round((100 * gol(v)) / v.length)} %` : '—');
  $('#tt-kpis').replaceChildren(...[['Tiros', tt.length], ['Goles', gol(tt)], ['xG (Liga)', xgS(tt)], ['% de gol', pctG(tt)]]
    .map(([l, v]) => { const c = el('div', { class: 'rm-card rm-kpi' }); c.append(el('p', { class: 'rm-sub' }, l), el('p', { class: 'n' }, v)); return c; }));
  const origen = (r) => (r.subtipo === 'Penalty' ? 'Penalti' : PAT[r.patron_juego] || r.patron_juego);
  $('#tt-tabla tbody').replaceChildren(...d3.groups(tt, origen).sort((a, b) => b[1].length - a[1].length).map(([o, v]) => {
    const tr = el('tr');
    [o, v.length, gol(v), xgS(v), pctG(v)].forEach((x) => tr.append(el('td', {}, x)));
    return tr;
  }));

  // Últimos partidos
  const xgDe = Object.fromEntries(rows('metricas_equipo').filter((r) => r.equipo === RM).map((r) => [r.match_id, r]));
  const RES_COL = { V: 'var(--color-ok)', E: 'var(--cds-chart-muted)', D: C_BAD };
  $('#t-ultimos').replaceChildren(...[...ps].sort((a, b) => b.fecha.localeCompare(a.fecha)).slice(0, 8).map((p) => {
    const [f, c] = gl(p), r = f > c ? 'V' : f === c ? 'E' : 'D', m = xgDe[p.match_id];
    const hp = rows('historico').find((h) => h.fecha === p.fecha);
    const li = el('li', { tabindex: '0', title: 'Abrir el análisis del partido' });
    const res = el('span', { class: 'res' }, r); res.style.background = RES_COL[r];
    const quien = el('div', { class: 'quien' });
    quien.append(escudo(hp ? hp.rival : p.rival), el('span', {}, `${p.local === RM ? 'vs' : 'en'} ${hp ? hp.rival : p.rival}`));
    const izq = el('div'); izq.append(quien, el('span', { class: 'det' }, `${fechaEs(p.fecha)} · ${p.competicion}${m && m.xg !== '' ? ` · xG ${m.xg}–${m.xg_contra}` : ''}`));
    li.append(res, izq, el('span', { class: 'marc' }, `${f}–${c}`));
    const abrir = () => { dash.setParams({ partido: Number(p.match_id), jugador: null }); showTab('partido'); };
    li.addEventListener('click', abrir);
    li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') abrir(); });
    return li;
  }));

  // xG por partido
  const box = $('#xgseason');
  box.querySelector('svg')?.remove();
  box.querySelector('.sin-xg')?.remove();
  // en "todas", el gráfico solo puede llevar los partidos con xG (Liga)
  const ms = rows('metricas_equipo').filter((r) => r.equipo === RM && ids.has(r.match_id) && (compSel !== TODAS || r.xg !== ''))
    .map((r) => ({ ...r, p: byId[r.match_id] })).sort((a, b) => a.p.fecha.localeCompare(b.p.fecha));
  if (ms.length && ms.every((d) => d.xg === '')) box.prepend(el('p', { class: 'sin-xg' }, 'Sin xG en esta competición: Understat solo cubre la Liga.'));
  else if (ms.length) {
    // alto: el de la tarjeta (se estira hasta la de últimos partidos), mínimo 300
    const W = Math.max(280, box.clientWidth), H = Math.max(300, box.clientHeight), m = { t: 14, r: 96, b: 26, l: 34 };
    const x = d3.scalePoint(ms.map((d) => d.match_id), [m.l, W - m.r]).padding(0.3);
    const y = d3.scaleLinear([0, d3.max(ms, (d) => Math.max(N(d.xg), N(d.xg_contra)))], [H - m.b, m.t]).nice();
    const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    svg.append('g').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(W - m.l - m.r)))
      .attr('font-size', null).attr('font-family', null).call((g) => g.select('.domain').remove())
      .call((g) => g.selectAll('line').style('stroke', 'var(--cds-chart-grid)')).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'));
    const step = Math.ceil(ms.length / Math.max(2, Math.floor((W - m.l - m.r) / 72)));  // ~72 px por etiqueta ("SEV 18/10")
    svg.append('g').attr('transform', `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).tickValues(ms.filter((_, i) => i % step === 0).map((d) => d.match_id)).tickFormat((id) => `${abrev(byId[id].rival)} ${byId[id].fecha.slice(8).replace(/^0/, '')}/${Number(byId[id].fecha.slice(5, 7))}`))
      .attr('font-size', null).attr('font-family', null).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'))
      .call((g) => g.selectAll('line,path').style('stroke', 'var(--cds-chart-axis)'));
    const lines = [['xg', 'xG a favor', C_RM()], ['xg_contra', 'xG en contra', C_BAD]];
    for (const [k, , c] of lines) {
      const linea = svg.append('path').datum(ms).attr('fill', 'none').style('stroke', c).attr('stroke-width', 2).attr('stroke-linejoin', 'round').attr('stroke-linecap', 'round')
        .attr('d', d3.line().x((d) => x(d.match_id)).y((d) => y(N(d[k])))).node();
      // la primera vez, la línea se dibuja de izquierda a derecha
      const L = linea.getTotalLength();
      entrada('xgseason', linea, [{ strokeDasharray: `${L} ${L}`, strokeDashoffset: L }, { strokeDasharray: `${L} ${L}`, strokeDashoffset: 0 }], { duration: 700, delay: 150, easing: EASE_MOVER });
    }
    const resCol = (d) => (N(d.goles) > N(d.p.goles_local) + N(d.p.goles_visitante) - N(d.goles) ? 'var(--color-ok)'
      : N(d.goles) * 2 === N(d.p.goles_local) + N(d.p.goles_visitante) ? 'var(--cds-chart-muted)' : C_BAD);
    const tip = tooltip(box);
    svg.append('g').selectAll('circle').data(ms).join('circle').attr('cx', (d) => x(d.match_id)).attr('cy', (d) => y(N(d.xg))).attr('r', 4)
      .style('fill', resCol).style('stroke', 'var(--color-panel)').attr('stroke-width', 1.5)
      .on('mouseenter', (ev, d) => tip.show(ev, `${fechaEs(d.p.fecha)} · ${d.p.local} ${d.p.goles_local}–${d.p.goles_visitante} ${d.p.visitante}`,
        [`xG a favor ${d.xg}`, `xG en contra ${d.xg_contra}`, 'Pulsa para abrir el post-partido']))
      .on('mouseleave', () => tip.hide())
      .on('click', (ev, d) => { dash.setParams({ partido: Number(d.match_id), jugador: null }); showTab('partido'); })
      .each(function (d, i) { entrada('xgseason', this, [{ opacity: 0 }, { opacity: 1 }], { duration: 200, delay: 150 + (700 * i) / ms.length, easing: EASE_OUT }); });
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
  const d2 = (x) => (x === '' ? '—' : N(x).toFixed(2));
  fillTable($('#tabla-temporada'), jt.map((r) => ({ ...r, xg: d2(r.xg), xa: d2(r.xa), duelos_pct: N(r.duelos_pct).toFixed(1) })), ['jugador', 'pj', 'minutos', 'goles', 'xg', 'asistencias', 'xa', 'pases_progresivos', 'recuperaciones', 'duelos_pct', 'perdidas_peligrosas'],
    (r) => r.clave, selT && selT.clave);

  // Mapa de temporada
  const tj = $('#t-jugador');
  const byMin = [...jt].sort((a, b) => b.minutos - a.minutos);
  tj.replaceChildren(...byMin.map((r) => el('option', { value: r.jugador }, r.jugador)));
  const jugador = jugadorSel(jt);
  tj.value = jugador || '';
  segCapaT((v) => v === (P().capa_t || 'zonas'));
  segTiposT((v) => (P().tipos || []).includes(v));
  $('#t-tipos').hidden = (P().capa_t || 'zonas') !== 'pases';
  segTirosT((v) => (P().tiros_tipo || []).includes(v));
  $('#t-tiros').hidden = P().capa_t !== 'tiros';
  if (ok('pases', 'tiros') && jugador) {
    const filt = (r) => ids.has(r.match_id) && r.equipo === RM && r.jugador === jugador;
    const legend = drawPitch($('#pitch-temporada'), {
      capa: P().capa_t || 'zonas', color: C_RM(), tipos: P().tipos || [], tiposTiro: P().tiros_tipo || [],
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
  $('#hist-rango').textContent = ts.length ? `${ts[0].temporada} – ${ts.at(-1).temporada}` : '';
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
    tr.append(el('td', {}, fechaEs(r.fecha)), el('td', {}, r.competicion), local, el('td', { class: 'sep' }, '–'), visitante, el('td', { class: 'estadio' }, r.estadio || '—'),
      el('td', {}, `${r.goles_local}–${r.goles_visitante}${r.penaltis ? ` (${r.penaltis.replace('-', '–')} pen.)` : ''}${conAl.has(r.partido_id) ? ' 👥' : ''}`));
    tr.lastChild.style.color = r.resultado === 'V' ? 'var(--color-ok)' : r.resultado === 'D' ? C_BAD : '';
    return tr;
  }));
  $('#hist-nota').textContent = ps.length > MAX ? `Se muestran los ${MAX} más recientes de ${ps.length.toLocaleString('es-ES')}: usa el buscador para el resto. 👥 = con alineaciones.` : '👥 = con alineaciones.';

  // Ficha del partido elegido
  const p = todos.find((r) => r.partido_id === partidoHist);
  $('#alineacion').hidden = !p;
  if (p) pintarFicha($('#alineacion'), p, 'h2');
}

// Ficha de un partido (resultado, ronda, goleadores y alineaciones): se usa en Histórico y en Títulos
function pintarFicha(cont, p, tagTitulo = 'h3') {
  const al = rows('historico_alineaciones').filter((r) => r.partido_id === p.partido_id);
  const titulo = marcadorFicha({ fecha: p.fecha, estadio: p.estadio, meta: `${p.competicion}${p.ronda ? ` · ${p.ronda}` : ''}`, local: p.local, visitante: p.visitante,
    gl: p.goles_local, gv: p.goles_visitante, penaltis: p.penaltis, golesL: golesWiki(p.goleadores_local), golesV: golesWiki(p.goleadores_visitante) });
  const faltan = [!p.goleadores_local && !p.goleadores_visitante && N(p.goles_local) + N(p.goles_visitante) ? 'goleadores' : '', al.length ? '' : 'alineaciones'].filter(Boolean);
  const gol = el('p', { class: 'rm-sub ficha-falta' }, faltan.length ? `Sin ${faltan.join(' ni ')} en las fuentes.` : '');
  cont.replaceChildren(titulo, gol, alineacionesEl(al, p.local));
}

// ---------- Jornadas y clasificaciones (calendario completo de WhoScored) ----------
// ronda de cada partido = cuántos partidos lleva ya su equipo en esa fase (vale para la Liga y para la fase de liga de Champions)
function conRondas(fase) {
  const n = {};
  return [...fase].sort((a, b) => a.fecha.localeCompare(b.fecha)).map((r) => {
    n[r.local] = (n[r.local] || 0) + 1; n[r.visitante] = (n[r.visitante] || 0) + 1;
    return { ...r, ronda: Math.max(n[r.local], n[r.visitante]) };
  });
}
// zonas de la tabla: [hasta la posición, clase, texto]
const ZONAS = { 'La Liga': [[4, 'zona-a', 'Copa de Europa'], [6, 'zona-b', 'Copa de la UEFA'], [7, 'zona-c', 'Conference League'], [17, '', ''], [20, 'zona-d', 'Descenso']],
  'Copa de Europa': [[8, 'zona-a', 'Octavos directos'], [24, 'zona-b', 'Eliminatoria previa'], [99, '', '']] };
function tablaClasif(partidos, comp) {
  const t = {};
  for (const r of partidos)
    for (const [eq, gf, gc] of [[r.local, N(r.goles_local), N(r.goles_visitante)], [r.visitante, N(r.goles_visitante), N(r.goles_local)]]) {
      const x = (t[eq] ??= { eq, pj: 0, g: 0, e: 0, p: 0, gf: 0, gc: 0 });
      x.pj += 1; x.gf += gf; x.gc += gc; x[gf > gc ? 'g' : gf === gc ? 'e' : 'p'] += 1;
    }
  // desempate simplificado: diferencia de goles y goles a favor
  const tabla = Object.values(t).map((x) => ({ ...x, pts: 3 * x.g + x.e, dg: x.gf - x.gc })).sort((a, b) => b.pts - a.pts || b.dg - a.dg || b.gf - a.gf);
  const zonas = ZONAS[comp] || [];
  const tb = el('tbody');
  tabla.forEach((x, i) => {
    const z = zonas.find(([hasta]) => i < hasta);
    const tr = el('tr', { class: `${x.eq === RM ? 'rm-fila ' : ''}${z ? z[1] : ''}` });
    [i + 1, x.eq, x.pj, x.g, x.e, x.p, `${x.gf}:${x.gc}`, x.dg > 0 ? `+${x.dg}` : x.dg, x.pts].forEach((v) => tr.append(el('td', {}, v)));
    tb.append(tr);
  });
  const tab = el('table', { class: 'tabla-clasif' });
  const th = el('tr');
  ['#', 'Equipo', 'PJ', 'G', 'E', 'P', 'Goles', 'DG', 'Pts'].forEach((h) => th.append(el('th', {}, h)));
  const thead = el('thead'); thead.append(th);
  tab.append(thead, tb);
  const wrap = el('div', { class: 'rm-tablewrap' }); wrap.append(tab);
  const ley = el('div', { class: 'rm-legend' });
  for (const [, cl, txt] of zonas.filter(([, cl]) => cl)) { const sp = el('span', {}); sp.append(el('i', { class: `zona ${cl}` }), txt); ley.append(sp); }
  return [wrap, ley];
}
// fase de la competición en que está el partido del Madrid (la que tenga clasificación si es fase de liga)
const faseDe = (cs, mio) => cs.filter((r) => r.fase === mio.fase);
const esLiga = (fase) => new Set(fase.flatMap((r) => [r.local, r.visitante])).size >= 16;

function pintarJornada(cont, p) {
  const cs = rows('competicion').filter((r) => r.competicion === p.competicion);
  const mio = cs.find((r) => r.fecha === p.fecha && (r.local === RM || r.visitante === RM));
  if (!mio) { cont.replaceChildren(el('p', { class: 'rm-sub' }, 'Sin resultados de la competición para este partido todavía.')); return; }
  const fase = conRondas(faseDe(cs, mio));
  const n = fase.find((r) => r.fecha === mio.fecha && r.local === mio.local).ronda;
  const res = el('ul', { class: 'jor-res' });
  for (const r of fase.filter((r) => r.ronda === n)) {
    const li = el('li', { class: r.local === RM || r.visitante === RM ? 'rm-fila' : '' });
    li.append(el('span', { class: 'l' }, r.local), el('b', {}, `${r.goles_local}–${r.goles_visitante}`), el('span', {}, r.visitante));
    res.append(li);
  }
  const partes = [el('h3', {}, `Jornada ${n}: resultados`), res];
  if (esLiga(fase)) partes.push(el('h3', {}, `Clasificación tras la jornada ${n}`), ...tablaClasif(fase.filter((r) => r.ronda <= n), p.competicion));
  cont.replaceChildren(...partes);
}

// Clasificaciones actuales de la selección del Resumen (una por competición con fase de liga)
function pintarClasificaciones(cont, comps) {
  const cajas = [];
  for (const comp of comps) {
    const cs = rows('competicion').filter((r) => r.competicion === comp);
    const mio = [...cs].reverse().find((r) => r.local === RM || r.visitante === RM);
    if (!mio) continue;
    const fase = conRondas(faseDe(cs, mio));
    if (!esLiga(fase)) continue;
    const c = el('div', { class: 'rm-card' });
    c.append(el('h2', {}, `Clasificación · ${comp === 'La Liga' ? 'LaLiga' : comp}`), el('p', { class: 'rm-sub' }, `Tras la jornada ${d3.max(fase, (r) => r.ronda)}`), ...tablaClasif(fase, comp));
    cajas.push(c);
  }
  cont.replaceChildren(...cajas);
  cont.hidden = !cajas.length;
}

// Alineaciones de los dos equipos: dorsal, jugador y posición en columnas; campito si hay coordenadas
function alineacionesEl(al, local) {
  const porDorsal = (a, b) => (a.dorsal === '' ? 999 : N(a.dorsal)) - (b.dorsal === '' ? 999 : N(b.dorsal));
  // primero el local, luego el visitante
  const equipos = d3.groups(al, (r) => r.equipo).sort(([a], [b]) => (b === local) - (a === local));
  const grid = el('div', { class: 'al-equipos' });
  grid.append(...equipos.map(([equipo, js]) => {
    const c = el('div', { class: 'rm-lineup' });
    c.append(conEscudo(equipo, 'h3'));
    const cuerpo = el('div', { class: 'al-cuerpo' });
    const lista = el('div', { class: 'al-lista' });
    const tit = js.filter((j) => String(j.titular) === '1').sort(porDorsal);
    for (const [nombre, grupo] of [['Titulares', tit], ['Suplentes', js.filter((j) => String(j.titular) !== '1').sort(porDorsal)]]) {
      if (!grupo.length) continue;
      const cab = el('div', { class: 'al-fila al-cab' });
      cab.append(el('span'), el('span', {}, nombre), el('span', {}, 'Posición'));
      lista.append(cab);
      for (const j of grupo) {
        const fila = el('div', { class: 'al-fila' });
        fila.append(el('span', { class: 'al-dorsal' }, j.dorsal || ''), el('span', { class: 'al-nom', title: j.jugador }, j.jugador),
          el('span', { class: 'al-pos' }, POS_ES[j.posicion] || j.posicion || '—'));
        lista.append(fila);
      }
    }
    cuerpo.append(lista);
    if (tit.some((j) => j.px != null && j.px !== '')) cuerpo.append(campito(tit, equipo === RM ? C_RM() : C_RIV()));
    c.append(cuerpo);
    return c;
  }));
  return grid;
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
    ['Copas de Europa', n((t) => t.comp_hist === 'Copa de Europa')], ['Copas del Rey', n((t) => t.comp_hist === 'Copa del Rey')],
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
    $('#tit-resumen').textContent = yo ? `${yo.pts} puntos · ${yo.g}V ${yo.e}E ${yo.p}D · goles ${yo.gf}–${yo.gc}` +
      (otro ? ` · ${t.tipo === 'Campeón' ? 'segundo' : 'campeón'}: ${otro.equipo} (${otro.pts})` : '') : '';
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
  $('#tit-resumen').textContent = `${ps.length} ${ps.length === 1 ? 'partido' : 'partidos'} · ${b.v}V ${b.e}E ${b.d}D · goles ${b.gf}–${b.gc}`;
  const tb = el('table'); const th = el('thead'); const hr = el('tr');
  for (const [h, a] of [['Fecha'], ['Ronda'], ['Partido', 3], ['Resultado'], ['Estadio']]) hr.append(el('th', a ? { colspan: a, class: 'partido' } : {}, h));
  th.append(hr); const bd = el('tbody');
  for (const r of ps) {
    const tr = el('tr', { 'data-key': r.partido_id });
    const loc = el('td', { class: 'loc' }), vis = el('td', { class: 'vis' });
    loc.append(conEscudo(r.local, 'span', true)); vis.append(conEscudo(r.visitante));
    tr.append(el('td', {}, fechaEs(r.fecha)), el('td', {}, r.ronda || '—'), loc, el('td', { class: 'sep' }, '–'), vis,
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
const VER_COL = { 'Por debajo': C_BAD, 'Por encima': 'var(--color-ok)', 'En línea': 'var(--cds-chart-muted)', 'Pocos minutos': 'var(--color-fg-muted)' };
let sortRen = { k: 'veredicto', asc: true };
$('#tabla-rendimiento').addEventListener('click', (ev) => {
  const th = ev.target.closest('th');
  if (th) { sortRen = { k: th.dataset.field, asc: sortRen.k === th.dataset.field ? !sortRen.asc : ['jugador', 'puesto', 'veredicto', 'motivo'].includes(th.dataset.field) }; render(); return; }
  const tr = ev.target.closest('tr[data-key]');
  if (tr) { dash.setParams({ jugador_t: tr.dataset.key }); $('#ficha-jugador').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
});
// Mismo criterio que procesar.py: desvío claro = al menos 1 de diferencia y un 30 % de lo esperado
const desvio = (real, esp) => (Math.abs(real - esp) >= 1 && Math.abs(real - esp) >= 0.3 * Math.max(esp, 1) ? Math.sign(real - esp) : 0);
const DESVIO_COL = { '-1': C_BAD, 0: 'var(--cds-chart-muted)', 1: 'var(--color-ok)' };
// Puntos de un jugador: real frente a esperado, con la diagonal "real = esperado"
function scatterRen(box, rs, xk, yk, xLabel, yLabel, unidad) {
  box.querySelector('svg')?.remove();
  const pts = rs.filter((d) => d[xk] > 0 || d[yk] > 0);
  if (!pts.length) return;
  const W = Math.max(280, box.clientWidth), H = 310, m = { t: 14, r: 16, b: 46, l: 40 };
  const mx = Math.ceil(Math.max(d3.max(pts, (d) => d[xk]), d3.max(pts, (d) => d[yk])) + 0.5);
  const x = d3.scaleLinear([0, mx], [m.l, W - m.r]), y = d3.scaleLinear([0, mx], [H - m.b, m.t]);
  const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
  svg.append('g').attr('transform', `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(5))
    .attr('font-size', null).attr('font-family', null).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'))
    .call((g) => g.selectAll('line,path').style('stroke', 'var(--cds-chart-axis)'));
  svg.append('g').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)))
    .attr('font-size', null).attr('font-family', null).call((g) => g.select('.domain').remove())
    .call((g) => g.selectAll('line').style('stroke', 'var(--cds-chart-grid)')).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'));
  svg.append('line').attr('x1', x(0)).attr('y1', y(0)).attr('x2', x(mx)).attr('y2', y(mx)).style('stroke', 'var(--cds-chart-reference)').attr('stroke-dasharray', '4 4');
  svg.append('text').attr('x', x(mx) - 4).attr('y', y(mx) + 14).attr('text-anchor', 'end').style('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text(`${yLabel.toLowerCase()} = ${unidad}`);
  svg.append('text').attr('x', W - m.r).attr('y', H - 4).attr('text-anchor', 'end').style('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text(xLabel);
  svg.append('text').attr('x', m.l).attr('y', m.t - 2).style('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text(yLabel);
  const tip = tooltip(box);
  svg.append('g').selectAll('circle').data(pts).join('circle').attr('cx', (d) => x(d[xk])).attr('cy', (d) => y(d[yk])).attr('r', 6)
    .style('fill', (d) => DESVIO_COL[desvio(d[yk], d[xk])]).style('stroke', 'var(--color-panel)').attr('stroke-width', 1.5)
    .on('mouseenter', (ev, d) => tip.show(ev, d.jugador, [`${d[yk]} ${yLabel.toLowerCase()} con ${d[xk].toFixed(2)} ${unidad}`]))
    .on('mouseleave', () => tip.hide());
  // etiquetas sin pisarse: se descarta la que cae encima de otra ya puesta (queda el tooltip)
  // etiquetas sin pisarse: se prueba a la derecha, izquierda, arriba y abajo del punto; si no cabe, queda el tooltip
  const puestas = [];  // cajas [x0, y0, x1, y1] ya ocupadas
  const choca = (b) => puestas.some((q) => b[0] < q[2] && q[0] < b[2] && b[1] < q[3] && q[1] < b[3]);
  for (const d of pts.filter((d) => desvio(d[yk], d[xk]) || d[xk] >= 2).sort((a, b) => Math.abs(desvio(b[yk], b[xk])) - Math.abs(desvio(a[yk], a[xk])) || b[xk] - a[xk])) {
    const p = d.jugador.split(' '), txt = p.at(-1) === 'Júnior' ? p[0] : p.at(-1), w = txt.length * 7.5, cx = x(d[xk]), cy = y(d[yk]);
    const sitio = [[cx + 9, cy + 4, 'start'], [cx - 9, cy + 4, 'end'], [cx, cy - 10, 'middle'], [cx, cy + 18, 'middle']]
      .map(([px, py, a]) => [px, py, a, a === 'start' ? [px, py - 10, px + w, py + 2] : a === 'end' ? [px - w, py - 10, px, py + 2] : [px - w / 2, py - 10, px + w / 2, py + 2]])
      .find(([, , , b]) => !choca(b) && b[0] >= m.l && b[2] <= W - 4);
    if (!sitio) continue;
    puestas.push(sitio[3]);
    svg.append('text').attr('x', sitio[0]).attr('y', sitio[1]).attr('text-anchor', sitio[2]).style('fill', 'var(--color-fg)').style('font-size', 'var(--cds-font-size-caption)').text(txt);
  }
}

// Tendencia: media de la forma (como en el post-partido) en sus 3 últimos partidos frente a los anteriores
function tendencias() {
  const partidos = rows('partidos'), jug = rows('metricas_jugador');
  const fecha = Object.fromEntries(partidos.map((p) => [p.match_id, p.fecha]));
  const por = {};
  for (const p of [...partidos].sort((a, b) => a.fecha.localeCompare(b.fecha)))
    for (const f of formaJugadores(Number(p.match_id), fecha, jug)) (por[f.r.jugador] ??= []).push(f.score);
  return Object.fromEntries(Object.entries(por).map(([j, v]) => {
    const m = Math.round(d3.mean(v.slice(-3)) * 10) / 10 || 0;  // || 0: sin "-0.0"
    return [j, v.length < 3 ? '' : `${m >= 0.2 ? '▲' : m <= -0.2 ? '▼' : '='} ${m.toFixed(1)}`];
  }));
}

// ---------- Ficha del jugador: radar frente a su puesto (con comparación) y forma partido a partido ----------
const RADAR = [['r_xg90', 'xG'], ['r_xa90', 'xA'], ['r_key_passes90', 'Pases clave'], ['r_xg_chain90', 'xGChain'], ['r_xg_buildup90', 'xGBuildup'],
  ['r_tklw90', 'Entradas'], ['r_int90', 'Intercep.']];
// competición|temporada elegida; si ya no existe (p. ej. un enlace con el nombre antiguo "Champions League"), todas las de la última temporada
const claveSel = () => {
  const ps = rows('partidos'), k = P().temporada;
  const vale = k && ps.some((p) => k === `${TODAS}|${p.temporada}` || k === `${p.competicion}|${p.temporada}`);
  return vale ? k : ps.length ? TODAS + '|' + ps.at(-1).temporada : '';
};
// jugador elegido; si no hay, el de campo con más minutos (los saques del portero no dicen nada en un mapa)
function jugadorSel(jt) {
  if (jt.some((r) => r.jugador === P().jugador_t)) return P().jugador_t;
  const gk = new Set(rows('metricas_jugador').filter((r) => r.posicion === 'GK').map((r) => r.jugador));
  return ([...jt].sort((a, b) => b.minutos - a.minutos).find((r) => !gk.has(r.jugador)) || jt[0])?.jugador;
}

function drawRadar(box, series) {
  box.querySelector('svg')?.remove();
  if (!series.length) return;
  const W = Math.min(460, Math.max(300, box.clientWidth)), H = W * 0.82, cx = W / 2, cy = H / 2 + 4, R = W * 0.24;  // margen para las etiquetas
  const ang = (i) => -Math.PI / 2 + (2 * Math.PI * i) / RADAR.length;
  const pt = (i, v) => [cx + Math.cos(ang(i)) * (R * v) / 100, cy + Math.sin(ang(i)) * (R * v) / 100];
  const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img')
    .attr('aria-label', series.map((s) => `${s.nombre}: ${RADAR.map(([k, l]) => `${l} percentil ${s.r[k] === '' ? 'sin dato' : s.r[k]}`).join(', ')}`).join('. '));
  for (const v of [25, 50, 75, 100])
    svg.append('polygon').attr('points', RADAR.map((_, i) => pt(i, v).join(',')).join(' ')).attr('fill', 'none').style('stroke', 'var(--cds-chart-grid)');
  RADAR.forEach(([, l], i) => {
    const [x, y] = pt(i, 100), [lx, ly] = pt(i, 122);
    svg.append('line').attr('x1', cx).attr('y1', cy).attr('x2', x).attr('y2', y).style('stroke', 'var(--cds-chart-grid)');
    svg.append('text').attr('x', lx).attr('y', ly + 4).attr('text-anchor', Math.abs(lx - cx) < 8 ? 'middle' : lx > cx ? 'start' : 'end')
      .style('fill', 'var(--color-fg-muted)').style('font-size', 'var(--cds-font-size-caption)').text(l);
  });
  svg.append('text').attr('x', cx + 3).attr('y', cy - R / 2 + 3).style('fill', 'var(--cds-chart-reference)').style('font-size', '10px').text('50');
  const tip = tooltip(box);
  for (const s of series) {
    const pts = RADAR.map(([k], i) => pt(i, s.r[k] === '' ? 0 : N(s.r[k])));
    svg.append('polygon').attr('points', pts.map((p) => p.join(',')).join(' ')).style('fill', s.color).attr('fill-opacity', 0.18)
      .style('stroke', s.color).attr('stroke-width', 2).attr('stroke-dasharray', s.discontinua ? '5 4' : null);
    svg.append('g').selectAll('circle').data(RADAR.map(([k, l], i) => ({ k, l, p: pts[i], v: s.r[k] }))).join('circle')
      .attr('cx', (d) => d.p[0]).attr('cy', (d) => d.p[1]).attr('r', 3.5).style('fill', s.color)
      .on('mouseenter', (ev, d) => tip.show(ev, s.nombre, [`${d.l}: percentil ${d.v === '' ? '—' : d.v}`]))
      .on('mouseleave', () => tip.hide());
  }
}

function drawForma(box, pts) {
  box.querySelector('svg')?.remove();
  box.querySelector('.sin-xg')?.remove();
  if (pts.length < 2) { box.prepend(el('p', { class: 'sin-xg' }, 'Hacen falta al menos 3 partidos previos con minutos para medir su forma.')); return; }
  const W = Math.max(280, box.clientWidth), H = 220, m = { t: 12, r: 10, b: 30, l: 34 };
  const x = d3.scaleBand(pts.map((d) => d.id), [m.l, W - m.r]).padding(0.25);
  const lim = Math.max(1, d3.max(pts, (d) => Math.abs(d.score)));
  const y = d3.scaleLinear([-lim, lim], [H - m.b, m.t]).nice();
  const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img')
    .attr('aria-label', `Forma en ${pts.length} partidos: ${pts.filter((d) => d.score >= 0.3).length} por encima de lo suyo y ${pts.filter((d) => d.score <= -0.3).length} por debajo`);
  svg.append('g').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(W - m.l - m.r)))
    .attr('font-size', null).attr('font-family', null).call((g) => g.select('.domain').remove())
    .call((g) => g.selectAll('line').style('stroke', 'var(--cds-chart-grid)')).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)'));
  const paso = Math.ceil(pts.length / Math.max(2, Math.floor((W - m.l - m.r) / 44)));
  svg.append('g').attr('transform', `translate(0,${H - m.b})`).call(d3.axisBottom(x).tickValues(pts.filter((_, i) => i % paso === 0).map((d) => d.id)).tickFormat((id) => pts.find((d) => d.id === id).etq).tickSize(0))
    .attr('font-size', null).attr('font-family', null).call((g) => g.select('.domain').remove()).call((g) => g.selectAll('text').style('fill', 'var(--color-fg-muted)').attr('dy', '1em'));
  svg.append('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y(0)).attr('y2', y(0)).style('stroke', 'var(--cds-chart-reference)');
  const tip = tooltip(box);
  svg.append('g').selectAll('rect').data(pts).join('rect').attr('x', (d) => x(d.id)).attr('width', x.bandwidth())
    .attr('y', (d) => y(Math.max(0, d.score))).attr('height', (d) => Math.abs(y(d.score) - y(0)))
    .style('fill', (d) => (d.score >= 0.3 ? 'var(--color-ok)' : d.score <= -0.3 ? C_BAD : 'var(--cds-chart-muted)')).attr('rx', 2)
    .on('mouseenter', (ev, d) => tip.show(ev, d.titulo, [`Forma ${d.score > 0 ? '+' : ''}${d.score.toFixed(1)} · ${d.min}'`, d.detalle]))
    .on('mouseleave', () => tip.hide());
}

function renderFicha() {
  const key = claveSel();
  const jt = rows('jugadores_temporada').filter((r) => r.temporada === key);
  if (!jt.length) return;
  const nombre = jugadorSel(jt);
  const porMin = [...jt].sort((a, b) => b.minutos - a.minutos);
  $('#f-jugador').replaceChildren(...porMin.map((r) => el('option', { value: r.jugador }, r.jugador)));
  $('#f-jugador').value = nombre;
  const comp = porMin.some((r) => r.jugador === P().comparar) && P().comparar !== nombre ? P().comparar : '';
  $('#f-comparar').replaceChildren(el('option', { value: '' }, 'Nadie'), ...porMin.filter((r) => r.jugador !== nombre).map((r) => el('option', { value: r.jugador }, r.jugador)));
  $('#f-comparar').value = comp;
  const yo = jt.find((r) => r.jugador === nombre);
  const ren = rows('rendimiento').find((r) => r.jugador === nombre);
  const ten = tendencias()[nombre];
  $('#fj-nombre').textContent = nombre + (ren ? ` · ${ren.puesto}` : '');
  $('#fj-kpis').replaceChildren(...[['Partidos', yo.pj], ['Minutos', yo.minutos], ['Goles', yo.goles], ['Asistencias', yo.asistencias],
    ['Veredicto', ren ? ren.veredicto : '—'], ['Tendencia', ten || '—']]
    .map(([l, v]) => { const c = el('div', { class: 'rm-card rm-kpi' }); c.append(el('p', { class: 'rm-sub' }, l), el('p', { class: 'n' }, v)); return c; }));
  $('#fj-motivo').textContent = ren ? ren.motivo + '.' : '';
  // radar (Liga): necesita sus percentiles; el portero no tiene
  const series = [];
  if (ren && RADAR.some(([k]) => ren[k] !== '')) series.push({ nombre, r: ren, color: C_RM() });
  const ren2 = comp && rows('rendimiento').find((r) => r.jugador === comp);
  if (ren2 && RADAR.some(([k]) => ren2[k] !== '')) series.push({ nombre: comp, r: ren2, color: C_RIV(), discontinua: true });
  const caja = $('#fj-radar');
  caja.querySelector('.sin-xg')?.remove();
  drawRadar(caja, series);
  if (!series.length) caja.prepend(el('p', { class: 'sin-xg' }, 'Sin percentiles: hacen falta 90 minutos en la Liga y no se calculan para porteros.'));
  drawLegend($('#fj-ley'), series.map((s) => ['', s.nombre, s.color]));
  // forma en cada partido de la selección
  const partidos = rows('partidos'), fecha = Object.fromEntries(partidos.map((p) => [p.match_id, p.fecha]));
  const [compSel, tempSel] = key.split('|');
  const pts = [];
  for (const p of [...partidos].filter((p) => p.temporada === tempSel && (compSel === TODAS || p.competicion === compSel)).sort((a, b) => a.fecha.localeCompare(b.fecha))) {
    const f = formaJugadores(Number(p.match_id), fecha, rows('metricas_jugador')).find((x) => x.r.jugador === nombre);
    if (!f) continue;
    const top = [...f.ms].sort((a, b) => Math.abs(b.z) - Math.abs(a.z))[0];
    pts.push({ id: p.match_id, score: f.score, min: f.r.minutos, etq: abrev(p.rival), titulo: `${fechaEs(p.fecha)} · ${p.local} ${p.goles_local}–${p.goles_visitante} ${p.visitante}`,
      detalle: `${top.valor} ${top.label[top.valor === 1 ? 0 : 1]} (suele ${top.esperado.toFixed(1)})` });
  }
  drawForma($('#fj-forma'), pts);
}

function renderRendimiento() {
  const ten = ok('partidos', 'metricas_jugador') ? tendencias() : {};
  // el del portero sale de un xG previo al tiro: se muestra como aproximado y en gris
  const rs = rows('rendimiento').map((r) => ({ ...r, veredicto: r.puesto === 'Portero' && r.veredicto !== 'Pocos minutos' ? `${r.veredicto} (aprox.)` : r.veredicto,
    pct_rol: r.pct_rol === '' ? '' : Math.round(N(r.pct_rol)), npxg: N(r.npxg), xa: N(r.xa), asistencias: N(r.asistencias), npg: N(r.goles) - N(r.penaltis),
    tendencia: ten[r.jugador] || '' }));
  scatterRen($('#ren-scatter'), rs.filter((d) => d.puesto !== 'Portero'), 'npxg', 'npg', 'xG sin penaltis (calidad de sus ocasiones)', 'Goles', 'xG');
  scatterRen($('#ren-scatter-xa'), rs.filter((d) => d.puesto !== 'Portero'), 'xa', 'asistencias', 'xA (calidad de las ocasiones que da)', 'Asistencias', 'xA');
  // Alertas
  const al = $('#ren-alertas');
  const malos = rs.filter((r) => r.veredicto.startsWith('Por debajo')).sort((a, b) => N(b.minutos) - N(a.minutos));
  al.replaceChildren(...(malos.length ? malos.map((r) => {
    const it = el('div', { class: r.puesto === 'Portero' ? 'item' : 'item bad' });
    const w = `jugador=${enc(r.jugador)}`;
    it.append(el('p')); it.lastChild.append(markEl('b', 'rendimiento', 'jugador', w, r.jugador), ` · ${r.puesto} · `, markEl('span', 'rendimiento', 'minutos', w, r.minutos), ' min',
      r.puesto === 'Portero' ? ' · aproximado: el xG no mide lo colocado que iba cada tiro' : '');
    it.append(el('p')); it.lastChild.append(el('span', { class: 'k' }, 'El dato: '), markEl('span', 'rendimiento', 'motivo', w, r.motivo), '.');
    return it;
  }) : [el('p', { class: 'item' }, 'Nadie claramente por debajo de lo esperado.')]));
  // Tabla
  const sk = sortRen.k, ord = { 'Por debajo': 0, 'En línea': 1, 'Por encima': 2, 'Pocos minutos': 4 };
  const txt = ['jugador', 'puesto', 'motivo'].includes(sk);
  const val = (r) => (sk === 'tendencia' ? (r.tendencia ? Number(r.tendencia.slice(2)) : -99) : N(r[sk]));
  const o = (v) => ord[v] ?? 3;  // los del portero (aprox.), antes de "Pocos minutos"
  rs.sort((a, b) => (sk === 'veredicto' ? o(a.veredicto) - o(b.veredicto) || N(b.minutos) - N(a.minutos)
    : txt ? String(a[sk]).localeCompare(String(b[sk])) : val(a) - val(b)) * (sortRen.asc || sk === 'veredicto' ? 1 : -1));
  document.querySelectorAll('#tabla-rendimiento th').forEach((th) => th.setAttribute('aria-sort', th.dataset.field === sk ? (sortRen.asc ? 'ascending' : 'descending') : 'none'));
  fillTable($('#tabla-rendimiento'), rs, ['jugador', 'puesto', 'minutos', 'goles', 'penaltis', 'npxg', 'g_menos_xg', 'asistencias', 'xa', 'a_menos_xa',
    'pct_rol', 'acierto_pase', 'prog90', 'recup90', 'duelos_pct', 'perdidas90', 'tendencia', 'veredicto', 'motivo'], (r) => r.jugador);
  $('#tabla-rendimiento tbody').querySelectorAll('tr').forEach((tr, i) => { tr.children[17].style.color = VER_COL[rs[i].veredicto] || 'var(--color-fg-muted)'; });
}

// La dirección guarda la sección y lo elegido en ella (#jugadores?jugador_t=...), para poder mandar el enlace exacto
const ENLACE = { resumen: ['temporada'], partido: ['partido', 'sub_p'], jugadores: ['temporada', 'jugador_t', 'comparar'], historico: ['comp'], titulos: [] };
function enlace(tab) {
  const q = new URLSearchParams();
  for (const k of ENLACE[tab] || []) if (P()[k] != null && P()[k] !== '') q.set(k, P()[k]);
  const h = `#${tab}${q.toString() ? '?' + q : ''}`;
  if (location.hash !== h) history.replaceState(null, '', h);
}

function render() {
  const marca = $('#brand-esc');
  if (!marca.firstChild && ok('escudos')) marca.append(escudo(RM));
  const tab = document.querySelector('.rm-page:not([hidden])')?.id;
  if (tab === 'partido') renderPartido();
  else if (tab === 'resumen') renderTemporada();
  else if (tab === 'jugadores') { renderFicha(); renderRendimiento(); renderTemporada(); }
  else if (tab === 'historico') renderHistorico();
  else if (tab === 'titulos') renderTitulos();
  if (tab) enlace(tab);
  // gráficos sin descripción propia: lector de pantalla lee el título de su tarjeta
  for (const g of document.querySelectorAll(`#${tab} .rm-chart > svg:not([aria-label])`))
    g.setAttribute('role', 'img'), g.setAttribute('aria-label', g.closest('.rm-card')?.querySelector('h2')?.textContent || 'Gráfico');
  // mientras llega un CSV, su hueco muestra una animación de carga
  for (const e of document.querySelectorAll(`#${tab} [data-source]`))
    e.toggleAttribute('data-cargando', e.dataset.source.split(' ').some((id) => dash.data(id).status === 'loading'));
  moverIndicador($('.menu'));
  document.querySelectorAll(CON_SCROLL).forEach(pistaScroll);
}

// la dirección se lee antes de pintar nada: el primer render la reescribe
const [hashTab, hashQ] = location.hash.slice(1).split('?');
if (hashQ) dash.setParams(Object.fromEntries([...new URLSearchParams(hashQ)].map(([k, v]) => [k, k === 'partido' ? Number(v) : v])));
// enlaces antiguos (#temporada, #rendimiento) siguen funcionando
const named = { temporada: 'resumen', rendimiento: 'jugadores' }[hashTab] || hashTab;
showTab(['resumen', 'partido', 'jugadores', 'historico', 'titulos'].includes(named) ? named : 'resumen', false);
dash.onData(render);
// un enlace pegado en la misma pestaña (solo cambia lo que va tras #) también se abre
window.addEventListener('hashchange', () => {
  const [tab, q] = location.hash.slice(1).split('?');
  if (q) dash.setParams(Object.fromEntries([...new URLSearchParams(q)].map(([k, v]) => [k, k === 'partido' ? Number(v) : v])));
  if (['resumen', 'partido', 'jugadores', 'historico', 'titulos'].includes(tab)) showTab(tab, false);
});

// ---------- Accesibilidad: filas y cabeceras de tabla se usan con el teclado (Intro o espacio) ----------
document.querySelectorAll('th[data-field]').forEach((th) => { th.tabIndex = 0; });
document.addEventListener('keydown', (ev) => {
  const t = ev.target;
  if ((ev.key === 'Enter' || ev.key === ' ') && t.matches && t.matches('tbody tr[tabindex], th[tabindex]')) { ev.preventDefault(); t.click(); }
});

// ---------- Exportar el informe del partido: la vista de impresión del navegador permite guardarlo en PDF ----------
$('#exportar').addEventListener('click', () => window.print());

// ---------- Buscador global: jugadores, partidos de la temporada y rivales del histórico ----------
(() => {
  const inp = $('#buscar'), lista = $('#buscar-res');
  const sinTildes = (x) => String(x).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  let res = [];
  const cerrar = () => { lista.hidden = true; inp.setAttribute('aria-expanded', 'false'); };
  const ir = (r) => { cerrar(); inp.value = ''; r.ir(); };
  inp.addEventListener('input', () => {
    const q = sinTildes(inp.value.trim());
    if (q.length < 2) { cerrar(); return; }
    // el histórico solo se descarga si se busca un rival
    const jug = [...new Set(rows('metricas_jugador').filter((r) => r.equipo === RM).map((r) => r.jugador))]
      .filter((n) => sinTildes(n).includes(q)).slice(0, 5)
      .map((n) => ({ tipo: 'Jugador', txt: n, ir: () => { dash.setParams({ jugador_t: n }); showTab('jugadores'); } }));
    const par = rows('partidos').filter((p) => sinTildes(`${p.rival} ${p.fecha} ${fechaEs(p.fecha)} ${p.competicion}`).includes(q)).slice(-5).reverse()
      .map((p) => ({ tipo: 'Partido', txt: `${fechaEs(p.fecha)} · ${p.local} ${p.goles_local}–${p.goles_visitante} ${p.visitante}`,
        ir: () => { dash.setParams({ partido: Number(p.match_id), jugador: null }); showTab('partido'); } }));
    const riv = [...new Set(rows('historico').map((r) => r.rival))].filter((n) => sinTildes(n).includes(q)).slice(0, 4)
      .map((n) => ({ tipo: 'Rival (histórico)', txt: n, ir: () => { $('#q-rival').value = n; showTab('historico'); $('#rivales').scrollIntoView({ behavior: 'smooth' }); } }));
    res = [...jug, ...par, ...riv];
    lista.replaceChildren(...(res.length ? res.map((r, i) => {
      const li = el('li', { role: 'option', id: `bus-${i}` });
      li.append(el('span', { class: 'tipo' }, r.tipo), el('span', {}, r.txt));
      li.addEventListener('mousedown', (ev) => { ev.preventDefault(); ir(r); });
      return li;
    }) : [el('li', { class: 'vacio' }, 'Sin resultados')]));
    lista.hidden = false; inp.setAttribute('aria-expanded', 'true');
  });
  inp.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' && res.length) ir(res[0]);
    if (ev.key === 'Escape') { inp.value = ''; cerrar(); }
  });
  inp.addEventListener('blur', cerrar);
})();
})();
