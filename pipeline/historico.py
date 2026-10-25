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
import gzip, hashlib, io, json, os, re, sys, unicodedata, urllib.request
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
# cada posición: (línea del campo, lado). Línea -> altura (0 propia portería, 1 rival); lado ordena de izquierda a derecha
POS = {"Goalkeeper": (0, 1), "Sweeper": (1, 1), "Centre-Back": (1, 1), "Left-Back": (1, 0), "Right-Back": (1, 2), "Defender": (1, 1),
       "Defensive Midfield": (2, 1), "Central Midfield": (3, 1), "Left Midfield": (3, 0), "Right Midfield": (3, 2), "Midfield": (3, 1),
       "Attacking Midfield": (4, 1), "Second Striker": (4, 1), "Left Winger": (5, 0), "Right Winger": (5, 2), "Centre-Forward": (5, 1),
       "Attack": (5, 1)}
ALTURA = {0: 0.06, 1: 0.23, 2: 0.39, 3: 0.54, 4: 0.69, 5: 0.86}


def colocar(al):
    """px/py de los titulares: una fila por línea (defensa, mediocentro, medios, mediapunta, delanteros),
    ordenada de izquierda a derecha por su posición (y dorsal si coinciden) y repartida a lo ancho."""
    al = al.copy()
    al["px"], al["py"] = np.nan, np.nan
    tit = al[(al["titular"] == 1) & al["posicion"].isin(POS)].copy()
    tit["linea"] = tit["posicion"].map(lambda p: POS[p][0])
    tit["lado"] = tit["posicion"].map(lambda p: POS[p][1])
    tit = tit.sort_values(["lado", "dorsal"])
    tit["i"] = tit.groupby(["partido_id", "equipo", "linea"]).cumcount()
    n = tit.groupby(["partido_id", "equipo", "linea"])["i"].transform("size")
    al.loc[tit.index, "px"] = (0.1 + 0.8 * (tit["i"] + 0.5) / n).round(3)
    al.loc[tit.index, "py"] = tit["linea"].map(ALTURA)
    return al


def temporada_actual(h):
    """Partidos de esta temporada que analiza la web (Liga, Copa de Europa, Copa...): sus alineaciones de WhoScored y,
    si la fuente del histórico no trae goleadores, los de los eventos. Se emparejan por fecha: el Madrid juega uno al día."""
    if not ((WEB / "alineaciones.csv").exists() and (WEB / "partidos.csv").exists()):
        return h, pd.DataFrame()
    pj, aw = pd.read_csv(WEB / "partidos.csv"), pd.read_csv(WEB / "alineaciones.csv")
    hoy = h[h["partido_id"].astype(str).str.startswith("espn")].drop_duplicates("fecha").set_index("fecha")
    fecha_de = dict(zip(pj["match_id"], pj["fecha"]))
    aw["fecha"] = aw["match_id"].map(fecha_de)
    aw = aw[aw["fecha"].isin(hoy.index)]
    aw["partido_id"] = aw["fecha"].map(hoy["partido_id"])
    aw["equipo"] = np.where(aw["equipo"] == RM, RM, aw["fecha"].map(hoy["rival"]))  # el rival con el nombre del histórico
    al = colocar(pd.DataFrame({"partido_id": aw["partido_id"], "equipo": aw["equipo"], "jugador": aw["jugador"],
                               "posicion": aw["posicion"].fillna(""), "titular": aw["titular"], "dorsal": aw["dorsal"]}))
    if (WEB / "incidencias.csv").exists():
        inc = pd.read_csv(WEB / "incidencias.csv")
        inc = inc[inc["tipo"].isin(["gol", "penalti", "gol_pp"])].assign(fecha=lambda d: d["match_id"].map(fecha_de))
        txt = lambda gs: "; ".join(f"{r.jugador}{' (p.p.)' if r.tipo == 'gol_pp' else ''} {r.minuto}{' (pen.)' if r.tipo == 'penalti' else ''}"
                                   for r in gs.itertuples())
        for fecha, gs in inc[inc["fecha"].isin(hoy.index)].groupby("fecha"):
            i = h.index[h["partido_id"] == hoy.loc[fecha, "partido_id"]][0]
            if h.loc[i, "goleadores_local"] == "" and h.loc[i, "goleadores_visitante"] == "":
                rm, riv = txt(gs[gs["equipo"] == RM]), txt(gs[gs["equipo"] != RM])
                h.loc[i, ["goleadores_local", "goleadores_visitante"]] = (rm, riv) if h.loc[i, "local"] == RM else (riv, rm)
    return h, al


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


def get_wiki(url):
    # Wikimedia pide un User-Agent que identifique al proyecto
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "real-madrid-analytics/1.0 (github.com/feeeeer/real-madrid-analytics)"}), timeout=60).read()


def temporada(fecha):
    y, m = int(fecha[:4]), int(fecha[5:7])
    y0 = y if m >= 7 else y - 1
    return f"{y0}/{str(y0 + 1)[2:]}"


def words(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    # sin siglas ni artículos: "Deportivo de A Coruna" y "Deportivo La Coruna" son el mismo club
    return [w for w in re.sub(r"[^a-z ]", " ", s).split() if w not in ("fc", "cf", "club", "de", "sad", "cd", "ud", "sd", "rc", "ca", "rcd", "la", "el", "a", "del")]


def unificar(nombres, canon):
    """Nombre de cada equipo en su forma canónica (la del histórico), si hay un candidato claro; si no, el suyo."""
    canon = sorted(set(canon) - {RM})  # nadie hereda el nombre del Madrid ("Real Madrid Castilla" es otro equipo)
    out = {}
    for n in set(nombres):
        if n in canon:
            out[n] = n
            continue
        a = set(words(n))
        # candidato válido: un nombre contiene todas las palabras del otro y comparten al menos la mitad
        # ("Athletic Club" -> "Athletic Bilbao"); nunca "Manchester City" -> "Manchester United" ni "Grêmio Porto Alegrense" -> "FC Porto"
        cand = [c for c in canon if a and (a <= set(words(c)) or set(words(c)) <= a)
                and 2 * len(a & set(words(c))) >= max(len(a), len(set(words(c))))]
        sc = sorted(((len(a & set(words(c))), -len(set(words(c)) - a), c) for c in cand), reverse=True)
        ok = sc and (len(sc) == 1 or sc[0][:2] > sc[1][:2])
        out[n] = sc[0][2] if ok else n
    return out


# el mismo club con nombres que no se parecen entre fuentes (o demasiado largos para la tabla)
ALIAS = {"AFC Ajax": "Ajax Amsterdam", "APOEL Nikosia": "APOEL Nicosia", "Associazione Sportiva Roma": "AS Roma",
         "Internazionale": "Inter Milan", "Olympiakos Syndesmos Filathlon Peiraios": "Olympiacos",
         "Frankfurter SG Eintracht": "Eintracht Frankfurt", "Fußballclub Red Bull Salzburg": "Red Bull Salzburg",
         "Malmö Fotbollförening": "Malmö FF", "Al-Hilal Saudi Football Club": "Al-Hilal",
         "Club Atlético San Lorenzo de Almagro": "San Lorenzo", "Grêmio Foot-Ball Porto Alegrense": "Grêmio",
         # nombres de Wikipedia
         "RCD Español": "Espanyol Barcelona", "Club Atlético de Bilbao": "Athletic Bilbao", "F.C. Internazionale Milano": "Inter Milan",
         "Real Gijón": "Sporting Gijon", "Sport Club Corinthians Paulista": "Corinthians", "Aberdeen F.C.": "Aberdeen",
         "Torino F.C.": "Torino", "Málaga CF": "Málaga", "Real Madrid Castilla Club de Fútbol": "Real Madrid Castilla",
         "Real Madrid Castilla": "Real Madrid Castilla", "Agrupación Deportiva Almería": "AD Almeria", "Club Deportivo Badajoz": "CD Badajoz",
         "Bizcaya (football team)": "Club Bizcaya", "Athletic Madrid": "Atletico Madrid",
         # grafías antiguas de las páginas de la Copa en inglés
         "Arenas de Guecho": "Arenas de Getxo", "CD Patria Aragón": "Patria Aragón", "Eclipse FC": "Eclipse Fútbol Club"}
# partidos que Wikipedia da dos veces con fechas distintas: el de la fecha equivocada (la buena, en la página de la edición)
ERRATAS = {"wk0453276107": "1923: la vuelta con el Athletic fue el 8 de abril, no el 4",
           "wk8015bc5409": "1951: la vuelta con el Atlético fue el 10 de mayo; el 20 se jugó la semifinal con la Real Sociedad",
           "wk3d97e7ee9b": "1991: la vuelta con el Atlético fue el 27 de febrero, no el 20",
           # salieron al unificar "Sestao SC" y "Sestao Sport Club": cada copia tenía un nombre y la fecha un día cambiada
           "wk41c8bb472c": "1987: la ida con el Sestao fue el 11 de noviembre (crónica de Mundo Deportivo del 12), no el 10",
           "wkfea0ae74c6": "1987: la vuelta con el Sestao fue el 25 de noviembre (crónica del 26), no el 24"}
# el mismo club con dos nombres en el histórico (según la fuente); los que se parecen pero son clubes distintos
# (Burgos CF / Real Burgos, AD / UD Almería, Patria FC de Madrid / Patria Aragón) se quedan separados
MISMO_CLUB = {"Sparta Praha": "AC Sparta Praha", "Sestao SC": "Sestao Sport Club"}
# y partidos con el año mal puesto (es.wikipedia pone el año de la edición a los de diciembre): la fecha buena
FECHA_BUENA = {"we4b85603676": "1928-12-09", "we6e47995b5e": "1928-12-19"}  # Oviedo, dieciseisavos de la Copa de 1928-29 (en.wikipedia)
# nombres de las clasificaciones y de las Ligas antiguas que no se emparejan solos con su escudo, o se emparejarían mal
# ("Madrid FC" es el Madrid de 1920-1931, no el Atlético; "Donostia", la Real Sociedad de 1931-1939)
NOMBRE_CLUB = {"Madrid FC": RM, "Athletic Madrid": "Atletico Madrid", "Atlético Aviación": "Atletico Madrid", "Atlético Bilbao": "Athletic Bilbao",
               "Donostia": "Real Sociedad", "Español": "Espanyol Barcelona", "Gimnástico": "Gimnastic", "Lérida": "UE Lleida",
               "RC Deportivo": "Deportivo La Coruna", "Racing": "Racing Santander", "Real Santander": "Racing Santander",
               "Real Gijón": "Sporting Gijon", "Unión Club": "Real Union"}


# ---------- Wikipedia (data/historico/wikipedia/wikipedia_rm.json, extraído a mano de las páginas de temporada del Madrid,
# de las finales y de las temporadas de Liga; no se descarga aquí) ----------
WIKI = BASE / "wikipedia" / "wikipedia_rm.json"
INTERNACIONAL = ["Copa de Europa / Champions", "Supercopa de Europa", "Mundial de Clubes", "Copa de la UEFA", "Recopa de Europa",
                 "Copa Intercontinental", "Copa Intercontinental de la FIFA", "Copa Latina", "Copa Iberoamericana"]
POS_WIKI = {"GK": "Goalkeeper", "SW": "Sweeper", "CB": "Centre-Back", "CH": "Centre-Back", "RB": "Right-Back", "RWB": "Right-Back",
            "LB": "Left-Back", "LWB": "Left-Back", "DF": "Defender", "DM": "Defensive Midfield", "CM": "Central Midfield",
            "RH": "Right Midfield", "LH": "Left Midfield", "RM": "Right Midfield", "LM": "Left Midfield", "MF": "Midfield",
            "AM": "Attacking Midfield", "IR": "Second Striker", "IL": "Second Striker", "SS": "Second Striker", "OR": "Right Winger",
            "OL": "Left Winger", "RW": "Right Winger", "LW": "Left Winger", "RF": "Right Winger", "LF": "Left Winger",
            "CF": "Centre-Forward", "ST": "Centre-Forward", "FW": "Attack", "W": "Attack"}
ES_RM = r"^(?!.*(Castilla|Aficionados| B$))(Real Madrid|Madrid FC|Madrid CF|Madrid C\.F\.|Madrid Club de Fútbol)"  # sin filiales
MESES = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                     "october", "november", "december"], 1)}


RONDAS = [(r"third[- ]place", "Tercer puesto"), (r"semi", "Semifinales"), (r"quarter", "Cuartos de final"), (r"round of 16|eightfinal", "Octavos de final"),
          (r"round of 32", "Dieciseisavos de final"), (r"round of 64", "Treintaidosavos de final"), (r"knockout phase play", "Play-off"),
          (r"preliminary|qualif", "Ronda previa"), (r"second group", "Segunda fase de grupos"), (r"group ([a-h])\b", "Grupo {}"),
          (r"group", "Fase de grupos"), (r"league phase", "Fase liga"), (r"first round", "Primera ronda"), (r"second round", "Segunda ronda"),
          (r"third round", "Tercera ronda"), (r"fourth round", "Cuarta ronda"), (r"fifth round", "Quinta ronda"), (r"sixth round", "Sexta ronda"),
          (r"knockout", "Eliminatorias"), (r"\bfinal", "Final")]


def ronda_es(ronda, seccion, comp):
    """Ronda en castellano: la del encabezado de la página ("Quarter-finals") o la de la caja ("Final"), más ida/vuelta/desempate."""
    if comp == "LaLiga":
        return f"Jornada {ronda}" if ronda.isdigit() else ""
    base = ""
    for texto in (*reversed(seccion.split(" > ")), ronda):
        for patron, es in RONDAS:
            m = re.search(patron, texto, re.I)
            if m:
                base = es.format(m[1].upper()) if "{}" in es else es
                break
        if base:
            break
    vuelta = re.search(r"first leg|1st leg|second leg|2nd leg|replay|tie[- ]?breaker|play-?off", f"{ronda} {seccion.split(' > ')[-1]}", re.I)
    leg = {"f": "ida", "1": "ida", "s": "vuelta", "2": "vuelta"}.get(vuelta[0][0].lower(), "desempate") if vuelta else ""
    if base and leg and base != "Play-off":
        return f"{base} ({leg})"
    return base or (leg.capitalize() if leg else "")


def fecha_wiki(s):
    """Fecha de una caja de partido de Wikipedia: {{Start date|1962|5|2}}, '2 May 1962' o 'May 2, 1962'."""
    m = re.search(r"\{\{\s*(?:start date|dts)[^|]*\|(\d{4})\|(\d{1,2})\|(\d{1,2})", s, re.I)
    if m:
        return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
    s = re.sub(r"\[\[[^\]|]*\|?([^\]]*)\]\]", r"\1", s)
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s) or re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if not m:
        return ""
    d, mes, y = (m[1], m[2], m[3]) if m[1].isdigit() else (m[2], m[1], m[3])
    return f"{y}-{MESES[mes.lower()]:02d}-{int(d):02d}" if mes.lower() in MESES else ""


def wikipedia_es(h, filas, rival_de, goleadores):
    """Partidos de las páginas de cada edición de Copa y Supercopa en es.wikipedia: completan los que ya hay
    (estadio, goleadores, ronda) y añaden los que faltan. Las fechas de las tablas de ida y vuelta salen del texto de cada ronda,
    así que se empareja con margen (60 días, mismo marcador y mismo campo)."""
    e = pd.DataFrame(filas)
    if e.empty:
        return h
    e = e[(e["fecha"] != "") & (e["local"] != "") & (e["visita"] != "")].drop_duplicates(["comp", "fecha", "local_t", "visita_t"])
    for c in ("local_t", "visita_t"):  # "Club Deportivo Badajoz (1905-2012)", "Palencia Club de Fútbol" -> nombre corto
        e[c] = e[c].str.replace(r"\s*\(.*\)$", "", regex=True).str.replace(r" Club de Fútbol$", "", regex=True).str.strip()
    e["rm_local"] = e["local"].str.contains(r"Madrid F\.? ?C|Real Madrid|Madrid C\. ?F|Madrid Club", regex=True) & ~e["local"].str.contains("Castilla|Atl")
    e["g_rm"] = np.where(e["rm_local"], e["gl"], e["gv"]).astype(int)
    e["g_riv"] = np.where(e["rm_local"], e["gv"], e["gl"]).astype(int)
    e["rival_t"] = np.where(e["rm_local"], e["visita_t"], e["local_t"])
    e["ronda_es"] = [f"{s} ({r.lower()})" if s and r in ("Ida", "Vuelta") else (r or s) for s, r in zip(e["seccion"], e["ronda"])]
    for c in ("goles_l", "goles_v"):
        # "Laca 3,2T,2T": los "2T" (segundo tiempo, sin minuto) fuera
        e[c] = [goleadores(re.sub(r",?\b\d+T\b", "", re.sub(r"^\*\s*|\s\*\s*", " ", g)).strip(), f) for g, f in zip(e[c], e["fecha"])]
    rm_l = h["local"].str.contains("Real Madrid") & ~h["local"].str.contains("Castilla")
    h_rm = np.where(rm_l, h["goles_local"], h["goles_visitante"]).astype(int)
    h_riv = np.where(rm_l, h["goles_visitante"], h["goles_local"]).astype(int)
    hf, usados, nuevos, n_ok = pd.to_datetime(h["fecha"]), set(), [], 0
    for r in e.itertuples():
        dif = (hf - pd.Timestamp(r.fecha)).abs()
        # mismo campo; o el mismo día con local y visitante cambiados (1904: el 5-5 es local en una página y visitante en otra)
        cand = h.index[(h["competicion"] == r.comp) & (dif <= pd.Timedelta(days=60)) & (h_rm == r.g_rm) & (h_riv == r.g_riv)
                       & ((rm_l == r.rm_local) | (dif <= pd.Timedelta(days=1)))]
        # y el mismo rival (alguna palabra en común: "Valencia C. F." / "Valencia CF"), para no confundir dos eliminatorias
        rw = set(words(rival_de.get(r.rival_t, r.rival_t))) | set(words(r.rival_t))
        cand = [i for i in cand if i not in usados and rw & set(words(h.loc[i, "visitante"] if rm_l[i] else h.loc[i, "local"]))]
        if cand:
            i = min(cand, key=lambda i: dif[i])
            usados.add(i)
            n_ok += 1
            for col, val in (("estadio", r.estadio), ("ronda", r.ronda_es)):
                if val and (pd.isna(h.loc[i, col]) or h.loc[i, col] == ""):
                    h.loc[i, col] = val
            if r.goles_l or r.goles_v:
                if h.loc[i, "goleadores_local"] == "" and h.loc[i, "goleadores_visitante"] == "":
                    h.loc[i, ["goleadores_local", "goleadores_visitante"]] = r.goles_l, r.goles_v
            rival_de.setdefault(r.rival_t, h.loc[i, "visitante"] if rm_l[i] else h.loc[i, "local"])
        elif not ((h["competicion"] == r.comp) & (dif <= pd.Timedelta(days=4)) & (rm_l == r.rm_local)).any():
            nuevos.append(r)  # sin otro partido del Madrid en ese campo esos días (si lo hay, es el mismo con otro marcador o fecha)
    n = pd.DataFrame([{"fecha": r.fecha, "competicion": r.comp, "goles_local": int(r.gl), "goles_visitante": int(r.gv),
                       "local": RM if r.rm_local else rival_de.get(r.local_t, r.local_t),
                       "visitante": rival_de.get(r.visita_t, r.visita_t) if r.rm_local else RM,
                       "partido_id": "we" + hashlib.md5(f"{r.fecha}{r.comp}{r.local_t}{r.visita_t}".encode()).hexdigest()[:10],
                       "fuente": "wikipedia", "neutral": False, "estadio": r.estadio, "ronda": r.ronda_es, "penaltis": "",
                       "goleadores_local": r.goles_l, "goleadores_visitante": r.goles_v} for r in nuevos])
    if len(n):
        n = n[(n["local"] != "") & (n["visitante"] != "")]
    print(f"Wikipedia (es): {n_ok} partidos completados, {len(n)} añadidos ({n.groupby('competicion').size().to_dict() if len(n) else {}})")
    return pd.concat([h, n], ignore_index=True) if len(n) else h


def wikipedia(h, al):
    """Completa el histórico con Wikipedia: añade los partidos que no están (copas antes de 2012, Recopa, UEFA, Intercontinental...),
    pone ronda, goleadores, penaltis y estadio a los que sí están y las alineaciones de las finales.
    Devuelve h, al, la clasificación de cada Liga y el palmarés."""
    d = json.loads(WIKI.read_text())
    w = pd.DataFrame(d["partidos"], columns=d["partidos_cols"])
    # Copa del Rey de las páginas de cada edición en en.wikipedia (copa_en.json): cajas de partido y tablas de ida y vuelta
    if (WIKI.parent / "copa_en.json").exists():
        c = pd.DataFrame(json.loads((WIKI.parent / "copa_en.json").read_text())["copa_en"])
        vuelta = c["pata"] == "2"  # la vuelta se juega en casa del segundo equipo y su marcador va con el local primero
        w = pd.concat([w, pd.DataFrame({
            "fecha": c["fecha"], "competicion": c["comp"], "ronda": c["ronda"],
            "local": np.where(vuelta, c["t2"], c["t1"]), "local_wiki": np.where(vuelta, c["t2w"], c["t1w"]),
            "visitante": np.where(vuelta, c["t1"], c["t2"]), "visitante_wiki": np.where(vuelta, c["t1w"], c["t2w"]),
            "goles_local": c["g1"], "goles_visitante": c["g2"], "penaltis": "", "estadio": c["estadio"], "ciudad": "",
            "goleadores_local": c["goles1"], "goleadores_visitante": c["goles2"],
            "fecha_aprox": c["fecha_aprox"].fillna("") if "fecha_aprox" in c else "",  # fecha estimada por la ronda (copa_antigua.py)
            "seccion": c["seccion"] + np.where(c["pata"] == "1", " > First leg", np.where(vuelta, " > Second leg", ""))})], ignore_index=True)
        w = w[w["local_wiki"].str.match(ES_RM) | w["visitante_wiki"].str.match(ES_RM) | w["local"].str.match(ES_RM) | w["visitante"].str.match(ES_RM)]
    w = w.drop_duplicates(["fecha", "competicion", "local_wiki", "visitante_wiki"])
    # el mismo partido en la página de la temporada y en la de la edición (nombres distintos): se queda el primero
    w = w[~w.duplicated(["fecha", "competicion", "goles_local", "goles_visitante"])]
    w[["goles_local", "goles_visitante"]] = w[["goles_local", "goles_visitante"]].astype(int)
    w["rm_local"] = w["local_wiki"].str.match(ES_RM) | w["local"].str.match(ES_RM)
    assert (w["rm_local"] | w["visitante_wiki"].str.match(ES_RM) | w["visitante"].str.match(ES_RM)).all(), "partido de Wikipedia sin el Madrid"
    w["g_rm"] = np.where(w["rm_local"], w["goles_local"], w["goles_visitante"])
    w["g_riv"] = np.where(w["rm_local"], w["goles_visitante"], w["goles_local"])
    pen = w["penaltis"].str.extract(r"(\d+)-(\d+)").fillna(0).astype(int)
    w["p_rm"] = np.where(w["rm_local"], pen[0], pen[1])
    w["p_riv"] = np.where(w["rm_local"], pen[1], pen[0])
    w["rival_wiki"] = np.where(w["rm_local"], w["visitante_wiki"], w["local_wiki"])
    # estadio sin referencias ni ciudad ("Santiago Bernabéu Stadium, Madrid" -> "Santiago Bernabéu")
    w["estadio"] = (w["estadio"].str.replace(r"\s*\[http\S*.*$", "", regex=True).str.replace(r",.*$", "", regex=True)
                    .str.replace(r"^(Estadio )?Santiago Bernab[eé]u( Stadium)?$", "Santiago Bernabéu", regex=True).str.strip(" ,"))
    for c in ("ronda", "goleadores_local", "goleadores_visitante"):
        w[c] = w[c].str.replace(r"\[\[[^\]|]*\|?([^\]]*)\]\]?|\*", r"\1", regex=True).str.strip(" ;")
    w["ronda"] = [ronda_es(r, sec, c) for r, sec, c in zip(w["ronda"], w["seccion"], w["competicion"])]
    # el mismo partido en dos páginas con local y visitante cambiados (4-1 y 1-4), o con un gol de menos en el mismo campo:
    # se queda el que trae más goleadores, que cuadran con el marcador (1916: el 2-0 da un goleador al que no marcó), y la ronda.
    # La ida y la vuelta con la misma fecha por error (1954, 1961) siguen siendo dos partidos: cambian el marcador y el estadio
    nombres = {lado: w[f"goleadores_{lado}"].fillna("").str.count(r"[^;]+") for lado in ("local", "visitante")}
    datos = sum(2 * n + 3 * (n == w[f"goles_{lado}"]) for lado, n in nombres.items()) + (w["ronda"] != "")
    w = w.loc[datos.sort_values(ascending=False, kind="stable").index]
    w = w[~w.duplicated(["fecha", "competicion", "g_rm", "g_riv"]) & ~w.duplicated(["fecha", "competicion", "rival_wiki", "estadio"])].sort_index()

    def goleadores(s, fecha):
        # "Ramos , 90+3; Khedira; Bale 110" -> "Ramos 90+3; Bale 110": desde 1990 las páginas meten tarjetas y tandas de penaltis
        # en la misma lista, así que solo cuenta quien tiene minuto
        out = []
        s = re.sub(r"\s*\[\[Penalty kick[^,;\]]*\]?\]?", " (pen.)", s)  # restos de enlaces: "76 [[Penalty kick (association football),90"
        s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]|\[\[|\]\]", r"\1", s)
        for g in s.split(";"):
            g = re.sub(r"\s+,\s*", " ", g).strip()
            if g and (fecha < "1990" or re.search(r"\d", g)):
                out.append(g)
        return "; ".join(out)
    for c in ("goleadores_local", "goleadores_visitante"):
        w[c] = [goleadores(s, f) for s, f in zip(w[c], w["fecha"])]

    for c in ("ronda", "penaltis", "goleadores_local", "goleadores_visitante"):
        h[c] = ""
    rm_l = h["local"].str.contains("Real Madrid") & ~h["local"].str.contains("Castilla")
    h_rm = np.where(rm_l, h["goles_local"], h["goles_visitante"]).astype(int)
    h_riv = np.where(rm_l, h["goles_visitante"], h["goles_local"]).astype(int)
    hf, usados, nuevos, rival_de = pd.to_datetime(h["fecha"]), set(), [], {}
    for r in w.itertuples():
        # el mismo partido: misma competición, ±4 días (las fechas antiguas no siempre coinciden) y mismo marcador,
        # o el marcador con la tanda de penaltis sumada (Transfermarkt la mete en los goles)
        cand = h.index[(h["competicion"] == r.competicion) & ((hf - pd.Timestamp(r.fecha)).abs() <= pd.Timedelta(days=4))
                       & (((h_rm == r.g_rm) & (h_riv == r.g_riv)) | ((h_rm == r.g_rm + r.p_rm) & (h_riv == r.g_riv + r.p_riv)))]
        cand = [i for i in cand if i not in usados]
        if cand:
            i = min(cand, key=lambda i: abs(hf[i] - pd.Timestamp(r.fecha)))
            usados.add(i)
            mismo_local = rm_l[i] == r.rm_local
            h.loc[i, ["goles_local", "goles_visitante"]] = (r.goles_local, r.goles_visitante) if mismo_local else (r.goles_visitante, r.goles_local)
            h.loc[i, "penaltis"] = r.penaltis if mismo_local or not r.penaltis else "-".join(r.penaltis.split("-")[::-1])
            h.loc[i, "ronda"] = r.ronda
            gl, gv = (r.goleadores_local, r.goleadores_visitante) if mismo_local else (r.goleadores_visitante, r.goleadores_local)
            h.loc[i, ["goleadores_local", "goleadores_visitante"]] = gl, gv
            if pd.isna(h.loc[i, "estadio"]) or h.loc[i, "estadio"] == "":
                h.loc[i, "estadio"] = r.estadio
            rival_de.setdefault(r.rival_wiki, h.loc[i, "visitante"] if rm_l[i] else h.loc[i, "local"])
        elif r.competicion not in ("Copa de Europa / Champions", "LaLiga"):  # Liga y Copa de Europa ya están enteras
            nuevos.append(r)
    n = pd.DataFrame([{"fecha": r.fecha, "competicion": r.competicion, "goles_local": r.goles_local, "goles_visitante": r.goles_visitante,
                       "local": RM if r.rm_local else r.local_wiki, "visitante": r.visitante_wiki if r.rm_local else RM,
                       "partido_id": "wk" + hashlib.md5(f"{r.fecha}{r.competicion}{r.local_wiki}{r.visitante_wiki}".encode()).hexdigest()[:10],
                       "fuente": "wikipedia", "neutral": False, "estadio": r.estadio, "ronda": r.ronda, "penaltis": r.penaltis,
                       "goleadores_local": r.goleadores_local, "goleadores_visitante": r.goleadores_visitante,
                       "fecha_aprox": getattr(r, "fecha_aprox", "") if isinstance(getattr(r, "fecha_aprox", ""), str) else ""} for r in nuevos])
    # el rival con el nombre que ya tiene en el histórico (aprendido de los partidos emparejados)
    for c in ("local", "visitante"):
        n[c] = n[c].map(lambda x: rival_de.get(x, x))
    n = n[(n["local"] != "") & (n["visitante"] != "")]  # cajas sin nombre de rival
    print(f"Wikipedia: {len(usados)} partidos completados, {len(n)} añadidos ({n.groupby('competicion').size().to_dict()})")
    h = pd.concat([h, n], ignore_index=True)
    h = wikipedia_es(h, d.get("es_partidos", []), rival_de, goleadores)

    # finales que no están en las páginas de temporada (Supercopa de 1997...): se añaden con su página de final
    limpio = lambda x: re.sub(r"\{\{[^}]*\}\}|\[\[[^\]|]*\||[\[\]']", "", x.replace("&ndash;", "–")).strip()
    extra = []
    for f in d["finales"]:
        fecha, sc = fecha_wiki(f["fecha"]), re.search(r"(\d+)\s*[–\-−]\s*(\d+)", limpio(f["marcador"]))
        comp = COMP_PALMARES.get(f["clave"].split("|")[0], "")
        if not (fecha and sc and comp) or ((pd.to_datetime(h["fecha"]) - pd.Timestamp(fecha)).abs() <= pd.Timedelta(days=1)).any() \
                or any(e["fecha"] == fecha for e in extra):
            continue
        e1, e2 = limpio(f["e1"]), limpio(f["e2"])
        rm1 = bool(re.match(ES_RM, e1))
        if not (rm1 or re.match(ES_RM, e2)):
            continue  # página de otra final (otro año)
        extra.append({"fecha": fecha, "competicion": comp, "local": RM if rm1 else e1, "visitante": e2 if rm1 else RM,
                      "goles_local": int(sc[1]), "goles_visitante": int(sc[2]), "estadio": limpio(f["estadio"]), "fuente": "wikipedia",
                      "neutral": False, "ronda": "Final", "partido_id": "wk" + hashlib.md5(f"{fecha}{comp}".encode()).hexdigest()[:10]})
    if extra:
        extra = pd.DataFrame(extra)
        for c in ("local", "visitante"):
            extra[c] = extra[c].map(lambda x: rival_de.get(x, x))
        print(f"Wikipedia: {len(extra)} finales añadidas desde su página: {extra[['fecha', 'competicion']].values.tolist()}")
        h = pd.concat([h, extra], ignore_index=True).fillna({c: "" for c in ("penaltis", "goleadores_local", "goleadores_visitante")})

    # alineaciones de las finales (las que no tenga ya Transfermarkt)
    filas = []
    con_al = set(al["partido_id"])
    hf = pd.to_datetime(h["fecha"])
    for f in d["finales"]:
        n1, n2 = {j["nombre"] for j in f["l1"]}, {j["nombre"] for j in f["l2"]}
        if n1 & n2 or sum(j["titular"] for j in f["l1"]) != 11 or sum(j["titular"] for j in f["l2"]) != 11:
            continue  # tabla mal leída de Wikipedia (los dos equipos con los mismos jugadores o sin once completo)
        fecha = fecha_wiki(f["fecha"])
        cand = h.index[(hf - pd.Timestamp(fecha)).abs() <= pd.Timedelta(days=1)] if fecha else []
        if len(cand) != 1:
            continue
        i = cand[0]
        pid = h.loc[i, "partido_id"]
        if pid in con_al:
            continue
        con_al.add(pid)  # una final puede venir dos veces (palmarés de campeón y de subcampeón)
        rm1 = bool(re.match(ES_RM, limpio(f["e1"])))
        if not (rm1 or re.match(ES_RM, limpio(f["e2"]))):
            continue
        rival = h.loc[i, "visitante"] if h.loc[i, "local"] == RM else h.loc[i, "local"]
        for lado, equipo in ((f["l1"], RM if rm1 else rival), (f["l2"], rival if rm1 else RM)):
            for j in lado:
                filas.append({"partido_id": pid, "equipo": equipo, "jugador": j["nombre"], "posicion": POS_WIKI.get(j["pos"], ""),
                              "titular": j["titular"], "dorsal": pd.to_numeric(j["num"], errors="coerce")})
    if filas:
        al = pd.concat([al, colocar(pd.DataFrame(filas))], ignore_index=True)
    print(f"Wikipedia: alineaciones de {len({f['partido_id'] for f in filas})} finales")

    ligas = pd.DataFrame([[f"{k[:4]}/{k[5:]}", *fila.split("|")] for k, v in d["ligas"].items() for fila in v],
                         columns=["temporada", "pos", "equipo", "pj", "g", "e", "p", "gf", "gc", "pts"])
    palmares = pd.DataFrame([{"competicion": c["comp"], "tipo": tipo, "etiqueta": et, "pagina": pg}
                             for c in d["palmares"] if c.get("comp") for tipo, lista in (("Campeón", c["titulos"]), ("Subcampeón", c["sub"]))
                             for et, pg in lista])
    return h, al, ligas, palmares


# palmarés de Wikipedia -> competición del histórico
COMP_PALMARES = {"Primera División de España": "LaLiga", "Copa del Rey": "Copa del Rey", "Supercopa de España": "Supercopa de España",
                 "Copa de la Liga": "Copa de la Liga", "Copa Eva Duarte": "Copa Eva Duarte", "Liga de Campeones": "Copa de Europa / Champions",
                 "Liga Europa": "Copa de la UEFA", "Recopa de Europa": "Recopa de Europa", "Supercopa de Europa": "Supercopa de Europa",
                 "Copa Intercontinental": "Copa Intercontinental", "Copa Intercontinental de la FIFA": "Copa Intercontinental de la FIFA",
                 "Copa Mundial de Clubes": "Mundial de Clubes", "Copa Latina": "Copa Latina", "Copa Iberoamericana": "Copa Iberoamericana"}
NACIONAL = {"Primera División de España", "Copa del Rey", "Supercopa de España", "Copa de la Liga", "Copa Eva Duarte"}
REGIONAL = {"Campeonato de Madrid / Centro", "Trofeo Mancomunado", "Copa Federación Centro"}
OTROS = {"Pequeña Copa del Mundo", "Copa Ibérica"}  # torneos no oficiales


def titulos(palmares, h):
    """Cada título y subcampeonato con la temporada del histórico en que se jugó (para enlazar sus partidos)."""
    t = palmares[palmares["competicion"].isin(set(COMP_PALMARES) | REGIONAL | OTROS)].copy()
    t["comp_hist"] = t["competicion"].map(COMP_PALMARES).fillna("")
    t["grupo"] = np.select([t["competicion"].isin(NACIONAL), t["competicion"].isin(REGIONAL), t["competicion"].isin(OTROS)],
                           ["Nacional", "Regional", "Otros"], "Internacional")

    def anio(etiqueta):  # "1962" -> 1962, "1957-58" -> 1958
        m = re.match(r"(\d{4})(?:-(\d{2}))?$", etiqueta)
        return int(m[1][:2] + m[2]) if m and m[2] else int(etiqueta[:4])

    # cada copa: su final (el partido de esa competición marcado como final en el año del título; si no, el último de ese año)
    # y la edición, los partidos de esa competición en los 11 meses anteriores a la final
    finales, usadas = {}, {}
    # primero los años exactos; después, los que no tienen partido ese año, con el año vecino
    # (la Copa Eva Duarte de 1947 se jugó en 1948) si no es el de otro título de la misma competición
    for pasada in ((0,), (1, -1)):
        for r in t.itertuples():
            if not r.comp_hist or r.comp_hist == "LaLiga" or r.Index in finales:
                continue
            y, p = anio(r.etiqueta), h[h["competicion"] == r.comp_hist]
            for yy in (y + d for d in pasada):
                x = p[p["fecha"].str[:4] == str(yy)]
                fin = x[x["ronda"].str.startswith("Final")]
                fecha = (fin if len(fin) else x)["fecha"].max() if len(x) else None
                if fecha and fecha not in usadas.get(r.comp_hist, set()):
                    finales[r.Index] = fecha
                    usadas.setdefault(r.comp_hist, set()).add(fecha)
                    break
    t["hasta"] = [finales.get(i, "") for i in t.index]
    t["desde"] = [(pd.Timestamp(f) - pd.Timedelta(days=330)).strftime("%Y-%m-%d") if f else "" for f in t["hasta"]]
    liga = t["comp_hist"] == "LaLiga"
    t["temporada"] = np.where(liga, t["pagina"].str.extract(r"(\d{4})-(\d{2})").apply(lambda m: f"{m[0]}/{m[1]}" if pd.notna(m[0]) else "", axis=1),
                              t["hasta"].map(lambda f: temporada(f) if f else ""))
    return t[["grupo", "competicion", "comp_hist", "tipo", "etiqueta", "temporada", "desde", "hasta"]]


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
    al = colocar(pd.read_csv(BASE / "base_alineaciones.csv", dtype={"partido_id": str}))
    actual = espn_actual()
    actual = actual[actual["fecha"] > base["fecha"].max()]
    h = pd.concat([base, actual], ignore_index=True)
    h[["local", "visitante"]] = h[["local", "visitante"]].replace(ALIAS)
    al["equipo"] = al["equipo"].replace(ALIAS)
    # todos los partidos con id, también los antiguos, para poder enlazar alineaciones y títulos
    sin_id = h["partido_id"].fillna("") == ""
    h.loc[sin_id, "partido_id"] = ["h" + hashlib.md5(f"{f}{c}".encode()).hexdigest()[:10]
                                   for f, c in zip(h.loc[sin_id, "fecha"], h.loc[sin_id, "competicion"])]
    h, al, ligas, palmares = wikipedia(h, al)
    h[["local", "visitante"]] = h[["local", "visitante"]].replace(ALIAS)
    h["temporada"] = h["fecha"].map(temporada)

    # nombres de rival: los de la base más antigua (Liga con Liga, Europa con Europa)
    domestico = ~h["competicion"].isin(INTERNACIONAL)
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
    # el Madrid se llama igual en todas las fuentes (su filial, el Castilla, no)
    h.loc[h["local"].str.contains("Real Madrid") & ~h["local"].str.contains("Castilla"), "local"] = RM
    h.loc[h["visitante"].str.contains("Real Madrid") & ~h["visitante"].str.contains("Castilla"), "visitante"] = RM

    local = h["local"] == RM
    h["rival"] = np.where(local, h["visitante"], h["local"])
    h["condicion"] = np.where(local, "Local", "Visitante")
    h["goles_rm"] = np.where(local, h["goles_local"], h["goles_visitante"]).astype(int)
    h["goles_rival"] = np.where(local, h["goles_visitante"], h["goles_local"]).astype(int)
    h["goles_local"], h["goles_visitante"] = h["goles_local"].astype(int), h["goles_visitante"].astype(int)
    h["resultado"] = np.select([h["goles_rm"] > h["goles_rival"], h["goles_rm"] == h["goles_rival"]], ["V", "E"], "D")

    # el mismo partido traído dos veces de Wikipedia (página de temporada y de edición, con un día de diferencia):
    # mismo rival, campo y marcador en ±3 días -> se queda el de la fuente más fiable (engsoccer/Transfermarkt antes que Wikipedia)
    h["_orden"] = np.select([h["fuente"] != "wikipedia", h["partido_id"].str.startswith("wk")], [0, 1], 2)
    h = h.sort_values(["_orden", "fecha"]).reset_index(drop=True)
    hf, quitar = pd.to_datetime(h["fecha"]), {}
    for _, g in h.groupby(["competicion", "rival", "condicion", "goles_rm", "goles_rival"]):
        if len(g) < 2:
            continue
        for i in g.index:
            if i in quitar:
                continue
            for j in g.index[g.index > i]:
                if j not in quitar and abs(hf[i] - hf[j]) <= pd.Timedelta(days=3) and h.loc[j, "fuente"] == "wikipedia":
                    quitar[j] = i
    # sus alineaciones pasan al partido que se queda (si no tenía)
    ids = h["partido_id"]
    con_al = set(al["partido_id"])
    for j, i in quitar.items():
        if ids[j] in con_al and ids[i] not in con_al:
            al.loc[al["partido_id"] == ids[j], "partido_id"] = ids[i]
    al = al[~al["partido_id"].isin({ids[j] for j in quitar} - {ids[i] for i in quitar.values()})]
    print(f"Duplicados de Wikipedia quitados: {len(quitar)}")
    h = h.drop(index=list(quitar)).drop(columns="_orden")

    # estadio: el de la fuente; antes de 2012 solo se sabe el del Madrid en casa (deducido por fecha)
    h["estadio"] = h["estadio"].fillna("")
    deducir = (h["estadio"] == "") & (h["local"] == RM) & ~h["neutral"].fillna(False).astype(bool) & (h["fecha"] < CORTE_TM)
    h.loc[deducir, "estadio"] = h.loc[deducir, "fecha"].map(estadio_madrid)
    # fuera de casa sin estadio: el campo del rival en su visita más cercana en el tiempo (máx. 3 años), salvo finales y partidos neutrales
    fuera = (h["condicion"] == "Visitante") & ~h["ronda"].str.startswith("Final") & ~h["neutral"].fillna(False).astype(bool)
    conocidos = h[fuera & (h["estadio"] != "")]
    hf = pd.to_datetime(h["fecha"])
    for i in h.index[fuera & (h["estadio"] == "")]:
        c = conocidos[conocidos["rival"] == h.loc[i, "rival"]]
        if len(c):
            dif = (pd.to_datetime(c["fecha"]) - hf[i]).abs()
            if dif.min() <= pd.Timedelta(days=3 * 365):
                h.loc[i, "estadio"] = c.loc[dif.idxmin(), "estadio"]

    # esta temporada: alineaciones y goleadores de los partidos analizados en la web (todas las competiciones)
    h, al_temp = temporada_actual(h)
    al = pd.concat([al, al_temp], ignore_index=True)

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
    # clubes antiguos sin id de Transfermarkt en nuestras fuentes: tabla a mano (ids de Transfermarkt sacados de Wikidata, o el escudo de Wikipedia)
    escudos.update(dict(pd.read_csv(BASE / "escudos_manual.csv").values))
    # los nombres de las clasificaciones (ESPN, Understat), las Ligas antiguas (Wikipedia) y los próximos partidos, con el escudo de su club
    otros = set(ligas["equipo"].dropna())
    for f in ("competicion.csv", "proximos.csv"):
        if (WEB / f).exists():
            d = pd.read_csv(WEB / f)
            otros |= set(d["local"].dropna()) | set(d["visitante"].dropna())
    auto = unificar(otros - set(escudos), [n for n in escudos if n != RM])
    for a in otros - set(escudos):
        b = NOMBRE_CLUB.get(a, auto.get(a))
        if b in escudos and (a in NOMBRE_CLUB or set(words(a)) <= set(words(b))):
            escudos[a] = escudos[b]
    print("Sin escudo:", sorted((set(h["local"]) | set(h["visitante"])) - set(escudos)))

    # el mismo partido con dos fechas en Wikipedia (comprobado en la página de cada edición): se quita el de la fecha mala
    h = h[~h["partido_id"].isin(ERRATAS)]
    for c in ("local", "visitante", "rival"):  # el mismo club con dos nombres según la fuente: uno solo en el cara a cara
        h[c] = h[c].replace(MISMO_CLUB)
    for pid, f in FECHA_BUENA.items():
        h.loc[h["partido_id"] == pid, ["fecha", "temporada"]] = f, temporada(f)
    hf = pd.to_datetime(h["fecha"])
    for _, g in h.assign(f=hf).sort_values("f").groupby(["competicion", "rival", "condicion", "goles_rm", "goles_rival"]):
        cerca = g["f"].diff().dt.days.le(10)
        if cerca.any():  # mismo rival, campo y resultado con días de diferencia: casi siempre una errata de fecha
            print("Posible partido repetido, revisar:", g.loc[cerca | cerca.shift(-1, fill_value=False), ["fecha", "competicion", "rival", "partido_id"]].values.tolist())

    # autocomprobaciones
    assert h["partido_id"].is_unique and (h["partido_id"] != "").all(), h[h["partido_id"].duplicated(keep=False)][["fecha", "competicion", "local", "visitante", "partido_id"]]
    assert not al.dropna(subset=["px"]).duplicated(["partido_id", "equipo", "px", "py"]).any(), al[al.dropna(subset=["px"]).duplicated(["partido_id", "equipo", "px", "py"], keep=False).reindex(al.index, fill_value=False)].head(30).to_string()
    assert (h["local"] == RM).sum() + (h["visitante"] == RM).sum() == len(h), "partido sin el Madrid"
    # Wikipedia pone a veces la ida y la vuelta el mismo día (1954, 1961): se quedan los dos partidos
    dup = h.duplicated(["fecha", "competicion"], keep=False)
    assert (h.loc[dup, "fuente"] == "wikipedia").all(), h[dup]
    # pero nunca el mismo partido dos veces (mismo día, rival y resultado)
    rep = h.duplicated(["fecha", "competicion", "rival", "goles_rm", "goles_rival"], keep=False)
    assert not rep.any(), h[rep][["fecha", "competicion", "local", "visitante", "goles_local", "goles_visitante", "partido_id"]]

    finales = ["Supercopa de Europa", "Copa Intercontinental", "Copa Intercontinental de la FIFA", "Copa Eva Duarte", "Copa Iberoamericana"]
    solo_final = h["competicion"].isin(finales) | ((h["competicion"] == "Supercopa de España") & (h["fecha"] < "2019-07-01"))
    for _, g in h[solo_final].sort_values("fecha").groupby(["competicion", "temporada"]):
        patas = ["Final"] if len(g) == 1 else ["Final (ida)", "Final (vuelta)", "Final (desempate)"][:len(g)]
        for i, pata in zip(g.index, patas):
            if h.loc[i, "ronda"] in ("", "Ida", "Vuelta", "Desempate", "Final"):
                h.loc[i, "ronda"] = pata
    h["fecha_aprox"] = h["fecha_aprox"].fillna("") if "fecha_aprox" in h else ""  # "1": fecha estimada por la ronda
    h = h.sort_values("fecha")[["fecha", "temporada", "competicion", "local", "visitante", "goles_local", "goles_visitante",
                                "rival", "condicion", "goles_rm", "goles_rival", "resultado", "estadio", "partido_id", "fuente",
                                "ronda", "penaltis", "goleadores_local", "goleadores_visitante", "fecha_aprox"]]
    WEB.mkdir(parents=True, exist_ok=True)
    tit = titulos(palmares, h)
    # la final de cada título o subcampeonato, aunque la fuente no diga la ronda
    claves = set(zip(tit["comp_hist"], tit["hasta"]))
    fin = (h["ronda"] == "") & np.array([(c, f) in claves for c, f in zip(h["competicion"], h["fecha"])])
    h.loc[fin, "ronda"] = "Final"
    h.to_csv(WEB / "historico.csv", index=False)
    ligas.to_csv(WEB / "ligas.csv", index=False)
    tit.to_csv(WEB / "titulos.csv", index=False)
    al["dorsal"] = pd.to_numeric(al["dorsal"], errors="coerce").astype("Int64")
    al[["partido_id", "equipo", "jugador", "posicion", "titular", "dorsal", "px", "py"]].to_csv(WEB / "historico_alineaciones.csv", index=False)
    # cada escudo se descarga una vez y se sirve desde la propia web (sin depender de que el origen permita enlazarlo)
    carpeta = WEB.parent / "escudos"
    carpeta.mkdir(exist_ok=True)
    locales = {}
    for url in set(escudos.values()):
        f = carpeta / (hashlib.md5(url.encode()).hexdigest()[:12] + ".png")
        try:
            if not f.exists():
                f.write_bytes(get_wiki(url) if "wikimedia.org" in url else get(url))
            locales[url] = f"escudos/{f.name}"
        except Exception as e:
            print(f"Escudo no descargado ({e}): {url}")
    pd.DataFrame(sorted((n, locales.get(u, u)) for n, u in escudos.items()), columns=["equipo", "url"]).to_csv(WEB / "escudos.csv", index=False)
    print(f"Escudos guardados en la web: {len(locales)} de {len(set(escudos.values()))}")
    print(f"Escudos: {len(escudos)} equipos; con estadio: {(h['estadio'] != '').sum()} de {len(h)} partidos")
    print(h.groupby("competicion").agg(partidos=("fecha", "size"), desde=("fecha", "min"), hasta=("fecha", "max")))
    print(f"{len(h)} partidos; alineaciones de {al['partido_id'].nunique()} partidos; temporada actual (ESPN): {len(actual)}")
    print("Rivales distintos:", h["rival"].nunique())
    # entrenadores de cada etapa y clasificaciones de jugadores (Wikipedia), coordenadas de los estadios (Wikidata): si fallan, se quedan los ficheros de la última vez
    for modulo in ("entrenadores", "estadios", "jugadores"):
        try:
            __import__(modulo).main(WEB)
        except Exception as e:
            print(f"{modulo}: sin actualizar ({e})")


if __name__ == "__main__":
    main()
