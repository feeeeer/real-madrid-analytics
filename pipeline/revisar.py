"""Revisión de los datos que publica la web (docs/data): si algo no cuadra, lo lista y sale con error (el workflow avisa).

- Escudos: cada equipo de cualquier tabla tiene el suyo, con la misma regla que la web (app.js: mismas palabras sin siglas ni
  artículos, o una genérica de diferencia; nunca el de otro club). Sin escudo solo se admiten clubes que dejaron de jugar con el
  Madrid antes de 1990 (los de principios de siglo, sin escudo en ninguna fuente).
- Clubes y estadios: ninguno con dos nombres que solo cambian en siglas, artículos, tildes o "Estadio".
- Partidos: ninguno repetido (mismo rival, campo y resultado con menos de 11 días de diferencia).
- Jugadores: las clasificaciones tienen sus partidos y cada jugador sale una vez por tabla.
Uso: python pipeline/revisar.py
"""
import csv, re, sys, unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

WEB = Path("docs/data")
RM = "Real Madrid"
SIGLAS = re.compile(r"^(fc|cf|cd|ud|sd|rcd|rc|ca|club|de|del|la|el|a|sad|sc|fk|ac|afc|cp|ce|ue|sk|bk)$")
GENERICAS = {"deportivo", "sport", "futbol", "football", "foot", "ball", "balompie"}
GEN_ESTADIO = {"estadio", "stadium", "estadi", "stade", "stadio", "stadion", "campo", "de", "del", "la", "el", "les", "municipal",
               "do", "da", "des", "du", "di"}
ALIAS_ESCUDO = {"RBL": "RB Leipzig"}


def leer(f):
    return list(csv.DictReader(open(WEB / f, encoding="utf-8"))) if (WEB / f).exists() else []


def plano(n):
    return unicodedata.normalize("NFD", str(n)).encode("ascii", "ignore").decode().lower()


def fichas(n):
    return frozenset(w for w in re.sub(r"[^a-z ]", " ", plano(n)).split() if w and not SIGLAS.match(w))


def nombre_es():
    """La tabla NOMBRE_ES de app.js: también cuenta para emparejar ("Athletic Bilbao" = "Athletic Club")."""
    js = Path("docs/app.js").read_text(encoding="utf-8")
    i = js.index("const NOMBRE_ES = {")
    return dict(re.findall(r"'([^']+)': '([^']+)'", js[i:js.index("};", i)]))


def main():
    errores = []
    NOM = nombre_es()
    esc = {r["equipo"]: r["url"] for r in leer("escudos.csv")}
    formas = lambda n: [f for f in {fichas(n), fichas(NOM.get(n, n))} if f]

    def parecido(a, b):
        d = a ^ b
        return 0 if not d else 1 if len(d) == 1 and next(iter(d)) in GENERICAS else None

    def escudo(n):
        if n in esc or n in ALIAS_ESCUDO:
            return esc.get(n) or esc.get(ALIAS_ESCUDO[n])
        claves = [k for k in esc if esc[k] != esc.get(RM)]
        for nivel in (0, 1):
            c = [k for k in claves if any(parecido(x, y) == nivel for x in formas(n) for y in formas(k))]
            if c:
                return esc[c[0]] if len({esc[k] for k in c}) == 1 else None
        return None

    hist = leer("historico.csv")
    ultimo = defaultdict(str)
    for r in hist:
        for k in ("local", "visitante"):
            ultimo[r[k]] = max(ultimo[r[k]], r["fecha"])
    nombres = set(ultimo)
    for f, cols in (("competicion.csv", ["local", "visitante"]), ("proximos.csv", ["local", "visitante"]), ("ligas.csv", ["equipo"]),
                    ("partidos.csv", ["local", "visitante"])):
        nombres |= {r[c] for r in leer(f) for c in cols if r[c]}
    sin = sorted(n for n in nombres if n and not escudo(n) and not (ultimo.get(n) and ultimo[n] < "1990"))
    if sin:
        errores.append(f"Equipos sin escudo: {sin}")
    # la regla nunca debe llevar un nombre con escudo al de otro club
    for n in list(esc):
        if esc[n] == esc.get(RM):
            continue
        guardado = esc.pop(n)
        otro = escudo(n)
        esc[n] = guardado
        if otro and otro != guardado:
            errores.append(f"La regla de escudos llevaría «{n}» al escudo de otro club")
    # clubes con dos nombres en el histórico
    por = defaultdict(set)
    for r in hist:
        por[fichas(r["rival"])].add(r["rival"])
    errores += [f"Mismo club con varios nombres: {sorted(v)}" for v in por.values() if len(v) > 1]
    # estadios con dos nombres
    est = defaultdict(set)
    for r in hist:
        if r["estadio"]:
            est[frozenset(w for w in re.sub(r"[^a-z0-9 ]", " ", plano(r["estadio"])).split() if w not in GEN_ESTADIO)].add(r["estadio"])
    errores += [f"Mismo estadio con varios nombres: {sorted(v)}" for k, v in est.items()
                if len(v) > 1 and k - {"madrid", "valencia", "olympic"}]
    # partidos repetidos
    grupos = defaultdict(list)
    for r in hist:
        grupos[(r["competicion"], r["rival"], r["condicion"], r["goles_rm"], r["goles_rival"])].append(r)
    for g in grupos.values():
        g.sort(key=lambda r: r["fecha"])
        for a, b in zip(g, g[1:]):
            if (date.fromisoformat(b["fecha"]) - date.fromisoformat(a["fecha"])).days <= 10:
                errores.append(f"Posible partido repetido: {a['fecha']} y {b['fecha']}, {a['competicion']}, {a['rival']} ({a['partido_id']}, {b['partido_id']})")
    # clasificaciones de jugadores
    jug = leer("jugadores.csv")
    for t in ("partidos", "goles", "asistencias"):
        filas = [r for r in jug if r["tipo"] == t]
        if not filas:
            errores.append(f"Jugadores: falta la tabla de {t}")
        errores += [f"Jugadores ({t}): {r['jugador']} sin partidos" for r in filas if not r["partidos"]]
        errores += [f"Jugadores ({t}): {n} sale {k} veces" for n, k in Counter(r["jugador"] for r in filas).items() if k > 1]
    for e in errores:
        print("✗", e)
    print(f"Revisión de datos: {len(errores)} problemas" if errores else "Revisión de datos: todo en orden")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
