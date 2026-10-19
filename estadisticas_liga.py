"""
Módulo de Cálculo de Estadísticas Avanzadas de Liga (Estilo SoccerStats)
Basado en datos de partidos finalizados y próximos de 'betplay_flashscore.db'.

Calcula:
1. Tabla General (Clasificación con PPG, Forma últimos 8, Clean Sheets, Scoring Rate, MPP)
2. Tablas Local / Visitante (Home / Away)
3. Rendimiento Relativo Local vs Visitante (Relative Home/Away Performance)
4. Forma Relativa (Relative Form: Últimos 8 vs Temporada completa)
5. Índice de Rendimiento por Puntos (PPI - Points Performance Index)
6. Calificación de Rendimiento (Performance Rating / PR)
7. Análisis de Calendario Restante (Run-in Analysis: Rivales jugados vs pendientes, Próximos 4)
8. Tabla de Segmentos (Segments Table: Distribución en 5 quintiles de puntos)
9. Estadísticas Globales de Liga (Over/Under, BTTS, % Victorias Local/Empate/Visitante, Promedio de Goles)
10. Tablas de Ataque y Defensa (Offence / Defence)
"""

import os
import re
import sys
import json
import sqlite3
import unicodedata
from datetime import datetime
from typing import Dict, List, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')
ESTADISTICAS_DIR = os.path.join(BASE_DIR, 'estadisticas')


def slugify(text: Optional[str]) -> str:
    if not text:
        return "desconocido"
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text or "desconocido"


def parse_jornada_num(jornada_str: Optional[str]) -> int:
    if not jornada_str:
        return 999
    m = re.search(r'\d+', jornada_str)
    return int(m.group()) if m else 999


def classify_competition_type(pais_nombre: str, nombre_flashscore: str, nombre_betplay: Optional[str] = "") -> str:
    """
    Clasifica la competición en:
    - 'Torneo Internacional' (Champions, Libertadores, Mundial, selecciones o pais Internacional)
    - 'Copa' (Copas nacionales: Copa del Rey, FA Cup, DFB-Pokal, Coppa Italia, etc.)
    - 'Liga' (Ligas regulares de cualquier división)
    """
    p = (pais_nombre or '').lower()
    n = (nombre_flashscore or '').lower()
    b = (nombre_betplay or '').lower()

    # 1. Torneo Internacional
    intl_keywords = [
        'internacional', 'champions league', 'europa league', 'conference league',
        'copa libertadores', 'copa sudamericana', 'nations league', 'campeonato del mundo',
        'world cup', 'eurocopa', 'copa america', 'concacaf', 'conmebol', 'libertadores',
        'sudamericana', 'fifa', 'uefa', 'mundial', 'esports'
    ]
    if p == 'internacional' or any(k in n for k in intl_keywords):
        return 'Torneo Internacional'

    # 2. Copa nacional
    cup_keywords = [
        'copa', 'cup', 'pokal', 'beker', 'taca', 'taça', 'coppa', 'coupe',
        'supercopa', 'super cup', 'trophy', 'shield'
    ]
    if any(k in n for k in cup_keywords) or any(k in b for k in cup_keywords):
        return 'Copa'

    # 3. Liga regular
    return 'Liga'


class LeagueStatsCalculator:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def get_competitions(self) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT c.id, c.pais_nombre, c.nombre_betplay, c.nombre_flashscore,
                   count(p.id) as total_partidos
            FROM competiciones c
            LEFT JOIN partidos p ON c.id = p.competicion_id
            GROUP BY c.id
            HAVING total_partidos > 0
            ORDER BY c.pais_nombre, c.nombre_flashscore
        """)
        return [dict(r) for r in cur.fetchall()]

    def calculate_for_competition(self, competicion_id: int) -> Dict[str, Any]:
        cur = self.conn.cursor()
        
        # 1. Obtener información de la competición
        cur.execute("SELECT * FROM competiciones WHERE id = ?", (competicion_id,))
        comp_row = cur.fetchone()
        if not comp_row:
            raise ValueError(f"Competición con id {competicion_id} no encontrada.")
        competition_info = dict(comp_row)
        competition_info['tipo_competicion'] = classify_competition_type(
            competition_info.get('pais_nombre', ''),
            competition_info.get('nombre_flashscore', ''),
            competition_info.get('nombre_betplay', '')
        )

        # 2. Cargar partidos finalizados (resultados)
        cur.execute("""
            SELECT id, jornada, fecha_hora, equipo_local, equipo_visitante,
                   goles_local, goles_visitante, link
            FROM partidos
            WHERE competicion_id = ? AND tipo = 'resultado' AND goles_local IS NOT NULL
            ORDER BY rowid ASC
        """, (competicion_id,))
        results = [dict(r) for r in cur.fetchall()]

        # 3. Cargar partidos próximos (fixture restante)
        cur.execute("""
            SELECT id, jornada, fecha_hora, equipo_local, equipo_visitante, link
            FROM partidos
            WHERE competicion_id = ? AND tipo = 'proximo'
            ORDER BY rowid ASC
        """, (competicion_id,))
        upcoming = [dict(r) for r in cur.fetchall()]

        if not results:
            return {
                "competition": competition_info,
                "error": "No hay partidos finalizados con marcador para esta competición."
            }

        # 4. Identificar equipos únicos
        teams_set = set()
        for m in results:
            teams_set.add(m['equipo_local'])
            teams_set.add(m['equipo_visitante'])
        for m in upcoming:
            teams_set.add(m['equipo_local'])
            teams_set.add(m['equipo_visitante'])
        teams = sorted(list(teams_set))
        num_teams = len(teams)
        total_season_matches_per_team = (num_teams - 1) * 2 if num_teams > 1 else 0

        # Ordenar resultados por jornada para consistencia cronológica
        results.sort(key=lambda m: (parse_jornada_num(m.get('jornada')), m.get('fecha_hora', '')))
        upcoming.sort(key=lambda m: (parse_jornada_num(m.get('jornada')), m.get('fecha_hora', '')))

        # 5. Estructura de datos por equipo
        team_stats: Dict[str, Dict[str, Any]] = {}
        for t in teams:
            team_stats[t] = {
                'team': t,
                'home': {'GP': 0, 'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'GD': 0, 'Pts': 0, 'pPts': 0.0, 'CS': 0, 'SR': 0, 'matches': []},
                'away': {'GP': 0, 'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'GD': 0, 'Pts': 0, 'pPts': 0.0, 'CS': 0, 'SR': 0, 'matches': []},
                'total': {'GP': 0, 'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'GD': 0, 'Pts': 0, 'pPts': 0.0, 'CS': 0, 'SR': 0, 'matches': []},
                'upcoming_home': [],
                'upcoming_away': []
            }

        # Procesar partidos jugados
        for m in results:
            home = m['equipo_local']
            away = m['equipo_visitante']
            gh = m['goles_local']
            ga = m['goles_visitante']

            # Resultado para local
            if gh > ga:
                wh, dh, lh = 1, 0, 0
                ptsh = 3
                pptsh = 1.0
                wa, da, la = 0, 0, 1
                ptsa = 0
                pptsa = 0.0
            elif gh == ga:
                wh, dh, lh = 0, 1, 0
                ptsh = 1
                pptsh = 0.5
                wa, da, la = 0, 1, 0
                ptsa = 1
                pptsa = 0.5
            else:
                wh, dh, lh = 0, 0, 1
                ptsh = 0
                pptsh = 0.0
                wa, da, la = 1, 0, 0
                ptsa = 3
                pptsa = 1.0

            csh = 1 if ga == 0 else 0
            srh = 1 if gh > 0 else 0
            csa = 1 if gh == 0 else 0
            sra = 1 if ga > 0 else 0

            # Actualizar Local
            sh = team_stats[home]['home']
            st_h = team_stats[home]['total']
            for s in (sh, st_h):
                s['GP'] += 1
                s['W'] += wh
                s['D'] += dh
                s['L'] += lh
                s['GF'] += gh
                s['GA'] += ga
                s['GD'] += (gh - ga)
                s['Pts'] += ptsh
                s['pPts'] += pptsh
                s['CS'] += csh
                s['SR'] += srh

            match_record_h = {
                'opponent': away, 'venue': 'home', 'gf': gh, 'ga': ga,
                'pts': ptsh, 'ppts': pptsh, 'jornada': m.get('jornada')
            }
            team_stats[home]['home']['matches'].append(match_record_h)
            team_stats[home]['total']['matches'].append(match_record_h)

            # Actualizar Visitante
            sa = team_stats[away]['away']
            st_a = team_stats[away]['total']
            for s in (sa, st_a):
                s['GP'] += 1
                s['W'] += wa
                s['D'] += da
                s['L'] += la
                s['GF'] += ga
                s['GA'] += gh
                s['GD'] += (ga - gh)
                s['Pts'] += ptsa
                s['pPts'] += pptsa
                s['CS'] += csa
                s['SR'] += sra

            match_record_a = {
                'opponent': home, 'venue': 'away', 'gf': ga, 'ga': gh,
                'pts': ptsa, 'ppts': pptsa, 'jornada': m.get('jornada')
            }
            team_stats[away]['away']['matches'].append(match_record_a)
            team_stats[away]['total']['matches'].append(match_record_a)

        # Procesar partidos próximos
        for m in upcoming:
            home = m['equipo_local']
            away = m['equipo_visitante']
            if home in team_stats:
                team_stats[home]['upcoming_home'].append({'opponent': away, 'venue': 'home', 'jornada': m.get('jornada')})
            if away in team_stats:
                team_stats[away]['upcoming_away'].append({'opponent': home, 'venue': 'away', 'jornada': m.get('jornada')})

        # 6. Calcular métricas derivadas por equipo (PPG, pPPG, etc.)
        for t, data in team_stats.items():
            for scope in ('home', 'away', 'total'):
                s = data[scope]
                gp = s['GP']
                s['PPG'] = round(s['Pts'] / gp, 2) if gp > 0 else 0.0
                s['pPPG'] = round((s['pPts'] / gp) * 100.0, 1) if gp > 0 else 0.0
                s['CS_pct'] = round((s['CS'] / gp) * 100.0, 1) if gp > 0 else 0.0
                s['SR_pct'] = round((s['SR'] / gp) * 100.0, 1) if gp > 0 else 0.0

            # Forma últimos 8 partidos
            last_8 = data['total']['matches'][-8:]
            pts_last_8 = sum(m['pts'] for m in last_8)
            gp_last_8 = len(last_8)
            data['ppg_last_8'] = round(pts_last_8 / gp_last_8, 2) if gp_last_8 > 0 else 0.0
            data['pts_last_8'] = pts_last_8

            # MPP: Máximos puntos posibles
            remaining_matches = total_season_matches_per_team - data['total']['GP']
            data['mpp'] = data['total']['Pts'] + (3 * max(0, remaining_matches))

        # 7. Construcción de tablas
        # A) Tabla General
        league_table = []
        for t, data in team_stats.items():
            tot = data['total']
            league_table.append({
                'team': t,
                'GP': tot['GP'],
                'W': tot['W'],
                'D': tot['D'],
                'L': tot['L'],
                'GF': tot['GF'],
                'GA': tot['GA'],
                'GD': tot['GD'],
                'Pts': tot['Pts'],
                'PPG': tot['PPG'],
                'last_8_PPG': data['ppg_last_8'],
                'CS': f"{int(round(tot['CS_pct']))}%",
                'SR': f"{int(round(tot['SR_pct']))}%",
                'MPP': data['mpp']
            })

        # Criterio de orden de clasificación: Puntos, Diferencia de Gol, Goles a Favor
        league_table.sort(key=lambda x: (x['Pts'], x['GD'], x['GF']), reverse=True)
        for idx, row in enumerate(league_table, start=1):
            row['rank'] = idx

        # B) Tabla Local (Home Table)
        home_table = []
        for t, data in team_stats.items():
            h = data['home']
            home_table.append({
                'team': t,
                'GP': h['GP'],
                'W': h['W'],
                'D': h['D'],
                'L': h['L'],
                'GF': h['GF'],
                'GA': h['GA'],
                'GD': h['GD'],
                'Pts': h['Pts'],
                'PPG': h['PPG']
            })
        home_table.sort(key=lambda x: (x['Pts'], x['GD'], x['GF']), reverse=True)
        for idx, row in enumerate(home_table, start=1):
            row['rank'] = idx

        # C) Tabla Visitante (Away Table)
        away_table = []
        for t, data in team_stats.items():
            a = data['away']
            away_table.append({
                'team': t,
                'GP': a['GP'],
                'W': a['W'],
                'D': a['D'],
                'L': a['L'],
                'GF': a['GF'],
                'GA': a['GA'],
                'GD': a['GD'],
                'Pts': a['Pts'],
                'PPG': a['PPG']
            })
        away_table.sort(key=lambda x: (x['Pts'], x['GD'], x['GF']), reverse=True)
        for idx, row in enumerate(away_table, start=1):
            row['rank'] = idx

        # D) Rendimiento Relativo Local / Visitante (Relative Home / Away)
        relative_home_away = []
        for t, data in team_stats.items():
            ppg_h = data['home']['PPG']
            ppg_a = data['away']['PPG']
            diff = round(ppg_h - ppg_a, 2)
            sign = "+" if diff > 0 else ""
            relative_home_away.append({
                'team': t,
                'GPh': data['home']['GP'],
                'GPa': data['away']['GP'],
                'Pts': data['total']['Pts'],
                'PPG_home': ppg_h,
                'PPG_away': ppg_a,
                'PPG_diff': f"{sign}{diff:.2f}",
                'raw_diff': diff
            })
        relative_home_away.sort(key=lambda x: (x['Pts'], -abs(x['raw_diff'])), reverse=True)
        for idx, row in enumerate(relative_home_away, start=1):
            row['rank'] = idx

        # E) Forma Relativa (Relative Form: Últimos 8 vs Todo)
        relative_form = []
        for t, data in team_stats.items():
            ppg_all = data['total']['PPG']
            ppg_last8 = data['ppg_last_8']
            if ppg_all > 0:
                rel_form_pct = round(((ppg_last8 - ppg_all) / ppg_all) * 100.0)
            else:
                rel_form_pct = 0
            sign = "+" if rel_form_pct > 0 else ("-" if rel_form_pct < 0 else "")
            relative_form.append({
                'team': t,
                'GP': data['total']['GP'],
                'Pts': data['total']['Pts'],
                'PPG_last_8': ppg_last8,
                'PPG_all': ppg_all,
                'relative_form': f"{sign}{abs(rel_form_pct)}%"
            })
        relative_form.sort(key=lambda x: (x['Pts'], x['PPG_last_8']), reverse=True)
        for idx, row in enumerate(relative_form, start=1):
            row['rank'] = idx

        # F) Points Performance Index (PPI) & Performance Ratings (PR)
        # Opponents PPG y pPPG según Soccerstats:
        # - Para partidos en casa: se toma el Away PPG del rival
        # - Para partidos de visitante: se toma el Home PPG del rival
        points_performance_index = []
        performance_ratings = []
        run_in_analysis = []

        for t, data in team_stats.items():
            played_matches = data['total']['matches']
            team_ppg = data['total']['PPG']
            team_pppg = data['total']['pPPG']

            # Rivales ya enfrentados
            opp_ppg_list = []
            opp_pppg_list = []
            for m in played_matches:
                opp = m['opponent']
                venue = m['venue']
                if venue == 'home':
                    opp_ppg_list.append(team_stats[opp]['away']['PPG'])
                    opp_pppg_list.append(team_stats[opp]['away']['pPPG'])
                else:
                    opp_ppg_list.append(team_stats[opp]['home']['PPG'])
                    opp_pppg_list.append(team_stats[opp]['home']['pPPG'])

            avg_opp_ppg = round(sum(opp_ppg_list) / len(opp_ppg_list), 2) if opp_ppg_list else 0.0
            avg_opp_pppg = round(sum(opp_pppg_list) / len(opp_pppg_list), 1) if opp_pppg_list else 0.0

            # PPI = Team PPG x Opponents PPG
            ppi = round(team_ppg * avg_opp_ppg, 2)
            points_performance_index.append({
                'team': t,
                'GP': data['total']['GP'],
                'Pts': data['total']['Pts'],
                'Team_PPG': team_ppg,
                'Opponents_PPG': avg_opp_ppg,
                'PPI': ppi
            })

            # PR = ((Team pPPG x 2) + Opponents pPPG) / 3
            pr = round(((team_pppg * 2.0) + avg_opp_pppg) / 3.0, 1)
            performance_ratings.append({
                'team': t,
                'GP': data['total']['GP'],
                'W': data['total']['W'],
                'D': data['total']['D'],
                'L': data['total']['L'],
                'Pts': data['total']['Pts'],
                'pPts': data['total']['pPts'],
                'Team_pPPG': f"{int(round(team_pppg))}%",
                'Opponents_pPPG': f"{int(round(avg_opp_pppg))}%",
                'PR': f"{pr:.1f}%",
                'raw_pr': pr
            })

            # Run-in Analysis: Rivales restantes
            upcoming_matches = []
            for um in data['upcoming_home']:
                upcoming_matches.append({'opponent': um['opponent'], 'venue': 'home', 'jornada': um.get('jornada')})
            for um in data['upcoming_away']:
                upcoming_matches.append({'opponent': um['opponent'], 'venue': 'away', 'jornada': um.get('jornada')})

            # Ordenar próximos partidos por jornada
            upcoming_matches.sort(key=lambda x: parse_jornada_num(x.get('jornada')))

            opp_rem_ppg_list = []
            for um in upcoming_matches:
                opp = um['opponent']
                if um['venue'] == 'home':
                    opp_rem_ppg_list.append(team_stats[opp]['away']['PPG'])
                else:
                    opp_rem_ppg_list.append(team_stats[opp]['home']['PPG'])

            avg_rem_ppg = round(sum(opp_rem_ppg_list) / len(opp_rem_ppg_list), 2) if opp_rem_ppg_list else 0.0

            # Played vs Remaining % diff: ((Played - Remaining) / Played) * 100
            if avg_opp_ppg > 0:
                p_vs_r_pct = round(((avg_opp_ppg - avg_rem_ppg) / avg_opp_ppg) * 100.0)
            else:
                p_vs_r_pct = 0
            sign_pr = "+" if p_vs_r_pct > 0 else ""

            # Next 4 opponents PPG
            next_4 = opp_rem_ppg_list[:4]
            next_4_ppg = round(sum(next_4) / len(next_4), 2) if next_4 else 0.0

            run_in_analysis.append({
                'team': t,
                'GP': data['total']['GP'],
                'Pts': data['total']['Pts'],
                'PPG': team_ppg,
                'Opponents_played_PPG': avg_opp_ppg,
                'Opponents_remaining_PPG': avg_rem_ppg,
                'Played_vs_Remaining': f"{sign_pr}{p_vs_r_pct}%",
                'Next_4_opponents': next_4_ppg
            })

        points_performance_index.sort(key=lambda x: (x['Pts'], x['PPI']), reverse=True)
        for idx, row in enumerate(points_performance_index, start=1):
            row['rank'] = idx

        performance_ratings.sort(key=lambda x: (x['Pts'], x['raw_pr']), reverse=True)
        for idx, row in enumerate(performance_ratings, start=1):
            row['rank'] = idx

        run_in_analysis.sort(key=lambda x: (x['Pts'], x['PPG']), reverse=True)
        for idx, row in enumerate(run_in_analysis, start=1):
            row['rank'] = idx

        # G) Tabla de Segmentos (Segments Table)
        # Divide en 5 segmentos basados en el puntaje del 1er puesto
        max_pts = max((r['Pts'] for r in league_table), default=1)
        if max_pts <= 0:
            max_pts = 1
        seg_width = max(max_pts / 5.0, 0.2)
        segments = {
            "5th Segment": {"range": f"hasta {seg_width:.1f} pts", "min": 0.0, "max": seg_width, "teams": []},
            "4th Segment": {"range": f"{seg_width + 0.1:.1f} a {seg_width * 2:.1f} pts", "min": seg_width, "max": seg_width * 2, "teams": []},
            "3rd Segment": {"range": f"{(seg_width * 2) + 0.1:.1f} a {seg_width * 3:.1f} pts", "min": seg_width * 2, "max": seg_width * 3, "teams": []},
            "2nd Segment": {"range": f"{(seg_width * 3) + 0.1:.1f} a {seg_width * 4:.1f} pts", "min": seg_width * 3, "max": seg_width * 4, "teams": []},
            "1st Segment": {"range": f"{(seg_width * 4) + 0.1:.1f} a {max_pts} pts", "min": seg_width * 4, "max": float(max_pts + 1), "teams": []}
        }

        for row in league_table:
            p = row['Pts']
            t_entry = f"({row['GP']}) {row['Pts']} {row['team']}"
            if p <= seg_width:
                segments["5th Segment"]["teams"].append(t_entry)
            elif p <= seg_width * 2:
                segments["4th Segment"]["teams"].append(t_entry)
            elif p <= seg_width * 3:
                segments["3rd Segment"]["teams"].append(t_entry)
            elif p <= seg_width * 4:
                segments["2nd Segment"]["teams"].append(t_entry)
            else:
                segments["1st Segment"]["teams"].append(t_entry)

        # H) Estadísticas Globales de Liga
        total_played = len(results)
        total_scheduled = total_played + len(upcoming)
        completion_pct = round((total_played / total_scheduled) * 100.0, 1) if total_scheduled > 0 else 0.0

        home_wins = sum(1 for m in results if m['goles_local'] > m['goles_visitante'])
        draws = sum(1 for m in results if m['goles_local'] == m['goles_visitante'])
        away_wins = sum(1 for m in results if m['goles_local'] < m['goles_visitante'])

        total_goals = sum(m['goles_local'] + m['goles_visitante'] for m in results)
        home_goals = sum(m['goles_local'] for m in results)
        away_goals = sum(m['goles_visitante'] for m in results)

        over_1_5 = sum(1 for m in results if (m['goles_local'] + m['goles_visitante']) > 1.5)
        over_2_5 = sum(1 for m in results if (m['goles_local'] + m['goles_visitante']) > 2.5)
        over_3_5 = sum(1 for m in results if (m['goles_local'] + m['goles_visitante']) > 3.5)
        btts = sum(1 for m in results if m['goles_local'] > 0 and m['goles_visitante'] > 0)

        league_stats = {
            "matches_played": total_played,
            "total_matches": total_scheduled,
            "completion_pct": f"{completion_pct}%",
            "home_wins_pct": f"{int(round((home_wins / total_played) * 100))}%" if total_played else "0%",
            "draws_pct": f"{int(round((draws / total_played) * 100))}%" if total_played else "0%",
            "away_wins_pct": f"{int(round((away_wins / total_played) * 100))}%" if total_played else "0%",
            "total_goals": total_goals,
            "goals_per_match": round(total_goals / total_played, 2) if total_played else 0.0,
            "home_goals_per_match": round(home_goals / total_played, 2) if total_played else 0.0,
            "away_goals_per_match": round(away_goals / total_played, 2) if total_played else 0.0,
            "over_1_5_pct": f"{int(round((over_1_5 / total_played) * 100))}%" if total_played else "0%",
            "over_2_5_pct": f"{int(round((over_2_5 / total_played) * 100))}%" if total_played else "0%",
            "over_3_5_pct": f"{int(round((over_3_5 / total_played) * 100))}%" if total_played else "0%",
            "btts_pct": f"{int(round((btts / total_played) * 100))}%" if total_played else "0%"
        }

        # I) Ataque y Defensa (Offence & Defence)
        offence_overall = sorted(
            [{'team': t, 'GP': d['total']['GP'], 'GF': d['total']['GF']} for t, d in team_stats.items()],
            key=lambda x: x['GF'], reverse=True
        )
        defence_overall = sorted(
            [{'team': t, 'GP': d['total']['GP'], 'GA': d['total']['GA']} for t, d in team_stats.items()],
            key=lambda x: x['GA']
        )
        offence_home = sorted(
            [{'team': t, 'GP': d['home']['GP'], 'GF': d['home']['GF']} for t, d in team_stats.items()],
            key=lambda x: x['GF'], reverse=True
        )
        defence_home = sorted(
            [{'team': t, 'GP': d['home']['GP'], 'GA': d['home']['GA']} for t, d in team_stats.items()],
            key=lambda x: x['GA']
        )
        offence_away = sorted(
            [{'team': t, 'GP': d['away']['GP'], 'GF': d['away']['GF']} for t, d in team_stats.items()],
            key=lambda x: x['GF'], reverse=True
        )
        defence_away = sorted(
            [{'team': t, 'GP': d['away']['GP'], 'GA': d['away']['GA']} for t, d in team_stats.items()],
            key=lambda x: x['GA']
        )

        # J) Calendario de Fechas de Partidos (fechas con actividad)
        fechas_partidos = {}
        for m in results:
            fh = m.get('fecha_hora', '')
            if fh and len(fh) >= 5:
                d = fh[:5]
                if d not in fechas_partidos:
                    fechas_partidos[d] = {'total': 0, 'resultado': 0, 'proximo': 0}
                fechas_partidos[d]['total'] += 1
                fechas_partidos[d]['resultado'] += 1

        for m in upcoming:
            fh = m.get('fecha_hora', '')
            if fh and len(fh) >= 5:
                d = fh[:5]
                if d not in fechas_partidos:
                    fechas_partidos[d] = {'total': 0, 'resultado': 0, 'proximo': 0}
                fechas_partidos[d]['total'] += 1
                fechas_partidos[d]['proximo'] += 1

        return {
            "competition": competition_info,
            "league_stats": league_stats,
            "league_table": league_table,
            "home_table": home_table,
            "away_table": away_table,
            "relative_home_away": relative_home_away,
            "relative_form": relative_form,
            "points_performance_index": points_performance_index,
            "performance_ratings": performance_ratings,
            "run_in_analysis": run_in_analysis,
            "segments_table": segments,
            "fechas_partidos": fechas_partidos,
            "tables_overview": {
                "offence_overall": offence_overall,
                "defence_overall": defence_overall,
                "offence_home": offence_home,
                "defence_home": defence_home,
                "offence_away": offence_away,
                "defence_away": defence_away
            }
        }

    def calculate_all_competitions(self, output_dir: str = ESTADISTICAS_DIR) -> Dict[str, Any]:
        """
        Calcula estadísticas avanzadas para todas las competiciones con resultados en la DB.
        - Guarda JSON individual por liga en: estadisticas/<pais>/<competicion>.json
        - Guarda un resumen general consolidado en: estadisticas/resumen_todas_las_ligas.json
        - Crea y actualiza la tabla SQLite 'estadisticas_resumen_ligas' en la base de datos.
        """
        os.makedirs(output_dir, exist_ok=True)
        comps = self.get_competitions()
        total = len(comps)
        print(f"\n[*] Procesando estadísticas avanzadas para {total} competiciones...")

        # 1. Crear tabla analítica en SQLite
        self.conn.execute("DROP TABLE IF EXISTS estadisticas_resumen_ligas;")
        self.conn.execute("""
        CREATE TABLE estadisticas_resumen_ligas (
            competicion_id INTEGER PRIMARY KEY,
            pais_nombre TEXT NOT NULL,
            nombre_flashscore TEXT NOT NULL,
            tipo_competicion TEXT NOT NULL,
            partidos_jugados INTEGER NOT NULL,
            total_partidos INTEGER NOT NULL,
            porcentaje_completado TEXT NOT NULL,
            total_goles INTEGER NOT NULL,
            promedio_goles REAL NOT NULL,
            promedio_goles_local REAL NOT NULL,
            promedio_goles_visitante REAL NOT NULL,
            pct_victorias_local TEXT NOT NULL,
            pct_empates TEXT NOT NULL,
            pct_victorias_visitante TEXT NOT NULL,
            pct_over_15 TEXT NOT NULL,
            pct_over_25 TEXT NOT NULL,
            pct_over_35 TEXT NOT NULL,
            pct_btts TEXT NOT NULL,
            lider_equipo TEXT,
            lider_puntos INTEGER,
            lider_ppg REAL,
            fecha_actualizacion TEXT NOT NULL,
            FOREIGN KEY (competicion_id) REFERENCES competiciones(id) ON DELETE CASCADE
        );
        """)
        self.conn.commit()

        resumen_global = []
        procesadas = 0
        omitidas = 0
        errores = 0

        for idx, c in enumerate(comps, 1):
            comp_id = c['id']
            pais = c['pais_nombre']
            nombre = c['nombre_flashscore']
            pais_slug = slugify(pais)
            comp_slug = slugify(nombre)

            pais_dir = os.path.join(output_dir, pais_slug)
            os.makedirs(pais_dir, exist_ok=True)

            try:
                data = self.calculate_for_competition(comp_id)
                if "error" in data:
                    omitidas += 1
                    continue

                # Guardar JSON individual
                file_path = os.path.join(pais_dir, f"{comp_slug}.json")
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                ls = data['league_stats']
                lider = data['league_table'][0] if data['league_table'] else {}
                tipo_comp = data['competition'].get('tipo_competicion', 'Liga')

                resumen_item = {
                    'competicion_id': comp_id,
                    'pais_nombre': pais,
                    'nombre_flashscore': nombre,
                    'tipo_competicion': tipo_comp,
                    'partidos_jugados': ls['matches_played'],
                    'total_partidos': ls['total_matches'],
                    'porcentaje_completado': ls['completion_pct'],
                    'total_goles': ls['total_goals'],
                    'promedio_goles': ls['goals_per_match'],
                    'promedio_goles_local': ls['home_goals_per_match'],
                    'promedio_goles_visitante': ls['away_goals_per_match'],
                    'pct_victorias_local': ls['home_wins_pct'],
                    'pct_empates': ls['draws_pct'],
                    'pct_victorias_visitante': ls['away_wins_pct'],
                    'pct_over_15': ls['over_1_5_pct'],
                    'pct_over_25': ls['over_2_5_pct'],
                    'pct_over_35': ls['over_3_5_pct'],
                    'pct_btts': ls['btts_pct'],
                    'lider_equipo': lider.get('team', ''),
                    'lider_puntos': lider.get('Pts', 0),
                    'lider_ppg': lider.get('PPG', 0.0),
                    'fechas_partidos': data.get('fechas_partidos', {}),
                    'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                # Upsert en la tabla analítica
                self.conn.execute("""
                INSERT OR REPLACE INTO estadisticas_resumen_ligas
                VALUES (:competicion_id, :pais_nombre, :nombre_flashscore, :tipo_competicion,
                        :partidos_jugados, :total_partidos, :porcentaje_completado, :total_goles,
                        :promedio_goles, :promedio_goles_local, :promedio_goles_visitante,
                        :pct_victorias_local, :pct_empates, :pct_victorias_visitante,
                        :pct_over_15, :pct_over_25, :pct_over_35, :pct_btts, :lider_equipo,
                        :lider_puntos, :lider_ppg, :fecha_actualizacion)
                """, resumen_item)

                resumen_global.append(resumen_item)
                procesadas += 1

                if idx % 25 == 0 or idx == total:
                    print(f"  -> Progreso: [{idx}/{total}] ligas evaluadas ({procesadas} procesadas exitosamente)...")

            except Exception as e:
                errores += 1
                print(f"  [!] Error en competición ID {comp_id} ({pais} - {nombre}): {e}")

        self.conn.commit()

        # Guardar archivo consolidado de resumen en JSON y JS (para compatibilidad file://)
        resumen_path = os.path.join(output_dir, 'resumen_todas_las_ligas.json')
        with open(resumen_path, 'w', encoding='utf-8') as f:
            json.dump(resumen_global, f, ensure_ascii=False, indent=2)

        resumen_js_path = os.path.join(output_dir, 'resumen_todas_las_ligas.js')
        with open(resumen_js_path, 'w', encoding='utf-8') as f:
            f.write("window.DATA_RESUMEN_LIGAS = " + json.dumps(resumen_global, ensure_ascii=False) + ";")

        print(f"\n[✓] PROCESO MASIVO COMPLETADO:")
        print(f"    - Competiciones procesadas con éxito: {procesadas}")
        if omitidas > 0:
            print(f"    - Competiciones sin partidos finalizados: {omitidas}")
        if errores > 0:
            print(f"    - Competiciones con error: {errores}")
        print(f"    - Archivos JSON individuales generados en: '{output_dir}/'")
        print(f"    - Resumen global JSON guardado en: '{resumen_path}'")
        print(f"    - Tabla SQLite actualizada: 'estadisticas_resumen_ligas'")

        return {
            'total_procesadas': procesadas,
            'total_omitidas': omitidas,
            'total_errores': errores,
            'resumen_path': resumen_path,
            'resumen': resumen_global
        }


def format_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Genera una tabla ASCII alineada limpiamente."""
    str_rows = [[str(cell) for cell in row] for row in rows]
    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for idx, cell in enumerate(row):
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], len(cell))
            else:
                col_widths.append(len(cell))

    header_line = "  ".join(h.ljust(col_widths[i]) if i < 2 else h.rjust(col_widths[i]) for i, h in enumerate(headers))
    separator = "  ".join("-" * col_widths[i] for i in range(len(headers)))
    data_lines = []
    for r in str_rows:
        line = "  ".join(r[i].ljust(col_widths[i]) if i < 2 else r[i].rjust(col_widths[i]) for i in range(len(r)))
        data_lines.append(line)

    return f"{header_line}\n{separator}\n" + "\n".join(data_lines)


def print_cli_report(data: Dict[str, Any]):
    comp = data['competition']
    ls = data['league_stats']

    print("=" * 80)
    print(f" ESTADÍSTICAS AVANZADAS: {comp['nombre_flashscore'].upper()} ({comp['pais_nombre'].upper()})")
    print("=" * 80)
    print(f"Partidos jugados: {ls['matches_played']} / {ls['total_matches']} ({ls['completion_pct']} completado)")
    print(f"Goles totales: {ls['total_goals']} | Promedio por partido: {ls['goals_per_match']} (Local: {ls['home_goals_per_match']} | Visitante: {ls['away_goals_per_match']})")
    print(f"Victorias Local: {ls['home_wins_pct']} | Empates: {ls['draws_pct']} | Victorias Visitante: {ls['away_wins_pct']}")
    print(f"Over 1.5: {ls['over_1_5_pct']} | Over 2.5: {ls['over_2_5_pct']} | Over 3.5: {ls['over_3_5_pct']} | Ambos marcan (BTTS): {ls['btts_pct']}")
    print("-" * 80)

    # 1. Tabla General
    print("\n[+] CLASIFICACIÓN GENERAL (LEAGUE TABLE):")
    headers = ["#", "Equipo", "PJ", "G", "E", "P", "GF", "GC", "DG", "Pts", "PPG", "Form8", "CS", "SR", "MPP"]
    rows = [
        [r['rank'], r['team'], r['GP'], r['W'], r['D'], r['L'], r['GF'], r['GA'], r['GD'], r['Pts'],
         f"{r['PPG']:.2f}", f"{r['last_8_PPG']:.2f}", r['CS'], r['SR'], r['MPP']]
        for r in data['league_table']
    ]
    print(format_table(headers, rows))

    # 2. Local vs Visitante
    print("\n[+] RENDIMIENTO RELATIVO LOCAL VS VISITANTE (RELATIVE HOME / AWAY):")
    headers = ["#", "Equipo", "PJ(L)", "PJ(V)", "Pts", "PPG Local", "PPG Visita", "Dif PPG"]
    rows = [
        [r['rank'], r['team'], r['GPh'], r['GPa'], r['Pts'], f"{r['PPG_home']:.2f}", f"{r['PPG_away']:.2f}", r['PPG_diff']]
        for r in data['relative_home_away']
    ]
    print(format_table(headers, rows))

    # 3. Points Performance Index (PPI)
    print("\n[+] ÍNDICE DE RENDIMIENTO POR PUNTOS (POINTS PERFORMANCE INDEX - PPI):")
    print("    * PPI = PPG del Equipo x Promedio de PPG de los rivales enfrentados")
    headers = ["#", "Equipo", "PJ", "Pts", "PPG Equipo", "PPG Rivales", "PPI"]
    rows = [
        [r['rank'], r['team'], r['GP'], r['Pts'], f"{r['Team_PPG']:.2f}", f"{r['Opponents_PPG']:.2f}", f"{r['PPI']:.2f}"]
        for r in data['points_performance_index']
    ]
    print(format_table(headers, rows))

    # 4. Performance Ratings
    print("\n[+] CALIFICACIÓN DE RENDIMIENTO (PERFORMANCE RATINGS - PR):")
    print("    * PR = ((pPPG Equipo x 2) + pPPG Rivales) / 3 | G=1pt, E=0.5pt, P=0pt")
    headers = ["#", "Equipo", "PJ", "G", "E", "P", "Pts", "pPts", "pPPG Equipo", "pPPG Rivales", "PR"]
    rows = [
        [r['rank'], r['team'], r['GP'], r['W'], r['D'], r['L'], r['Pts'], f"{r['pPts']:.1f}", r['Team_pPPG'], r['Opponents_pPPG'], r['PR']]
        for r in data['performance_ratings']
    ]
    print(format_table(headers, rows))

    # 5. Run-in Analysis
    print("\n[+] ANÁLISIS DE CALENDARIO RESTANTE (RUN-IN ANALYSIS):")
    print("    * Dificultad basada en el PPG del rival en la condición específica (local/visitante)")
    headers = ["#", "Equipo", "PJ", "Pts", "PPG", "Rivales Jugados", "Rivales Pendientes", "Jug vs Pend", "Próximos 4"]
    rows = [
        [r['rank'], r['team'], r['GP'], r['Pts'], f"{r['PPG']:.2f}", f"{r['Opponents_played_PPG']:.2f}",
         f"{r['Opponents_remaining_PPG']:.2f}", r['Played_vs_Remaining'], f"{r['Next_4_opponents']:.2f}"]
        for r in data['run_in_analysis']
    ]
    print(format_table(headers, rows))

    # 6. Tabla de Segmentos
    print("\n[+] TABLA DE SEGMENTOS (SEGMENTS TABLE):")
    for seg_name, sinfo in reversed(data['segments_table'].items()):
        teams_str = ", ".join(sinfo['teams']) if sinfo['teams'] else "Ninguno"
        print(f"  - {seg_name.upper()} ({sinfo['range']}): {teams_str}")

    print("\n" + "=" * 80)


if __name__ == '__main__':
    calc = LeagueStatsCalculator()
    try:
        if "--all" in sys.argv:
            calc.calculate_all_competitions()
        else:
            # Buscar ID en argumentos o usar LaLiga (84) por defecto
            comp_id = 84
            for arg in sys.argv[1:]:
                if arg.isdigit():
                    comp_id = int(arg)
                    break

            report = calc.calculate_for_competition(comp_id)
            if "error" in report:
                print(f"[!] {report['error']}")
            else:
                print_cli_report(report)
                out_json_path = os.path.join(BASE_DIR, f"estadisticas_comp_{comp_id}.json")
                with open(out_json_path, 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                print(f"[✓] Estadísticas exportadas a: {out_json_path}")
    finally:
        calc.close()

