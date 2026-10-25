"""Eliminatorias del Madrid en la Copa de 1903 a 1945 (páginas de cada edición en en.wikipedia) -> copa_en.json.

Las ediciones de 1931-1936 se llaman "Copa del Presidente de la República" y las de 1939-1945 "Copa del Generalísimo":
el título "AAAA Copa del Rey" redirige a ellas. En esas páginas las eliminatorias van en tablas {{TwoLegResult}} y
{{OneLegResult}} sin fecha; la fecha sale del texto de la ronda ("The first leg was played on March 11. The second leg
was played on March 18.") o de la nota del desempate ("Played in Barcelona on April 18."). Sin fecha, el partido no se añade.
Las filas van con el mismo formato que las demás de copa_en.json (en la vuelta, el marcador con el local primero) y
historico.py las cruza con lo que ya hay: solo entran las que faltan.
Uso: python pipeline/copa_antigua.py
"""
import csv, json, re, time, unicodedata, urllib.error, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

DEST = Path("data/historico/wikipedia/copa_en.json")
MESES = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                     "october", "november", "december"], 1)}
RM = re.compile(r"Real Madrid|Madrid FC|Madrid CF|Madrid F\.C\.")
# fechas que la página en inglés no da y la española sí (notas del cuadro): (año, rival en el enlace, tipo) -> fecha
CONOCIDAS = {(1936, "Arenas de Guecho", "oneleg"): "1936-05-21"}  # "desempate Madrid, 21 Mayo 6-1"
DIA = r"(" + "|".join(m.capitalize() for m in MESES) + r") (\d{1,2})"


def equipo(celda):
    """'[[Real Madrid|Madrid FC]]' -> ('Madrid FC', 'Real Madrid'); quita negritas y banderas."""
    c = re.sub(r"'''?|\{\{[^}]*\}\}", "", celda).strip()
    m = re.search(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", c)
    return (m.group(2) or m.group(1), m.group(1)) if m else (c, c)


def goles(txt):
    m = re.search(r"(\d+)\s*[–-]\s*(\d+)", re.sub(r"<ref.*?(</ref>|/>)", "", txt))
    return m.groups() if m else None


def fecha(mes, dia, anio):
    return f"{anio}-{MESES[mes.lower()]:02d}-{int(dia):02d}"


def buscar(prefijo, texto, anio):
    """La fecha tras el prefijo, en orden americano ("on March 11") o británico ("on 11 March")."""
    m = re.search(prefijo + DIA, texto)
    if m:
        return date.fromisoformat(fecha(*m.groups(), anio))
    m = re.search(prefijo + r"(\d{1,2}) (" + "|".join(x.capitalize() for x in MESES) + r")\b", texto)
    return date.fromisoformat(fecha(m.group(2), m.group(1), anio)) if m else None


def celdas(plantilla):
    """Celdas de {{TwoLegResult|...}}: se separa por '|' salvo dentro de [[enlace|texto]] y de <ref>...</ref>."""
    return re.split(r"\|(?![^\[]*\]\])(?![^<]*</ref>)", plantilla)


def edicion(anio):
    q = urllib.parse.urlencode({"action": "parse", "page": f"{anio} Copa del Rey", "redirects": 1, "prop": "wikitext", "format": "json", "formatversion": 2})
    req = urllib.request.Request(f"https://en.wikipedia.org/w/api.php?{q}", headers={"User-Agent": "RealMadridAnalytics/1.0 (https://real-madrid-analytics.vercel.app; datos abiertos para una web sin ánimo de lucro)"})
    for intento in range(5):  # Wikipedia corta con 429 si se le pide deprisa: se espera y se reintenta
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=30).read())
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or intento == 4:
                raise
            time.sleep(20 * (intento + 1))
    if "parse" not in d:
        return []
    pagina, texto = d["parse"]["title"], d["parse"]["wikitext"]
    refs = dict(re.findall(r"<ref name=\"?([^\">/]+?)\"?>(.*?)</ref>", texto))  # notas con nombre, para las que se reutilizan
    rondas = []  # en orden: fechas conocidas de la ronda (de cualquier eliminatoria) y las filas del Madrid
    for seccion in re.split(r"\n(?===[^=])", texto):
        cab = re.match(r"==\s*([^=]+?)\s*==", seccion)
        base = {"pagina": pagina, "comp": "Copa del Rey", "seccion": cab.group(1) if cab else "", "estadio": "", "goles1": "", "goles2": "", "ronda": ""}
        ida = buscar(r"first leg (?:was|were) played on ", seccion, anio)
        vuelta = buscar(r"second leg (?:was|were) played on ", seccion, anio)
        unico = buscar(r"(?:matches|match) (?:was|were) played on ", seccion, anio)
        dos, uno, filas = "{{TwoLegResult" in seccion, "{{OneLegResult" in seccion, []
        for m in re.finditer(r"\{\{TwoLegResult\|(.*?)\}\}\n", seccion):
            c = celdas(m.group(1))
            t1, t1w = equipo(c[0]); t2, t2w = equipo(c[3])
            if not (RM.search(t1 + t1w) or RM.search(t2 + t2w)) or len(c) < 7:
                continue
            g1, g2 = goles(c[5]), goles(c[6])
            eq = {"t1": t1, "t1w": t1w, "t2": t2, "t2w": t2w, "tipo": "twoleg"}
            if g1:
                filas.append(({**base, **eq, "pata": "1", "g1": g1[0], "g2": g1[1]}, ida, "ida"))
            if g2:  # en la tabla, la vuelta va con el equipo 1 primero; en copa_en.json, con el local (el equipo 2)
                filas.append(({**base, **eq, "pata": "2", "g1": g2[1], "g2": g2[0]}, vuelta, "vuelta"))
        for m in re.finditer(r"\{\{OneLegResult\|(.*?)\}\}\n", seccion):
            c = celdas(m.group(1))
            if len(c) < 4:
                continue
            t1, t1w = equipo(c[0]); t2, t2w = equipo(c[3])
            g = goles(c[2])
            if (RM.search(t1 + t1w) or RM.search(t2 + t2w)) and g:
                ref = re.search(r"<ref name=\"?([^\"/>]+?)\"? ?/>", c[2])  # nota reutilizada: su fecha está donde se definió
                nota = buscar(r"(?:on|in) ", refs.get(ref.group(1), "") if ref else c[2], anio)
                filas.append(({**base, "t1": t1, "t1w": t1w, "t2": t2, "t2w": t2w, "tipo": "oneleg", "pata": "", "g1": g[0], "g2": g[1]},
                              nota or unico, "desempate" if dos else "unico"))
        if dos or uno:
            rondas.append({"nombre": base["seccion"], "ida": ida, "vuelta": vuelta, "unico": unico, "dos": dos, "filas": filas})
    # sin fecha en la página: hacia atrás desde la final, una semana por partido (las rondas se jugaban domingo a domingo)
    fin = re.search(r"concluded on " + DIA + r",? (\d{4})", texto)
    cursor = date.fromisoformat(fecha(fin.group(1), fin.group(2), fin.group(3))) if fin else None
    # si la final va en una tabla de partido único, es la última "ronda": se le deja su propia fecha
    if cursor and rondas and not rondas[-1]["dos"] and rondas[-1]["nombre"].lower().startswith("final"):
        cursor += timedelta(7)
    salida = []
    for r in reversed(rondas):
        conocida = r["ida"] or r["unico"]
        if r["dos"]:
            v = r["vuelta"] or (cursor - timedelta(7) if cursor else None)
            i = r["ida"] or (v - timedelta(7) if v else None)
            estim = {"ida": i, "vuelta": v, "desempate": v + timedelta(3) if v else None, "unico": i}
        else:
            u = r["unico"] or (cursor - timedelta(7) if cursor else None)
            estim = {"unico": u, "desempate": u, "ida": u, "vuelta": u}
        for fila, f, pata in r["filas"]:
            f = f or (date.fromisoformat(CONOCIDAS[k]) if (k := (anio, fila["t2w"], fila["tipo"])) in CONOCIDAS else None)
            if f or estim[pata]:
                salida.append({**fila, "fecha": (f or estim[pata]).isoformat(), "fecha_aprox": "" if f else "1"})
        cursor = conocida or estim["ida"] or cursor
    return salida


def palabras(n):
    t = unicodedata.normalize("NFD", n).encode("ascii", "ignore").decode().lower()
    return set(re.sub(r"[^a-z ]", " ", t).split()) - {"fc", "cf", "cd", "club", "de", "real", "madrid", "athletic", "sporting"} or {t}


def ya_en_historico(r, hist):
    """El partido (con fecha estimada) ya está en el histórico: misma edición, mismo rival y mismo resultado para el Madrid."""
    vuelta = r["pata"] == "2"
    local, visit = (r["t2"], r["t1"]) if vuelta else (r["t1"], r["t2"])
    rm_local = bool(RM.search(local + (r["t2w"] if vuelta else r["t1w"])))
    g_rm, g_riv = (r["g1"], r["g2"]) if rm_local else (r["g2"], r["g1"])
    rival = palabras(visit if rm_local else local)
    # ±1 año: alguna fuente pone el año de la edición a partidos de diciembre (Oviedo, diciembre de 1928 o de 1929)
    return any(abs(int(h["fecha"][:4]) - int(r["fecha"][:4])) <= 1 and h["goles_rm"] == g_rm and h["goles_rival"] == g_riv and rival & palabras(h["rival"]) for h in hist)


def main():
    datos = json.loads(DEST.read_text())
    ya = {(r["fecha"], r["t1w"], r["t2w"]) for r in datos["copa_en"]}
    hist = [h for h in csv.DictReader(open("docs/data/historico.csv", encoding="utf-8")) if h["competicion"] == "Copa del Rey"]
    nuevas = []
    for anio in range(1903, 1946):
        time.sleep(3)
        for r in edicion(anio):
            if r["fecha_aprox"] and ya_en_historico(r, hist):
                continue
            if (r["fecha"], r["t1w"], r["t2w"]) not in ya:
                ya.add((r["fecha"], r["t1w"], r["t2w"]))
                nuevas.append(r)
                datos["copa_en"].append(r)
        DEST.write_text(json.dumps(datos, ensure_ascii=False))  # tras cada edición: si Wikipedia corta, lo hecho se queda
    print(f"copa_en.json: {len(nuevas)} partidos nuevos del Madrid en la Copa de 1903-1945")
    for r in nuevas:
        print(f"   {r['fecha']}{' (aprox.)' if r['fecha_aprox'] else ''} {r['t1']} - {r['t2']} ({r['pata'] or 'único'}) {r['g1']}-{r['g2']}")


if __name__ == "__main__":
    assert equipo("'''[[Real Madrid|Madrid FC]]'''") == ("Madrid FC", "Real Madrid") and goles(" 1–5 ") == ("1", "5")
    assert celdas("[[A|B]]|| 1–8 <ref>x|y</ref> |[[C]]|| 0–3 | 1–5 |winner=2")[5:7] == [" 0–3 ", " 1–5 "]
    main()
