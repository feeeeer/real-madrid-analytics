"""Programa único de la temporada: descarga lo nuevo de cada fuente y regenera los datos de la web.

Uso: python pipeline/actualizar.py

- Understat: calendario, xG por jugador y partido, tiros con coordenadas (Liga).
- WhoScored: eventos Opta de cada partido (solo descarga los que faltan; un partido descargado no se vuelve a pedir).
- FBref: estadísticas básicas de toda la Liga (para los percentiles por puesto).
Si una fuente falla se conservan sus últimos datos, se procesa igual y el programa termina con error para que
GitHub avise por email.
"""
import json, os, subprocess, sys, traceback
from datetime import datetime, timezone
from pathlib import Path

import certifi
import pandas as pd

os.environ.setdefault("SSL_CERT_FILE", certifi.where())  # Python de python.org en Mac no trae certificados
import soccerdata as sd  # noqa: E402

RM, LIGA = "Real Madrid", "ESP-La Liga"
hoy = datetime.now(timezone.utc)
T = hoy.year if hoy.month >= 7 else hoy.year - 1
SEASON = f"{T}-{T + 1}"
F = Path("data/fuentes") / SEASON
(F / "whoscored_eventos").mkdir(parents=True, exist_ok=True)
fallos = []


def guardar(df, nombre):
    if isinstance(df.columns, pd.MultiIndex):  # FBref devuelve columnas en dos niveles
        df.columns = ["_".join(str(c) for c in col if c and not str(c).startswith("Unnamed")).strip("_") for col in df.columns]
    df = df.reset_index()
    df.to_csv(F / f"{nombre}.csv", index=False)
    print(f"   {nombre}.csv: {len(df)} filas", flush=True)


def es_rm(df):
    return df["home_team"].astype(str).str.contains(RM) | df["away_team"].astype(str).str.contains(RM)


def paso(nombre):
    def deco(fn):
        print(f"\n== {nombre} ==", flush=True)
        try:
            fn()
        except Exception:
            traceback.print_exc()
            fallos.append(nombre)
    return deco


@paso("understat")
def _():
    us = sd.Understat(LIGA, SEASON)
    sched = us.read_schedule().reset_index()
    rm = sched[es_rm(sched) & sched["is_result"]]
    guardar(rm, "understat_partidos_rm")
    guardar(us.read_player_season_stats(), "understat_jugadores_liga")
    ids = rm["game_id"].tolist()
    if ids:  # soccerdata guarda en caché cada partido: solo se descargan los nuevos
        guardar(us.read_player_match_stats(match_id=ids), "understat_jugadores_partido")
        guardar(us.read_shot_events(match_id=ids), "understat_tiros")


@paso("whoscored")
def _():
    ws = sd.WhoScored(LIGA, SEASON, headless=True)
    sched = ws.read_schedule(force_cache=False).reset_index()
    # terminado = empezó hace más de 4 horas y tiene marcador (así nunca se guarda un partido a medias)
    fin = pd.to_datetime(sched["date"], utc=True) < pd.Timestamp(hoy) - pd.Timedelta(hours=4)
    jugados = sched[es_rm(sched) & fin & sched["home_score"].notna()]
    guardar(jugados, "whoscored_partidos_rm")
    hechos = {int(p.stem) for p in (F / "whoscored_eventos").glob("*.csv")}
    nuevos = [int(g) for g in jugados["game_id"] if int(g) not in hechos]
    print(f"   {len(nuevos)} partidos nuevos", flush=True)
    for gid in nuevos:
        ev = ws.read_events(match_id=gid).reset_index()
        assert len(ev) > 500, f"partido {gid}: solo {len(ev)} eventos"  # un partido completo tiene ~1.500
        ev.to_csv(F / "whoscored_eventos" / f"{gid}.csv", index=False)
        print(f"   partido {gid}: {len(ev)} eventos", flush=True)


@paso("fbref")
def _():
    guardar(sd.FBref(LIGA, SEASON, headless=True).read_player_season_stats("misc"), "fbref_jugadores_misc")


print("\n== procesar ==", flush=True)
r = subprocess.run([sys.executable, "pipeline/procesar.py", str(F), "docs/data"])
if r.returncode:
    fallos.append("procesar")

n = len(pd.read_csv("docs/data/partidos.csv")) if Path("docs/data/partidos.csv").exists() else 0
Path("docs/data/estado.json").write_text(json.dumps(
    {"actualizado": hoy.isoformat(timespec="minutes"), "temporada": SEASON, "partidos": n, "fallos": fallos}, ensure_ascii=False))
print(f"\nPartidos analizados: {n}. Fallos: {fallos or 'ninguno'}")
sys.exit(1 if fallos else 0)
