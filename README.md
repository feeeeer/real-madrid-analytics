# Real Madrid Analytics

Web de análisis de datos del Real Madrid que se actualiza sola después de cada partido.

**Web:** [real-madrid-analytics.vercel.app](https://real-madrid-analytics.vercel.app)

- **Post-partido** de cada jornada de la temporada: comparativa con el rival, informe táctico automático, mapas de pases (origen → destino) y de tiros por jugador, xG acumulado.
- **Rendimiento vs esperado**: goles frente a xG, asistencias frente a xA, percentil de cada jugador frente a los de su puesto en toda la Liga y pérdidas peligrosas.
- **Temporada**: xG a favor y en contra partido a partido, mapas acumulados por jugador.
- **Histórico**: todos los resultados oficiales disponibles en fuentes abiertas, con alineaciones de los dos equipos desde 2012 y de las grandes finales anteriores, goleadores y rondas.
- **Títulos**: el palmarés completo; cada título enlaza a su clasificación de Liga o a los partidos hasta la copa.

## Cómo funciona

```
Mac (runner propio de GitHub Actions), 02:00 y 08:00
  pipeline/actualizar.py  ->  Understat + WhoScored + FBref  ->  data/fuentes/<temporada>/
  pipeline/procesar.py    ->  métricas, informe y mapas       ->  docs/data/*.csv
Servidores de GitHub, 08:30
  pipeline/historico.py   ->  engsoccerdata + Transfermarkt + ESPN  ->  docs/data/historico*.csv
Vercel publica docs/ en cada cambio
```

WhoScored y FBref bloquean las IPs de los servidores de GitHub, así que el análisis de la temporada se ejecuta en un Mac propio registrado como runner. Si está dormido a la hora programada, la tarea espera en cola y se ejecuta al despertar. El histórico no tiene ese problema y corre en la nube.

Cada partido de WhoScored se descarga una sola vez (solo si empezó hace más de 4 horas y tiene marcador). Si una fuente falla se conservan sus últimos datos, la web se publica igual y GitHub avisa por email.

## Fuentes

| Fuente | Qué aporta |
|---|---|
| WhoScored (vía [soccerdata](https://github.com/probberechts/soccerdata)) | Eventos Opta de cada partido con coordenadas: pases, tiros, entradas, duelos |
| Understat (vía soccerdata) | xG y xA por tiro, jugador y partido |
| FBref (vía soccerdata) | Estadísticas básicas de toda la Liga, para los percentiles por puesto |
| engsoccerdata | Liga 1928/29–2011/12 y Copa de Europa 1955–2012 |
| [transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets) (CC0) | Todas las competiciones 2012/13–2025/26, con alineaciones |
| ESPN | Resultados de la temporada actual en todas las competiciones |
| Wikipedia | Copa y Supercopa antes de 2012, Recopa, Copa de la UEFA, Supercopa de Europa, Intercontinental, Mundial de Clubes, Copa de la Liga y Copa Latina; estadios, goleadores y jornadas de Liga; rondas, penaltis, alineaciones de finales, clasificaciones de Liga y palmarés. Extraído una vez de las páginas de temporada del club y de cada final (en.wikipedia), y del palmarés y las ediciones de Copa y Supercopa (es.wikipedia) y guardado en `data/historico/wikipedia/` (`wikipedia_rm.json` y `copa_en.json`, las ediciones de Copa en inglés). Los estadios de los partidos fuera de casa que no da ninguna fuente se deducen del campo del rival en su visita más cercana (máx. 3 años) |

La Copa del Rey anterior a 2012 está incompleta (sobre todo antes de 1940): Wikipedia no tiene todos sus partidos.

## Métricas

- **xG / xG concedido**: suma del xG de Understat de los tiros de cada equipo. `xg_contraataque`: tiros que WhoScored marca como contraataque (*FastBreak*).
- **PPDA**: pases del rival en su 60 % de campo por cada entrada, intercepción o falta nuestra en esa zona. Bajo = presión alta.
- **Pérdidas peligrosas**: balón perdido en el propio tercio sin superar el medio campo (sin contar saques de puerta).
- **Pases progresivos**: pase completado que avanza 15 yardas o más.
- **% duelos ganados**: entradas y duelos aéreos ganados sobre el total.
- **Rendimiento vs esperado**: "por debajo" si goles − xG ≤ −1, asistencias − xA ≤ −1, percentil de rol < 35 (frente a su puesto en la Liga, mínimo 270 min) o pérdidas peligrosas en el cuartil más alto de la plantilla.

Opta no registra presiones, así que no hay métricas de presión.

## Ejecutar en local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python pipeline/actualizar.py        # temporada
python pipeline/historico.py         # histórico (--base para reconstruirlo desde cero)
python3 -m http.server -d docs 8000  # abrir http://localhost:8000
```
