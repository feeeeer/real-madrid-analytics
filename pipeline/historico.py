"""Base de datos histórica de resultados del Real Madrid (todas las competiciones que hay en fuentes abiertas).

Uso:
    python pipeline/historico.py            # rápido: base guardada + temporada actual (ESPN) -> docs/data/historico*.csv
    python pipeline/historico.py --base     # reconstruye la base (engsoccerdata + transfermarkt-datasets) en data/historico/

Fuentes:
  - engsoccerdata: Liga 1928/29-2011/12 y Copa de Europa / Champions 1955-2012 (resultados)
  - transfermarkt-datasets (CC0): todas las competiciones oficiales 2012/13-2025/26, con alineaciones de los dos equipos
  - ESPN (API pública de su web): temporada actual, todas las competiciones
  - Alineaciones de la temporada actual: las de los eventos de WhoScored (docs/data/metricas_jugador.csv)
"""
import gzip, io, json, os, re, sys, unicodedata, urllib.request
from datetime import date
from pathlib import Path

import certifi
import numpy as np
import pandas as pd

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

BASE, WEB = Path("data/historico"), Path("docs/data")
RM, TM_RM, ESPN_RM = "Real Madrid", 418, 86
CORTE_TM = "2012-07-01"  # desde aquí manda Transfermarkt (todas las competiciones y alineaciones)
TM = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/"
TM_COMP = {"ES1": "LaLiga", "CL": "Champions League", "CDR": "Copa del Rey", "SUC": "Supercopa de España",
           "USC": "Supercopa de Europa", "KLUB": "Mundial de Clubes"}
COLS = ["fecha", "temporada", "competicion", "local", "visitante", "goles_local", "goles_visitante", "partido_id", "fuente",
        "estadio", "neutral", "id_local", "id_visitante", "logo_local", "logo_visitante"]
ESCUDO_TM = "https://tmssl.akamaized.net/images/wappen/head/{}.png"
# posición de Transfermarkt -> punto de un campo vertical (px: 0 banda izquierda, 1 derecha; py: 0 propia portería, 1 rival)
POS = {"Goalkeeper": (0.5, 0.06), "Sweeper": (0.5, 0.15), "Centre-Back": (0.5, 0.22), "Left-Back": (0.12, 0.28),
       "Right-Back": (0.88, 0.28), "Defender": (0.5, 0.25), "Defensive Midfield": (0.5, 0.40), "Central Midfield": (0.5, 0.53),
       "Left Midfield": (0.12, 0.55), "Right Midfield": (0.88, 0.55), "Midfield": (0.5, 0.53), "Attacking Midfield": (0.5, 0.67),
       "Left Winger": (0.15, 0.79), "Right Winger": (0.85, 0.79), "Second Striker": (0.5, 0.80), "Centre-Forward": (0.5, 0.89),
       "Attack": (0.5, 0.85)}


def colocar(al):
    """px/py de los titulares según su posición; si varios comparten posición, se reparten a lo ancho."""
    al = al.copy()
    al["px"], al["py"] = np.nan, np.nan
    tit = al[(al["titular"] == 1) & al["posicion"].isin(POS)]
    for _, grupo in tit.groupby(["partido_id", "equipo", "posicion"]):
        x0, y0 = POS[grupo["posicion"].iloc[0]]
        n = len(grupo)
        for i, idx in enumerate(grupo.sort_values("dorsal").index):
            al.loc[idx, "px"] = round(min(max(x0 + (i - (n - 1) / 2) * 0.22, 0.06), 0.94), 3)
            al.loc[idx, "py"] = y0
    return al


def estadio_madrid(fecha):
    """Campo del Madrid en casa antes de 2012 (las fuentes antiguas no traen estadio)."""
    if fecha < "1946-07-01":
        return "Campo de Chamartín"
    if fecha < "1947-12-14":
        return "Estadio Metropolitano"  # mientras se construía el nuevo Chamartín
    if fecha < "1955-01-04":
        return "Nuevo Estadio Chamartín"
    return "Santiago Bernabéu"


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=300).read()


def temporada(fecha):
    y, m = int(fecha[:4]), int(fecha[5:7])
    y0 = y if m >= 7 else y - 1
    return f"{y0}/{str(y0 + 1)[2:]}"


def words(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return [w for w in re.sub(r"[^a-z ]", " ", s).split() if w not in ("fc", "cf", "club", "de", "sad", "cd", "ud", "sd", "rc", "ca", "rcd")]


def unificar(nombres, canon):
    """Nombre de cada equipo en su forma canónica (la del histórico), si hay un candidato claro; si no, el suyo."""
    canon = sorted(set(canon))
    out = {}
    for n in set(nombres):
        if n in canon:
            out[n] = n
            continue
        a = set(words(n))
        sc = sorted(((len(a & set(words(c))), -len(set(words(c)) - a), c) for c in canon), reverse=True)
        ok = sc and sc[0][0] > 0 and (len(sc) == 1 or sc[0][:2] > sc[1][:2])
        out[n] = sc[0][2] if ok else n
    return out


def construir_base():
    BASE.mkdir(parents=True, exist_ok=True)
    gh = "https://raw.githubusercontent.com/jalapic/engsoccerdata/master/data-raw/"
    es = pd.read_csv(io.BytesIO(get(gh + "spain.csv")))
    es = es[((es["home"] == RM) | (es["visitor"] == RM)) & (es["Date"] < CORTE_TM)]
    liga = pd.DataFrame({"fecha": es["Date"], "competicion": "LaLiga", "local": es["home"], "visitante": es["visitor"],
                         "goles_local": es["hgoal"], "goles_visitante": es["vgoal"], "partido_id": "", "fuente": "engsoccerdata",
                         "neutral": False})
    ch = pd.read_csv(io.BytesIO(get(gh + "champs.csv")))
    ch = ch[((ch["home"] == RM) | (ch["visitor"] == RM)) & (ch["Date"] < CORTE_TM)]
    # en las eliminatorias con prórroga, el resultado final del partido incluye la prórroga
    gl = np.where(ch["aethgoal"].notna(), ch["aethgoal"], ch["hgoal"])
    gv = np.where(ch["aetvgoal"].notna(), ch["aetvgoal"], ch["vgoal"])
    europa = pd.DataFrame({"fecha": ch["Date"], "competicion": "Copa de Europa / Champions", "local": ch["home"], "visitante": ch["visitor"],
                           "goles_local": gl, "goles_visitante": gv, "partido_id": "", "fuente": "engsoccerdata",
                           "neutral": ch["round"].astype(str).str.lower().eq("final").values})

    g = pd.read_csv(io.BytesIO(gzip.decompress(get(TM + "games.csv.gz"))))
    g = g[((g["home_club_id"] == TM_RM) | (g["away_club_id"] == TM_RM)) & g["competition_id"].isin(TM_COMP) & (g["date"] >= CORTE_TM)]
    g = g[g["home_club_goals"].notna()]
    tm = pd.DataFrame({"fecha": g["date"], "competicion": g["competition_id"].map(TM_COMP).replace({"Champions League": "Copa de Europa / Champions"}),
                       "local": g["home_club_name"], "visitante": g["away_club_name"], "goles_local": g["home_club_goals"],
                       "goles_visitante": g["away_club_goals"], "partido_id": "tm" + g["game_id"].astype(str), "fuente": "transfermarkt",
                       "estadio": g["stadium"], "neutral": False, "id_local": g["home_club_id"], "id_visitante": g["away_club_id"]})
    # el Madrid se llama igual en todas las fuentes
    for c, cid in (("local", "home_club_id"), ("visitante", "away_club_id")):
        tm.loc[g[cid].values == TM_RM, c] = RM

    lin = pd.read_csv(io.BytesIO(gzip.decompress(get(TM + "game_lineups.csv.gz"))))
    lin = lin[lin["game_id"].isin(g["game_id"])]
    club = {**dict(zip(g["home_club_id"], tm["local"])), **dict(zip(g["away_club_id"], tm["visitante"]))}
    al = pd.DataFrame({"partido_id": "tm" + lin["game_id"].astype(str), "equipo": lin["club_id"].map(club).fillna(""),
                       "jugador": lin["player_name"], "posicion": lin["position"], "titular": (lin["type"] == "starting_lineup").astype(int),
                       "dorsal": pd.to_numeric(lin["number"], errors="coerce")})
    al = colocar(al)
    base = pd.concat([liga, europa, tm], ignore_index=True)
    base.to_csv(BASE / "base.csv", index=False)
    al.to_csv(BASE / "base_alineaciones.csv", index=False)
    print(f"base: {len(base)} partidos ({base['fecha'].min()} a {base['fecha'].max()}), {len(al)} filas de alineaciones")


def espn_actual():
    """Partidos oficiales jugados esta temporada, de la API pública de ESPN."""
    hoy = date.today()
    y0 = hoy.year if hoy.month >= 7 else hoy.year - 1
    j = json.loads(get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/teams/{ESPN_RM}/schedule?season={y0}"))
    filas = []
    for e in j.get("events", []):
        liga = (e.get("league") or {}).get("name") or (e.get("league") or {}).get("abbreviation") or ""
        comp = ("LaLiga" if "laliga" in liga.lower().replace(" ", "") else "Copa de Europa / Champions" if "champions" in liga.lower()
                else "Copa del Rey" if "copa del rey" in liga.lower() else "Supercopa de España" if "spanish super" in liga.lower() or "supercopa" in liga.lower()
                else "Supercopa de Europa" if "uefa super" in liga.lower() else "Mundial de Clubes" if "club world" in liga.lower() else None)
        c = e["competitions"][0]
        if comp is None or not c.get("status", e.get("status", {})).get("type", {}).get("completed"):
            continue  # amistosos y partidos sin jugar fuera
        eq = {t["homeAway"]: t for t in c["competitors"]}
        score = lambda t: int(float(t["score"]["value"] if isinstance(t["score"], dict) else t["score"]))
        logo = lambda t: t["team"].get("logo") or (t["team"].get("logos") or [{}])[0].get("href", "")
        filas.append({"fecha": e["date"][:10], "competicion": comp, "local": eq["home"]["team"]["displayName"],
                      "visitante": eq["away"]["team"]["displayName"], "goles_local": score(eq["home"]),
                      "goles_visitante": score(eq["away"]), "partido_id": "espn" + str(e["id"]), "fuente": "ESPN",
                      "estadio": (c.get("venue") or {}).get("fullName", ""), "neutral": bool(c.get("neutralSite")),
                      "logo_local": logo(eq["home"]), "logo_visitante": logo(eq["away"])})
    return pd.DataFrame(filas, columns=[c for c in COLS if c != "temporada"])


def main():
    if "--base" in sys.argv or not (BASE / "base.csv").exists():
        construir_base()
    base = pd.read_csv(BASE / "base.csv", dtype={"partido_id": str}).fillna({"partido_id": ""})
    al = pd.read_csv(BASE / "base_alineaciones.csv", dtype={"partido_id": str})
    actual = espn_actual()
    actual = actual[actual["fecha"] > base["fecha"].max()]
    h = pd.concat([base, actual], ignore_index=True)
    h["temporada"] = h["fecha"].map(temporada)

    # nombres de rival: los de la base más antigua (Liga con Liga, Europa con Europa)
    domestico = ~h["competicion"].isin(["Copa de Europa / Champions", "Supercopa de Europa", "Mundial de Clubes"])
    for mask in (domestico, ~domestico):
        canon = pd.concat([h.loc[mask & (h["fuente"] == "engsoccerdata"), c] for c in ("local", "visitante")])
        nombres = pd.concat([h.loc[mask, c] for c in ("local", "visitante")])
        m = unificar(nombres, canon)
        for c in ("local", "visitante"):
            h.loc[mask, c] = h.loc[mask, c].map(m)
        al.loc[al["partido_id"].isin(h.loc[mask, "partido_id"]), "equipo"] = al["equipo"].map(lambda n: m.get(n, n))
    # mismo club escrito distinto entre fuentes ("Barcelona" / "FC Barcelona"): se queda el nombre más reciente
    clave = lambda n: " ".join(sorted(words(n)))
    nombres = pd.concat([h[["fecha", c]].set_axis(["fecha", "nombre"], axis=1) for c in ("local", "visitante")], ignore_index=True)
    mejor = nombres.assign(k=nombres["nombre"].map(clave)).sort_values("fecha").groupby("k")["nombre"].last()
    for c in ("local", "visitante"):
        h[c] = h[c].map(lambda n: mejor.get(clave(n), n))
    al["equipo"] = al["equipo"].map(lambda n: mejor.get(clave(n), n))
    h.loc[h["local"].str.contains("Real Madrid"), "local"] = RM
    h.loc[h["visitante"].str.contains("Real Madrid"), "visitante"] = RM

    local = h["local"] == RM
    h["rival"] = np.where(local, h["visitante"], h["local"])
    h["condicion"] = np.where(local, "Local", "Visitante")
    h["goles_rm"] = np.where(local, h["goles_local"], h["goles_visitante"]).astype(int)
    h["goles_rival"] = np.where(local, h["goles_visitante"], h["goles_local"]).astype(int)
    h["goles_local"], h["goles_visitante"] = h["goles_local"].astype(int), h["goles_visitante"].astype(int)
    h["resultado"] = np.select([h["goles_rm"] > h["goles_rival"], h["goles_rm"] == h["goles_rival"]], ["V", "E"], "D")

    # estadio: el de la fuente; antes de 2012 solo se sabe el del Madrid en casa (deducido por fecha)
    h["estadio"] = h["estadio"].fillna("")
    deducir = (h["estadio"] == "") & (h["local"] == RM) & ~h["neutral"].fillna(False).astype(bool) & (h["fecha"] < CORTE_TM)
    h.loc[deducir, "estadio"] = h.loc[deducir, "fecha"].map(estadio_madrid)

    # alineaciones de esta temporada: las de los eventos de WhoScored (dorsal y posición media de cada titular)
    if (WEB / "alineaciones.csv").exists() and (WEB / "partidos.csv").exists():
        pj, aw = pd.read_csv(WEB / "partidos.csv"), pd.read_csv(WEB / "alineaciones.csv")
        liga = h[h["competicion"] == "LaLiga"].set_index("fecha")
        aw["fecha"] = aw["match_id"].map(dict(zip(pj["match_id"], pj["fecha"])))
        aw = aw[aw["fecha"].isin(liga.index)]
        aw["partido_id"] = aw["fecha"].map(liga["partido_id"])
        # el rival con el nombre del histórico
        aw["equipo"] = np.where(aw["equipo"] == RM, RM, aw["fecha"].map(liga["rival"]))
        aw = aw[aw["partido_id"].str.startswith("espn")]
        al = pd.concat([al, pd.DataFrame({"partido_id": aw["partido_id"], "equipo": aw["equipo"], "jugador": aw["jugador"],
                                          "posicion": aw["linea"].fillna(""), "titular": aw["titular"], "dorsal": aw["dorsal"],
                                          "px": aw["px"], "py": aw["py"]})], ignore_index=True)

    # escudos: el de Transfermarkt por id de club; si no hay, el logo de ESPN
    escudos = {}
    for lado in ("local", "visitante"):
        for n, i, lg in zip(h[lado], h[f"id_{lado}"], h[f"logo_{lado}"]):
            if pd.notna(i) and i != "":
                escudos[n] = ESCUDO_TM.format(int(float(i)))
            elif isinstance(lg, str) and lg and n not in escudos:
                escudos[n] = lg
    # los nombres de WhoScored (post-partido) también, emparejados con los del histórico
    if (WEB / "partidos.csv").exists():
        pj = pd.read_csv(WEB / "partidos.csv")
        ws_nombres = set(pj["local"]) | set(pj["visitante"])
        # el Madrid nunca es candidato: "Real Betis" no puede heredar su escudo por compartir "Real"
        for a, b in unificar(ws_nombres - {RM}, [n for n in escudos if n != RM]).items():
            # solo si todas sus palabras están en el otro nombre: "Atletico" -> "Atletico Madrid", nunca "Real Sociedad" -> "Real Betis"
            if b in escudos and set(words(a)) <= set(words(b)):
                escudos.setdefault(a, escudos[b])

    # autocomprobaciones
    assert h["partido_id"].replace("", np.nan).dropna().is_unique
    assert (h["local"] == RM).sum() + (h["visitante"] == RM).sum() == len(h), "partido sin el Madrid"
    assert not h.duplicated(["fecha", "competicion"]).any(), h[h.duplicated(["fecha", "competicion"], keep=False)]

    h = h.sort_values("fecha")[["fecha", "temporada", "competicion", "local", "visitante", "goles_local", "goles_visitante",
                                "rival", "condicion", "goles_rm", "goles_rival", "resultado", "estadio", "partido_id", "fuente"]]
    WEB.mkdir(parents=True, exist_ok=True)
    h.to_csv(WEB / "historico.csv", index=False)
    al["dorsal"] = pd.to_numeric(al["dorsal"], errors="coerce").astype("Int64")
    al[["partido_id", "equipo", "jugador", "posicion", "titular", "dorsal", "px", "py"]].to_csv(WEB / "historico_alineaciones.csv", index=False)
    pd.DataFrame(sorted(escudos.items()), columns=["equipo", "url"]).to_csv(WEB / "escudos.csv", index=False)
    print(f"Escudos: {len(escudos)} equipos; con estadio: {(h['estadio'] != '').sum()} de {len(h)} partidos")
    print(h.groupby("competicion").agg(partidos=("fecha", "size"), desde=("fecha", "min"), hasta=("fecha", "max")))
    print(f"{len(h)} partidos; alineaciones de {al['partido_id'].nunique()} partidos; temporada actual (ESPN): {len(actual)}")
    print("Rivales distintos:", h["rival"].nunique())


if __name__ == "__main__":
    main()
