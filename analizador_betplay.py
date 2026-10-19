"""
Módulo de Cruce y Priorización de Mercados de Betplay con Estadísticas Reales de Liga.
Compara la probabilidad estadística histórica contra la probabilidad implícita de las cuotas de Betplay,
calculando el Valor Esperado (Edge / Value Betting).
"""

import os
import re
import json
import sqlite3
import unicodedata
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')
ESTADISTICAS_DIR = os.path.join(BASE_DIR, 'estadisticas')


def slugify(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_-]+', '-', text).strip('-')


def clean_team_name(name: str) -> str:
    """Limpia sufijos comunes como (W), (F), Femenino, U20, FC, etc. para emparejamiento."""
    if not name:
        return ""
    cleaned = re.sub(r'\(.*?\)', '', name)
    cleaned = re.sub(r'\b(women|fem|femenino|femenil|u\d+|fc|cf|cd|ca|jk|sk|if|ff|bk)\b', '', cleaned, flags=re.IGNORECASE)
    return slugify(cleaned)


class BetplayMarketPrioritizer:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def run_analysis(self) -> Dict[str, Any]:
        cur = self.conn.cursor()

        # 1. Cargar estadísticas de competiciones
        resumen_json_path = os.path.join(ESTADISTICAS_DIR, 'resumen_todas_las_ligas.json')
        if not os.path.exists(resumen_json_path):
            raise FileNotFoundError(f"No se encontró {resumen_json_path}. Ejecute 'python estadisticas_liga.py --all' primero.")

        with open(resumen_json_path, 'r', encoding='utf-8') as f:
            stats_list = json.load(f)

        stats_by_id = {s['competicion_id']: s for s in stats_list}

        # 2. Cargar tabla de competiciones para mapeo
        cur.execute("SELECT id, pais_nombre, nombre_flashscore, nombre_betplay FROM competiciones")
        competiciones = [dict(r) for r in cur.fetchall()]

        # 3. Cargar partidos de Betplay
        cur.execute("""
            SELECT id, partido, equipo_local, equipo_visitante, pais, competicion,
                   fecha_partido, estado, link, total_mercados_unicos
            FROM betplay_partidos
        """)
        betplay_matches = [dict(r) for r in cur.fetchall()]

        print(f"[*] Analizando {len(betplay_matches)} partidos de Betplay contra las estadísticas...")

        analyzed_picks = []
        matches_with_picks = []
        comp_picks_count = {}

        for bp in betplay_matches:
            bp_id = bp['id']
            partido = bp['partido']
            local = bp['equipo_local']
            visita = bp['equipo_visitante']
            bp_pais = bp['pais']
            bp_comp = bp['competicion']
            fecha_iso = bp['fecha_partido'] or ""
            link = bp['link'] or ""

            # Extraer fecha DD.MM
            fecha_ddmm = ""
            if fecha_iso and len(fecha_iso) >= 10:
                try:
                    dt = datetime.fromisoformat(fecha_iso.replace('Z', '+00:00'))
                    fecha_ddmm = dt.strftime('%d.%m')
                except Exception:
                    fecha_ddmm = f"{fecha_iso[8:10]}.{fecha_iso[5:7]}"

            # Buscar competición coincidente con lógica robusta y libre de falsos positivos
            bp_p_slug = slugify(bp_pais)
            bp_c_slug = slugify(bp_comp)

            candidates = [
                c for c in competiciones 
                if slugify(c['pais_nombre']) == bp_p_slug or c['pais_nombre'] == 'Internacional'
            ]

            best_c = None
            # Prioridad 1: Coincidencia exacta con nombre_betplay
            for c in candidates:
                c_bp = slugify(c.get('nombre_betplay'))
                if c_bp and c_bp == bp_c_slug:
                    best_c = c
                    break

            # Prioridad 2: Coincidencia exacta con nombre_flashscore
            if not best_c:
                for c in candidates:
                    c_fs = slugify(c.get('nombre_flashscore'))
                    if c_fs and c_fs == bp_c_slug:
                        best_c = c
                        break

            # Prioridad 3: Substring con scoring por longitud del match (evita empty string bug)
            if not best_c:
                scored = []
                for c in candidates:
                    c_bp = slugify(c.get('nombre_betplay'))
                    c_fs = slugify(c.get('nombre_flashscore'))
                    sc = 0
                    if c_bp and len(c_bp) >= 3 and (c_bp in bp_c_slug or bp_c_slug in c_bp):
                        sc = max(sc, len(c_bp))
                    if c_fs and len(c_fs) >= 3 and (c_fs in bp_c_slug or bp_c_slug in c_fs):
                        sc = max(sc, len(c_fs))
                    if sc > 0:
                        scored.append((sc, c))
                if scored:
                    scored.sort(key=lambda x: x[0], reverse=True)
                    best_c = scored[0][1]

            if not best_c or best_c['id'] not in stats_by_id:
                continue

            matched_comp_id = best_c['id']
            c_stats = stats_by_id[matched_comp_id]
            pais_nombre = c_stats['pais_nombre']
            liga_nombre = c_stats['nombre_flashscore']
            tipo_comp = c_stats.get('tipo_competicion', 'Liga')

            # 4. Regresión Bayesiana para muestras pequeñas (evita distorsión en copas o ligas con pocos partidos)
            n_partidos = int(c_stats.get('partidos_jugados', 0) or 0)
            def regress_prob(obs_p: float, prior_p: float, n: int, weight: float = 16.0) -> float:
                if n <= 0:
                    return prior_p
                if n >= 45:
                    return obs_p
                return (n * obs_p + weight * prior_p) / (n + weight)

            p_o15_raw = float(c_stats['pct_over_15'].replace('%', '')) / 100.0
            p_o25_raw = float(c_stats['pct_over_25'].replace('%', '')) / 100.0
            p_o35_raw = float(c_stats['pct_over_35'].replace('%', '')) / 100.0
            p_btts_raw = float(c_stats['pct_btts'].replace('%', '')) / 100.0
            p_hw_raw = float(c_stats['pct_victorias_local'].replace('%', '')) / 100.0
            p_dr_raw = float(c_stats['pct_empates'].replace('%', '')) / 100.0
            p_aw_raw = float(c_stats['pct_victorias_visitante'].replace('%', '')) / 100.0

            p_o15 = regress_prob(p_o15_raw, 0.74, n_partidos)
            p_o25 = regress_prob(p_o25_raw, 0.49, n_partidos)
            p_o35 = regress_prob(p_o35_raw, 0.28, n_partidos)
            p_btts = regress_prob(p_btts_raw, 0.50, n_partidos)
            p_hw = regress_prob(p_hw_raw, 0.44, n_partidos)
            p_dr = regress_prob(p_dr_raw, 0.26, n_partidos)
            p_aw = regress_prob(p_aw_raw, 0.30, n_partidos)
            prom_goles = c_stats['promedio_goles']

            # Intentar cargar estadísticas específicas de los equipos si el JSON individual existe
            team_stats_local = None
            team_stats_visita = None
            p_slug = slugify(pais_nombre)
            c_slug = slugify(liga_nombre)
            ind_json_path = os.path.join(ESTADISTICAS_DIR, p_slug, f"{c_slug}.json")
            if os.path.exists(ind_json_path):
                try:
                    with open(ind_json_path, 'r', encoding='utf-8') as f_ind:
                        ind_data = json.load(f_ind)
                    l_table = ind_data.get('league_table', [])
                    loc_clean = clean_team_name(local)
                    vis_clean = clean_team_name(visita)
                    for t in l_table:
                        t_clean = clean_team_name(t.get('team', ''))
                        if loc_clean and t_clean and (loc_clean == t_clean or loc_clean in t_clean or t_clean in loc_clean):
                            team_stats_local = t
                        if vis_clean and t_clean and (vis_clean == t_clean or vis_clean in t_clean or t_clean in vis_clean):
                            team_stats_visita = t
                except Exception:
                    pass

            # Cargar cuotas de Betplay más recientes para este partido (respetando snapshots históricos)
            cur.execute("""
                SELECT mercado, opcion, cuota, linea, fecha_extraccion
                FROM betplay_cuotas
                WHERE partido_id = ? AND (
                    fecha_extraccion = (SELECT MAX(fecha_extraccion) FROM betplay_cuotas WHERE partido_id = ?)
                    OR fecha_extraccion IS NULL
                )
            """, (bp_id, bp_id))
            cuotas_partido = [dict(r) for r in cur.fetchall()]

            partido_picks = []

            for q in cuotas_partido:
                mercado = q['mercado']
                opcion = q['opcion']
                cuota = q['cuota']
                linea = q['linea']

                if not cuota or cuota <= 1.05:
                    continue

                stat_prob = None
                mercado_desc = ""
                justificacion = ""

                # 1. Total de goles (convencional y asiático)
                if mercado in ['Total de goles', 'Total asiático'] and opcion == 'Más de':
                    if linea == 1.5:
                        stat_prob = p_o15
                        mercado_desc = 'Más de 1.5 Goles'
                        justificacion = f"La liga registra un {c_stats['pct_over_15']} de partidos con +1.5 goles (promedio {prom_goles} g/pj)."
                    elif linea == 2.0:
                        stat_prob = p_o15 * 0.4 + p_o25 * 0.6
                        mercado_desc = 'Más de 2.0 Goles Asiático'
                        justificacion = f"Promedio de {prom_goles} goles/partido y {c_stats['pct_over_25']} de partidos con más de 2.5 goles."
                    elif linea == 2.5:
                        stat_prob = p_o25
                        mercado_desc = 'Más de 2.5 Goles'
                        extra_info = ""
                        if team_stats_local and team_stats_visita:
                            extra_info = f" {team_stats_local['team']} anota en {team_stats_local.get('SR', '')} y {team_stats_visita['team']} en {team_stats_visita.get('SR', '')}."
                        justificacion = f"La competición tiene un {c_stats['pct_over_25']} de partidos con más de 2.5 goles (promedio {prom_goles} g/pj).{extra_info}"
                    elif linea == 3.0:
                        stat_prob = p_o25 * 0.4 + p_o35 * 0.6
                        mercado_desc = 'Más de 3.0 Goles Asiático'
                        justificacion = f"Liga altamente ofensiva con {c_stats['pct_over_35']} de partidos superando los 3.5 goles."
                    elif linea == 3.5:
                        stat_prob = p_o35
                        mercado_desc = 'Más de 3.5 Goles'
                        justificacion = f"Liga con {c_stats['pct_over_35']} de partidos con más de 3.5 goles (promedio {prom_goles} g/pj)."
                
                elif mercado in ['Total de goles', 'Total asiático'] and opcion == 'Menos de':
                    if linea == 2.5 and p_o25 <= 0.45:
                        stat_prob = 1.0 - p_o25
                        mercado_desc = 'Menos de 2.5 Goles'
                        justificacion = f"Competición de perfil bajo en goles ({int(round(stat_prob*100))}% de partidos con menos de 2.5 goles, promedio {prom_goles} g/pj)."
                    elif linea == 3.0 and p_o35 <= 0.30:
                        stat_prob = 1.0 - (p_o25 * 0.3 + p_o35 * 0.7)
                        mercado_desc = 'Menos de 3.0 Goles Asiático'
                        justificacion = f"Baja frecuencia de marcadores abultados en la competición ({int(round(stat_prob*100))}% por debajo de 3.0)."
                    elif linea == 3.5 and p_o35 <= 0.28:
                        stat_prob = 1.0 - p_o35
                        mercado_desc = 'Menos de 3.5 Goles'
                        justificacion = f"Competición con apenas {c_stats['pct_over_35']} de partidos con 4 o más goles ({int(round(stat_prob*100))}% de acierto histórico)."

                # 2. Ambos Equipos Marcarán
                elif mercado == 'Ambos Equipos Marcarán':
                    if opcion == 'Sí' and p_btts >= 0.52:
                        stat_prob = p_btts
                        extra_info = ""
                        if team_stats_local and team_stats_visita:
                            extra_info = f" {team_stats_local['team']} (SR {team_stats_local.get('SR', '')}) vs {team_stats_visita['team']} (SR {team_stats_visita.get('SR', '')})."
                        mercado_desc = 'Ambos Equipos Marcan (Sí)'
                        justificacion = f"El {c_stats['pct_btts']} de los partidos disputados en esta competición terminaron con ambos equipos anotando.{extra_info}"
                    elif opcion == 'No' and p_btts <= 0.44:
                        stat_prob = 1.0 - p_btts
                        mercado_desc = 'Ambos Equipos Marcan (No)'
                        justificacion = f"Solo el {c_stats['pct_btts']} marcan ambos; el {int(round(stat_prob*100))}% de las veces al menos uno queda en cero."

                # 3. Resultado Final (1X2)
                elif mercado == 'Resultado Final':
                    if opcion == '1':
                        loc_w_pct = (team_stats_local['W'] / team_stats_local['GP']) if team_stats_local and team_stats_local.get('GP') else None
                        vis_l_pct = (team_stats_visita['L'] / team_stats_visita['GP']) if team_stats_visita and team_stats_visita.get('GP') else None
                        
                        if loc_w_pct is not None and vis_l_pct is not None:
                            stat_prob = (loc_w_pct * 0.45) + (vis_l_pct * 0.25) + (p_hw * 0.30)
                            mercado_desc = f'Victoria Local ({local})'
                            justificacion = f"{team_stats_local['team']} ({team_stats_local.get('PPG', '')} PPG, {int(loc_w_pct*100)}% victorias) vs {team_stats_visita['team']}; localía liga {c_stats['pct_victorias_local']}."
                        elif p_hw >= 0.48 and cuota <= 2.75:
                            stat_prob = p_hw
                            mercado_desc = f'Victoria Local ({local})'
                            justificacion = f"Fuerte localía en la competición: {c_stats['pct_victorias_local']} de victorias locales."

                    elif opcion == '2':
                        vis_w_pct = (team_stats_visita['W'] / team_stats_visita['GP']) if team_stats_visita and team_stats_visita.get('GP') else None
                        loc_l_pct = (team_stats_local['L'] / team_stats_local['GP']) if team_stats_local and team_stats_local.get('GP') else None
                        
                        if vis_w_pct is not None and loc_l_pct is not None:
                            stat_prob = (vis_w_pct * 0.45) + (loc_l_pct * 0.25) + (p_aw * 0.30)
                            mercado_desc = f'Victoria Visitante ({visita})'
                            justificacion = f"{team_stats_visita['team']} ({team_stats_visita.get('PPG', '')} PPG, {int(vis_w_pct*100)}% victorias) frente a tasa visitante de liga {c_stats['pct_victorias_visitante']}."
                        elif p_aw >= 0.38 and cuota <= 2.90:
                            stat_prob = p_aw
                            mercado_desc = f'Victoria Visitante ({visita})'
                            justificacion = f"Alta tasa de victorias visitantes en la liga: {c_stats['pct_victorias_visitante']}."

                    elif opcion == 'X' and p_dr >= 0.30 and cuota <= 3.80:
                        stat_prob = p_dr
                        mercado_desc = f'Empate (X)'
                        justificacion = f"Alta frecuencia de empates en la competición: {c_stats['pct_empates']}."

                # 4. Doble Oportunidad
                elif mercado == 'Doble Oportunidad':
                    if opcion == '1X' and cuota <= 2.50:
                        loc_not_l = ((team_stats_local['W'] + team_stats_local['D']) / team_stats_local['GP']) if team_stats_local and team_stats_local.get('GP') else None
                        if loc_not_l is not None:
                            stat_prob = (loc_not_l * 0.6) + ((p_hw + p_dr) * 0.4)
                            mercado_desc = f'Doble Oportunidad 1X ({local} o Empate)'
                            justificacion = f"{team_stats_local['team']} puntúa en el {int(round(loc_not_l*100))}% de sus partidos (1X liga: {int(round((p_hw+p_dr)*100))}%)."
                        elif (p_hw + p_dr) >= 0.65:
                            stat_prob = p_hw + p_dr
                            mercado_desc = f'Doble Oportunidad 1X ({local} o Empate)'
                            justificacion = f"El equipo local puntúa en el {int(round(stat_prob*100))}% de los encuentros de esta liga."
                    elif opcion == 'X2' and cuota <= 2.50:
                        vis_not_l = ((team_stats_visita['W'] + team_stats_visita['D']) / team_stats_visita['GP']) if team_stats_visita and team_stats_visita.get('GP') else None
                        if vis_not_l is not None:
                            stat_prob = (vis_not_l * 0.6) + ((p_dr + p_aw) * 0.4)
                            mercado_desc = f'Doble Oportunidad X2 (Empate o {visita})'
                            justificacion = f"{team_stats_visita['team']} puntúa en el {int(round(vis_not_l*100))}% de sus partidos (X2 liga: {int(round((p_dr+p_aw)*100))}%)."
                        elif (p_dr + p_aw) >= 0.60:
                            stat_prob = p_dr + p_aw
                            mercado_desc = f'Doble Oportunidad X2 (Empate o {visita})'
                            justificacion = f"El visitante puntúa en el {int(round(stat_prob*100))}% de los partidos de la competición."
                    elif opcion == '12' and p_dr <= 0.20 and cuota <= 1.45:
                        stat_prob = p_hw + p_aw
                        mercado_desc = f'Doble Oportunidad 12 (Sin Empate)'
                        justificacion = f"Baja tasa de empates en la competición ({c_stats['pct_empates']}); se define ganador en el {int(round(stat_prob*100))}% de partidos."

                # 5. Apuesta sin empate (Draw No Bet)
                elif mercado == 'Apuesta sin empate':
                    p_tot = p_hw + p_aw
                    if p_tot > 0:
                        if opcion == '1' and (p_hw / p_tot) >= 0.58 and cuota <= 2.30:
                            stat_prob = p_hw / p_tot
                            mercado_desc = f'Apuesta sin empate: {local}'
                            justificacion = f"El local gana el {int(round(stat_prob*100))}% de los partidos con desenlace (empate devuelve apuesta)."
                        elif opcion == '2' and (p_aw / p_tot) >= 0.52 and cuota <= 2.40:
                            stat_prob = p_aw / p_tot
                            mercado_desc = f'Apuesta sin empate: {visita}'
                            justificacion = f"El visitante gana el {int(round(stat_prob*100))}% de los partidos definidos de la liga."

                # Si tenemos una probabilidad estadística calculada
                if stat_prob and stat_prob >= 0.45:
                    implied_prob = 1.0 / cuota
                    edge = (stat_prob * cuota) - 1.0
                    cuota_justa = round(1.0 / stat_prob, 2)

                    # Clasificar Prioridad:
                    # - BANKER: Probabilidad >= 82% (alta certeza histórica)
                    # - ALTA (Value Bet): Probabilidad >= 65% y Edge > 0%
                    # - MEDIA: Probabilidad >= 52% y Edge >= 3%
                    # - OUTSIDER: Edge >= 10% y Probabilidad >= 35%
                    if stat_prob >= 0.82:
                        prioridad = 'BANKER'
                    elif stat_prob >= 0.65 and edge > 0:
                        prioridad = 'ALTA'
                    elif stat_prob >= 0.50 and edge >= 0.03:
                        prioridad = 'MEDIA'
                    elif edge >= 0.10 and stat_prob >= 0.35:
                        prioridad = 'OUTSIDER'
                    elif edge > 0:
                        prioridad = 'NORMAL'
                    else:
                        continue  # Descartar apuestas sin ventaja y sin certeza

                    # Consultar trazabilidad y evolución histórica de esta cuota
                    if linea is not None:
                        cur.execute("""
                            SELECT cuota, fecha_extraccion
                            FROM betplay_cuotas
                            WHERE partido_id = ? AND mercado = ? AND opcion = ? AND linea = ?
                            ORDER BY fecha_extraccion ASC
                        """, (bp_id, mercado, opcion, linea))
                    else:
                        cur.execute("""
                            SELECT cuota, fecha_extraccion
                            FROM betplay_cuotas
                            WHERE partido_id = ? AND mercado = ? AND opcion = ? AND linea IS NULL
                            ORDER BY fecha_extraccion ASC
                        """, (bp_id, mercado, opcion))

                    hist_rows = [dict(r) for r in cur.fetchall()]
                    if hist_rows:
                        cuota_apertura = hist_rows[0]['cuota']
                        fecha_apertura = hist_rows[0]['fecha_extraccion']
                        cuota_anterior = hist_rows[-2]['cuota'] if len(hist_rows) > 1 else cuota
                        delta_total = round(cuota - cuota_apertura, 2)
                        delta_reciente = round(cuota - cuota_anterior, 2)
                        if delta_total < -0.01:
                            tendencia = 'baja'
                        elif delta_total > 0.01:
                            tendencia = 'sube'
                        else:
                            tendencia = 'estable'
                        historial_list = hist_rows
                    else:
                        cuota_apertura = cuota
                        fecha_apertura = q.get('fecha_extraccion') or ""
                        cuota_anterior = cuota
                        delta_total = 0.0
                        delta_reciente = 0.0
                        tendencia = 'estable'
                        historial_list = [{'cuota': cuota, 'fecha': fecha_apertura}]

                    pick_item = {
                        'partido_id': bp_id,
                        'partido': partido,
                        'equipo_local': local,
                        'equipo_visitante': visita,
                        'pais': pais_nombre,
                        'competicion': liga_nombre,
                        'competicion_id': matched_comp_id,
                        'tipo_competicion': tipo_comp,
                        'fecha_iso': fecha_iso,
                        'fecha_ddmm': fecha_ddmm,
                        'mercado': mercado,
                        'opcion': opcion,
                        'linea': linea,
                        'mercado_desc': mercado_desc,
                        'cuota': cuota,
                        'cuota_apertura': cuota_apertura,
                        'fecha_apertura': fecha_apertura,
                        'cuota_anterior': cuota_anterior,
                        'variacion_cuota': delta_total,
                        'variacion_reciente': delta_reciente,
                        'tendencia': tendencia,
                        'total_capturas': len(historial_list),
                        'historial_cuotas': historial_list,
                        'fecha_extraccion': q.get('fecha_extraccion') or "",
                        'cuota_justa': cuota_justa,
                        'prob_estadistica': f"{int(round(stat_prob * 100))}%",
                        'prob_implicita': f"{int(round(implied_prob * 100))}%",
                        'edge': f"{edge * 100:+.1f}%",
                        'raw_edge': round(edge * 100, 1),
                        'stat_prob_num': round(stat_prob * 100, 1),
                        'prioridad': prioridad,
                        'justificacion': justificacion,
                        'link': link
                    }

                    analyzed_picks.append(pick_item)
                    partido_picks.append(pick_item)

            if partido_picks:
                matches_with_picks.append({
                    'partido_id': bp_id,
                    'partido': partido,
                    'equipo_local': local,
                    'equipo_visitante': visita,
                    'pais': pais_nombre,
                    'competicion': liga_nombre,
                    'competicion_id': matched_comp_id,
                    'tipo_competicion': tipo_comp,
                    'fecha_ddmm': fecha_ddmm,
                    'link': link,
                    'total_picks': len(partido_picks),
                    'picks': sorted(partido_picks, key=lambda x: (
                        0 if x['prioridad'] == 'ALTA' else (1 if x['prioridad'] == 'BANKER' else 2),
                        -x['raw_edge']
                    ))
                })
                comp_picks_count[matched_comp_id] = comp_picks_count.get(matched_comp_id, 0) + len(partido_picks)

        # Ordenar selecciones globales por prioridad y mayor Edge
        analyzed_picks.sort(key=lambda x: (
            0 if x['prioridad'] == 'ALTA' else (1 if x['prioridad'] == 'BANKER' else (2 if x['prioridad'] == 'MEDIA' else 3)),
            -x['raw_edge']
        ))

        # 4. Crear tabla SQLite para consultas rápidas con trazabilidad y evolución
        self.conn.execute("DROP TABLE IF EXISTS betplay_mercados_priorizados;")
        self.conn.execute("""
        CREATE TABLE betplay_mercados_priorizados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partido_id INTEGER NOT NULL,
            partido TEXT NOT NULL,
            pais TEXT NOT NULL,
            competicion TEXT NOT NULL,
            competicion_id INTEGER NOT NULL,
            tipo_competicion TEXT,
            fecha_ddmm TEXT,
            mercado TEXT NOT NULL,
            opcion TEXT NOT NULL,
            linea REAL,
            mercado_desc TEXT NOT NULL,
            cuota REAL NOT NULL,
            cuota_apertura REAL,
            variacion_cuota REAL,
            tendencia TEXT,
            total_capturas INTEGER,
            historial_cuotas TEXT,
            fecha_extraccion TEXT,
            cuota_justa REAL NOT NULL,
            prob_estadistica TEXT NOT NULL,
            prob_implicita TEXT NOT NULL,
            edge TEXT NOT NULL,
            raw_edge REAL NOT NULL,
            prioridad TEXT NOT NULL,
            justificacion TEXT NOT NULL,
            link TEXT,
            FOREIGN KEY (partido_id) REFERENCES betplay_partidos(id) ON DELETE CASCADE
        );
        """)

        for p in analyzed_picks:
            self.conn.execute("""
            INSERT INTO betplay_mercados_priorizados
            (partido_id, partido, pais, competicion, competicion_id, tipo_competicion, fecha_ddmm,
             mercado, opcion, linea, mercado_desc, cuota, cuota_apertura, variacion_cuota, tendencia,
             total_capturas, historial_cuotas, fecha_extraccion, cuota_justa, prob_estadistica,
             prob_implicita, edge, raw_edge, prioridad, justificacion, link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p['partido_id'], p['partido'], p['pais'], p['competicion'], p['competicion_id'],
                p['tipo_competicion'], p['fecha_ddmm'], p['mercado'], p['opcion'], p['linea'],
                p['mercado_desc'], p['cuota'], p['cuota_apertura'], p['variacion_cuota'], p['tendencia'],
                p['total_capturas'], json.dumps(p['historial_cuotas']), p['fecha_extraccion'],
                p['cuota_justa'], p['prob_estadistica'], p['prob_implicita'], p['edge'],
                p['raw_edge'], p['prioridad'], p['justificacion'], p['link']
            ))
        self.conn.commit()

        # 5. Enriquecer resumen_todas_las_ligas con la cantidad de apuestas de valor Betplay
        for s in stats_list:
            cid = s['competicion_id']
            s['betplay_picks_count'] = comp_picks_count.get(cid, 0)
            s['betplay_matches_count'] = sum(1 for m in matches_with_picks if m['competicion_id'] == cid)

        with open(resumen_json_path, 'w', encoding='utf-8') as f:
            json.dump(stats_list, f, ensure_ascii=False, indent=2)

        resumen_js_path = os.path.join(ESTADISTICAS_DIR, 'resumen_todas_las_ligas.js')
        with open(resumen_js_path, 'w', encoding='utf-8') as f:
            f.write("window.DATA_RESUMEN_LIGAS = " + json.dumps(stats_list, ensure_ascii=False) + ";\n")

        # 6. Exportar JSON de Mercados Priorizados
        out_json = os.path.join(ESTADISTICAS_DIR, 'betplay_mercados_priorizados.json')
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(analyzed_picks, f, ensure_ascii=False, indent=2)

        out_js = os.path.join(ESTADISTICAS_DIR, 'betplay_mercados_priorizados.js')
        with open(out_js, 'w', encoding='utf-8') as f:
            f.write("window.DATA_BETPLAY_PRIORIZADOS = " + json.dumps(analyzed_picks, ensure_ascii=False) + ";\n")

        # 7. Exportar resumen agrupado por partido para vistas directas
        out_matches_json = os.path.join(ESTADISTICAS_DIR, 'betplay_partidos_con_picks.json')
        with open(out_matches_json, 'w', encoding='utf-8') as f:
            json.dump(matches_with_picks, f, ensure_ascii=False, indent=2)

        out_matches_js = os.path.join(ESTADISTICAS_DIR, 'betplay_partidos_con_picks.js')
        with open(out_matches_js, 'w', encoding='utf-8') as f:
            f.write("window.DATA_BETPLAY_MATCHES_PICKS = " + json.dumps(matches_with_picks, ensure_ascii=False) + ";\n")

        # 8. Exportar catálogo completo de eventos y cuotas para el visualizador por país/competición
        self.exportar_eventos_cuotas(analyzed_picks)

        bankers_count = sum(1 for p in analyzed_picks if p['prioridad'] == 'BANKER')
        altas_count = sum(1 for p in analyzed_picks if p['prioridad'] == 'ALTA')
        medias_count = sum(1 for p in analyzed_picks if p['prioridad'] == 'MEDIA')

        print(f"\n[✓] ANÁLISIS DE MERCADOS BETPLAY COMPLETADO:")
        print(f"    - Partidos evaluados con cuotas: {len(betplay_matches)}")
        print(f"    - Partidos con selecciones de valor: {len(matches_with_picks)}")
        print(f"    - Total selecciones priorizadas: {len(analyzed_picks)}")
        print(f"    - Selecciones ALTA PRIORIDAD (Value Bets): {altas_count}")
        print(f"    - Selecciones BANKER (Alta Certeza >=82%): {bankers_count}")
        print(f"    - Selecciones MEDIA PRIORIDAD: {medias_count}")
        print(f"    - Catálogo completo de eventos exportado en: estadisticas/betplay_eventos_cuotas.json (.js)")
        print(f"    - JSON de valor exportado en: {out_json}")
        print(f"    - JS fallback exportado en: {out_js}")
        print(f"    - Tabla SQLite actualizada: 'betplay_mercados_priorizados'")

        return {
            'total_picks': len(analyzed_picks),
            'picks': analyzed_picks,
            'matches': matches_with_picks
        }

    def exportar_eventos_cuotas(self, analyzed_picks=None):
        """Exporta todos los eventos con sus mercados completos y evolución histórica para el visualizador web."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT bp.id, bp.partido, bp.equipo_local, bp.equipo_visitante, bp.pais, bp.competicion,
                   bp.fecha_partido, bp.link, bp.fecha_extraccion, bp.total_mercados_unicos
            FROM betplay_partidos bp
            ORDER BY bp.pais, bp.competicion, bp.fecha_partido
        """)
        partidos = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT partido_id, categoria, mercado, tipo, opcion, cuota, linea, participante, fecha_extraccion
            FROM betplay_cuotas
            ORDER BY partido_id, categoria, mercado, linea, opcion, fecha_extraccion ASC
        """)
        all_cuotas = cur.fetchall()

        partido_cuotas = {}
        for r in all_cuotas:
            pid = r['partido_id']
            if pid not in partido_cuotas:
                partido_cuotas[pid] = []
            partido_cuotas[pid].append(dict(r))

        eventos = []
        for p in partidos:
            pid = p['id']
            raw_q = partido_cuotas.get(pid, [])
            
            lineas_dict = {}
            for q in raw_q:
                key = (q['mercado'], q['opcion'], q['linea'], q['participante'])
                if key not in lineas_dict:
                    lineas_dict[key] = {
                        'categoria': q['categoria'],
                        'mercado': q['mercado'],
                        'opcion': q['opcion'],
                        'linea': q['linea'],
                        'participante': q['participante'],
                        'historial': []
                    }
                lineas_dict[key]['historial'].append({
                    'cuota': q['cuota'],
                    'fecha': q['fecha_extraccion']
                })

            mercados_procesados = {}
            for key, l_data in lineas_dict.items():
                m_name = l_data['mercado']
                if m_name not in mercados_procesados:
                    mercados_procesados[m_name] = {
                        'categoria': l_data['categoria'],
                        'mercado': m_name,
                        'opciones': []
                    }
                
                hist = l_data['historial']
                cuota_actual = hist[-1]['cuota'] if hist else None
                cuota_apertura = hist[0]['cuota'] if hist else None
                delta = round(cuota_actual - cuota_apertura, 2) if (cuota_actual and cuota_apertura) else 0.0
                
                tendencia = 'estable'
                if delta < -0.01:
                    tendencia = 'baja'
                elif delta > 0.01:
                    tendencia = 'sube'

                mercados_procesados[m_name]['opciones'].append({
                    'opcion': l_data['opcion'],
                    'linea': l_data['linea'],
                    'participante': l_data['participante'],
                    'cuota': cuota_actual,
                    'cuota_apertura': cuota_apertura,
                    'variacion': delta,
                    'tendencia': tendencia,
                    'total_tomas': len(hist),
                    'historial': hist
                })

            eventos.append({
                'id': pid,
                'partido': p['partido'],
                'local': p['equipo_local'],
                'visita': p['equipo_visitante'],
                'pais': p['pais'] or 'Internacional',
                'competicion': p['competicion'],
                'fecha_partido': p['fecha_partido'],
                'link': p['link'],
                'fecha_extraccion': p['fecha_extraccion'],
                'total_mercados': len(mercados_procesados),
                'mercados': list(mercados_procesados.values())
            })

        out_json = os.path.join(ESTADISTICAS_DIR, 'betplay_eventos_cuotas.json')
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(eventos, f, ensure_ascii=False, indent=2)

        out_js = os.path.join(ESTADISTICAS_DIR, 'betplay_eventos_cuotas.js')
        with open(out_js, 'w', encoding='utf-8') as f:
            f.write('window.DATA_BETPLAY_EVENTOS = ' + json.dumps(eventos, ensure_ascii=False) + ';\n')

        # 9. Generar Feed Ultraligero y de Alto Rendimiento para la Web (betplay_eventos_resumen)
        from datetime import timezone, timedelta
        cot_zone = timezone(timedelta(hours=-5))

        picks_by_event = {}
        if analyzed_picks:
            for pk in analyzed_picks:
                pid = pk.get('partido_id')
                if pid not in picks_by_event:
                    picks_by_event[pid] = []
                picks_by_event[pid].append(pk)

        resumen_eventos = []
        for ev in eventos:
            pid = ev['id']
            q1, qX, q2 = None, None, None
            q_over, q_under = None, None
            btts_si, btts_no = None, None

            for m in ev.get('mercados', []):
                m_name = m.get('mercado', '')
                if m_name in ('Tiempo reglamentario', '1X2', 'Ganador del partido'):
                    for op in m.get('opciones', []):
                        lbl = str(op.get('opcion', '')).strip()
                        if lbl == '1' or lbl == ev['local']:
                            q1 = op.get('cuota')
                        elif lbl in ('X', 'Empate'):
                            qX = op.get('cuota')
                        elif lbl == '2' or lbl == ev['visita']:
                            q2 = op.get('cuota')
                elif 'Total de goles' in m_name:
                    for op in m.get('opciones', []):
                        if op.get('linea') == 2.5:
                            lbl = str(op.get('opcion', '')).lower()
                            if 'más' in lbl or 'over' in lbl:
                                q_over = op.get('cuota')
                            elif 'menos' in lbl or 'under' in lbl:
                                q_under = op.get('cuota')
                elif m_name == 'Ambos Equipos Marcarán':
                    for op in m.get('opciones', []):
                        lbl = str(op.get('opcion', '')).lower()
                        if lbl in ('sí', 'si'):
                            btts_si = op.get('cuota')
                        elif lbl == 'no':
                            btts_no = op.get('cuota')

            iso = ev.get('fecha_partido') or ''
            d_cot, h_cot = '', ''
            if iso:
                try:
                    dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(cot_zone)
                    d_cot = dt.strftime('%Y-%m-%d')
                    h_cot = dt.strftime('%H:%M')
                except Exception:
                    d_cot = iso[:10]

            ev_picks = picks_by_event.get(pid, [])
            best_edge = 0.0
            for pk in ev_picks:
                try:
                    ed = float(pk.get('edge', 0.0))
                    if ed > best_edge:
                        best_edge = ed
                except Exception:
                    pass

            resumen_eventos.append({
                'id': pid,
                'partido': ev['partido'],
                'local': ev['local'],
                'visita': ev['visita'],
                'pais': ev['pais'],
                'competicion': ev['competicion'],
                'fecha_partido': iso,
                'fecha_colombia': d_cot,
                'hora_colombia': h_cot,
                'link': ev['link'],
                'total_mercados': ev['total_mercados'],
                'fecha_extraccion': ev['fecha_extraccion'],
                'odds_1x2': {'1': q1, 'X': qX, '2': q2},
                'odds_ou25': {'over': q_over, 'under': q_under},
                'odds_btts': {'si': btts_si, 'no': btts_no},
                'picks_count': len(ev_picks),
                'best_edge': round(best_edge, 3),
                'top_pick': ev_picks[0] if ev_picks else None
            })

        out_resumen_json = os.path.join(ESTADISTICAS_DIR, 'betplay_eventos_resumen.json')
        with open(out_resumen_json, 'w', encoding='utf-8') as f:
            json.dump(resumen_eventos, f, ensure_ascii=False, indent=2)

        out_resumen_js = os.path.join(ESTADISTICAS_DIR, 'betplay_eventos_resumen.js')
        with open(out_resumen_js, 'w', encoding='utf-8') as f:
            f.write('window.DATA_BETPLAY_EVENTOS_RESUMEN = ' + json.dumps(resumen_eventos, ensure_ascii=False) + ';\n')


if __name__ == '__main__':
    prioritizer = BetplayMarketPrioritizer()
    try:
        prioritizer.run_analysis()
    finally:
        prioritizer.close()
