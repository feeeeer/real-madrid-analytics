"""Programa único de la temporada: descarga lo nuevo de cada fuente y regenera los datos de la web.

Uso: python pipeline/actualizar.py

- Understat: calendario, xG por jugador y partido, tiros con coordenadas (Liga).
- WhoScored: eventos Opta de cada partido de Liga, Champions y Copa (solo descarga los que faltan; un partido
  descargado no se vuelve a pedir).
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
# soccerdata no trae la Champions ni la Copa para WhoScored: se le añaden en su fichero de ligas propias
EXTRA = {"INT-Champions League": {"WhoScored": "Europe - Champions League", "season_start": "Aug", "season_end": "May"},
         "ESP-Copa del Rey": {"WhoScored": "Spain - Copa del Rey", "season_start": "Aug", "season_end": "May"}}
_cfg = Path(os.environ.get("SOCCERDATA_DIR", Path.home() / "soccerdata")) / "config"
_cfg.mkdir(parents=True, exist_ok=True)
(_cfg / "league_dict.json").write_text(json.dumps(EXTRA))
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
    # una competición que falle no frena a las demás; el calendario de la que falle conserva su última versión
    viejo = pd.read_csv(F / "whoscored_partidos_rm.csv") if (F / "whoscored_partidos_rm.csv").exists() else pd.DataFrame(columns=["league"])
    viejo_cal = pd.read_csv(F / "whoscored_calendario.csv") if (F / "whoscored_calendario.csv").exists() else pd.DataFrame(columns=["league"])
    calendarios, completos, errores = [], [], []
    for liga in [LIGA, *EXTRA]:
        print(f"   -- {liga}", flush=True)
        try:
            ws = sd.WhoScored(liga, SEASON, headless=True)
            sched = ws.read_schedule(force_cache=False).reset_index()
            # terminado = empezó hace más de 4 horas y tiene marcador (así nunca se guarda un partido a medias)
            fin = pd.to_datetime(sched["date"], utc=True) < pd.Timestamp(hoy) - pd.Timedelta(hours=4)
            jugados = sched[es_rm(sched) & fin & sched["home_score"].notna()]
            hechos = {int(p.stem) for p in (F / "whoscored_eventos").glob("*.csv")}
            nuevos = [int(g) for g in jugados["game_id"] if int(g) not in hechos]
            print(f"   {len(jugados)} partidos jugados, {len(nuevos)} nuevos", flush=True)
            for gid in nuevos:
                ev = ws.read_events(match_id=gid).reset_index()
                if len(ev) < 500:  # un partido completo tiene ~1.500; algunas rondas de Copa no tienen datos Opta
                    assert liga != LIGA, f"partido {gid}: solo {len(ev)} eventos"
                    print(f"   partido {gid}: solo {len(ev)} eventos, se omite", flush=True)
                    continue
                ev.to_csv(F / "whoscored_eventos" / f"{gid}.csv", index=False)
                print(f"   partido {gid}: {len(ev)} eventos", flush=True)
            calendarios.append(jugados)
            # todos los partidos ya jugados de la competición (no solo los del Madrid): resultados de la jornada y clasificación
            completos.append(sched[fin & sched["home_score"].notna()][["league", "stage_id", "date", "home_team", "away_team", "home_score", "away_score"]])
        except Exception:
            traceback.print_exc()
            errores.append(liga)
            calendarios.append(viejo[viejo["league"] == liga])
            completos.append(viejo_cal[viejo_cal["league"] == liga])
    guardar(pd.concat(calendarios, ignore_index=True).drop(columns="index", errors="ignore"), "whoscored_partidos_rm")
    guardar(pd.concat(completos, ignore_index=True).drop(columns="index", errors="ignore"), "whoscored_calendario")
    assert not errores, f"fallaron: {errores}"


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
