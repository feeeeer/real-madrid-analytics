"""Procesa las fuentes de la temporada (data/fuentes/<temporada>) y escribe los datos de la web (docs/data).

Uso: python pipeline/procesar.py [data/fuentes/2026-2027] [docs/data]

Solo entran los partidos que ya tienen eventos de WhoScored; los de Liga, además, el xG de Understat (el resto
espera a la siguiente ejecución). Champions y Copa no tienen xG (Understat solo cubre la Liga): sus tiros salen de
los eventos de WhoScored con el xG vacío. Coordenadas: Opta 0-100 -> campo 120x80, cada equipo atacando de izquierda a derecha.
"""
import ast, re, sys, unicodedata
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
g["home_team"], g["away_team"] = g["home_team"].map(to_ws), g["away_team"].map(to_ws)
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

ROL = {"F": ["xg90", "xa90", "xg_chain90"], "M": ["xg_chain90", "xg_buildup90", "xa90", "int90", "tklw90"],
       "D": ["int90", "tklw90", "xg_buildup90"]}
ws_rm = jug[(jug["equipo"] == RM) & jug["match_id"].isin(liga_ids)].groupby("jugador").agg(
    pases=("pases", "sum"), acierto=("acierto_pase", lambda s: np.average(s, weights=jug.loc[s.index, "pases"].clip(lower=1))),
    prog=("pases_progresivos", "sum"), recup=("recuperaciones", "sum"), dg=("duelos_ganados", "sum"),
    dp=("duelos_perdidos", "sum"), perd=("perdidas_peligrosas", "sum"), mins_ws=("minutos", "sum"))
us_rm = us_liga[us_liga["team"] == RM]
m_ws = match_names(us_rm["player"].tolist(), ws_rm.index.tolist())
fb_rm = fb_misc[fb_misc["team"] == RM]
m_fb = match_names(us_rm["player"].tolist(), fb_rm["player"].tolist())

ren = []
for r in us_rm.itertuples():
    grupo = grupo_de(r.team, r.player, r.position)
    if r.minutes < 90 or grupo in (None, "GK"):
        continue
    w = ws_rm.loc[m_ws[r.player]] if r.player in m_ws else None
    f = fb_rm[fb_rm["player"] == m_fb.get(r.player)]
    f90 = f["90s"].iloc[0] if len(f) and f["90s"].iloc[0] > 0 else None
    val = {"xg90": r.xg * 90 / r.minutes, "xa90": r.xa * 90 / r.minutes, "xg_chain90": r.xg_chain * 90 / r.minutes,
           "xg_buildup90": r.xg_buildup * 90 / r.minutes,
           "int90": f["Performance_Int"].iloc[0] / f90 if f90 else np.nan, "tklw90": f["Performance_TklW"].iloc[0] / f90 if f90 else np.nan}
    pcts = {k: pct((liga if k not in ("int90", "tklw90") else fbm).query("grupo == @grupo")[k], v)
            for k, v in val.items() if not np.isnan(v)}
    rol = [pcts[k] for k in ROL[grupo] if k in pcts]
    pct_rol = round(np.mean(rol)) if rol else np.nan
    perd90 = w["perd"] * 90 / w["mins_ws"] if w is not None else np.nan
    malos, buenos = [], []
    if r.goals - r.xg <= -1:
        malos.append(f"remata por debajo de su xG ({r.goals} goles con {r.xg:.1f} xG)")
    if r.assists - r.xa <= -1:
        malos.append(f"sus pases generan más de lo que acaban en asistencia ({r.assists} con {r.xa:.1f} xA)")
    if pct_rol < 35:
        malos.append(f"percentil {pct_rol} de su puesto en la Liga en las métricas de su rol")
    if r.goals - r.xg >= 1:
        buenos.append(f"remata por encima de su xG ({r.goals} goles con {r.xg:.1f} xG)")
    if pct_rol >= 75:
        buenos.append(f"percentil {pct_rol} de su puesto en la Liga")
    if malos and buenos:
        malos.append("aunque " + " y ".join(buenos))
    ren.append(dict(
        jugador=m_ws.get(r.player, r.player), puesto={"D": "Defensa", "M": "Centrocampista", "F": "Delantero"}[grupo],
        minutos=r.minutes, goles=r.goals, xg=round(r.xg, 2), g_menos_xg=round(r.goals - r.xg, 2), asistencias=r.assists,
        xa=round(r.xa, 2), a_menos_xa=round(r.assists - r.xa, 2), xg90=round(val["xg90"], 2), xa90=round(val["xa90"], 2),
        xgchain90=round(val["xg_chain90"], 2), pct_rol=pct_rol,
        acierto_pase=round(w["acierto"], 1) if w is not None else np.nan,
        prog90=round(w["prog"] * 90 / w["mins_ws"], 1) if w is not None else np.nan,
        recup90=round(w["recup"] * 90 / w["mins_ws"], 1) if w is not None else np.nan,
        duelos_pct=round(100 * w["dg"] / max(w["dg"] + w["dp"], 1), 1) if w is not None else np.nan,
        perdidas90=round(perd90, 2), _malos=malos, _buenos=buenos,
    ))
ren = pd.DataFrame(ren)
# pérdidas peligrosas: alerta si está en el cuartil más alto de la plantilla
lim = ren["perdidas90"].quantile(0.75)
for i, r in ren.iterrows():
    if r["perdidas90"] > lim and r["perdidas90"] > 0.5:
        r["_malos"].append(f"{r['perdidas90']:.1f} pérdidas peligrosas por 90 min, de las más altas de la plantilla")
ren["veredicto"] = ren.apply(lambda r: "Por debajo" if r["_malos"] else "Por encima" if r["_buenos"] else "En línea", axis=1)
ren["motivo"] = ren.apply(lambda r: "; ".join(r["_malos"] or r["_buenos"]) or "Sin desviaciones claras", axis=1)
ren = ren.drop(columns=["_malos", "_buenos"]).sort_values(["veredicto", "minutos"], ascending=[True, False])

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

# ---------- Guardar ----------
OUT.mkdir(parents=True, exist_ok=True)
for name, df in {"partidos": partidos, "metricas_equipo": eq, "metricas_jugador": jug, "pases": pases,
                 "tiros": tiros, "rendimiento": ren, "alineaciones": alineaciones}.items():
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"{name}.csv: {len(df)} filas")
