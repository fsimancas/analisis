"""
Módulo Optimizado: Extractor de Detalles de Partidos (Flashscore)
================================================================
Versión de alto rendimiento basada en Playwright asíncrono, paralelización
por workers, bloqueo de assets pesados y commits optimizados en SQLite (WAL mode).

Conserva intactos los parsers de BeautifulSoup (parsers_detalle.py),
la estructura JSON y el esquema normalizado en 'betplay_flashscore.db'.
Respeta y continúa exactamente por el checkpoint donde se quedó el extractor anterior.
"""

import os
import sys
import re
import json
import time
import asyncio
import sqlite3
import argparse
import datetime
import unicodedata
from playwright.async_api import async_playwright
from parsers_detalle import (
    parse_resumen,
    parse_estadisticas,
    parse_alineaciones,
    parse_jugadores_stats_table
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')
DETALLES_DIR = os.path.join(BASE_DIR, 'partidos_detalles')

os.makedirs(DETALLES_DIR, exist_ok=True)

# Lock para sincronizar escrituras en SQLite entre workers asíncronos
DB_LOCK = asyncio.Lock()


def slugify(text: str) -> str:
    if not text:
        return "desconocido"
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text or "desconocido"


def init_db_schema():
    """Garantiza la creación de tablas y activa el modo WAL para concurrencia."""
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode = WAL;")
        cur.execute("PRAGMA synchronous = NORMAL;")
        cur.execute("PRAGMA foreign_keys = ON;")

        # 1. Tabla de cabecera de detalle
        cur.execute("""
        CREATE TABLE IF NOT EXISTS partidos_detalles (
            partido_id TEXT PRIMARY KEY,
            competicion_id INTEGER NOT NULL,
            sistema_local TEXT,
            sistema_visitante TEXT,
            rating_medio_local REAL,
            rating_medio_visitante REAL,
            entrenador_local TEXT,
            entrenador_visitante TEXT,
            json_path TEXT,
            actualizado_el TEXT NOT NULL,
            FOREIGN KEY (partido_id) REFERENCES partidos(id) ON DELETE CASCADE,
            FOREIGN KEY (competicion_id) REFERENCES competiciones(id) ON DELETE CASCADE
        );
        """)

        # 2. Tabla de incidencias (Resumen)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS partidos_incidentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partido_id TEXT NOT NULL,
            periodo TEXT,
            minuto TEXT,
            equipo TEXT,
            tipo TEXT,
            jugador TEXT,
            jugador_id TEXT,
            jugador_sale TEXT,
            jugador_sale_id TEXT,
            nota TEXT,
            FOREIGN KEY (partido_id) REFERENCES partidos(id) ON DELETE CASCADE
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_incidentes_partido ON partidos_incidentes(partido_id);")

        # 3. Tabla de estadísticas colectivas
        cur.execute("""
        CREATE TABLE IF NOT EXISTS partidos_estadisticas (
            partido_id TEXT NOT NULL,
            periodo TEXT NOT NULL,
            seccion TEXT NOT NULL,
            metrica TEXT NOT NULL,
            valor_local TEXT,
            valor_visitante TEXT,
            PRIMARY KEY (partido_id, periodo, seccion, metrica),
            FOREIGN KEY (partido_id) REFERENCES partidos(id) ON DELETE CASCADE
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stats_partido ON partidos_estadisticas(partido_id);")

        # 4. Tabla de alineaciones
        cur.execute("""
        CREATE TABLE IF NOT EXISTS partidos_alineaciones (
            partido_id TEXT NOT NULL,
            jugador_id TEXT NOT NULL,
            equipo TEXT NOT NULL,
            rol TEXT NOT NULL,
            dorsal TEXT,
            nombre TEXT NOT NULL,
            posicion TEXT,
            calificacion REAL,
            capitan INTEGER DEFAULT 0,
            minuto_salida TEXT,
            motivo_ausencia TEXT,
            PRIMARY KEY (partido_id, jugador_id, rol),
            FOREIGN KEY (partido_id) REFERENCES partidos(id) ON DELETE CASCADE
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alineaciones_partido ON partidos_alineaciones(partido_id);")

        # 5. Tabla de estadísticas individuales de jugadores
        cur.execute("""
        CREATE TABLE IF NOT EXISTS partidos_jugadores_stats (
            partido_id TEXT NOT NULL,
            jugador_id TEXT NOT NULL,
            tab TEXT NOT NULL,
            metrica_alias TEXT NOT NULL,
            valor TEXT,
            PRIMARY KEY (partido_id, jugador_id, tab, metrica_alias),
            FOREIGN KEY (partido_id) REFERENCES partidos(id) ON DELETE CASCADE
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jugadores_stats_partido ON partidos_jugadores_stats(partido_id);")

        # 6. Tabla de checkpoints para detalles
        cur.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints_detalles_partidos (
            partido_id TEXT PRIMARY KEY,
            competicion_id INTEGER NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            fecha_extraccion TEXT NOT NULL,
            error TEXT,
            FOREIGN KEY (partido_id) REFERENCES partidos(id) ON DELETE CASCADE
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_det_estado ON checkpoints_detalles_partidos(estado);")

        conn.commit()


async def route_intercept(route):
    """Bloquea recursos innecesarios (imágenes, medios, fuentes y trackers) para máxima velocidad."""
    req = route.request
    rtype = req.resource_type
    url = req.url
    if rtype in ("image", "media", "font"):
        await route.abort()
        return
    if any(t in url for t in ("google-analytics", "doubleclick", "scorecardresearch", "advert", "banners", "livesportmedia", "facebook", "twitter")):
        await route.abort()
        return
    await route.continue_()


async def save_match_details_async(match_id, comp_id, comp_slug, data):
    """Guarda primero en archivo JSON y luego persiste en SQLite con bloqueo thread-safe."""
    # 1. Guardar primero en JSON
    comp_dir = os.path.join(DETALLES_DIR, comp_slug)
    os.makedirs(comp_dir, exist_ok=True)
    json_path = os.path.join(comp_dir, f"{match_id}.json")

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    now = datetime.datetime.now().isoformat()

    # Checkpoint JSON de la competición
    chk_json_path = os.path.join(comp_dir, "_checkpoint.json")
    try:
        chk_data = {}
        if os.path.exists(chk_json_path):
            with open(chk_json_path, 'r', encoding='utf-8') as f:
                chk_data = json.load(f)
        if 'partidos' not in chk_data:
            chk_data['partidos'] = {}
        chk_data['competicion_id'] = comp_id
        chk_data['competicion_slug'] = comp_slug
        chk_data['ultima_actualizacion'] = now
        chk_data['partidos'][match_id] = {'estado': 'completado', 'fecha': now}
        chk_data['total_procesados'] = len(chk_data['partidos'])
        with open(chk_json_path, 'w', encoding='utf-8') as f:
            json.dump(chk_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # 2. Persistir en SQLite con exclusión mutua
    async with DB_LOCK:
        with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON;")

            # A. partidos_detalles
            alin = data.get('alineaciones', {})
            cur.execute("""
            INSERT OR REPLACE INTO partidos_detalles (
                partido_id, competicion_id, sistema_local, sistema_visitante,
                rating_medio_local, rating_medio_visitante,
                entrenador_local, entrenador_visitante, json_path, actualizado_el
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                match_id,
                comp_id,
                alin.get('sistema_local', ''),
                alin.get('sistema_visitante', ''),
                float(alin.get('rating_medio_local')) if alin.get('rating_medio_local') else None,
                float(alin.get('rating_medio_visitante')) if alin.get('rating_medio_visitante') else None,
                alin.get('entrenadores', {}).get('local', ''),
                alin.get('entrenadores', {}).get('visitante', ''),
                json_path,
                now
            ))

            # B. partidos_incidentes
            cur.execute("DELETE FROM partidos_incidentes WHERE partido_id = ?", (match_id,))
            incidents_rows = [
                (
                    match_id,
                    inc.get('periodo'),
                    inc.get('minuto'),
                    inc.get('equipo'),
                    inc.get('tipo'),
                    inc.get('jugador'),
                    inc.get('jugador_id'),
                    inc.get('jugador_sale'),
                    inc.get('jugador_sale_id'),
                    inc.get('nota')
                )
                for inc in data.get('resumen', [])
            ]
            if incidents_rows:
                cur.executemany("""
                INSERT INTO partidos_incidentes (
                    partido_id, periodo, minuto, equipo, tipo, jugador, jugador_id, jugador_sale, jugador_sale_id, nota
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, incidents_rows)

            # C. partidos_estadisticas
            stats_rows = []
            for periodo, sections in data.get('estadisticas', {}).items():
                for sec_name, metrics in sections.items():
                    for met_name, vals in metrics.items():
                        stats_rows.append((
                            match_id,
                            periodo,
                            sec_name,
                            met_name,
                            str(vals.get('local', '')),
                            str(vals.get('visitante', ''))
                        ))
            if stats_rows:
                cur.executemany("""
                INSERT OR REPLACE INTO partidos_estadisticas (
                    partido_id, periodo, seccion, metrica, valor_local, valor_visitante
                ) VALUES (?, ?, ?, ?, ?, ?);
                """, stats_rows)

            # D. partidos_alineaciones
            alin_rows = []
            for rol_tipo, players in [
                ('titular', alin.get('titulares', [])),
                ('sustituido', alin.get('sustituidos', [])),
                ('suplente', alin.get('suplentes', [])),
                ('ausente', alin.get('ausentes', []))
            ]:
                for p in players:
                    p_id = p.get('jugador_id') or p.get('nombre')
                    if not p_id:
                        continue
                    rating_val = None
                    try:
                        rating_val = float(p.get('calificacion')) if p.get('calificacion') else None
                    except ValueError:
                        rating_val = None

                    cap = 1 if '(C)' in p.get('rol', '') else 0
                    alin_rows.append((
                        match_id,
                        p_id,
                        p.get('equipo', ''),
                        rol_tipo,
                        p.get('dorsal', ''),
                        p.get('nombre', ''),
                        p.get('posicion', ''),
                        rating_val,
                        cap,
                        p.get('minuto_salida', ''),
                        p.get('motivo_ausencia', '')
                    ))
            if alin_rows:
                cur.executemany("""
                INSERT OR REPLACE INTO partidos_alineaciones (
                    partido_id, jugador_id, equipo, rol, dorsal, nombre, posicion, calificacion, capitan, minuto_salida, motivo_ausencia
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, alin_rows)

            # E. partidos_jugadores_stats
            p_stats_rows = []
            for tab_name, players in data.get('estadisticas_jugadores', {}).items():
                for p in players:
                    p_id = p.get('jugador_id') or p.get('nombre')
                    if not p_id:
                        continue
                    for k, v in p.items():
                        if k in ('jugador_id', 'nombre', 'posicion'):
                            continue
                        p_stats_rows.append((
                            match_id,
                            p_id,
                            tab_name,
                            k,
                            str(v)
                        ))
            if p_stats_rows:
                cur.executemany("""
                INSERT OR REPLACE INTO partidos_jugadores_stats (
                    partido_id, jugador_id, tab, metrica_alias, valor
                ) VALUES (?, ?, ?, ?, ?);
                """, p_stats_rows)

            # F. Checkpoint en SQLite
            cur.execute("""
            INSERT OR REPLACE INTO checkpoints_detalles_partidos (
                partido_id, competicion_id, estado, fecha_extraccion, error
            ) VALUES (?, ?, 'completado', ?, NULL);
            """, (match_id, comp_id, now))

            conn.commit()

    return json_path


async def record_error_async(match_id, comp_id, err_msg, comp_slug=None):
    now = datetime.datetime.now().isoformat()
    if comp_slug:
        comp_dir = os.path.join(DETALLES_DIR, comp_slug)
        os.makedirs(comp_dir, exist_ok=True)
        chk_json_path = os.path.join(comp_dir, "_checkpoint.json")
        try:
            chk_data = {}
            if os.path.exists(chk_json_path):
                with open(chk_json_path, 'r', encoding='utf-8') as f:
                    chk_data = json.load(f)
            if 'partidos' not in chk_data:
                chk_data['partidos'] = {}
            chk_data['competicion_id'] = comp_id
            chk_data['competicion_slug'] = comp_slug
            chk_data['ultima_actualizacion'] = now
            chk_data['partidos'][match_id] = {'estado': 'error', 'error': str(err_msg)[:300], 'fecha': now}
            with open(chk_json_path, 'w', encoding='utf-8') as f:
                json.dump(chk_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    async with DB_LOCK:
        with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO checkpoints_detalles_partidos (
                partido_id, competicion_id, estado, fecha_extraccion, error
            ) VALUES (?, ?, 'error', ?, ?);
            """, (match_id, comp_id, now, str(err_msg)[:500]))
            conn.commit()


async def scrape_single_match_fast(context, match_url, match_id):
    """Extrae las 4 secciones con carga optimizada sin esperas fijas innecesarias."""
    if match_url:
        if "/partido/" in match_url:
            match_url = f"https://www.flashscore.co/partido/{match_url.split('/partido/', 1)[1]}"
        else:
            match_url = re.sub(r'^(https?://[^/]+)+https?:?/?/?', 'https://', match_url)
    page = await context.new_page()
    try:
        await page.goto(match_url, wait_until="domcontentloaded", timeout=35000)
        try:
            await page.wait_for_selector(".smv__verticalSections", timeout=12000)
        except Exception:
            await page.wait_for_timeout(1000)

        # 1. Resumen
        html_resumen = await page.content()
        resumen_data = parse_resumen(html_resumen)

        # 2. Estadísticas (partido completo, 1T, 2T)
        stats_partido, stats_1t, stats_2t = {}, {}, {}
        btn_stats = page.locator("a[data-analytics-alias='match-statistics']")
        if await btn_stats.count() > 0:
            try:
                await btn_stats.first.click()
                await page.wait_for_selector(".statisticsContent", timeout=4000)
                stats_partido = parse_estadisticas(await page.content())

                # 1er tiempo
                btn_1t = page.locator("a[title='1er Tiempo']")
                if await btn_1t.count() > 0:
                    await btn_1t.first.click()
                    await page.wait_for_timeout(150)
                    stats_1t = parse_estadisticas(await page.content())

                # 2º tiempo
                btn_2t = page.locator("a[title='2º Tiempo']")
                if await btn_2t.count() > 0:
                    await btn_2t.first.click()
                    await page.wait_for_timeout(150)
                    stats_2t = parse_estadisticas(await page.content())
            except Exception:
                pass

        # 3. Alineaciones
        alineaciones_data = {}
        btn_lineups = page.locator("a[data-analytics-alias='lineups']")
        if await btn_lineups.count() > 0:
            try:
                await btn_lineups.first.click()
                await page.wait_for_selector("[data-testid='wcl-lineupsGroup'], .fp-fieldWrapper_-6T8g", timeout=4000)
                alineaciones_data = parse_alineaciones(await page.content())
            except Exception:
                pass

        # 4. Estadísticas de Jugadores
        jugadores_stats = {}
        btn_pstats = page.locator("a[data-analytics-alias='player-match-statistics']")
        if await btn_pstats.count() > 0:
            try:
                await btn_pstats.first.click()
                # Solo si el contenedor de estadísticas de jugadores existe y se despliega
                await page.wait_for_selector(".tabContent__player-match-statistics", timeout=3000)

                tabs = [
                    ('top_stats', 'principales'),
                    ('shots', 'remates'),
                    ('attack', 'ataque'),
                    ('passes', 'pases'),
                    ('defense', 'defensa'),
                    ('goalkeeping', 'paradas'),
                    ('general', 'general')
                ]
                for alias, label in tabs:
                    try:
                        tab_btn = page.locator(f"a[data-analytics-alias='{alias}']")
                        if await tab_btn.count() > 0:
                            await tab_btn.first.click(timeout=1500)
                            await page.wait_for_timeout(100)
                            jugadores_stats[label] = parse_jugadores_stats_table(await page.content())
                    except Exception:
                        pass
            except Exception:
                pass

        return {
            'partido_id': match_id,
            'url': match_url,
            'fecha_extraccion': datetime.datetime.now().isoformat(),
            'resumen': resumen_data,
            'estadisticas': {
                'partido_completo': stats_partido,
                '1er_tiempo': stats_1t,
                '2o_tiempo': stats_2t
            },
            'alineaciones': alineaciones_data,
            'estadisticas_jugadores': jugadores_stats
        }
    finally:
        await page.close()


def sync_global_checkpoints():
    try:
        with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT chk.competicion_id, c.nombre_flashscore, count(chk.partido_id)
                FROM checkpoints_detalles_partidos chk
                JOIN competiciones c ON chk.competicion_id = c.id
                WHERE chk.estado = 'completado'
                GROUP BY chk.competicion_id, c.nombre_flashscore
            """)
            comps = cur.fetchall()
            cur.execute("SELECT count(*) FROM checkpoints_detalles_partidos WHERE estado = 'completado'")
            tot_ok = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM checkpoints_detalles_partidos WHERE estado = 'error'")
            tot_err = cur.fetchone()[0]

        resumen_global = {
            'fecha_actualizacion': datetime.datetime.now().isoformat(),
            'total_partidos_completados': tot_ok,
            'total_partidos_error': tot_err,
            'total_competiciones_activas': len(comps),
            'competiciones': {
                slugify(cname): {
                    'competicion_id': cid,
                    'nombre': cname,
                    'procesados': cnt
                }
                for cid, cname, cnt in comps
            }
        }
        global_chk_file = os.path.join(DETALLES_DIR, 'checkpoints_detalles.json')
        with open(global_chk_file, 'w', encoding='utf-8') as f:
            json.dump(resumen_global, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


async def worker_loop(worker_id, queue, context, counter, total, force):
    """Bucle consumidor de cada worker paralelo."""
    while not queue.empty():
        try:
            m_id, comp_id, comp_name, m_link, chk_estado = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        if not force and chk_estado == 'completado':
            counter['omitidos'] += 1
            queue.task_done()
            continue

        comp_slug = slugify(comp_name)
        counter['procesando'] += 1
        current_idx = counter['procesando']

        t0 = time.perf_counter()
        try:
            data = await scrape_single_match_fast(context, m_link, m_id)
            json_path = await save_match_details_async(m_id, comp_id, comp_slug, data)
            elapsed = time.perf_counter() - t0
            counter['exitosos'] += 1
            print(f"[{current_idx}/{total} | W{worker_id}] OK: {m_id} ({comp_name}) en {elapsed:.2f}s -> {os.path.basename(json_path)}")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            counter['fallidos'] += 1
            print(f"[{current_idx}/{total} | W{worker_id}] ERROR {m_id} en {elapsed:.2f}s: {e}")
            await record_error_async(m_id, comp_id, e, comp_slug=comp_slug)
        finally:
            queue.task_done()


async def process_matches_parallel(matches, num_workers=4, force=False):
    total = len(matches)
    print(f"\n[*] Iniciando extracción optimizada de {total} partidos con {num_workers} workers paralelos...")

    queue = asyncio.Queue()
    for m in matches:
        queue.put_nowait(m)

    counter = {
        'procesando': 0,
        'exitosos': 0,
        'omitidos': 0,
        'fallidos': 0
    }

    t_start = time.perf_counter()

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await context.route("**/*", route_intercept)

        workers = [
            asyncio.create_task(worker_loop(w_id, queue, context, counter, total, force))
            for w_id in range(1, num_workers + 1)
        ]

        await asyncio.gather(*workers)
        await browser.close()

    total_time = time.perf_counter() - t_start
    sync_global_checkpoints()

    print("\n" + "=" * 60)
    print(" RESUMEN DE EXTRACCIÓN OPTIMIZADA")
    print("=" * 60)
    print(f" Total procesados con éxito: {counter['exitosos']}")
    print(f" Omitidos por checkpoint:    {counter['omitidos']}")
    print(f" Errores registrados:        {counter['fallidos']}")
    print(f" Tiempo total:               {total_time:.2f}s")
    if counter['exitosos'] > 0:
        print(f" Rendimiento promedio:       {total_time / counter['exitosos']:.2f}s por partido")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Extractor Optimizado de Detalles de Partidos (Playwright Paralelo)")
    parser.add_argument("--partido", type=str, help="ID o URL del partido específico a extraer")
    parser.add_argument("--competicion", type=str, help="ID o slug de la competición específica")
    parser.add_argument("--limit", type=int, default=None, help="Límite máximo de partidos a procesar")
    parser.add_argument("--workers", type=int, default=4, help="Número de workers paralelos (default: 4)")
    parser.add_argument("--force", action="store_true", help="Forzar re-descarga aunque esté completado")
    parser.add_argument("--status", action="store_true", help="Ver estado de avance de detalles")
    parser.add_argument("--todas", action="store_true", help="Procesar todas las competiciones (ignora filtro de 44 competiciones residuales)")
    parser.add_argument("--ruta-flashscore", action="store_true", default=True, help="Procesar únicamente las 44 competiciones asignadas a Flashscore (por defecto: True)")
    args = parser.parse_args()

    init_db_schema()

    if args.status:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM partidos WHERE tipo = 'resultado' AND link IS NOT NULL;")
            total_terminados = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM checkpoints_detalles_partidos WHERE estado = 'completado';")
            completados = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM checkpoints_detalles_partidos WHERE estado = 'error';")
            errores = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM partidos_detalles;")
            detalles_bd = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM partidos_incidentes;")
            incidentes_bd = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM partidos_estadisticas;")
            stats_bd = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM partidos_alineaciones;")
            alineaciones_bd = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM partidos_jugadores_stats;")
            pstats_bd = cur.fetchone()[0]

            # Estadísticas específicas del subconjunto residual de Flashscore (44 ligas)
            cur.execute("""
            SELECT count(p.id) 
            FROM partidos p
            JOIN competiciones_fotmob cf ON p.competicion_id = cf.competicion_id
            WHERE cf.ruta_optima = 'flashscore' AND p.tipo = 'resultado' AND p.link IS NOT NULL;
            """)
            fs_total = cur.fetchone()[0]
            cur.execute("""
            SELECT count(chk.partido_id) 
            FROM checkpoints_detalles_partidos chk
            JOIN competiciones_fotmob cf ON chk.competicion_id = cf.competicion_id
            WHERE cf.ruta_optima = 'flashscore' AND chk.estado = 'completado';
            """)
            fs_completados = cur.fetchone()[0]

            print("==================================================")
            print(" ESTADO DE DETALLES DE PARTIDOS (BETPLAY / FLASHSCORE)")
            print("==================================================")
            print(f"[REGLA 80/20] Competiciones Residuales Flashscore (44 ligas):")
            print(f"  • Total partidos finalizados:   {fs_total:,}")
            print(f"  • Partidos completados (DONE):  {fs_completados:,}")
            print(f"  • Partidos pendientes:          {max(0, fs_total - fs_completados):,}")
            print("--------------------------------------------------")
            print(f"[HISTÓRICO GLOBAL] Total catálogo (207 competiciones):")
            print(f"  • Total jugados con enlace:     {total_terminados:,}")
            pct = (completados / total_terminados * 100) if total_terminados else 0
            print(f"  • Partidos procesados en DB:    {completados:,} ({pct:.1f}%)")
            print(f"  • Partidos con error:           {errores:,}")
            print("--------------------------------------------------")
            print(f"Registros en 'partidos_detalles':        {detalles_bd:,}")
            print(f"Registros en 'partidos_incidentes':      {incidentes_bd:,}")
            print(f"Registros en 'partidos_estadisticas':    {stats_bd:,}")
            print(f"Registros en 'partidos_alineaciones':    {alineaciones_bd:,}")
            print(f"Registros en 'partidos_jugadores_stats': {pstats_bd:,}")
            print("==================================================")
            return

    # Consulta de partidos a procesar
    if args.partido:
        query = """
        SELECT p.id, p.competicion_id, c.nombre_flashscore, p.link, chk.estado
        FROM partidos p
        JOIN competiciones c ON p.competicion_id = c.id
        LEFT JOIN checkpoints_detalles_partidos chk ON p.id = chk.partido_id
        WHERE p.link IS NOT NULL
        """
        m_id = args.partido.strip()
        if 'mid=' in m_id:
            m_id = m_id.split('mid=')[-1].split('&')[0]
        query += " AND (p.id = ? OR p.link LIKE ?)"
        params = [m_id, f"%{m_id}%"]
    else:
        query = """
        SELECT p.id, p.competicion_id, c.nombre_flashscore, p.link, chk.estado
        FROM partidos p
        JOIN competiciones c ON p.competicion_id = c.id
        LEFT JOIN checkpoints_detalles_partidos chk ON p.id = chk.partido_id
        WHERE p.link IS NOT NULL AND p.tipo = 'resultado'
        """
        params = []
        # Por defecto, restringe estrictamente a las 44 ligas asignadas a Flashscore
        if not args.todas and not args.competicion:
            query += " AND c.id IN (SELECT competicion_id FROM competiciones_fotmob WHERE ruta_optima = 'flashscore')"
        if args.competicion:
            query += " AND (c.id = ? OR c.nombre_flashscore LIKE ? OR c.link_flashscore LIKE ?)"
            params.extend([args.competicion, f"%{args.competicion}%", f"%{args.competicion}%"])
        if not args.force:
            query += " AND (chk.estado IS NULL OR chk.estado != 'completado')"

    query += " ORDER BY p.fecha_hora DESC"

    if args.limit:
        query += f" LIMIT {args.limit}"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        matches = cur.fetchall()

    if not matches:
        print("\n[✓] Checkpoints al día: Todos los partidos ya se encuentran completados.")
        print("    No hay nuevos partidos finalizados pendientes de procesar para esta consulta.")
        return

    asyncio.run(process_matches_parallel(matches, num_workers=args.workers, force=args.force))


if __name__ == '__main__':
    main()
