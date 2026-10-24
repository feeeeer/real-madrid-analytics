"""Procesa las fuentes de la temporada (data/fuentes/<temporada>) y escribe los datos de la web (docs/data).

Uso: python pipeline/procesar.py [data/fuentes/2026-2027] [docs/data]

Solo entran los partidos que ya tienen eventos de WhoScored; los de Liga, además, el xG de Understat (el resto
espera a la siguiente ejecución). Champions y Copa no tienen xG (Understat solo cubre la Liga): sus tiros salen de
los eventos de WhoScored con el xG vacío. Coordenadas: Opta 0-100 -> campo 120x80, cada equipo atacando de izquierda a derecha.
"""
import ast, json, re, sys, unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "data/fuentes/2026-2027")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/data")
RM, ENTRENADOR = "Real Madrid", "José Mourinho"
TEMPORADA = SRC.name.replace("-", "/")
COMP = {"ESP-La Liga": "La Liga", "INT-Champions League": "Champions League", "ESP-Copa del Rey": "Copa del Rey"}
MIN_LIGA = 270  # minutos mínimos para entrar en los percentiles de la Liga

ws = pd.concat([pd.read_csv(f, low_memory=False) for f in sorted((SRC / "whoscored_eventos").glob("*.csv"))], ignore_index=True)
us_shots = pd.read_csv(SRC / "understat_tiros.csv")
us_pm = pd.read_csv(SRC / "understat_jugadores_partido.csv")
us_liga = pd.read_csv(SRC / "understat_jugadores_liga.csv")
us_games = pd.read_csv(SRC / "understat_partidos_rm.csv")
ws_games = pd.read_csv(SRC / "whoscored_partidos_rm.csv")
fb_misc = pd.read_csv(SRC / "fbref_jugadores_misc.csv")


def words(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", " ", s).split()


norm = lambda s: set(words(s))


def match_names(src_names, dst_names):
    """Empareja nombres de dos fuentes por solapamiento de palabras (sin tildes). Solo acepta emparejamientos únicos."""
    out = {}
    for a in src_names:
        # más palabras en común; luego menos palabras sobrantes ("Atletico" antes que "Real Madrid"); luego mismo apellido
        scores = sorted((((len(norm(a) & norm(b)), -len(norm(b) - norm(a)), words(a)[-1:] == words(b)[-1:]), b)
                         for b in dst_names), reverse=True)
        if scores and scores[0][0][0] > 0 and (len(scores) == 1 or scores[0][0] > scores[1][0]):
            out[a] = scores[0][1]
    return out


# ---------- Eventos WhoScored ----------
ws["q"] = ws["qualifiers"].fillna("[]").map(lambda s: {d["type"]["displayName"] for d in ast.literal_eval(s)})
ws["ok"] = ws["outcome_type"] == "Successful"
ws["X"], ws["Y"] = ws["x"] * 1.2, (100 - ws["y"]) * 0.8
ws["EX"], ws["EY"] = ws["end_x"] * 1.2, (100 - ws["end_y"]) * 0.8
ws["fecha"] = ws["game"].str[:10]
# solo partidos con eventos de WhoScored; los de Liga, además con resultado en Understat
us_fechas = set(us_games.loc[us_games["is_result"].astype(str) == "True", "date"].str[:10])
g = ws_games[ws_games["game_id"].isin(ws["game_id"])].assign(fecha=lambda d: d["game"].str[:10], competicion=lambda d: d["league"].map(COMP))
g = g[(g["competicion"] != "La Liga") | g["fecha"].isin(us_fechas)]
ws = ws[ws["game_id"].isin(g["game_id"])]
ws_teams = set(ws["team"])
to_ws = lambda t: t if t in ws_teams else match_names([t], ws_teams).get(t, t)  # el calendario y los eventos nombran distinto a algunos equipos
# por id de equipo: el calendario y los eventos pueden nombrar distinto ("RB Leipzig" / "RBL")
nombre_ws = ws.drop_duplicates("team_id").set_index("team_id")["team"]
g["home_team"], g["away_team"] = g["home_team_id"].map(nombre_ws).fillna(g["home_team"]), g["away_team_id"].map(nombre_ws).fillna(g["away_team"])
partidos = pd.DataFrame({
    "match_id": g["game_id"], "fecha": g["fecha"], "competicion": g["competicion"], "temporada": TEMPORADA, "jornada": "",
    "local": g["home_team"], "visitante": g["away_team"], "goles_local": g["home_score"].astype(int), "goles_visitante": g["away_score"].astype(int),
    "rival": np.where(g["home_team"] == RM, g["away_team"], g["home_team"]), "entrenador_rm": ENTRENADOR, "estadio": "",
}).sort_values("fecha")
mid_by_fecha = dict(zip(partidos["fecha"], partidos["match_id"]))
liga_ids = set(partidos.loc[partidos["competicion"] == "La Liga", "match_id"])
ws["match_id"] = ws["fecha"].map(mid_by_fecha)
assert ws["match_id"].notna().all()

# ---------- Tiros Understat (+ contraataque de WhoScored por coordenadas exactas) ----------
us_shots["fecha"] = us_shots["date"].str[:10]
us_shots["match_id"] = us_shots["fecha"].map(mid_by_fecha)
us_shots = us_shots[us_shots["match_id"].isin(liga_ids)]
us_shots["equipo"] = us_shots["team"].map(to_ws)
ws_shots = ws[ws["type"].isin(["Goal", "SavedShot", "MissedShots", "ShotOnPost"])]
fast, pen = set(), set()  # Understat marca los penaltis como "Set Piece": se toman de WhoScored
for r in us_shots.itertuples():
    c = ws_shots[(ws_shots["match_id"] == r.match_id) & ((ws_shots["x"] - 100 * r.location_x).abs() < 0.6)
                 & ((ws_shots["y"] - 100 * r.location_y).abs() < 0.6)]
    if len(c) and "FastBreak" in c.iloc[0]["q"]:
        fast.add(r.shot_id)
    if len(c) and "Penalty" in c.iloc[0]["q"]:
        pen.add(r.shot_id)
es_pen = (us_shots["situation"] == "Penalty") | us_shots["shot_id"].isin(pen)
RES = {"Goal": "Goal", "Saved Shot": "Saved", "Missed Shot": "Off T", "Blocked Shot": "Blocked", "Shot On Post": "Post", "Own Goal": "Own Goal"}
PAT = {"Open Play": "Regular Play", "From Corner": "From Corner", "Set Piece": "From Free Kick", "Direct Freekick": "From Free Kick", "Penalty": "Other"}
tiros = pd.DataFrame({
    "tiro_id": "us" + us_shots["shot_id"].astype(str), "match_id": us_shots["match_id"], "equipo": us_shots["equipo"],
    "jugador": us_shots["player"], "x": (us_shots["location_x"] * 120).round(1), "y": ((1 - us_shots["location_y"]) * 80).round(1),
    "xg": us_shots["xg"].round(3), "resultado": us_shots["result"].map(RES),
    "subtipo": np.where(es_pen, "Penalty", "Open Play"),
    "patron_juego": np.where(us_shots["shot_id"].isin(fast), "From Counter", np.where(es_pen, "Other", us_shots["situation"].map(PAT))),
    "minuto": us_shots["minute"],
})
tiros = tiros[tiros["resultado"] != "Own Goal"]  # el gol en propia meta no es un tiro de quien lo marca

# los mismos tiros desde los eventos de WhoScored (sin xG): los de Champions y Copa salen de aquí
s = ws_shots[~ws_shots["q"].map(lambda q: "OwnGoal" in q)]
q = s["q"]
tiros_ws = pd.DataFrame({
    "tiro_id": "ws" + s["game_id"].astype(str) + "_" + s["team_id"].astype(str) + "_" + s["event_id"].astype(str),
    "match_id": s["match_id"], "equipo": s["team"], "jugador": s["player"], "x": s["X"].round(1), "y": s["Y"].round(1), "xg": np.nan,
    "resultado": np.select([s["type"] == "Goal", s["type"] == "ShotOnPost", s["type"] == "MissedShots", q.map(lambda q: "Blocked" in q)],
                           ["Goal", "Post", "Off T", "Blocked"], "Saved"),
    "subtipo": np.where(q.map(lambda q: "Penalty" in q), "Penalty", "Open Play"),
    "patron_juego": q.map(lambda q: "From Counter" if "FastBreak" in q else "Other" if "Penalty" in q else "From Corner" if "FromCorner" in q
                          else "From Free Kick" if q & {"SetPiece", "DirectFreekick", "ThrowinSetPiece"} else "Regular Play"),
    "minuto": s["minute"],
})
# comprobación: en la Liga, WhoScored y Understat deben contar los mismos tiros por resultado
for mid in liga_ids:
    a = tiros_ws[tiros_ws["match_id"] == mid]["resultado"].value_counts()
    b = tiros[tiros["match_id"] == mid]["resultado"].value_counts()
    assert (a.sub(b, fill_value=0).abs() <= 2).all(), (mid, a.to_dict(), b.to_dict())
tiros = pd.concat([tiros, tiros_ws[~tiros_ws["match_id"].isin(liga_ids)]], ignore_index=True)
# el tirador con el nombre de WhoScored ("Kylian Mbappe-Lottin" -> "Kylian Mbappé"), el mismo que en pases y alineaciones
for (mid, eq), idx in tiros.groupby(["match_id", "equipo"]).groups.items():
    m = match_names(tiros.loc[idx, "jugador"].unique(), ws.loc[(ws["match_id"] == mid) & (ws["team"] == eq), "player"].dropna().unique())
    tiros.loc[idx, "jugador"] = tiros.loc[idx, "jugador"].map(lambda n: m.get(n, n))

# ---------- Métricas por equipo ----------
def danger_loss(e):
    """Misma definición que metrics.py: pérdida en el propio tercio sin superar el medio campo; no cuenta saques de puerta."""
    return (e["X"] < 40) & ((e["type"] == "Dispossessed") | ((e["type"] == "BallTouch") & ~e["ok"])
            | ((e["type"] == "Pass") & ~e["ok"] & ~e["q"].map(lambda q: "GoalKick" in q) & (e["EX"] < 60)))

passes_all = ws[(ws["type"] == "Pass") & ~ws["q"].map(lambda q: "ThrowIn" in q)]
eq_rows = []
for p in partidos.itertuples():
    ev = ws[ws["match_id"] == p.match_id]
    for t, riv in ((p.local, p.visitante), (p.visitante, p.local)):
        me, op = ev[ev["team"] == t], ev[ev["team"] == riv]
        sh, sh_op = tiros[(tiros["match_id"] == p.match_id) & (tiros["equipo"] == t)], tiros[(tiros["match_id"] == p.match_id) & (tiros["equipo"] == riv)]
        pa = passes_all[(passes_all["match_id"] == p.match_id) & (passes_all["team"] == t)]
        pa_op = passes_all[(passes_all["match_id"] == p.match_id) & (passes_all["team"] == riv)]
        comp = pa[pa["ok"]]
        xg = (lambda d: round(d["xg"].sum(), 2)) if p.match_id in liga_ids else (lambda d: np.nan)  # sin xG fuera de la Liga
        def_act = me[(me["X"] >= 48) & (me["type"].isin(["Tackle", "Interception"]) | ((me["type"] == "Foul") & ~me["ok"]))]
        won = ((me["type"] == "Tackle") | ((me["type"] == "Aerial") & me["ok"])).sum()
        lost = ((me["type"] == "Challenge") | ((me["type"] == "Aerial") & ~me["ok"])).sum()
        eq_rows.append(dict(
            match_id=p.match_id, equipo=t, rival=riv, goles=p.goles_local if t == p.local else p.goles_visitante,
            xg=xg(sh), npxg=xg(sh[sh["subtipo"] != "Penalty"]),
            xg_contraataque=xg(sh[sh["patron_juego"] == "From Counter"]), tiros=len(sh),
            tiros_puerta=int(sh["resultado"].isin(["Goal", "Saved"]).sum()),
            posesion=round(100 * len(pa) / max(len(pa) + len(pa_op), 1), 1), pases=len(pa),
            acierto_pase=round(100 * len(comp) / max(len(pa), 1), 1),
            pases_progresivos=int((comp["EX"] - comp["X"] >= 15).sum()),
            pases_ultimo_tercio=int(((comp["X"] < 80) & (comp["EX"] >= 80)).sum()),
            ppda=round((pa_op["X"] < 72).sum() / max(len(def_act), 1), 1),
            presiones=np.nan, presiones_campo_rival=np.nan,  # Opta no registra presiones
            recuperaciones_campo_rival=int((me["type"].isin(["BallRecovery", "Interception"]) & me["ok"] & (me["X"] >= 60)).sum()),
            duelos_ganados_pct=round(100 * won / max(won + lost, 1), 1),
            perdidas_peligrosas=int(danger_loss(me).sum()), contrapresiones=np.nan, recup_tras_perdida=np.nan,
            xg_contra=xg(sh_op), fuente="Opta",
        ))
eq = pd.DataFrame(eq_rows)
eq.insert(0, "clave", eq["match_id"].astype(str) + "|" + eq["equipo"])

# ---------- Métricas por jugador y partido ----------
fin = ws.groupby("match_id")["expanded_minute"].max()
jug_rows = []
for (mid, team, pid), e in ws[ws["player_id"].notna()].groupby(["match_id", "team", "player_id"]):
    on, off = e[e["type"] == "SubstitutionOn"], e[e["type"] == "SubstitutionOff"]
    mins = (off["expanded_minute"].min() if len(off) else fin[mid]) - (on["expanded_minute"].min() if len(on) else 0)
    pa = e[(e["type"] == "Pass") & ~e["q"].map(lambda q: "ThrowIn" in q)]
    comp = pa[pa["ok"]]
    jug_rows.append(dict(
        match_id=mid, equipo=team, jugador_id=int(pid), jugador=e["player"].iloc[0], titular=int(on.empty),
        posicion="GK" if e["type"].isin(["KeeperPickup", "Claim", "Punch", "Smother", "KeeperSweeper"]).any() else "",
        minutos=int(max(mins, 1)), goles=int(((e["type"] == "Goal") & ~e["q"].map(lambda q: "OwnGoal" in q)).sum()),
        pases_clave=int(pa["q"].map(lambda q: bool(q & {"KeyPass", "IntentionalGoalAssist", "IntentionalAssist"})).sum()),
        asistencias=int(pa["q"].map(lambda q: "IntentionalGoalAssist" in q).sum()),
        pases=len(pa), acierto_pase=round(100 * len(comp) / max(len(pa), 1), 1),
        pases_progresivos=int((comp["EX"] - comp["X"] >= 15).sum()),
        regates=int(((e["type"] == "TakeOn") & e["ok"]).sum()), presiones=np.nan,
        recuperaciones=int((e["type"].isin(["BallRecovery", "Interception"]) & e["ok"]).sum()),
        duelos_ganados=int(((e["type"] == "Tackle") | ((e["type"] == "Aerial") & e["ok"])).sum()),
        duelos_perdidos=int(((e["type"] == "Challenge") | ((e["type"] == "Aerial") & ~e["ok"])).sum()),
        perdidas_peligrosas=int(danger_loss(e).sum()),
    ))
jug = pd.DataFrame(jug_rows)

# xG, xA y asistencias por jugador desde Understat, emparejando nombres dentro de cada partido y equipo
us_pm["match_id"] = us_pm["game"].str[:10].map(mid_by_fecha)
us_pm["equipo"] = us_pm["team"].map(to_ws)
us_pm = us_pm[us_pm["match_id"].isin(liga_ids)]
jug["xg"] = jug["xa"] = np.where(jug["match_id"].isin(liga_ids), 0.0, np.nan)
sin_emparejar = []
for (mid, team), u in us_pm.groupby(["match_id", "equipo"]):
    jj = jug[(jug["match_id"] == mid) & (jug["equipo"] == team)]
    m = match_names(u["player"].tolist(), jj["jugador"].tolist())
    for r in u.itertuples():
        if r.player not in m:
            if r.xg + r.xa > 0:
                sin_emparejar.append(r.player)
            continue
        i = jj.index[jj["jugador"] == m[r.player]][0]
        jug.loc[i, ["xg", "xa", "asistencias"]] = [round(r.xg, 2), round(r.xa, 2), r.assists]
jug.insert(0, "clave", jug["match_id"].astype(str) + "|" + jug["jugador_id"].astype(str))

# ---------- Alineaciones: dorsal y titularidad del FormationSet de WhoScored ----------
LINEA = {"1": "GK", "2": "DF", "3": "MF", "4": "FW"}
al_rows = []
for r in ws[ws["type"] == "FormationSet"].drop_duplicates(["match_id", "team"]).itertuples():
    q = {d["type"]["displayName"]: d.get("value", "") for d in ast.literal_eval(r.qualifiers)}
    ids, dorsales = q["InvolvedPlayers"].split(","), q["JerseyNumber"].split(",")
    lineas = q["PlayerPosition"].split(",")
    for pid, dorsal, linea in zip(ids, dorsales, lineas):
        j = jug[(jug["match_id"] == r.match_id) & (jug["jugador_id"] == int(pid))]
        if j.empty:
            continue  # suplente que no jugó: WhoScored no da su nombre
        titular = linea.strip() in LINEA
        al_rows.append(dict(match_id=r.match_id, equipo=r.team, jugador=j["jugador"].iloc[0], dorsal=int(dorsal),
                            titular=int(titular), linea=LINEA.get(linea.strip(), "")))
alineaciones = pd.DataFrame(al_rows)
# posición titular de cada jugador en el partido (Understat: GK, DC, DL, AML, FW...), con las etiquetas de Transfermarkt
US_POS = {"GK": "Goalkeeper", "DC": "Centre-Back", "DL": "Left-Back", "DR": "Right-Back", "DMC": "Defensive Midfield",
          "DML": "Defensive Midfield", "DMR": "Defensive Midfield", "MC": "Central Midfield", "ML": "Left Midfield",
          "MR": "Right Midfield", "AMC": "Attacking Midfield", "AML": "Left Winger", "AMR": "Right Winger",
          "FW": "Centre-Forward", "FWL": "Centre-Forward", "FWR": "Centre-Forward"}
# a quien sale desde el banquillo ("Sub") se le pone su posición más habitual como titular esta temporada
habitual = us_pm[us_pm["position"] != "Sub"].groupby("player")["position"].agg(lambda v: v.value_counts().index[0])
alineaciones["posicion"] = ""
for (mid, team), u in us_pm.groupby(["match_id", "equipo"]):
    sel = (alineaciones["match_id"] == mid) & (alineaciones["equipo"] == team)
    m = match_names(u["player"].tolist(), alineaciones.loc[sel, "jugador"].tolist())
    for r in u.itertuples():
        pos = r.position if r.position != "Sub" else habitual.get(r.player, "")
        if r.player in m:
            alineaciones.loc[sel & (alineaciones["jugador"] == m[r.player]), "posicion"] = US_POS.get(pos, "")
# fuera de la Liga no hay posición de Understat: la habitual del jugador en la Liga y, si no la hay (rivales), su línea
# shortcut: línea gruesa (todos los defensas como centrales), usar TeamFormation de Opta si se quiere el dibujo exacto
hab = us_pm[(us_pm["position"] != "Sub") & (us_pm["equipo"] == RM)].groupby("player")["position"].agg(lambda v: v.value_counts().index[0])
hab_rm = match_names(hab.index.tolist(), alineaciones.loc[alineaciones["equipo"] == RM, "jugador"].unique())
hab_rm = {b: US_POS.get(hab[a], "") for a, b in hab_rm.items()}
LINEA_POS = {"GK": "Goalkeeper", "DF": "Centre-Back", "MF": "Central Midfield", "FW": "Centre-Forward"}
vacia = alineaciones["posicion"] == ""
alineaciones.loc[vacia, "posicion"] = [(hab_rm.get(j, "") if e == RM else "") or LINEA_POS.get(l, "")
                                       for j, e, l in alineaciones.loc[vacia, ["jugador", "equipo", "linea"]].itertuples(index=False)]
alineaciones = alineaciones.drop(columns="linea")
# misma colocación en el campito que el histórico (una fila por línea, de izquierda a derecha)
sys.path.insert(0, str(Path(__file__).parent))
from historico import colocar  # noqa: E402
alineaciones = colocar(alineaciones.rename(columns={"match_id": "partido_id"})).rename(columns={"partido_id": "match_id"})
assert (alineaciones.loc[alineaciones["titular"] == 1, "posicion"] != "").mean() > 0.95, "titulares sin posición"
assert (alineaciones.groupby(["match_id", "equipo"])["titular"].sum() == 11).all(), "alineación sin 11 titulares"

# ---------- Pases para los mapas ----------
pa = passes_all.merge(jug[["match_id", "jugador_id", "jugador"]].rename(columns={"jugador_id": "player_id"}), on=["match_id", "player_id"])
pases = pd.DataFrame({
    "match_id": pa["match_id"], "equipo": pa["team"], "jugador": pa["jugador"],
    "x": pa["X"].round(1), "y": pa["Y"].round(1), "fin_x": pa["EX"].round(1), "fin_y": pa["EY"].round(1),
    "tipo": np.where(pa["q"].map(lambda q: bool(q & {"KeyPass", "IntentionalGoalAssist", "IntentionalAssist"})), "clave",
                     np.where(pa["ok"], "completo", "fallado")), "minuto": pa["minute"],
})

# ---------- Incidencias del partido (línea de tiempo): goles, tarjetas y cambios ----------
equipos_de = {p.match_id: (p.local, p.visitante) for p in partidos.itertuples()}
otro = lambda mid, t: [x for x in equipos_de[mid] if x != t][0]
inc = []
for r in ws[ws["type"] == "Goal"].itertuples():
    pp = "OwnGoal" in r.q
    inc.append(dict(match_id=r.match_id, minuto=r.minute, orden=r.expanded_minute, equipo=otro(r.match_id, r.team) if pp else r.team,
                    tipo="gol_pp" if pp else "penalti" if "Penalty" in r.q else "gol", jugador=r.player, sale=""))
TARJ = {"Yellow": "amarilla", "SecondYellow": "segunda_amarilla", "Red": "roja"}
for r in ws[ws["type"] == "Card"].itertuples():
    inc.append(dict(match_id=r.match_id, minuto=r.minute, orden=r.expanded_minute, equipo=r.team, tipo=TARJ.get(r.card_type, "amarilla"), jugador=r.player, sale=""))
entra = ws[ws["type"] == "SubstitutionOn"].set_index(["match_id", "player_id"])["player"]
for r in ws[ws["type"] == "SubstitutionOff"].itertuples():
    inc.append(dict(match_id=r.match_id, minuto=r.minute, orden=r.expanded_minute, equipo=r.team, tipo="cambio",
                    jugador=entra.get((r.match_id, r.related_player_id), ""), sale=r.player))
incidencias = pd.DataFrame(inc, columns=["match_id", "minuto", "orden", "equipo", "tipo", "jugador", "sale"]).sort_values(["match_id", "orden"])
# comprobación: los goles de la línea de tiempo cuadran con el marcador
for p in partidos.itertuples():
    gi = incidencias[(incidencias["match_id"] == p.match_id) & incidencias["tipo"].isin(["gol", "penalti", "gol_pp"])]["equipo"].value_counts()
    assert gi.get(p.local, 0) == p.goles_local and gi.get(p.visitante, 0) == p.goles_visitante, (p.fecha, gi.to_dict())

# ---------- Red de pases: posición media de cada jugador y pases entre cada pareja ----------
toques = ws[ws["is_touch"].astype(str) == "True"].copy()  # orden de los ficheros = orden del partido
toques["sig_equipo"] = toques.groupby("match_id")["team"].shift(-1)
toques["sig_jugador"] = toques.groupby("match_id")["player"].shift(-1)
pc = toques[(toques["type"] == "Pass") & toques["ok"] & (toques["sig_equipo"] == toques["team"]) & (toques["sig_jugador"] != toques["player"])]
red_enlaces = pc.groupby(["match_id", "team", "player", "sig_jugador"]).size().reset_index(name="n")
red_enlaces.columns = ["match_id", "equipo", "de", "a", "n"]
red_nodos = toques[toques["player"].notna()].groupby(["match_id", "team", "player"]).agg(x=("X", "mean"), y=("Y", "mean"), toques=("type", "size")).reset_index()
red_nodos = red_nodos.rename(columns={"team": "equipo", "player": "jugador"}).round({"x": 1, "y": 1})
red_nodos["pases"] = red_nodos.apply(lambda r: int(red_enlaces[(red_enlaces["match_id"] == r.match_id) & (red_enlaces["de"] == r.jugador)]["n"].sum()), axis=1)

# ---------- Recuperaciones y pérdidas (mapa) ----------
rec = ws[ws["type"].isin(["BallRecovery", "Interception"]) & ws["ok"]]
per = ws[(ws["type"] == "Dispossessed") | ((ws["type"] == "BallTouch") & ~ws["ok"])]
acciones = pd.concat([
    pd.DataFrame({"match_id": rec["match_id"], "equipo": rec["team"], "jugador": rec["player"], "tipo": "recuperacion",
                  "x": rec["X"].round(1), "y": rec["Y"].round(1), "minuto": rec["minute"], "peligrosa": 0}),
    pd.DataFrame({"match_id": per["match_id"], "equipo": per["team"], "jugador": per["player"], "tipo": "perdida",
                  "x": per["X"].round(1), "y": per["Y"].round(1), "minuto": per["minute"], "peligrosa": danger_loss(per).astype(int)}),
], ignore_index=True).sort_values(["match_id", "minuto"])

# ---------- Rendimiento frente a lo esperado ----------
fb_teams = set(fb_misc["team"])
to_fb_team = lambda t: t if t in fb_teams else match_names([t], fb_teams).get(t, t)


def pos_us(p):
    return str(p).split()[0] if str(p).split()[0] in ("GK", "D", "M", "F") else None

liga = us_liga[us_liga["minutes"] >= MIN_LIGA].copy()
for c in ("xg", "xa", "xg_chain", "xg_buildup", "key_passes"):
    liga[c + "90"] = liga[c] * 90 / liga["minutes"]
FB_POS = {"GK": "GK", "DF": "D", "MF": "M", "FW": "F"}
# el puesto sale de FBref (Understat pone a Vinícius de centrocampista); Understat solo si no hay emparejamiento
fb_pos = {}
for team, u in us_liga.groupby("team"):
    f = fb_misc[fb_misc["team"] == to_fb_team(team)]
    for a, b in match_names(u["player"].tolist(), f["player"].tolist()).items():
        fb_pos[(team, a)] = FB_POS.get(f.loc[f["player"] == b, "pos"].iloc[0][:2])
grupo_de = lambda team, player, pos: fb_pos.get((team, player)) or pos_us(pos)
liga["grupo"] = [grupo_de(t, p, q) for t, p, q in zip(liga["team"], liga["player"], liga["position"])]
fbm = fb_misc[fb_misc["90s"] >= MIN_LIGA / 90].copy()
fbm["grupo"] = fbm["pos"].str[:2].map(FB_POS)
fbm["int90"], fbm["tklw90"] = fbm["Performance_Int"] / fbm["90s"], fbm["Performance_TklW"] / fbm["90s"]

def pct(series, value):
    return round(100 * (series < value).mean() + 50 * (series == value).mean())

# rol fino del jugador del Madrid: su posición más habitual de titular en la Liga (Understat), no solo defensa/medio/delantero
ROL_US = {"GK": "Portero", "DC": "Central", "DL": "Lateral", "DR": "Lateral", "DML": "Lateral", "DMR": "Lateral",
          "DMC": "Mediocentro", "MC": "Mediocentro", "ML": "Mediapunta o extremo", "MR": "Mediapunta o extremo",
          "AML": "Mediapunta o extremo", "AMR": "Mediapunta o extremo", "AMC": "Mediapunta o extremo",
          "FW": "Delantero", "FWL": "Delantero", "FWR": "Delantero"}
ROL_GRUESO = {"GK": "Portero", "D": "Central", "M": "Mediocentro", "F": "Delantero"}
# con quién se compara cada rol en la Liga (grupos de FBref/Understat) y con qué métricas
ROL = {"Central": ("D", ["int90", "tklw90", "xg_buildup90"]), "Lateral": ("D", ["xa90", "xg_buildup90", "tklw90"]),
       "Mediocentro": ("M", ["xg_buildup90", "int90", "tklw90", "xa90"]),
       "Mediapunta o extremo": ("MF", ["xg90", "xa90", "xg_chain90"]), "Delantero": ("F", ["xg90", "xa90", "xg_chain90"])}
RADAR = ["xg90", "xa90", "key_passes90", "xg_chain90", "xg_buildup90", "tklw90", "int90"]
rm_pm = us_pm[(us_pm["equipo"] == RM) & (us_pm["position"] != "Sub")]
rol_us = rm_pm.groupby("player")["position"].agg(lambda v: ROL_US.get(v.value_counts().index[0]))
# métricas Opta (pase, progresivos, recuperaciones, duelos, pérdidas): todas las competiciones
ws_rm = jug[jug["equipo"] == RM].groupby("jugador").agg(
    pases=("pases", "sum"), acierto=("acierto_pase", lambda s: np.average(s, weights=jug.loc[s.index, "pases"].clip(lower=1))),
    prog=("pases_progresivos", "sum"), recup=("recuperaciones", "sum"), dg=("duelos_ganados", "sum"),
    dp=("duelos_perdidos", "sum"), perd=("perdidas_peligrosas", "sum"), mins_ws=("minutos", "sum"))
us_rm = us_liga[us_liga["team"] == RM]
m_ws = match_names(us_rm["player"].tolist(), ws_rm.index.tolist())
fb_rm = fb_misc[fb_misc["team"] == RM]
m_fb = match_names(us_rm["player"].tolist(), fb_rm["player"].tolist())
pen = tiros[(tiros["subtipo"] == "Penalty") & (tiros["resultado"] == "Goal") & tiros["match_id"].isin(liga_ids)]["jugador"].value_counts()


def desvio(real, esperado):
    """Desvío claro: al menos 1 de diferencia y un 30 % de lo esperado (−1.9 sobre 10.9 xG no es lo mismo que −2.6 sobre 3.6)."""
    d = real - esperado
    return np.sign(d) if abs(d) >= 1 and abs(d) >= 0.3 * max(esperado, 1) else 0


ren = []
for r in us_rm.itertuples():
    if r.minutes < 90:
        continue
    rol = rol_us.get(r.player) or ROL_GRUESO.get(grupo_de(r.team, r.player, r.position))
    if rol is None:
        continue
    w = ws_rm.loc[m_ws[r.player]] if r.player in m_ws else None
    nombre = m_ws.get(r.player, r.player)
    f = fb_rm[fb_rm["player"] == m_fb.get(r.player)]
    f90 = f["90s"].iloc[0] if len(f) and f["90s"].iloc[0] > 0 else None
    fila = dict(jugador=nombre, puesto=rol, minutos=r.minutes, goles=r.goals, penaltis=int(pen.get(nombre, 0)), npxg=round(r.np_xg, 2),
                g_menos_xg=round(r.np_goals - r.np_xg, 2), asistencias=r.assists, xa=round(r.xa, 2), a_menos_xa=round(r.assists - r.xa, 2),
                xg90=round(r.xg * 90 / r.minutes, 2), xa90=round(r.xa * 90 / r.minutes, 2), xgchain90=round(r.xg_chain * 90 / r.minutes, 2),
                pct_rol=np.nan, acierto_pase=round(w["acierto"], 1) if w is not None else np.nan,
                prog90=round(w["prog"] * 90 / w["mins_ws"], 1) if w is not None else np.nan,
                recup90=round(w["recup"] * 90 / w["mins_ws"], 1) if w is not None else np.nan,
                duelos_pct=round(100 * w["dg"] / max(w["dg"] + w["dp"], 1), 1) if w is not None else np.nan,
                perdidas90=round(w["perd"] * 90 / w["mins_ws"], 2) if w is not None else np.nan, _malos=[], _buenos=[])
    if rol == "Portero":
        # paradas frente al xG de los tiros a puerta recibidos en la Liga (xG previo al tiro: aproximación)
        # shortcut: se le cuentan todos los tiros de los partidos en que jugó, aunque saliera antes; usar minutos si hay rotación
        mids = jug[(jug["jugador"] == nombre) & jug["match_id"].isin(liga_ids)]["match_id"]
        rec = tiros[tiros["match_id"].isin(mids) & (tiros["equipo"] != RM) & tiros["resultado"].isin(["Goal", "Saved"])]
        gc, xgc = int((rec["resultado"] == "Goal").sum()), rec["xg"].sum()
        texto = f"encajó {gc} goles en tiros a puerta que valían {xgc:.1f} xG: {abs(gc - xgc):.1f} {'más' if gc > xgc else 'menos'} de lo esperado"
        {1: fila["_buenos"], -1: fila["_malos"], 0: []}[desvio(xgc, gc)].append(texto)
        fila["_neutro"] = texto
        ren.append(fila)
        continue
    grupos, metricas = ROL[rol]
    grupos = list(grupos)
    val = {"xg90": r.xg * 90 / r.minutes, "xa90": r.xa * 90 / r.minutes, "xg_chain90": r.xg_chain * 90 / r.minutes,
           "xg_buildup90": r.xg_buildup * 90 / r.minutes,
           "int90": f["Performance_Int"].iloc[0] / f90 if f90 else np.nan, "tklw90": f["Performance_TklW"].iloc[0] / f90 if f90 else np.nan}
    pcts = [pct((liga if k not in ("int90", "tklw90") else fbm).query("grupo in @grupos")[k], val[k]) for k in metricas if not np.isnan(val[k])]
    # radar de la ficha del jugador: percentil de cada métrica frente a los de su puesto en la Liga
    val["key_passes90"] = r.key_passes * 90 / r.minutes
    for k in RADAR:
        fila["r_" + k] = pct((liga if k not in ("int90", "tklw90") else fbm).query("grupo in @grupos")[k], val[k]) if not np.isnan(val[k]) else np.nan
    if r.minutes >= MIN_LIGA and pcts:
        fila["pct_rol"] = round(np.mean(pcts))
    d = desvio(r.np_goals, r.np_xg)
    if d:
        (fila["_buenos"] if d > 0 else fila["_malos"]).append(
            f"remata {'por encima' if d > 0 else 'por debajo'} de su xG sin penaltis ({r.np_goals} {'gol' if r.np_goals == 1 else 'goles'} con {r.np_xg:.1f})")
    d = desvio(r.assists, r.xa)
    if d:
        (fila["_buenos"] if d > 0 else fila["_malos"]).append(
            f"{'da más asistencias de lo que valen sus pases' if d > 0 else 'sus pases merecen más asistencias de las que llegan'} ({r.assists} con {r.xa:.1f} xA)")
    if fila["pct_rol"] >= 75:
        fila["_buenos"].append(f"percentil {fila['pct_rol']:.0f} entre los de su puesto en la Liga")
    elif fila["pct_rol"] < 35:
        fila["_malos"].append(f"percentil {fila['pct_rol']:.0f} entre los de su puesto en la Liga")
    ren.append(fila)
ren = pd.DataFrame(ren)
# pérdidas peligrosas: alerta solo si dobla la mediana de su puesto en la plantilla (los defensas pierden más en su tercio)
campo = ren[(ren["puesto"] != "Portero") & (ren["minutos"] >= MIN_LIGA)]
for i, r in ren[ren["puesto"] != "Portero"].iterrows():
    mismos = campo[campo["puesto"] == r["puesto"]]
    med = (mismos if len(mismos) >= 3 else campo)["perdidas90"].median()
    if r["perdidas90"] >= max(2 * med, 1.0):
        r["_malos"].append(f"{r['perdidas90']:.1f} pérdidas peligrosas por 90 min, el doble de lo normal en su puesto ({med:.1f})")
pocos = ren["minutos"] < MIN_LIGA
balance = ren["_buenos"].map(len) - ren["_malos"].map(len)
ren["veredicto"] = np.where(pocos, "Pocos minutos", np.where(balance > 0, "Por encima", np.where(balance < 0, "Por debajo", "En línea")))
ren["motivo"] = [f"menos de {MIN_LIGA} minutos en la Liga: sin veredicto" if p else "; ".join(m + b) or neutro if isinstance(neutro, str) else "; ".join(m + b) or "sin desviaciones claras"
                 for p, m, b, neutro in zip(pocos, ren["_malos"], ren["_buenos"], ren.get("_neutro", pd.Series([np.nan] * len(ren))))]
ren["motivo"] = ren["motivo"].str[0].str.upper() + ren["motivo"].str[1:]
ren = ren.drop(columns=["_malos", "_buenos", "_neutro"], errors="ignore").sort_values(["veredicto", "minutos"], ascending=[True, False])

# ---------- Autocomprobaciones ----------
for p in partidos.itertuples():
    for t, goles in ((p.local, p.goles_local), (p.visitante, p.goles_visitante)):
        ev_goals = ((ws["match_id"] == p.match_id) & (ws["type"] == "Goal") &
                    (((ws["team"] == t) & ~ws["q"].map(lambda q: "OwnGoal" in q)) |
                     ((ws["team"] != t) & ws["q"].map(lambda q: "OwnGoal" in q)))).sum()
        assert ev_goals == goles, (p.fecha, t, ev_goals, goles)
us_x = us_games.assign(f=us_games["date"].str[:10]).set_index("f")
for p in partidos[partidos["match_id"].isin(liga_ids)].itertuples():
    rm_xg = eq[(eq["match_id"] == p.match_id) & (eq["equipo"] == RM)]["xg"].iloc[0]
    ref = us_x.loc[p.fecha, "home_xg" if p.local == RM else "away_xg"]
    assert abs(rm_xg - ref) < 0.35, (p.fecha, rm_xg, ref)  # el xG de partido de Understat no es exactamente la suma de sus tiros
assert len(ren) and ren["jugador"].notna().all()
print("Sin emparejar (con xG o xA):", sorted(set(sin_emparejar)) or "ninguno")

# ---------- Resultados de cada competición (para la jornada y la clasificación) ----------
cal_f = SRC / "whoscored_calendario.csv"
cal = pd.read_csv(cal_f) if cal_f.exists() else pd.DataFrame(columns=["league", "stage_id", "date", "home_team", "away_team", "home_score", "away_score"])
competicion = pd.DataFrame({
    "competicion": cal["league"].map(COMP), "fase": cal["stage_id"], "fecha": cal["date"].astype(str).str[:10],
    "local": cal["home_team"], "visitante": cal["away_team"],
    "goles_local": cal["home_score"].astype("Int64"), "goles_visitante": cal["away_score"].astype("Int64"),
}).sort_values(["competicion", "fecha"])

# la Liga entera de Understat (accesible desde la nube) y la fase de liga de la Copa de Europa de ESPN: se usa la fuente
# con más partidos de cada competición (la de WhoScored solo llega cuando el Mac está encendido)
def resultados(comp, df):
    global competicion
    if len(df) > (competicion["competicion"] == comp).sum():
        competicion = pd.concat([competicion[competicion["competicion"] != comp], df], ignore_index=True)

uc_f = SRC / "understat_calendario.csv"
if uc_f.exists():
    uc = pd.read_csv(uc_f)
    resultados("La Liga", pd.DataFrame({"competicion": "La Liga", "fase": "liga", "fecha": uc["date"].astype(str).str[:10],
                                        "local": uc["home_team"], "visitante": uc["away_team"],
                                        "goles_local": uc["home_goals"].astype("Int64"), "goles_visitante": uc["away_goals"].astype("Int64")}))
marc = [m for f in sorted((SRC / "espn").glob("marcador_uefa.champions_*.json")) for m in json.loads(f.read_text())]
if marc:
    loc = lambda m, l: next(e for e in m["equipos"] if e["local"] == l)
    resultados("Champions League", pd.DataFrame([{"competicion": "Champions League", "fase": "liga", "fecha": m["fecha"],
        "local": loc(m, True)["nombre"], "visitante": loc(m, False)["nombre"],
        "goles_local": int(loc(m, True)["goles"]), "goles_visitante": int(loc(m, False)["goles"])} for m in marc]).drop_duplicates())
competicion = competicion.sort_values(["competicion", "fecha"])

# ---------- Partidos sin eventos de WhoScored todavía (Mac apagado): datos básicos de ESPN y, en Liga, xG y tiros de Understat ----------
LIGA_ESPN = {"esp.1": "La Liga", "uefa.champions": "Champions League", "esp.copa_del_rey": "Copa del Rey", "esp.super_cup": "Supercopa de España"}
# profundidad de cada puesto de ESPN en el campo: así se reparten los titulares en las líneas del sistema ("4-2-3-1")
PROF = {"G": 0, "CD": 1, "LB": 1, "RB": 1, "LWB": 1.5, "RWB": 1.5, "DM": 2, "CM": 3, "LM": 3, "RM": 3, "AM": 4, "LW": 4.5, "RW": 4.5, "F": 5, "CF": 5, "ST": 5}
def minuto(txt):
    """ "90'+4'" -> 94"""
    n = [int(x) for x in re.findall(r"\d+", str(txt))]
    return sum(n[:2]) if n else 0

ws_fechas = pd.to_datetime(partidos["fecha"])
nombres_rm = jug.loc[jug["equipo"] == RM].drop_duplicates("jugador").set_index("jugador")["jugador_id"]
us_tiros_all = pd.read_csv(SRC / "understat_tiros.csv").assign(fecha=lambda d: d["date"].str[:10])
us_pm_all = pd.read_csv(SRC / "understat_jugadores_partido.csv").assign(fecha=lambda d: d["game"].str[:10])
nuevos = {k: [] for k in ("partidos", "eq", "jug", "al", "tiros", "inc")}
for fj in sorted((SRC / "espn").glob("[0-9]*.json")) if (SRC / "espn").exists() else []:
    r = json.loads(fj.read_text())
    cab = r["header"]["competitions"][0]
    fecha = cab["date"][:10]
    if (abs(ws_fechas - pd.Timestamp(fecha)) <= pd.Timedelta(days=1)).any():
        continue  # ya está con los eventos de WhoScored, más completos
    mid, comp = int(fj.stem), LIGA_ESPN[r["liga"]]
    lado = {c["homeAway"]: c for c in cab["competitors"]}
    local, visit = lado["home"]["team"]["displayName"], lado["away"]["team"]["displayName"]
    gl, gv = int(lado["home"]["score"]), int(lado["away"]["score"])
    nuevos["partidos"].append(dict(match_id=mid, fecha=fecha, competicion=comp, temporada=TEMPORADA, jornada="", local=local, visitante=visit,
                                   goles_local=gl, goles_visitante=gv, rival=visit if local == RM else local, entrenador_rm=ENTRENADOR, estadio=""))
    # nombres del Madrid como en WhoScored (los del resto de la temporada); los rivales, como los da ESPN
    rm_nom = match_names([j["athlete"]["displayName"] for e in r["rosters"] if e["team"]["displayName"] == RM for j in e["roster"]], nombres_rm.index.tolist())
    nom = lambda eq, n: rm_nom.get(n, n) if eq == RM else n
    # Understat (solo Liga): tiros y xG de jugador, con los equipos emparejados por nombre
    ut = us_tiros_all[us_tiros_all["fecha"] == fecha] if comp == "La Liga" else us_tiros_all.iloc[0:0]
    a_espn = match_names(list(ut["team"].unique()), [local, visit]) if len(ut) else {}
    up = us_pm_all[us_pm_all["fecha"] == fecha] if comp == "La Liga" else us_pm_all.iloc[0:0]
    xg_eq = {a_espn.get(t, t): v for t, v in ut[ut["result"] != "Own Goal"].groupby("team")["xg"].sum().items()}
    # nombres de Understat ("Kylian Mbappe-Lottin") -> los de la web, dentro de cada equipo
    n_us = {}
    for tu in set(ut["team"]) | set(up["team"]):
        te = a_espn.get(tu, tu)
        web = [nom(te, j["athlete"]["displayName"]) for e in r["rosters"] if e["team"]["displayName"] == te for j in e["roster"]]
        n_us.update(match_names(list(set(ut.loc[ut["team"] == tu, "player"]) | set(up.loc[up["team"] == tu, "player"])), web))
    for e in r["boxscore"]["teams"]:
        t, st = e["team"]["displayName"], {x["name"]: x.get("displayValue") for x in e["statistics"]}
        num = lambda k: float(st[k]) if st.get(k) not in (None, "") else np.nan
        otro_eq = visit if t == local else local
        nuevos["eq"].append(dict(match_id=mid, equipo=t, rival=otro_eq, goles=gl if t == local else gv,
                                 xg=round(xg_eq.get(t, 0), 2) if len(ut) else np.nan, tiros=num("totalShots"), tiros_puerta=num("shotsOnTarget"),
                                 posesion=num("possessionPct"), pases=num("totalPasses"),
                                 acierto_pase=round(100 * num("accuratePasses") / num("totalPasses"), 1) if num("totalPasses") else np.nan,
                                 xg_contra=round(xg_eq.get(otro_eq, 0), 2) if len(ut) else np.nan, fuente="ESPN"))
    # alineaciones, minutos y goles de cada jugador
    for e in r["rosters"]:
        t = e["team"]["displayName"]
        tit = [j for j in e["roster"] if j.get("starter")]
        lineas = [int(x) for x in str(e.get("formation", "")).split("-") if x.isdigit()]
        prof = lambda j: PROF.get(j["position"]["abbreviation"].split("-")[0], 3)
        # de izquierda a derecha: LB 0, CD-L 1, CD 2, CD-R 3, RB 4
        lado_j = lambda j: (lambda a: 0 if a[0] == "L" else 4 if a[0] == "R" else 1 if a.endswith("-L") else 3 if a.endswith("-R") else 2)(j["position"]["abbreviation"])
        campo = [j for j in sorted(tit, key=prof) if prof(j) > 0]
        coloca, i0 = {}, 0
        if sum(lineas) == len(campo):  # reparte por líneas del sistema, de izquierda a derecha
            for n_l, (k, n) in enumerate(zip(range(len(lineas)), lineas)):
                fila = sorted(campo[i0:i0 + n], key=lado_j)
                i0 += n
                for i, j in enumerate(fila):
                    lj = lado_j(j)
                    izq, der = lj <= 1 and n > 1, lj >= 3 and n > 1
                    lab = ("Left-Back" if lj == 0 else "Right-Back" if lj == 4 else "Centre-Back") if k == 0 else \
                          "Centre-Forward" if k == len(lineas) - 1 and n <= 2 else \
                          ("Left Winger" if izq else "Right Winger" if der else "Centre-Forward") if k == len(lineas) - 1 else \
                          "Defensive Midfield" if k == 1 and len(lineas) >= 4 else \
                          ("Left Winger" if izq else "Right Winger" if der else "Attacking Midfield") if k >= 2 else \
                          ("Left Midfield" if lj == 0 else "Right Midfield" if lj == 4 else "Central Midfield")
                    coloca[j["athlete"]["id"]] = (round(0.1 + 0.8 * (i + 0.5) / n, 3), round(0.23 + 0.63 * k / max(len(lineas) - 1, 1), 2), lab)
        for j in e["roster"]:
            jugo = j.get("starter") or j.get("subbedIn")
            n = nom(t, j["athlete"]["displayName"])
            px, py, lab = coloca.get(j["athlete"]["id"], (0.5, 0.06, "Goalkeeper") if j.get("starter") and prof(j) == 0 else (np.nan, np.nan, ""))
            nuevos["al"].append(dict(match_id=mid, equipo=t, jugador=n, dorsal=int(j["jersey"]) if str(j.get("jersey", "")).isdigit() else "",
                                     titular=int(bool(j.get("starter"))), posicion=lab, px=px, py=py))
            if not jugo:
                continue
            cambios = [minuto(p["clock"]["displayValue"]) for p in j.get("plays", []) if p.get("substitution")]
            ent = 0 if j.get("starter") else (cambios[0] if cambios else 90)
            sal = (cambios[-1] if j.get("subbedOut") and cambios else 90)
            stt = {x["name"]: x.get("value") or 0 for x in j.get("stats", [])}
            u = up[up["player"].map(lambda x: n_us.get(x, x)) == n] if len(up) else up
            nuevos["jug"].append(dict(match_id=mid, equipo=t, jugador_id=int(nombres_rm.get(n, j["athlete"]["id"])), jugador=n,
                                      titular=int(bool(j.get("starter"))), posicion="GK" if prof(j) == 0 else "", minutos=max(sal - ent, 1),
                                      goles=int(stt.get("totalGoals", 0)), asistencias=int(stt.get("goalAssists", 0)),
                                      xg=round(u["xg"].sum(), 2) if len(u) else (0.0 if len(ut) else np.nan),
                                      xa=round(u["xa"].sum(), 2) if len(u) else (0.0 if len(ut) else np.nan)))
    # tiros de Understat (Liga); el penalti se reconoce por su sitio exacto (Understat lo apunta como balón parado)
    for s_ in ut[ut["result"] != "Own Goal"].itertuples():
        t = a_espn.get(s_.team, s_.team)
        pen = s_.location_x == 0.885 and s_.location_y == 0.5
        nuevos["tiros"].append(dict(tiro_id=f"us{s_.shot_id}", match_id=mid, equipo=t, jugador=n_us.get(s_.player, s_.player), x=round(s_.location_x * 120, 1),
                                    y=round((1 - s_.location_y) * 80, 1), xg=round(s_.xg, 3), resultado=RES.get(s_.result, s_.result),
                                    subtipo="Penalty" if pen else "Open Play", patron_juego="Other" if pen else PAT.get(s_.situation, s_.situation), minuto=s_.minute))
    # incidencias: goles, tarjetas y cambios
    TIPO = {"Yellow Card": "amarilla", "Red Card": "roja", "Second Yellow": "segunda_amarilla"}
    inc_p = []
    for k in r.get("keyEvents", []):
        tx, part = k["type"]["text"], [p["athlete"]["displayName"] for p in k.get("participants", [])]
        t = k.get("team", {}).get("displayName")
        if not t or not part:
            continue
        mnt = minuto(k.get("clock", {}).get("displayValue"))
        tipo = "gol_pp" if "Own Goal" in tx else "penalti" if tx.startswith("Penalty - Scored") else "gol" if tx.startswith("Goal") else \
            TIPO.get(tx, "segunda_amarilla" if "Second" in tx else "cambio" if tx == "Substitution" else "")
        if tipo:
            inc_p.append(dict(match_id=mid, minuto=mnt, orden=mnt, equipo=t, tipo=tipo, jugador=nom(t, part[0]),
                              sale=nom(t, part[1]) if tipo == "cambio" and len(part) > 1 else ""))
    goles_inc = pd.Series([x["equipo"] for x in inc_p if x["tipo"] in ("gol", "penalti", "gol_pp")]).value_counts()
    if goles_inc.get(local, 0) != gl or goles_inc.get(visit, 0) != gv:  # ESPN apunta el gol en propia puerta al equipo del que lo marca
        for x in inc_p:
            if x["tipo"] == "gol_pp":
                x["equipo"] = visit if x["equipo"] == local else local
    nuevos["inc"].extend(inc_p)

if nuevos["partidos"]:
    print("Partidos solo con ESPN (falta el detalle de WhoScored):", [p["fecha"] for p in nuevos["partidos"]])
    pn = pd.DataFrame(nuevos["partidos"])
    partidos = pd.concat([partidos, pn], ignore_index=True).sort_values("fecha")
    en = pd.DataFrame(nuevos["eq"]); en.insert(0, "clave", en["match_id"].astype(str) + "|" + en["equipo"])
    eq = pd.concat([eq, en], ignore_index=True)
    jn = pd.DataFrame(nuevos["jug"]); jn.insert(0, "clave", jn["match_id"].astype(str) + "|" + jn["jugador_id"].astype(str))
    jug = pd.concat([jug, jn], ignore_index=True)
    alineaciones = pd.concat([alineaciones, pd.DataFrame(nuevos["al"])], ignore_index=True)
    tiros = pd.concat([tiros, pd.DataFrame(nuevos["tiros"])], ignore_index=True)
    incidencias = pd.concat([incidencias, pd.DataFrame(nuevos["inc"])], ignore_index=True)
    # comprobación: goles de las incidencias = marcador
    for p in nuevos["partidos"]:
        gi = incidencias[(incidencias["match_id"] == p["match_id"]) & incidencias["tipo"].isin(["gol", "penalti", "gol_pp"])]["equipo"].value_counts()
        assert gi.get(p["local"], 0) == p["goles_local"] and gi.get(p["visitante"], 0) == p["goles_visitante"], (p["fecha"], gi.to_dict())

# ---------- Guardar ----------
OUT.mkdir(parents=True, exist_ok=True)
for name, df in {"partidos": partidos, "metricas_equipo": eq, "metricas_jugador": jug, "pases": pases,
                 "tiros": tiros, "rendimiento": ren, "alineaciones": alineaciones, "competicion": competicion,
                 "incidencias": incidencias, "red_nodos": red_nodos, "red_enlaces": red_enlaces, "acciones": acciones}.items():
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"{name}.csv: {len(df)} filas")
