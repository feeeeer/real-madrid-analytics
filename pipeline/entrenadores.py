"""Entrenadores del primer equipo y sus etapas (es.wikipedia, anexo de entrenadores) -> docs/data/entrenadores.csv.

Cada fila de la tabla: nombre, bandera, fecha de inicio, fecha de fin y {{edad en días|d|m|a|d|m|a}} con las dos fechas
exactas. Si falta esa plantilla, se leen las fechas escritas ("1 de abril de 1930", "marzo de 1930", "1941").
Uso suelto: python pipeline/entrenadores.py
"""
import csv, json, re, urllib.request
from pathlib import Path

URL = ("https://es.wikipedia.org/w/api.php?action=parse&page=Anexo:Entrenadores_del_Real_Madrid_Club_de_F%C3%BAtbol"
       "&prop=wikitext&format=json&formatversion=2")
MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                                     "octubre", "noviembre", "diciembre"], 1)}


def fecha(txt, fin=False):
    """'1 de abril de 1930' -> 1930-04-01; 'marzo de 1930' -> 1930-03-01 (o fin de mes); '1941' -> 1941-01-01 (o 31-12)."""
    t = re.sub(r"<ref.*?(</ref>|/>)|\{\{.*?\}\}|'''?", "", txt).strip().lower()
    m = re.search(r"(?:(\d{1,2}) de )?(?:(" + "|".join(MESES) + r") de )?(\d{4})", t)
    if not m:
        return ""
    d, mes, a = m.groups()
    mes = MESES[mes] if mes else (12 if fin else 1)
    d = int(d) if d else (28 if fin and m.group(2) else 31 if fin else 1)
    return f"{a}-{mes:02d}-{d:02d}"


def enlace(celda):
    """El título de la página enlazada: igual en las dos tablas ("[[Juan de Cárcer|Juanito Cárcer]]" -> "Juan de Cárcer")."""
    m = re.search(r"\[\[([^|\]]+)", celda)
    return re.sub(r"\s*\(.*\)$", "", m.group(1)).strip() if m else None  # "Arthur Johnson (futbolista)" -> "Arthur Johnson"


def etapas(wikitext):
    filas = []
    for bloque in wikitext.split("\n|-"):
        celdas = [c.strip() for c in bloque.split("\n|")[1:]]
        if len(celdas) < 4 or "bandera" not in celdas[1].lower():
            continue
        nombre = enlace(celdas[0])
        if not nombre:
            continue
        pais = re.search(r"bandera\|([A-Z]{3})", celdas[1], re.I)
        exacto = re.search(r"edad en días\|(\d+)\|(\d+)\|(\d{4})\|(\d+)\|(\d+)\|(\d{4})", bloque)
        if exacto:
            d1, m1, a1, d2, m2, a2 = map(int, exacto.groups())
            desde, hasta = f"{a1}-{m1:02d}-{d1:02d}", f"{a2}-{m2:02d}-{d2:02d}"
        else:
            desde, hasta = fecha(celdas[2]), fecha(celdas[3], fin=True)
        if desde:
            filas.append({"entrenador": nombre, "pais": pais.group(1).upper() if pais else "", "desde": desde, "hasta": hasta})
    return filas


def titulos(wikitext):
    """Tabla "Récord de títulos oficiales": entrenador -> (número de títulos, detalle en texto)."""
    out = {}
    for bloque in wikitext.split("\n|-")[1:]:
        celdas = [c.strip() for c in bloque.split("\n|")[1:]]
        nom = enlace(celdas[0]) if celdas else None
        n = re.search(r"(\d+)\s*$", celdas[1]) if len(celdas) > 2 else None
        if nom and n:
            det = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", celdas[2]).replace("SuperCups", "Supercopas de Europa").replace("SuperCup", "Supercopa de Europa")
            out[nom] = (int(n.group(1)), re.sub(r"<ref.*?(</ref>|/>)", "", det).strip(" ."))
    return out


def main(dest=Path("docs/data")):
    req = urllib.request.Request(URL, headers={"User-Agent": "rm-analytics/1.0"})
    texto = json.loads(urllib.request.urlopen(req, timeout=30).read())["parse"]["wikitext"]
    # solo la tabla del primer equipo: detrás vienen la del femenino, las nacionalidades y la línea temporal
    filas = etapas(texto[texto.index("== Historial de entrenadores =="):texto.index("Sección femenina")])
    assert len(filas) > 50, f"solo {len(filas)} etapas: ¿ha cambiado la tabla del anexo?"
    tit = titulos(texto[texto.index("== Récord de títulos oficiales =="):texto.index("== Notas ==")])
    assert tit.get("Miguel Muñoz", (0,))[0] >= 14, "no se ha leído la tabla de títulos por entrenador"
    for r in filas:
        r["titulos"], r["detalle_titulos"] = tit.get(r["entrenador"], (0, ""))
    with open(dest / "entrenadores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["entrenador", "pais", "desde", "hasta", "titulos", "detalle_titulos"])
        w.writeheader()
        w.writerows(sorted(filas, key=lambda r: r["desde"]))
    print(f"   entrenadores.csv: {len(filas)} etapas", flush=True)


if __name__ == "__main__":
    assert fecha("1 de abril de 1930") == "1930-04-01" and fecha("marzo de 1930", fin=True) == "1930-03-28" and fecha("1941", fin=True) == "1941-12-31"
    main()
