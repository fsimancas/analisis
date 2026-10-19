"""
Scraper de Partidos y Resultados de HOY de Flashscore (Solo Competiciones Activas)
==================================================================================
- Descarga los partidos y marcadores de las diferentes competiciones que SOLO se jugaron en el día de hoy.
- Filtra de manera inteligente únicamente las competiciones cubiertas por Betplay en betplay_flashscore.db.
- Actualiza en tiempo real la tabla 'partidos' en SQLite (goles, estado 'finalizado', fecha).
- Actualiza los checkpoints de las competiciones correspondientes.
- Permite sincronizar opcionalmente las estadísticas de liga y el Radar de Valor.
"""

import os
import sys
import re
import json
import time
import argparse
import sqlite3
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')
PARTIDOS_DIR = os.path.join(BASE_DIR, 'partidos')

os.makedirs(PARTIDOS_DIR, exist_ok=True)


def parse_scores(score_text: str):
    """Convierte texto de goles a entero de forma segura."""
    if not score_text:
        return None
    cleaned = re.sub(r'\D', '', score_text.strip())
    return int(cleaned) if cleaned else None


def limpiar_nombre_equipo(name: str) -> str:
    """Limpia textos auxiliares inyectados por Flashscore."""
    if not name:
        return ""
    cleaned = re.sub(r'Equipo que avanza.*', '', name, flags=re.IGNORECASE)
    cleaned = re.sub(r'Tras penaltis.*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'Prórroga.*', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def clasificar_estado(stage_text: str, score_h, score_a):
    """Clasifica el estado del partido según la descripción de Flashscore."""
    st = (stage_text or "").lower().strip()
    if any(k in st for k in ["finalizado", "fin", "penaltis", "prórroga", "tras prórroga"]):
        return "finalizado"
    if any(k in st for k in ["aplazado", "cancelado", "interrumpido", "suspendido"]):
        return "suspendido"
    if any(k in st for k in ["1t", "2t", "descanso", "en juego", "min"]) or re.search(r"\d+'", st):
        return "en_juego"
    if score_h is not None and score_a is not None:
        return "finalizado"
    return "por_jugar"


def cargar_competiciones_db():
    """Carga todas las competiciones de Betplay indexadas por su slug de Flashscore."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.link_flashscore, c.nombre_flashscore, c.pais_nombre 
        FROM competiciones c 
        WHERE c.link_flashscore IS NOT NULL AND c.link_flashscore LIKE 'http%'
    """)
    rows = cur.fetchall()
    conn.close()

    comp_by_slug = {}
    for cid, link, cname, pname in rows:
        slug_part = link.replace('https://www.flashscore.co', '').strip('/')
        comp_by_slug[slug_part] = (cid, cname, pname, link)

    return comp_by_slug


def ejecutar_scraper_hoy(fecha_filtro: str = None, tab_results: bool = False, actualizar_stats: bool = True):
    t_inicio = time.perf_counter()
    hoy_dt = datetime.now()
    fecha_str = fecha_filtro or hoy_dt.strftime("%d.%m.%Y")
    fecha_ddmm = hoy_dt.strftime("%d.%m.")

    print("\n" + "=" * 75)
    print("      SCRAPER DE PARTIDOS DE HOY (FLASHSCORE - SOLO COMPETICIONES ACTIVAS)")
    print(f"      Fecha: {fecha_str} | Base de datos: betplay_flashscore.db")
    print("=" * 75)

    comp_by_slug = cargar_competiciones_db()
    print(f"[1/4] Catálogo de competiciones Betplay cargado ({len(comp_by_slug)} ligas/torneos mapeados).")

    # 1. Navegación en Flashscore con Playwright nativo (msedge)
    print("[2/4] Conectando con Flashscore y extrayendo partidos del día...", end="", flush=True)
    t_nav_ini = time.perf_counter()
    html = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            page.goto("https://www.flashscore.co/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_selector(".event__match", timeout=25000)
            
            # Si se pide pestaña exclusiva de finalizados
            if tab_results:
                btn_res = page.query_selector("[data-testid='wcl-scores-tabs-button-results']")
                if btn_res and btn_res.is_visible():
                    btn_res.click()
                    page.wait_for_timeout(1500)

            # Desplazamiento dinámico para asegurar la carga completa de todas las ligas
            prev_len = 0
            for i in range(12):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(700)
                curr_len = page.evaluate("document.querySelectorAll('.event__match').length")
                if curr_len == prev_len:
                    break
                prev_len = curr_len

            html = page.content()
        except Exception as e:
            print(f" [!] Error en la carga: {e}")
            browser.close()
            return
        finally:
            browser.close()

    t_nav_fin = time.perf_counter()
    print(f" OK! ({prev_len} partidos capturados en {t_nav_fin - t_nav_ini:.2f}s)")

    # 2. Parseo y Filtrado por Competiciones de Betplay
    print("[3/4] Identificando competiciones que jugaron hoy y extrayendo marcadores...")
    soup = BeautifulSoup(html, 'html.parser')
    container = soup.find('div', class_=lambda c: c and 'sportName' in c and 'soccer' in c) or soup

    current_comp = None
    partidos_hoy = []
    competitions_activas = {}

    for el in container.find_all('div', recursive=False):
        classes = el.get('class', [])
        
        # Cabecera de Competición
        if any('headerLeague__wrapper' in c for c in classes):
            a_tag = el.find('a', href=True)
            if a_tag:
                href = a_tag['href'].strip('/')
                matched = comp_by_slug.get(href)
                if not matched:
                    # Coincidencia flexible de slug
                    for s_part, c_info in comp_by_slug.items():
                        if s_part in href or href in s_part:
                            matched = c_info
                            break
                current_comp = matched
            else:
                current_comp = None

        # Fila de Partido (solo si pertenece a una competición de Betplay)
        elif any('event__match' in c for c in classes) and current_comp:
            mid = el.get('id', '').replace('g_1_', '')
            if not mid:
                continue

            home_el = el.find(class_=lambda c: c and 'homeParticipant' in c)
            away_el = el.find(class_=lambda c: c and 'awayParticipant' in c)
            score_h_el = el.find(class_=lambda c: c and 'score--home' in c)
            score_a_el = el.find(class_=lambda c: c and 'score--away' in c)
            stage_el = el.find(class_=lambda c: c and ('stage' in c or 'time' in c or 'status' in c))
            link_tag = el.find('a', class_='eventRowLink')

            h_name = limpiar_nombre_equipo(home_el.get_text(strip=True)) if home_el else "Local"
            a_name = limpiar_nombre_equipo(away_el.get_text(strip=True)) if away_el else "Visitante"
            sh = parse_scores(score_h_el.get_text(strip=True)) if score_h_el else None
            sa = parse_scores(score_a_el.get_text(strip=True)) if score_a_el else None
            st_text = stage_el.get_text(strip=True) if stage_el else "Finalizado"
            
            estado = clasificar_estado(st_text, sh, sa)
            p_link = f"https://www.flashscore.co{link_tag['href']}" if link_tag and link_tag.get('href') else None

            # Construir fecha_hora normalizada
            hora = re.search(r"\d{2}:\d{2}", st_text)
            f_hora = f"{fecha_ddmm} {hora.group(0)}" if hora else f"{fecha_ddmm} Finalizado"

            cid, cname, pname, clink = current_comp
            competitions_activas[cid] = (cname, pname)

            partidos_hoy.append({
                "id": mid,
                "competicion_id": cid,
                "competicion_nombre": cname,
                "pais_nombre": pname,
                "tipo": "resultado" if estado == "finalizado" else "fixture",
                "jornada": "Fecha de Hoy",
                "fecha_hora": f_hora,
                "equipo_local": h_name,
                "equipo_visitante": a_name,
                "goles_local": sh,
                "goles_visitante": sa,
                "link": p_link,
                "estado": estado
            })

    if not partidos_hoy:
        print("[!] No se detectaron partidos para las competiciones de Betplay en el día de hoy.")
        return

    # 3. Persistir en SQLite con trazabilidad e integridad referencial
    print(f"\n[4/4] Guardando {len(partidos_hoy)} partidos en SQLite y actualizando checkpoints...")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    partidos_insertados = 0
    partidos_actualizados = 0

    for p in partidos_hoy:
        # Verificar existencia previa
        cur.execute("SELECT goles_local, goles_visitante, estado FROM partidos WHERE id = ?", (p['id'],))
        row = cur.fetchone()

        if row:
            partidos_actualizados += 1
        else:
            partidos_insertados += 1

        cur.execute("""
        INSERT INTO partidos (
            id, competicion_id, tipo, jornada, fecha_hora,
            equipo_local, equipo_visitante, goles_local, goles_visitante,
            link, estado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            competicion_id = excluded.competicion_id,
            tipo = excluded.tipo,
            fecha_hora = excluded.fecha_hora,
            equipo_local = excluded.equipo_local,
            equipo_visitante = excluded.equipo_visitante,
            goles_local = excluded.goles_local,
            goles_visitante = excluded.goles_visitante,
            link = excluded.link,
            estado = excluded.estado;
        """, (
            p['id'], p['competicion_id'], p['tipo'], p['jornada'], p['fecha_hora'],
            p['equipo_local'], p['equipo_visitante'], p['goles_local'], p['goles_visitante'],
            p['link'], p['estado']
        ))

    # Actualizar checkpoints de las competiciones que jugaron hoy
    now_iso = datetime.now().isoformat()
    for cid in competitions_activas:
        cur.execute("SELECT count(*) FROM partidos WHERE competicion_id = ?", (cid,))
        tot_c = cur.fetchone()[0]
        cur.execute("""
        INSERT INTO checkpoints_competiciones (
            competicion_id, estado, fecha_actualizacion, total_partidos, partidos_nuevos, partidos_actualizados, error
        ) VALUES (?, 'completado', ?, ?, ?, ?, NULL)
        ON CONFLICT(competicion_id) DO UPDATE SET
            estado = 'completado',
            fecha_actualizacion = excluded.fecha_actualizacion,
            total_partidos = excluded.total_partidos;
        """, (cid, now_iso, tot_c, 0, 0))

    conn.commit()
    conn.close()

    # 4. Guardar archivo JSON histórico del día
    out_json = os.path.join(PARTIDOS_DIR, f"partidos_hoy_{hoy_dt.strftime('%Y%m%d')}.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "fecha": fecha_str,
            "total_partidos": len(partidos_hoy),
            "total_competiciones_activas": len(competitions_activas),
            "competiciones": [{"id": cid, "competicion": c[0], "pais": c[1]} for cid, c in competitions_activas.items()],
            "partidos": partidos_hoy
        }, f, ensure_ascii=False, indent=2)

    t_fin = time.perf_counter()
    duracion = t_fin - t_inicio

    # 5. Resumen en consola
    print("\n" + "=" * 75)
    print("               RESUMEN DE DESCARGA: PARTIDOS DE HOY                  ")
    print("=" * 75)
    print(f" Competiciones activas hoy:   {len(competitions_activas)} competiciones")
    print(f" Total partidos procesados:   {len(partidos_hoy)} partidos")
    print(f"   ├─ Partidos nuevos insertados: {partidos_insertados}")
    print(f"   └─ Partidos actualizados:      {partidos_actualizados}")
    print(f" Almacenamiento SQLite:       {DB_PATH}")
    print(f" Archivo JSON exportado:      {out_json}")
    print(f" ⏱ Duración total:            {duracion:.2f} segundos")
    print("-" * 75)

    print("\nDetalle de Competiciones que jugaron hoy:")
    for cid, (cname, pname) in competitions_activas.items():
        sub_p = [p for p in partidos_hoy if p['competicion_id'] == cid]
        print(f"  • #{cid:>3} [{pname}] {cname}: {len(sub_p)} partido(s)")
        for m in sub_p:
            sh_str = str(m['goles_local']) if m['goles_local'] is not None else '-'
            sa_str = str(m['goles_visitante']) if m['goles_visitante'] is not None else '-'
            print(f"       {m['equipo_local']} {sh_str} - {sa_str} {m['equipo_visitante']}  ({m['estado'].upper()})")

    print("=" * 75 + "\n")

    # 6. Sincronización automática de estadísticas de liga y radar si se solicitó
    if actualizar_stats:
        print("[*] Sincronizando estadísticas y Radar de Valor con los nuevos marcadores...")
        try:
            from estadisticas_liga import LeagueStatsCalculator
            calc = LeagueStatsCalculator()
            try:
                for cid in competitions_activas:
                    calc.calculate_for_competition(cid)
                print(f"  [✓] {len(competitions_activas)} ligas recalculadas con los nuevos resultados.")
            finally:
                calc.close()

            from analizador_betplay import BetplayMarketPrioritizer
            prioritizer = BetplayMarketPrioritizer()
            try:
                prioritizer.run_analysis()
                print("  [✓] Radar de Valor y catálogo de eventos Betplay actualizados.")
            finally:
                prioritizer.close()
        except Exception as e:
            print(f"  [!] Advertencia al sincronizar estadísticas: {e}")


def main():
    parser = argparse.ArgumentParser(description="Descarga partidos de competiciones que jugaron hoy en Flashscore.")
    parser.add_argument("--fecha", help="Fecha específica a procesar (DD.MM.YYYY)")
    parser.add_argument("--ayer", action="store_true", help="Descargar partidos de ayer")
    parser.add_argument("--results-only", action="store_true", help="Filtrar pestaña solo finalizados")
    parser.add_argument("--no-stats", action="store_true", help="Omitir recálculo de estadísticas y radar")
    args = parser.parse_args()

    fecha = args.fecha
    if args.ayer:
        ayer_dt = datetime.now() - timedelta(days=1)
        fecha = ayer_dt.strftime("%d.%m.%Y")

    ejecutar_scraper_hoy(fecha_filtro=fecha, tab_results=args.results_only, actualizar_stats=not args.no_stats)


if __name__ == "__main__":
    main()
