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
MANUAL = {"Campo de Chamartín": (40.4521, -3.6885), "Nuevo Chamartín": BERNABEU, "Santiago Bernabéu": BERNABEU,  # historico.py los nombra por fecha
          "Antiguo Metropolitano": (40.4473, -3.7085),  # el del Atlético en Cuatro Caminos (1923-1966)
          "Metropolitano": (40.4362, -3.5995), "Vicente Calderón": (40.4017, -3.7206), "Estadio Vicente Calderón": (40.4017, -3.7206),
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
          "Heliópolis": (37.3565, -5.9817), "Hipódromo": (40.4419, -3.6886),
          # campos desaparecidos o que Wikidata no tiene: los conocidos, en su sitio; los demás, en el centro de su ciudad
          "Madrid": (40.4168, -3.7038), "Bardin": (38.3452, -0.4810), "San Juan": (42.8125, -1.6458), "Patronato Obrero": (37.3830, -5.9900),
          "Cruz Alta": (41.5480, 2.1070), "Eliondo": (43.3380, -3.0100), "El Arcángel": (37.8730, -4.7650), "Tiro del Pichón": (40.4200, -3.7200),
          "Torrero": (41.6330, -0.8900), "Ibaiondo": (43.3400, -3.0100), "Montjuïc": (41.3647, 2.1557), "El Sequiol": (39.9860, -0.0500),
          "Avenida Cataluña": (41.1200, 1.2450), "Nova Creu Alta": (41.5540, 2.1020), "Creu Alta": (41.5480, 2.1070), "Stadio delle Alpi": (45.1096, 7.6413),
          "San Lázaro": (42.8860, -8.5250), "Camp de la Indústria": (41.3820, 2.1450), "Camp del Carrer Entença": (41.3800, 2.1490),
          "La Viña": (38.3600, -0.4900), "Juan Rojas": (36.8400, -2.4460), "Los Pajaritos": (41.7690, -2.4780), "Av. Plaza de Toros": (40.4300, -3.6700),
          "Ondarreta Stadium": (43.3180, -2.0050), "Campo del Mercantil": (37.3900, -5.9800), "Campo de la Reina Victoria": (37.3750, -5.9850),
          "Santa Marina": (38.8780, -6.9700), "Valencia": (39.4699, -0.3763), "Municipal de Zorrilla": (41.6520, -4.7350),
          "ChMP Central Stadium": (46.4800, 30.7500), "Nuevo Matapiñonera": (40.5480, -3.6260), "Diego Armando Maradona": (40.8280, 14.1930),
          "NSK Olimpiyskyi": (50.4330, 30.5220), "Al-Awwal Park": (24.7890, 46.8390), "Butarque": (40.3410, -3.7610), "Velódromo": (41.3900, 2.1500),
          "Huelva": (37.2614, -6.9447), "Martínez Campos": (43.3400, -3.0100), "Alicante": (38.3452, -0.4810), "Cantabria": (43.3500, -4.0500),
          "El Calvario": (40.9600, -5.6600), "Domecq": (36.6900, -6.1300), "Varela": (35.5700, -5.3700), "La Puentecilla": (42.6000, -5.5700),
          "Stade Bosuil": (51.2320, 4.4730), "Mithat Paşa Stadium": (41.0390, 28.9940), "Stadionul 23 August": (44.4370, 26.1520),
          "Iparralde": (43.2600, -2.9300), "De Kuip": (51.8940, 4.5230), "Grünwalder Stadion": (48.1110, 11.5740),
          "Stadion Dr. Václava Vacka": (50.1000, 14.4160), "Sevilla": (37.3891, -5.9845), "Castellón de la Plana": (39.9860, -0.0500),
          "Las Palmas de Gran Canaria": (28.1000, -15.4200), "Baseball Ground": (52.9100, -1.4730), "Nuevo Mirador": (36.1300, -5.4600),
          "Luzhniki": (55.7158, 37.5537), "Mini Estadi": (41.3790, 2.1180), "Colombino": (37.2500, -6.9400), "La Maladière": (46.9960, 6.9460),
          "Stadion Crvena Zvezda": (44.7830, 20.4650), "Vallecas": (40.3918, -3.6588)}


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
