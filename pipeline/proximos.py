"""Próximos partidos oficiales del Madrid (ESPN, accesible desde la nube) -> docs/data/proximos.csv.

Los nombres de ESPN ("Barcelona", "Athletic Club") se pasan a los del histórico y los escudos ("FC Barcelona",
"Athletic Bilbao") para que la web cruce el próximo rival con el cara a cara y su escudo.
Uso suelto: python pipeline/proximos.py
"""
import csv, json, unicodedata, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

COMP = {"esp.1": "LaLiga", "uefa.champions": "Copa de Europa", "esp.copa_del_rey": "Copa del Rey", "esp.super_cup": "Supercopa de España"}
SOBRAN = {"fc", "cf", "cd", "ud", "sd", "rcd", "rc", "ca", "sc", "ac", "club", "de", "del", "the"}
URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/teams/86/schedule?fixture=true"  # 86 = Real Madrid


def fichas(nombre):
    t = unicodedata.normalize("NFD", nombre).encode("ascii", "ignore").decode().lower().replace(".", " ").replace("-", " ")
    return set(t.split()) - SOBRAN


def canonico(nombre, conocidos):
    """El nombre conocido que contiene todas las palabras del de ESPN, el más corto; si no hay, el de ESPN."""
    f = fichas(nombre)
    cands = [c for c in conocidos if f and f <= fichas(c)]
    return min(cands, key=lambda c: len(fichas(c))) if cands else nombre


def main(dest=Path("docs/data")):
    conocidos = {r["equipo"] for r in csv.DictReader(open(dest / "escudos.csv", encoding="utf-8"))}
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    filas = []
    for ev in json.loads(urllib.request.urlopen(req, timeout=30).read())["events"]:
        liga, comp = ev["league"]["slug"], ev["competitions"][0]
        # el que se está jugando y el recién acabado también: la web pone su marcador en directo hasta que se procesa como jugado
        reciente = datetime.now(timezone.utc) - datetime.fromisoformat(ev["date"].replace("Z", "+00:00")) < timedelta(hours=6)
        if liga not in COMP or (comp["status"]["type"]["state"] != "pre" and not reciente):
            continue
        eq = {c["homeAway"]: c["team"]["displayName"] for c in comp["competitors"]}
        nom = {k: "Real Madrid" if v == "Real Madrid" else canonico(v, conocidos) for k, v in eq.items()}
        filas.append({"fecha": ev["date"], "id": ev["id"], "liga": liga, "competicion": COMP[liga], "fase": ev.get("seasonType", {}).get("name", ""),
                      "local": nom["home"], "visitante": nom["away"], "estadio": comp.get("venue", {}).get("fullName", "")})
    filas.sort(key=lambda r: r["fecha"])
    with open(dest / "proximos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["fecha", "id", "liga", "competicion", "fase", "local", "visitante", "estadio"])  # id y liga: marcador en directo
        w.writeheader()
        w.writerows(filas[:6])
    print(f"   proximos.csv: {len(filas[:6])} partidos", flush=True)


if __name__ == "__main__":
    assert canonico("Barcelona", {"FC Barcelona", "Espanyol Barcelona"}) == "FC Barcelona"
    assert canonico("Athletic Club", {"Athletic Bilbao", "Club Atlético"}) == "Athletic Bilbao"
    assert canonico("Inventado FC", {"FC Barcelona"}) == "Inventado FC"
    main()
