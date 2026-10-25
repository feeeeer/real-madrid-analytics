"""Clasificaciones históricas de jugadores del Madrid (Wikipedia) -> docs/data/jugadores.csv.

- partidos: es.wikipedia, "Anexo:Jugadores con más partidos del Real Madrid Club de Fútbol" (partidos oficiales).
- goles: es.wikipedia, "Anexo:Máximos goleadores del Real Madrid Club de Fútbol" (los partidos salen de su promedio, "450 / 438").
- asistencias: es.wikipedia, "Anexo:Estadísticas del Real Madrid Club de Fútbol" (datos desde 1980, se actualiza tras cada partido);
  sus partidos, del anexo de partidos.
El nombre es el del enlace; si es una sola palabra, el del artículo ("Ronaldo" -> "Ronaldo Nazário", nunca "Cristiano Ronaldo").
Uso suelto: python pipeline/jugadores.py
"""
import csv, json, re, unicodedata, urllib.parse, urllib.request
from pathlib import Path

UA = {"User-Agent": "RealMadridAnalytics/1.0 (https://real-madrid-analytics.vercel.app; datos abiertos para una web sin ánimo de lucro)"}


def wikitext(lang, pagina):
    q = {"action": "parse", "page": pagina, "redirects": 1, "prop": "wikitext", "format": "json", "formatversion": 2}
    req = urllib.request.Request(f"https://{lang}.wikipedia.org/w/api.php?{urllib.parse.urlencode(q)}", headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=60).read())["parse"]["wikitext"]


def limpia(t):
    return re.sub(r"<ref[^>]*/>|<ref.*?</ref>|<!--.*?-->|'''?|\{\{bandera[^}]*\}\}|\{\{flagicon[^}]*\}\}", "", t, flags=re.S).strip()


def jugador(celda):
    """'[[Raúl González Blanco|Raúl González]]' -> 'Raúl González'; '[[Ronaldo Nazário|Ronaldo]]' -> 'Ronaldo Nazário'."""
    m = re.search(r"\[\[(?!(?:Archivo|File|Imagen|Image):)([^|\]]+)(?:\|([^\]]+))?\]\]", celda)  # no la bandera ([[Archivo:...]])
    if not m:
        return None
    apodo = re.search(r"''([^']+)''", celda[m.end():] + (m.group(2) or ""))  # "José Martínez ''Pirri''" -> "Pirri"
    if apodo:
        return apodo.group(1).strip()
    articulo = re.sub(r"\s*\(.*\)$", "", m.group(1)).strip()  # "Santillana (futbolista)" -> "Santillana"
    texto = (m.group(2) or articulo).strip()
    return texto if len(texto.split()) > 1 else articulo


def filas(tabla):
    """Celdas de cada fila de una tabla wiki (separadas por saltos de línea, '||' o '!!')."""
    for fila in re.split(r"\n\|-[^\n]*", tabla)[1:]:
        celdas = []
        for linea in fila.strip("\n").split("\n"):
            if linea[:1] in "|!" and not linea.startswith("|}"):
                celdas += re.split(r"\|\||!!", linea[1:])
        yield [c.strip() for c in celdas]


def primera_tabla(texto):
    i = texto.index('{| class="sortable"')
    return texto[i:texto.index("\n|}", i)]


def numero(c):
    m = re.search(r"\d+", limpia(c).replace(".", ""))
    return int(m.group()) if m else None


def anios(c):
    """'2009 - 18 (9)' / '1994–2010' -> (2009, 2018)"""
    a = re.findall(r"\d{2,4}", limpia(c))
    if not a:
        return "", ""
    if len(a) == 1 or re.search(r"\d\s*[-–]\s*\(", limpia(c)):  # "2018 - (8)": sigue en el club
        return int(a[0]), ""
    d, h = int(a[0]), int(a[1])
    if h < 100:
        h += (d // 100) * 100 + (100 if h < d % 100 else 0)
    return d, h


def palabras(n):
    t = unicodedata.normalize("NFD", n).encode("ascii", "ignore").decode().lower()
    return set(re.sub(r"[^a-z ]", " ", t).split())


# nombres que encajan con dos jugadores del anexo de partidos; decidido por los años en el club
MISMO_JUGADOR = {"Míchel": "Míchel González",  # 1982-1996; Míchel Salgado jugó de 1999 a 2009
                 "Juanito": "Juanito Gómez"}   # 1977-1987; Juanito Alonso, de 1948 a 1960


def canonico(n, part):
    """El nombre con el que sale en la tabla de partidos, para que un jugador se llame igual en todas las tablas."""
    nombres = [p["jugador"] for p in part]
    if n in nombres:
        return n
    if n in MISMO_JUGADOR:
        return MISMO_JUGADOR[n]
    cands = [m for m in nombres if palabras(m) <= palabras(n) or palabras(n) <= palabras(m)]
    return cands[0] if len(cands) == 1 else n


def main(dest=Path("docs/data")):
    salida, part = [], []
    for c in filas(primera_tabla(wikitext("es", "Anexo:Jugadores con más partidos del Real Madrid Club de Fútbol"))):
        if len(c) > 2 and (n := jugador(c[1])) and (t := numero(c[2])):
            part.append({"tipo": "partidos", "jugador": n, "partidos": t, "valor": t, "desde": "", "hasta": ""})
    assert part and part[0]["valor"] >= 700, "no se ha leído la tabla de partidos"
    salida += part
    for c in filas(primera_tabla(wikitext("es", "Anexo:Máximos goleadores del Real Madrid Club de Fútbol"))):
        if len(c) > 4 and (n := jugador(c[1])) and (g := numero(c[3])):
            pj = re.search(r"#expr:\s*\d+\s*/\s*(\d+)", " ".join(c))  # el promedio: goles / partidos
            d, h = anios(c[2])
            c2 = canonico(n, part)  # los partidos, los del anexo de partidos si está (que un jugador tenga los mismos en todas las tablas)
            pj = next((p["partidos"] for p in part if p["jugador"] == c2), None) or (int(pj.group(1)) if pj else "")
            salida.append({"tipo": "goles", "jugador": c2, "partidos": pj, "valor": g, "desde": d, "hasta": h})
    assert any(r["tipo"] == "goles" and r["valor"] >= 450 for r in salida), "no se ha leído la tabla de goleadores"
    # asistencias: es.wikipedia, "Anexo:Estadísticas del Real Madrid Club de Fútbol" (se actualiza tras cada partido)
    txt = wikitext("es", "Anexo:Estadísticas del Real Madrid Club de Fútbol")
    i = txt.index("=== Máximos asistentes ===")
    tabla = re.sub(r"<!--.*?-->", "", txt[txt.index("{|", i):txt.index("\n|}", i)], flags=re.S)  # hay comentarios que parten la fila
    for c in filas(tabla):
        if len(c) > 2 and (n := jugador(c[0])) and (a := numero(c[1])):
            c2 = canonico(n, part)  # su nombre y sus partidos, los del anexo de partidos
            # si no está en el anexo de partidos (menos de ~200), los de la tabla de goleadores ("Ángel di María" = "Ángel Di María")
            gol = next((r for r in salida if r["tipo"] == "goles" and palabras(r["jugador"]) == palabras(c2)), None)
            c2 = gol["jugador"] if gol and c2 not in {p["jugador"] for p in part} else c2
            pj = next((p["partidos"] for p in part if p["jugador"] == c2), "") or (gol["partidos"] if gol else "")
            salida.append({"tipo": "asistencias", "jugador": c2, "partidos": pj, "valor": a, "desde": "", "hasta": ""})
    assert sum(r["tipo"] == "asistencias" for r in salida) >= 10, "no se ha leído la tabla de asistencias"
    nombres = {p["jugador"] for p in part}
    sueltos = sorted({r["jugador"] for r in salida if r["jugador"] not in nombres and r["tipo"] != "partidos" and float(r["valor"] or 0) >= 100})
    if sueltos:
        print("   jugadores sin emparejar con la tabla de partidos (revisar):", sueltos, flush=True)
    with open(dest / "jugadores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["tipo", "jugador", "partidos", "valor", "desde", "hasta"])
        w.writeheader()
        w.writerows(salida)
    print("   jugadores.csv: " + ", ".join(f"{t} {sum(r['tipo'] == t for r in salida)}" for t in ("partidos", "goles", "asistencias")), flush=True)


if __name__ == "__main__":
    assert jugador("{{bandera|POR}} [[Cristiano Ronaldo]]") == "Cristiano Ronaldo"
    assert jugador("[[Ronaldo Nazário|Ronaldo]]") == "Ronaldo Nazário" and jugador("[[Santillana (futbolista)|Santillana]]") == "Santillana"
    assert anios("2009 - 18 (9)") == (2009, 2018) and anios("1953–1964") == (1953, 1964) and anios("1994 - 2010") == (1994, 2010)
    assert anios("2018 - (8)") == (2018, "") and jugador("[[Archivo:Flag.png|20px]] [[Ferenc Puskás]]") == "Ferenc Puskás"
    assert jugador("[[José Martínez Sánchez|José Martínez]] ''Pirri''") == "Pirri"
    main()
