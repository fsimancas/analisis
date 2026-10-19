"""
Script Maestro con Sistema de Checkpoints y Actualización Incremental
para las competiciones de Flashscore cubiertas por Betplay.

Características:
1. CHECKPOINTING INTELIGENTE:
   - Guarda el estado de cada competición ('completado', 'error', 'pendiente') en la tabla 'checkpoints_competiciones'.
   - Por defecto (modo --resume), omite las competiciones ya completadas y solo procesa las pendientes.
2. ACTUALIZACIÓN INCREMENTAL (--incremental):
   - Para competiciones ya descargadas, no vuelve a paginar todo el historial.
   - Solo extrae los partidos recientes y próximos.
   - Detecta si un partido cambió de 'por_jugar' a 'finalizado' o si hay partidos nuevos y los sincroniza sin re-descargar todo.
3. FORZAR RE-DESCARGA (--force):
   - Permite forzar la re-descarga completa de una o todas las competiciones si se requiere.
4. CONTROL Y RESUMEN (--status):
   - Muestra el estado del progreso de las 205 competiciones y el total de partidos en la base de datos.
"""

import os
import re
import sys
import json
import time
import argparse
import sqlite3
import datetime
import unicodedata
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')
PARTIDOS_DIR = os.path.join(BASE_DIR, 'partidos')

os.makedirs(PARTIDOS_DIR, exist_ok=True)

def slugify(text):
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text

def init_db_schema():
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        
        # Tabla de partidos
        cur.execute("""
        CREATE TABLE IF NOT EXISTS partidos (
            id TEXT PRIMARY KEY,
            competicion_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            estado TEXT NOT NULL,
            jornada TEXT,
            fecha_hora TEXT,
            equipo_local TEXT NOT NULL,
            equipo_visitante TEXT NOT NULL,
            goles_local INTEGER,
            goles_visitante INTEGER,
            link TEXT,
            FOREIGN KEY (competicion_id) REFERENCES competiciones(id) ON DELETE CASCADE
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_partidos_competicion ON partidos(competicion_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_partidos_tipo ON partidos(tipo);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_partidos_estado ON partidos(estado);")

        # Tabla de checkpoints
        cur.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints_competiciones (
            competicion_id INTEGER PRIMARY KEY,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            fecha_actualizacion TEXT NOT NULL,
            total_partidos INTEGER DEFAULT 0,
            partidos_nuevos INTEGER DEFAULT 0,
            partidos_actualizados INTEGER DEFAULT 0,
            error TEXT,
            FOREIGN KEY (competicion_id) REFERENCES competiciones(id) ON DELETE CASCADE
        );
        """)
        conn.commit()

def get_checkpoint(comp_id):
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        cur.execute("SELECT estado, total_partidos, fecha_actualizacion, error FROM checkpoints_competiciones WHERE competicion_id = ?", (comp_id,))
        row = cur.fetchone()
        if row:
            return {'estado': row[0], 'total_partidos': row[1], 'fecha': row[2], 'error': row[3]}
        return None

def update_checkpoint(comp_id, estado, total=0, nuevos=0, actualizados=0, error=None):
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        now = datetime.datetime.now().isoformat()
        cur.execute("""
        INSERT INTO checkpoints_competiciones (
            competicion_id, estado, fecha_actualizacion, total_partidos, partidos_nuevos, partidos_actualizados, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(competicion_id) DO UPDATE SET
            estado = excluded.estado,
            fecha_actualizacion = excluded.fecha_actualizacion,
            total_partidos = excluded.total_partidos,
            partidos_nuevos = excluded.partidos_nuevos,
            partidos_actualizados = excluded.partidos_actualizados,
            error = excluded.error;
        """, (comp_id, estado, now, total, nuevos, actualizados, error))
        conn.commit()

def get_existing_matches_map(comp_id):
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, tipo, estado, goles_local, goles_visitante, fecha_hora FROM partidos WHERE competicion_id = ?", (comp_id,))
        matches = {
            row[0]: {
                'tipo': row[1],
                'estado': row[2],
                'goles_local': row[3],
                'goles_visitante': row[4],
                'fecha_hora': row[5]
            }
            for row in cur.fetchall()
        }
        return matches

def get_competitions_from_db(pais_filter=None, comp_filter=None, limit=None, solo_residuales=False):
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        query = """
        SELECT c.id, c.pais_id, p.nombre_betplay, p.slug, c.nombre_betplay, c.nombre_flashscore, c.link_flashscore
        FROM competiciones c
        JOIN paises p ON c.pais_id = p.id
        WHERE c.link_flashscore IS NOT NULL 
          AND c.link_flashscore LIKE 'http%'
        """
        params = []
        
        if solo_residuales:
            query += " AND c.id IN (SELECT competicion_id FROM competiciones_fotmob WHERE ruta_optima = 'flashscore')"
        
        if pais_filter:
            query += " AND (p.slug LIKE ? OR p.nombre_betplay LIKE ? OR p.nombre_flashscore LIKE ?)"
            term = f"%{pais_filter}%"
            params.extend([term, term, term])
            
        if comp_filter:
            query += " AND (c.link_flashscore LIKE ? OR c.nombre_flashscore LIKE ? OR c.nombre_betplay LIKE ? OR CAST(c.id AS TEXT) = ?)"
            term = f"%{comp_filter}%"
            params.extend([term, term, term, str(comp_filter).strip()])
            
        query += " ORDER BY c.id ASC"
        
        if limit:
            query += f" LIMIT {int(limit)}"
            
        cur.execute(query, params)
        rows = cur.fetchall()
        
    competitions = []
    for r in rows:
        competitions.append({
            'comp_id': r[0],
            'pais_id': r[1],
            'pais_nombre': r[2],
            'pais_slug': r[3],
            'nombre_betplay': r[4],
            'nombre_flashscore': r[5],
            'link_flashscore': r[6]
        })
    return competitions


def fetch_html_tab(context, page_holder, url, max_clicks=10, retries=3):
    for attempt in range(1, retries + 1):
        page = page_holder.get('page')
        if not page or page.is_closed():
            page = context.new_page()
            page_holder['page'] = page

        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if resp and resp.status == 404:
                return ""
            break
        except Exception as e:
            if attempt == retries:
                print(f"      [!] Error navegando a {url} tras {retries} intentos: {e}")
                return ""
            time.sleep(1.5 * attempt)
            try:
                page.close()
            except Exception:
                pass
            page_holder['page'] = context.new_page()

    page = page_holder['page']
    try:
        page.wait_for_selector(".event__match", timeout=10000)
    except Exception:
        return ""

    click_count = 0
    while click_count < max_clicks:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.0)
        
        btn = page.query_selector("[data-testid='wcl-section-footer'] button")
        if btn and btn.is_visible():
            text = btn.inner_text().strip()
            if "Mostrar más partidos" in text:
                btn.click()
                time.sleep(1.8)
                click_count += 1
                continue
        break
        
    return page.content()

def parse_html_matches(html, match_type):
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    container = soup.find('div', class_=lambda c: c and 'sportName' in c and 'soccer' in c) or soup
    
    matches = []
    current_round = "General"
    seen_ids = set()

    for el in container.find_all(['div'], recursive=True):
        classes = el.get('class', [])
        
        if any('event__round' in c for c in classes):
            round_text = el.get_text(strip=True)
            if round_text:
                current_round = round_text
                
        if any('event__match' in c for c in classes) and el.get('id', '').startswith('g_'):
            match_id = el.get('id', '').replace('g_1_', '')
            if match_id in seen_ids:
                continue
            seen_ids.add(match_id)

            link_tag = el.find('a', class_='eventRowLink')
            link = link_tag.get('href') if link_tag else None
            if link and link.startswith('/'):
                link = f"https://www.flashscore.co{link}"

            time_tag = el.find(class_=lambda c: c and 'event__stageTime' in c)
            raw_time = time_tag.get_text(strip=True) if time_tag else ""

            estado = 'finalizado' if match_type == 'resultado' else 'por_jugar'
            clean_time = raw_time
            if 'Suspendido' in raw_time:
                estado = 'suspendido'
                clean_time = raw_time.replace('Suspendido', '').strip()
            elif 'Aplazado' in raw_time:
                estado = 'aplazado'
                clean_time = raw_time.replace('Aplazado', '').strip()
            elif 'Cancelado' in raw_time:
                estado = 'cancelado'
                clean_time = raw_time.replace('Cancelado', '').strip()

            home_tag = el.find(class_=lambda c: c and 'event__homeParticipant' in c)
            away_tag = el.find(class_=lambda c: c and 'event__awayParticipant' in c)
            home_team = home_tag.get_text(strip=True) if home_tag else ""
            away_team = away_tag.get_text(strip=True) if away_tag else ""

            score_home_tag = el.find(class_=lambda c: c and 'event__score--home' in c)
            score_away_tag = el.find(class_=lambda c: c and 'event__score--away' in c)
            
            score_home_raw = score_home_tag.get_text(strip=True) if score_home_tag else None
            score_away_raw = score_away_tag.get_text(strip=True) if score_away_tag else None
            
            score_home = int(score_home_raw) if score_home_raw and score_home_raw.isdigit() else None
            score_away = int(score_away_raw) if score_away_raw and score_away_raw.isdigit() else None

            matches.append({
                'id': match_id,
                'tipo': match_type,
                'estado': estado,
                'jornada': current_round,
                'fecha_hora': clean_time,
                'equipo_local': home_team,
                'equipo_visitante': away_team,
                'goles_local': score_home,
                'goles_visitante': score_away,
                'link': link
            })

    return matches

def sync_matches_to_db_and_json(comp, matches_scraped):
    """
    Sincroniza partidos detectados:
    - Deduplica en memoria por ID para evitar colisiones entre resultados y partidos.
    - Compara contra los que ya existen en la DB globalmente.
    - Inserta o actualiza usando ON CONFLICT(id) DO UPDATE SET de forma idempotente.
    - Garantiza el cierre de conexiones y maneja timeouts para prevenir database locks.
    - Actualiza el JSON consolidado de la competición.
    """
    comp_id = comp['comp_id']
    
    # 1. Deduplicar en memoria preservando el estado más completo (finalizado > por_jugar)
    dedup_map = {}
    for m in matches_scraped:
        mid = m['id']
        if mid not in dedup_map:
            dedup_map[mid] = m
        else:
            if m.get('tipo') == 'resultado' or m.get('estado') == 'finalizado':
                dedup_map[mid] = m
    matches_scraped = list(dedup_map.values())
    
    if not matches_scraped:
        with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM partidos WHERE competicion_id = ?", (comp_id,))
            total_en_db = cur.fetchone()[0]
        return total_en_db, 0, 0

    # 2. Consultar partidos existentes en la DB por ID para calcular 'nuevos' y 'actualizados'
    match_ids = [m['id'] for m in matches_scraped]
    existing_db_map = {}
    
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        chunk_size = 500
        for i in range(0, len(match_ids), chunk_size):
            chunk = match_ids[i:i + chunk_size]
            placeholders = ','.join(['?'] * len(chunk))
            cur.execute(f"""
                SELECT id, competicion_id, tipo, estado, goles_local, goles_visitante, fecha_hora 
                FROM partidos WHERE id IN ({placeholders})
            """, chunk)
            for row in cur.fetchall():
                existing_db_map[row[0]] = {
                    'competicion_id': row[1],
                    'tipo': row[2],
                    'estado': row[3],
                    'goles_local': row[4],
                    'goles_visitante': row[5],
                    'fecha_hora': row[6]
                }

    records_to_upsert = []
    nuevos_count = 0
    actualizados_count = 0

    for m in matches_scraped:
        mid = m['id']
        record = (
            m['id'], comp_id, m['tipo'], m['estado'], m['jornada'], m['fecha_hora'],
            m['equipo_local'], m['equipo_visitante'], m['goles_local'], m['goles_visitante'], m['link']
        )
        
        if mid not in existing_db_map:
            nuevos_count += 1
            records_to_upsert.append(record)
        else:
            prev = existing_db_map[mid]
            if (prev['competicion_id'] != comp_id or
                prev['estado'] != m['estado'] or 
                prev['goles_local'] != m['goles_local'] or 
                prev['goles_visitante'] != m['goles_visitante'] or
                prev['tipo'] != m['tipo']):
                actualizados_count += 1
                records_to_upsert.append(record)

    # 3. Ejecutar Upsert seguro e idempotente en SQLite
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        
        if records_to_upsert:
            cur.executemany("""
            INSERT INTO partidos (
                id, competicion_id, tipo, estado, jornada, fecha_hora, equipo_local, equipo_visitante, goles_local, goles_visitante, link
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                competicion_id = excluded.competicion_id,
                tipo = excluded.tipo,
                estado = excluded.estado,
                jornada = excluded.jornada,
                fecha_hora = excluded.fecha_hora,
                equipo_local = excluded.equipo_local,
                equipo_visitante = excluded.equipo_visitante,
                goles_local = excluded.goles_local,
                goles_visitante = excluded.goles_visitante,
                link = excluded.link;
            """, records_to_upsert)
            conn.commit()

        cur.execute("SELECT count(*) FROM partidos WHERE competicion_id = ?", (comp_id,))
        total_en_db = cur.fetchone()[0]

    # 4. Guardar en JSON (merge con los existentes)
    comp_slug = slugify(comp['nombre_flashscore'])
    pais_dir = os.path.join(PARTIDOS_DIR, comp['pais_slug'])
    os.makedirs(pais_dir, exist_ok=True)
    json_path = os.path.join(pais_dir, f"{comp_slug}.json")
    
    existing_json_data = []
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                existing_json_data = json.load(f)
        except Exception:
            existing_json_data = []
            
    json_map = {item['id']: item for item in existing_json_data}
    for m in matches_scraped:
        json_map[m['id']] = m
        
    merged_list = list(json_map.values())
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(merged_list, f, ensure_ascii=False, indent=2)

    return total_en_db, nuevos_count, actualizados_count

def print_status():
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT count(*) FROM competiciones WHERE link_flashscore LIKE 'http%'")
        total_valid = cur.fetchone()[0]
        
        cur.execute("SELECT estado, count(*), sum(total_partidos) FROM checkpoints_competiciones GROUP BY estado")
        check_rows = cur.fetchall()
        
        cur.execute("SELECT count(*) FROM competiciones WHERE link_flashscore LIKE 'http%' AND id NOT IN (SELECT competicion_id FROM checkpoints_competiciones WHERE estado = 'completado')")
        pendientes = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM partidos")
        total_partidos = cur.fetchone()[0]
        
    print("\n=======================================================")
    print("           ESTADO DE CHECKPOINTS Y PROGRESO            ")
    print("=======================================================")
    print(f"Total competiciones Betplay:  {total_valid}")
    for est, cnt, parts in check_rows:
        print(f"  - Competiciones '{est}':  {cnt} (acumulado: {parts or 0} partidos)")
    print(f"Competiciones pendientes:     {pendientes}")
    print(f"Total partidos en la DB:      {total_partidos}")
    print("=======================================================\n")

def run_scraper(competitions, mode="resume", max_clicks=10, delay=1.0):
    total = len(competitions)
    print(f"\n==================================================")
    print(f"Iniciando scraper en modo [{mode.upper()}] para {total} competiciones...")
    print(f"==================================================\n")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page_holder = {'page': context.new_page()}

        for idx, comp in enumerate(competitions, 1):
            comp_id = comp['comp_id']
            cp = get_checkpoint(comp_id)
            
            # 1. Comprobación de Checkpoint
            if mode == "resume":
                if cp and cp['estado'] == 'completado':
                    print(f"[{idx}/{total}] [-] OMITIDO: #{comp_id} {comp['pais_nombre']} -> {comp['nombre_flashscore']} ya completada ({cp['total_partidos']} partidos guardados).")
                    continue

            # Reciclar periódicamente la pestaña cada 25 competiciones para prevenir memory leaks y sockets huérfanos
            if idx > 1 and idx % 25 == 0:
                try:
                    page_holder['page'].close()
                except Exception:
                    pass
                page_holder['page'] = context.new_page()
                    
            clicks_to_do = 1 if mode == "incremental" else max_clicks
            
            base_url = comp['link_flashscore'].rstrip('/')
            url_res = f"{base_url}/resultados/"
            url_par = f"{base_url}/partidos/"
            
            tag = "INCREMENTAL" if mode == "incremental" else "DESCARGA"
            print(f"[{idx}/{total}] [{tag}] #{comp_id} {comp['pais_nombre']} -> {comp['nombre_flashscore']} (Betplay: {comp['nombre_betplay']})")
            
            try:
                # Resultados
                html_res = fetch_html_tab(context, page_holder, url_res, max_clicks=clicks_to_do)
                resultados = parse_html_matches(html_res, "resultado")
                
                # Próximos
                html_par = fetch_html_tab(context, page_holder, url_par, max_clicks=clicks_to_do)
                partidos = parse_html_matches(html_par, "proximo")
                
                all_scraped = resultados + partidos
                total_db, nuevos, actualizados = sync_matches_to_db_and_json(comp, all_scraped)
                
                update_checkpoint(comp_id, estado='completado', total=total_db, nuevos=nuevos, actualizados=actualizados, error=None)
                print(f"    -> OK: {total_db} partidos totales en DB | +{nuevos} nuevos | ~{actualizados} actualizados.")
                
            except Exception as e:
                print(f"    -> ERROR en competición #{comp_id}: {e}")
                update_checkpoint(comp_id, estado='error', total=0, nuevos=0, actualizados=0, error=str(e))
                
            if delay > 0 and idx < total:
                time.sleep(delay)
                
        browser.close()
        
    print("\n[+] Proceso finalizado.")
    print_status()

def main():
    parser = argparse.ArgumentParser(description="Scraper de partidos de Flashscore con Checkpoints y Modo Incremental")
    parser.add_argument('--all', action='store_true', help="Procesar todas las competiciones")
    parser.add_argument('--pais', type=str, help="Filtrar por país (ej. colombia, espana)")
    parser.add_argument('--competicion', type=str, help="Filtrar por competición (ej. laliga-ea-sports)")
    parser.add_argument('--limit', type=int, help="Límite de competiciones")
    parser.add_argument('--force', action='store_true', help="Forzar re-descarga completa ignorando checkpoints")
    parser.add_argument('--incremental', action='store_true', help="Modo incremental: solo extrae partidos recientes y nuevos sin re-descargar histórico")
    parser.add_argument('--solo-residuales', action='store_true', help="Filtrar únicamente las 44 competiciones residuales asignadas a Flashscore")
    parser.add_argument('--status', action='store_true', help="Mostrar estado de los checkpoints y progreso")
    parser.add_argument('--max-clicks', type=int, default=10, help="Máximo de clics en 'Mostrar más partidos'")
    parser.add_argument('--delay', type=float, default=1.0, help="Pausa en segundos entre competiciones")
    
    args = parser.parse_args()
    init_db_schema()
    
    if args.status:
        print_status()
        return

    # Determinar modo
    if args.force:
        mode = "force"
    elif args.incremental:
        mode = "incremental"
    else:
        mode = "resume"  # Por defecto salta lo ya completado

    comps = get_competitions_from_db(pais_filter=args.pais, comp_filter=args.competicion, limit=args.limit, solo_residuales=args.solo_residuales)
    
    if not comps:
        print("[!] No se encontraron competiciones con los filtros especificados.")
        sys.exit(1)
        
    run_scraper(comps, mode=mode, max_clicks=args.max_clicks, delay=args.delay)

if __name__ == '__main__':
    main()
