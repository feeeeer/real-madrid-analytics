"""Coordenadas de cada estadio del histórico (Wikidata) -> docs/data/estadios.csv, para el mapa de la web.

1. Las que ya están en estadios.csv se conservan (cada ejecución solo busca los estadios nuevos).
2. Nombre exacto (es/en, también nombres alternativos) entre los recintos deportivos de Wikidata: una consulta SPARQL.
3. Los que quedan, con el buscador de Wikidata (el primer resultado que sea un recinto deportivo con coordenadas).
4. MANUAL manda sobre todo: nombres antiguos o ambiguos que el buscador confundiría.
Uso suelto: python pipeline/estadios.py
"""
import csv, json, time, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path

UA = {"User-Agent": "RealMadridAnalytics/1.0 (https://real-madrid-analytics.vercel.app; datos abiertos para una web sin ánimo de lucro)"}
BERNABEU = (40.4531, -3.6883)
# campos con varios nombres a lo largo del tiempo, o que el buscador confunde (lat, lon)
MANUAL = {"Chamartín": BERNABEU, "Campo de Chamartín": BERNABEU, "Nuevo Chamartín": BERNABEU, "Nuevo Estadio Chamartín": BERNABEU,
          "Estadio Chamartín": BERNABEU, "Metropolitano": (40.4473, -3.7085),  # el del Atlético en Cuatro Caminos (1923-1966)
          "Estadio Metropolitano": (40.4362, -3.5995), "Vicente Calderón": (40.4017, -3.7206), "Estadio Vicente Calderón": (40.4017, -3.7206),
          "Nervión": (37.3840, -5.9705), "Atocha": (43.3156, -1.9737), "Estadio Atocha": (43.3156, -1.9737),
          # los que el buscador no encuentra (nombre corto o sin tilde)
          "San Mamés": (43.2641, -2.9494), "El Sardinero": (43.4762, -3.7935), "Sarrià": (41.3889, 2.1336), "Sarriá": (41.3889, 2.1336),
          "Sarria": (41.3889, 2.1336), "Estadio Sarriá": (41.3889, 2.1336), "Estadio Sarria": (41.3889, 2.1336), "José Zorrilla": (41.6445, -4.7612),
          "Jose Zorrilla": (41.6445, -4.7612), "La Cerámica": (39.9441, -0.1035), "Estadio La Romareda": (41.6366, -0.9018),
          "Parc des Princes": (48.8414, 2.2530), "San Siro": (45.4781, 9.1240), "Giuseppe Meazza": (45.4781, 9.1240),
          "Riyadh Air Metropolitano": (40.4362, -3.5995), "Nuevo Riazor": (43.3687, -8.4174), "Abanca Riazor": (43.3687, -8.4174),
          "Etihad Stadium": (53.4831, -2.2004), "Vallecas": (40.3918, -3.6588), "Campo Vallecas": (40.3918, -3.6588),
          "Mallorca Son Moix": (39.5900, 2.6300), "Montilivi": (41.9612, 2.8286), "Reale Arena": (43.3014, -1.9736),
          "Estadi Olímpic Lluís Companys": (41.3647, 2.1557), "Olímpic Lluís Companys": (41.3647, 2.1557), "Vicente Calderón Stadium": (40.4017, -3.7206),
          "Vicente Calderon": (40.4017, -3.7206), "Manzanares": (40.4017, -3.7206), "El Plantío": (42.3364, -3.6873),
          "Ramón de Carranza": (36.5027, -6.2729), "Stade de Gerland": (45.7238, 4.8320), "Castalia": (39.9933, -0.0469),
          "Heliópolis": (37.3565, -5.9817), "Hipódromo": (40.4419, -3.6886)}


def pedir(url, datos=None):
    for i in range(5):
        try:
            req = urllib.request.Request(url, data=datos, headers={**UA, "Accept": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except Exception:
            time.sleep(15 * (i + 1))
    return {}


def punto(texto):
    """'Point(-3.68 40.45)' -> (40.45, -3.68)"""
    lon, lat = texto.removeprefix("Point(").rstrip(")").split()
    return round(float(lat), 4), round(float(lon), 4)


def recintos(ids):
    """De estos elementos de Wikidata, los que son recintos deportivos (Q483110 y subclases) con coordenadas."""
    q = f"SELECT ?i ?c WHERE {{ VALUES ?i {{ {' '.join('wd:' + i for i in ids)} }} ?i wdt:P625 ?c ; wdt:P31/wdt:P279* wd:Q483110 . }}"
    r = pedir("https://query.wikidata.org/sparql", urllib.parse.urlencode({"query": q, "format": "json"}).encode())
    return {b["i"]["value"].rsplit("/", 1)[1]: punto(b["c"]["value"]) for b in r.get("results", {}).get("bindings", [])}


def main(web=Path("docs/data"), buscar=True):
    usos = Counter(r["estadio"] for r in csv.DictReader(open(web / "historico.csv", encoding="utf-8")) if r["estadio"])
    previo = web / "estadios.csv"
    coords = {r["estadio"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(previo, encoding="utf-8"))} if previo.exists() else {}
    faltan = [n for n in usos if n not in coords and n not in MANUAL and '"' not in n]
    if faltan and buscar:  # nombre exacto entre los recintos deportivos
        vals = " ".join(f'"{n}"@{l}' for n in faltan for l in ("es", "en"))
        q = f"SELECT ?l ?c WHERE {{ VALUES ?l {{ {vals} }} ?i rdfs:label|skos:altLabel ?l ; wdt:P625 ?c ; wdt:P31/wdt:P279* wd:Q483110 . }}"
        r = pedir("https://query.wikidata.org/sparql", urllib.parse.urlencode({"query": q, "format": "json"}).encode())
        for b in r.get("results", {}).get("bindings", []):
            coords.setdefault(b["l"]["value"], punto(b["c"]["value"]))
    for n in [n for n in faltan if buscar and n not in coords and usos[n] >= 2]:  # el buscador, para los que se repiten
        time.sleep(1.2)
        hits = pedir("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbsearchentities", "search": n, "language": "es", "type": "item", "limit": 3, "format": "json"})).get("search", [])
        enc = recintos([h["id"] for h in hits]) if hits else {}
        primero = next((h["id"] for h in hits if h["id"] in enc), None)  # en el orden del buscador
        if primero:
            coords[n] = enc[primero]
    coords.update(MANUAL)
    with open(previo, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["estadio", "lat", "lon"])
        w.writerows(sorted((n, *c) for n, c in coords.items() if n in usos))
    con = sum(k for n, k in usos.items() if n in coords)
    print(f"   estadios.csv: {sum(n in coords for n in usos)} de {len(usos)} estadios; {con} de {sum(usos.values())} partidos con estadio localizado", flush=True)


if __name__ == "__main__":
    assert punto("Point(-3.6883 40.4531)") == (40.4531, -3.6883)
    main()
