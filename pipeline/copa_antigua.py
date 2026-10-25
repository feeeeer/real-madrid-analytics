"""Eliminatorias del Madrid en la Copa de 1903 a 1945 (páginas de cada edición en en.wikipedia) -> copa_en.json.

Las ediciones de 1931-1936 se llaman "Copa del Presidente de la República" y las de 1939-1945 "Copa del Generalísimo":
el título "AAAA Copa del Rey" redirige a ellas. En esas páginas las eliminatorias van en tablas {{TwoLegResult}} y
{{OneLegResult}} sin fecha; la fecha sale del texto de la ronda ("The first leg was played on March 11. The second leg
was played on March 18.") o de la nota del desempate ("Played in Barcelona on April 18."). Sin fecha, el partido no se añade.
Las filas van con el mismo formato que las demás de copa_en.json (en la vuelta, el marcador con el local primero) y
historico.py las cruza con lo que ya hay: solo entran las que faltan.
Uso: python pipeline/copa_antigua.py
"""
import json, re, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

DEST = Path("data/historico/wikipedia/copa_en.json")
MESES = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                     "october", "november", "december"], 1)}
RM = re.compile(r"Real Madrid|Madrid FC|Madrid CF|Madrid F\.C\.")
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
    pagina, texto, filas = d["parse"]["title"], d["parse"]["wikitext"], []
    for seccion in re.split(r"\n(?===[^=])", texto):
        cab = re.match(r"==\s*([^=]+?)\s*==", seccion)
        base = {"pagina": pagina, "comp": "Copa del Rey", "seccion": cab.group(1) if cab else "", "estadio": "", "goles1": "", "goles2": "", "ronda": ""}
        ida = re.search(r"first leg (?:was|were) played on " + DIA, seccion)
        vuelta = re.search(r"second leg (?:was|were) played on " + DIA, seccion)
        unico = re.search(r"(?:matches|match) (?:was|were) played on " + DIA, seccion)
        for m in re.finditer(r"\{\{TwoLegResult\|(.*?)\}\}\n", seccion):
            c = celdas(m.group(1))
            t1, t1w = equipo(c[0]); t2, t2w = equipo(c[3])
            if not (RM.search(t1 + t1w) or RM.search(t2 + t2w)) or not (ida and vuelta) or len(c) < 7:
                continue
            g1, g2 = goles(c[5]), goles(c[6])
            if g1:
                filas.append({**base, "t1": t1, "t1w": t1w, "t2": t2, "t2w": t2w, "tipo": "twoleg", "pata": "1",
                              "fecha": fecha(*ida.groups(), anio), "g1": g1[0], "g2": g1[1]})
            if g2:  # en la tabla, la vuelta va con el equipo 1 primero; en copa_en.json, con el local (el equipo 2)
                filas.append({**base, "t1": t1, "t1w": t1w, "t2": t2, "t2w": t2w, "tipo": "twoleg", "pata": "2",
                              "fecha": fecha(*vuelta.groups(), anio), "g1": g2[1], "g2": g2[0]})
        for m in re.finditer(r"\{\{OneLegResult\|(.*?)\}\}\n", seccion):
            c = celdas(m.group(1))
            if len(c) < 4:
                continue
            t1, t1w = equipo(c[0]); t2, t2w = equipo(c[3])
            if not (RM.search(t1 + t1w) or RM.search(t2 + t2w)):
                continue
            f = re.search(r"on " + DIA, c[2]) or unico
            g = goles(c[2])
            if f and g:
                filas.append({**base, "t1": t1, "t1w": t1w, "t2": t2, "t2w": t2w, "tipo": "oneleg", "pata": "",
                              "fecha": fecha(*f.groups(), anio), "g1": g[0], "g2": g[1]})
    return filas


def main():
    datos = json.loads(DEST.read_text())
    ya = {(r["fecha"], r["t1w"], r["t2w"]) for r in datos["copa_en"]}
    nuevas = []
    for anio in range(1903, 1946):
        time.sleep(3)
        for r in edicion(anio):
            if (r["fecha"], r["t1w"], r["t2w"]) not in ya:
                ya.add((r["fecha"], r["t1w"], r["t2w"]))
                nuevas.append(r)
                datos["copa_en"].append(r)
        DEST.write_text(json.dumps(datos, ensure_ascii=False))  # tras cada edición: si Wikipedia corta, lo hecho se queda
    print(f"copa_en.json: {len(nuevas)} partidos nuevos del Madrid en la Copa de 1903-1945")
    for r in nuevas:
        print(f"   {r['fecha']} {r['t1']} - {r['t2']} ({r['pata'] or 'único'}) {r['g1']}-{r['g2']}")


if __name__ == "__main__":
    assert equipo("'''[[Real Madrid|Madrid FC]]'''") == ("Madrid FC", "Real Madrid") and goles(" 1–5 ") == ("1", "5")
    assert celdas("[[A|B]]|| 1–8 <ref>x|y</ref> |[[C]]|| 0–3 | 1–5 |winner=2")[5:7] == [" 0–3 ", " 1–5 "]
    main()
