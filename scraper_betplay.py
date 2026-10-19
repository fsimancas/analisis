"""
Scraper de Mercados y Cuotas de BetPlay (Kambi Sportsbook)
==========================================================
Extrae todos los partidos, mercados y cuotas de BetPlay:
- Extrae la totalidad de los mercados (1X2, Hándicap, Over/Under, Ambos Marcan, etc.)
- Registra fecha y hora exacta de extracción
- Genera el enlace directo a cada partido (https://betplay.com.co/apuestas#/event/{id})
- Soporta las competiciones definidas en codigo.md
- Modos: Extracción API ultra-rápida (por defecto) o Automatización Playwright Browser (--browser)
"""

import os
import sys
import re
import json
import time
import argparse
import urllib.request
import urllib.error
import sqlite3
from datetime import datetime
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CODIGO_MD_PATH = os.path.join(BASE_DIR, "codigo.md")
OUTPUT_DIR = os.path.join(BASE_DIR, "betplay_cuotas")
DB_PATH = os.path.join(BASE_DIR, "betplay_flashscore.db")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://betplay.com.co",
    "Referer": "https://betplay.com.co/",
    "Accept": "application/json, text/plain, */*"
}

KAMBI_BASE = "https://us.offering-api.kambicdn.com/offering/v2018/betplay"


def slugify(text: str) -> str:
    """Convierte texto en un slug seguro para nombres de carpetas."""
    text = text.lower().strip()
    text = re.sub(r'[áàäâ]', 'a', text)
    text = re.sub(r'[éèëê]', 'e', text)
    text = re.sub(r'[íìïî]', 'i', text)
    text = re.sub(r'[óòöô]', 'o', text)
    text = re.sub(r'[úùüû]', 'u', text)
    text = re.sub(r'ñ', 'n', text)
    text = re.sub(r'[^a-z0-9_-]', '_', text)
    return re.sub(r'_+', '_', text).strip('_')


def cargar_competiciones_de_codigo_md() -> list:
    """Lee codigo.md y extrae la lista de países y competiciones con sus URLs y slugs."""
    if not os.path.exists(CODIGO_MD_PATH):
        print(f"[!] No se encontró el archivo: {CODIGO_MD_PATH}")
        return []

    with open(CODIGO_MD_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    competitions = []
    blocks = soup.find_all("div", class_="sc-jGKxIK")

    for b in blocks:
        # Extraer nombre del país
        c_div = b.find("div", class_="sc-jxOSlx")
        country = c_div.get_text(strip=True) if c_div else "Internacional"

        # Extraer sub-ligas
        for sl in b.find_all("li", class_="sc-fTFjTM"):
            a = sl.find("a")
            if not a or not a.get("href"):
                continue
            href = a["href"]
            name_div = sl.find("div", class_="sc-jxOSlx")
            name = name_div.get_text(strip=True) if name_div else ""

            match = re.search(r"football/(.*)$", href)
            slug = match.group(1).rstrip("/") if match else ""

            competitions.append({
                "pais": country,
                "competicion": name,
                "url": href,
                "slug": slug,
                "pais_slug": slugify(country),
                "competicion_slug": slugify(name)
            })

    return competitions


def api_request(url: str):
    """Realiza una petición GET al endpoint de Kambi."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  [!] HTTP Error {e.code} en {url}")
        return None
    except Exception as e:
        print(f"  [!] Error de conexión: {e}")
        return None


def obtener_partidos_competicion(slug: str) -> list:
    """
    Obtiene la lista de eventos/partidos activos para un slug de competición.
    Prueba formato jerárquico ('.../all/matches.json') y de nivel superior ('.../all/all/matches.json').
    """
    # Variante 1: formato con país/liga (ej. germany/bundesliga)
    url1 = f"{KAMBI_BASE}/listView/football/{slug}/all/matches.json?channel_id=1&client_id=200&lang=es_CO&market=CO&useCombined=true"
    data = api_request(url1)
    if data and "events" in data:
        return data["events"]

    # Variante 2: formato top-level o internacional (ej. champions_league)
    url2 = f"{KAMBI_BASE}/listView/football/{slug}/all/all/matches.json?channel_id=1&client_id=200&lang=es_CO&market=CO&useCombined=true"
    data2 = api_request(url2)
    if data2 and "events" in data2:
        return data2["events"]

    return []


def clasificar_mercado(nombre: str, tipo: str, ocurrencia: str) -> str:
    """Clasifica un mercado en una de las 9 categorías estándar."""
    n = nombre.lower()
    
    if "intervalo" in n or re.search(r"\d+:\d+-\d+:\d+", n):
        return "7. Mercados por intervalos de tiempo"
    if "tiro de esquina" in n or "tiros de esquina" in n or ocurrencia == "CORNERS":
        return "6. Mercados de tiros de esquina"
    if "falta" in n or "fuera de juego" in n or ocurrencia in ["FOULS", "OFFSIDES"]:
        return "8. Mercados de faltas y fuera de juego"
    if "paradas del portero" in n or "portero" in n or ocurrencia == "SAVES":
        return "4. Mercados de porteros"
    if ("tiro" in n or "disparo" in n) and "jugador" not in n and "esquina" not in n:
        return "5. Mercados de tiros y tiros a puerta"
    if any(k in n for k in ["anotará", "anotador", "marca al", "jugador", "asistencia", "recibe una tarjeta", "marca o recibe", "disparos del jugador", "disparos a puerta del jugador"]):
        return "3. Mercados de goleadores y jugadores"
    if any(k in n for k in ["gol", "goles", "ambos equipos", "marcarán", "sin recibir goles", "propia meta"]) and not any(k in n for k in ["hándicap", "primer gol (empate", "tiempo reglamentario"]):
        return "2. Mercados de goles"
    if any(k in n for k in ["resultado", "ganador", "doble oportunidad", "apuesta sin empate", "descanso", "2ª parte", "hándicap", "al menos una parte", "primer gol", "tiempo reglamentario", "asiático"]):
        return "1. Resultado del partido y ganador"
    return "9. Otros mercados"


def extraer_mercados_de_partido(event_id: int) -> dict:
    """
    Extrae todos los mercados y cuotas para un partido específico usando el endpoint de betoffer,
    agrupándolos y clasificándolos en las 9 categorías estándar sin duplicados.
    """
    url = f"{KAMBI_BASE}/betoffer/event/{event_id}.json?channel_id=1&client_id=200&includeParticipants=true&lang=es_CO&market=CO&onlyMain=false"
    data = api_request(url)
    if not data:
        return {}

    events = data.get("events", [])
    ev = events[0] if events else {}
    bet_offers = data.get("betOffers", [])

    extraction_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Extraer país y liga de la jerarquía de paths
    paths = ev.get("path", [])
    pais = "Desconocido"
    competicion = ev.get("group", "")
    for p in paths:
        t_key = p.get("termKey", "")
        if t_key != "football" and pais == "Desconocido":
            pais = p.get("name", "")
        elif t_key != "football" and not competicion:
            competicion = p.get("name", "")

    # Agrupar ofertas por mercado único y por categoría
    categorizados = {
        "1. Resultado del partido y ganador": {},
        "2. Mercados de goles": {},
        "3. Mercados de goleadores y jugadores": {},
        "4. Mercados de porteros": {},
        "5. Mercados de tiros y tiros a puerta": {},
        "6. Mercados de tiros de esquina": {},
        "7. Mercados por intervalos de tiempo": {},
        "8. Mercados de faltas y fuera de juego": {},
        "9. Otros mercados": {}
    }

    mercados_raw = []

    for bo in bet_offers:
        crit = bo.get("criterion", {})
        m_name = crit.get("label", "Sin Nombre").strip()
        bo_type = bo.get("betOfferType", {}).get("name", "")
        lifetime = crit.get("lifetime", "")
        occurrence = crit.get("occurrenceType", "")

        cat = clasificar_mercado(m_name, bo_type, occurrence)

        outcomes = []
        for o in bo.get("outcomes", []):
            raw_odds = o.get("odds", 0)
            dec_odds = round(raw_odds / 1000.0, 2) if raw_odds else None

            line = o.get("line")
            line_val = (line / 1000.0) if line is not None else None

            item = {
                "opcion": o.get("label", ""),
                "cuota": dec_odds
            }
            if line_val is not None:
                item["linea"] = line_val
            if o.get("participant"):
                item["participante"] = o.get("participant")

            outcomes.append(item)

        mercados_raw.append({
            "mercado_id": bo.get("id"),
            "mercado": m_name,
            "categoria": cat,
            "tipo": bo_type,
            "fase": lifetime,
            "tipo_suceso": occurrence,
            "cuotas": outcomes
        })

        # Estructuración agrupada sin duplicados por nombre de mercado
        cat_dict = categorizados[cat]
        if m_name not in cat_dict:
            cat_dict[m_name] = {
                "mercado": m_name,
                "tipo": bo_type,
                "fase": lifetime,
                "lineas_o_selecciones": []
            }

        cat_dict[m_name]["lineas_o_selecciones"].append({
            "mercado_id": bo.get("id"),
            "cuotas": outcomes
        })

    # Convertir los diccionarios de categorías en listas ordenadas
    mercados_organizados = {}
    resumen_categorias = {}
    total_unicos = 0

    for cat_name, m_dict in categorizados.items():
        lista_m = list(m_dict.values())
        mercados_organizados[cat_name] = lista_m
        resumen_categorias[cat_name] = len(lista_m)
        total_unicos += len(lista_m)

    partido_data = {
        "partido_id": event_id,
        "partido": ev.get("name", ""),
        "equipo_local": ev.get("homeName", ""),
        "equipo_visitante": ev.get("awayName", ""),
        "pais": pais,
        "competicion": competicion or ev.get("group", ""),
        "fecha_partido": ev.get("start", ""),
        "estado": ev.get("state", "NOT_STARTED"),
        "link_partido": f"https://betplay.com.co/apuestas#/event/{event_id}",
        "fecha_extraccion": extraction_time,
        "total_mercados_unicos": total_unicos,
        "total_ofertas_kambi": len(bet_offers),
        "resumen_categorias": resumen_categorias,
        "mercados_por_categoria": mercados_organizados,
        "mercados_raw": mercados_raw
    }

    return partido_data


def guardar_partido(partido_data: dict, subfolder: str = ""):
    """Guarda los datos del partido con sus mercados y cuotas en formato JSON y preserva historial."""
    if not partido_data or not partido_data.get("partido_id"):
        return

    pid = partido_data["partido_id"]
    save_dir = os.path.join(OUTPUT_DIR, subfolder) if subfolder else OUTPUT_DIR
    os.makedirs(save_dir, exist_ok=True)

    # 1. Guardar archivo principal (último estado vigente)
    filename = f"{pid}.json"
    filepath = os.path.join(save_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(partido_data, f, ensure_ascii=False, indent=2)

    # 2. Guardar snapshot histórico inmutable para trazabilidad y evolución
    f_extraccion = partido_data.get("fecha_extraccion", "")
    if f_extraccion:
        hist_dir = os.path.join(save_dir, "historial")
        os.makedirs(hist_dir, exist_ok=True)
        t_slug = re.sub(r'[^0-9]', '_', f_extraccion).strip('_')
        hist_filepath = os.path.join(hist_dir, f"{pid}_{t_slug}.json")
        with open(hist_filepath, "w", encoding="utf-8") as f:
            json.dump(partido_data, f, ensure_ascii=False, indent=2)

    return filepath


def init_betplay_db():
    """Crea las tablas de cuotas y partidos de BetPlay en SQLite con soporte de trazabilidad."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS betplay_partidos (
        id INTEGER PRIMARY KEY,
        partido TEXT NOT NULL,
        equipo_local TEXT NOT NULL,
        equipo_visitante TEXT NOT NULL,
        pais TEXT,
        competicion TEXT,
        fecha_partido TEXT,
        estado TEXT,
        link TEXT,
        fecha_extraccion TEXT,
        total_mercados_unicos INTEGER,
        total_ofertas_kambi INTEGER,
        duracion_extraccion_ms REAL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS betplay_cuotas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partido_id INTEGER NOT NULL,
        categoria TEXT NOT NULL,
        mercado TEXT NOT NULL,
        tipo TEXT,
        opcion TEXT NOT NULL,
        cuota REAL,
        linea REAL,
        participante TEXT,
        kambi_betoffer_id INTEGER,
        fecha_extraccion TEXT,
        FOREIGN KEY (partido_id) REFERENCES betplay_partidos(id) ON DELETE CASCADE
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_betplay_cuotas_partido ON betplay_cuotas (partido_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_betplay_cuotas_mercado ON betplay_cuotas (mercado)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_betplay_cuotas_categoria ON betplay_cuotas (categoria)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_betplay_cuotas_partido_fecha ON betplay_cuotas (partido_id, fecha_extraccion)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_betplay_cuotas_mercado_opcion ON betplay_cuotas (partido_id, mercado, opcion, linea)")
    
    # Vista para consultar rápidamente la última foto de cuotas de cada partido
    cur.execute("""
    CREATE VIEW IF NOT EXISTS betplay_cuotas_actuales AS
    SELECT bc.*
    FROM betplay_cuotas bc
    JOIN (
        SELECT partido_id, MAX(fecha_extraccion) AS max_fecha
        FROM betplay_cuotas
        GROUP BY partido_id
    ) ult ON bc.partido_id = ult.partido_id AND bc.fecha_extraccion = ult.max_fecha;
    """)

    conn.commit()
    conn.close()


def guardar_partido_en_db(partido_data: dict, duracion_ms: float = 0.0) -> int:
    """Inserta partido y sus cuotas preservando el historial de extracciones en SQLite."""
    if not partido_data or not partido_data.get("partido_id"):
        return 0

    init_betplay_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    pid = partido_data["partido_id"]
    fecha_extraccion = partido_data.get("fecha_extraccion") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
    INSERT INTO betplay_partidos (
        id, partido, equipo_local, equipo_visitante, pais, competicion,
        fecha_partido, estado, link, fecha_extraccion,
        total_mercados_unicos, total_ofertas_kambi, duracion_extraccion_ms
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        partido = excluded.partido,
        equipo_local = excluded.equipo_local,
        equipo_visitante = excluded.equipo_visitante,
        fecha_partido = excluded.fecha_partido,
        estado = excluded.estado,
        fecha_extraccion = excluded.fecha_extraccion,
        total_mercados_unicos = excluded.total_mercados_unicos,
        total_ofertas_kambi = excluded.total_ofertas_kambi,
        duracion_extraccion_ms = excluded.duracion_extraccion_ms
    """, (
        pid,
        partido_data.get("partido"),
        partido_data.get("equipo_local"),
        partido_data.get("equipo_visitante"),
        partido_data.get("pais"),
        partido_data.get("competicion"),
        partido_data.get("fecha_partido"),
        partido_data.get("estado"),
        partido_data.get("link_partido"),
        fecha_extraccion,
        partido_data.get("total_mercados_unicos"),
        partido_data.get("total_ofertas_kambi"),
        round(duracion_ms, 2)
    ))

    # Trazabilidad total: NO eliminamos cuotas de extracciones pasadas.
    # Solo limpiamos si ya existía una inserción para este MISMO timestamp (idempotencia en reintentos inmediatos).
    cur.execute("DELETE FROM betplay_cuotas WHERE partido_id = ? AND fecha_extraccion = ?", (pid, fecha_extraccion))

    filas = []
    for m in partido_data.get("mercados_raw", []):
        cat = m.get("categoria", "")
        mercado = m.get("mercado", "")
        tipo = m.get("tipo", "")
        bo_id = m.get("mercado_id")
        for c in m.get("cuotas", []):
            filas.append((
                pid,
                cat,
                mercado,
                tipo,
                c.get("opcion", ""),
                c.get("cuota"),
                c.get("linea"),
                c.get("participante"),
                bo_id,
                fecha_extraccion
            ))

    cur.executemany("""
    INSERT INTO betplay_cuotas (
        partido_id, categoria, mercado, tipo, opcion, cuota, linea, participante, kambi_betoffer_id, fecha_extraccion
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, filas)

    conn.commit()
    conn.close()
    return len(filas)


def raspar_partido_con_cronometro(event_id: int) -> tuple:
    """
    Ejecuta el scraper midiendo con alta precisión (time.perf_counter)
    el tiempo total transcurrido desde el inicio hasta el guardado en JSON y SQLite.
    """
    print(f"\n[⏱] INICIANDO SCRAPER DE BETPLAY PARA EL PARTIDO #{event_id}...")
    t_inicio = time.perf_counter()

    # 1. Extracción de cuotas y mercados vía Kambi REST
    p_data = extraer_mercados_de_partido(event_id)
    if not p_data:
        print("[!] No se obtuvieron datos para el partido.")
        return None, 0.0

    t_extraccion = time.perf_counter()
    duracion_extraccion_ms = (t_extraccion - t_inicio) * 1000

    # 2. Guardado en JSON
    subf = os.path.join(slugify(p_data["pais"]), slugify(p_data["competicion"]), "partidos")
    saved_json = guardar_partido(p_data, subfolder=subf)
    # También guardamos una copia en partidos_individuales
    guardar_partido(p_data, subfolder="partidos_individuales")

    # 3. Guardado en SQLite (betplay_partidos y betplay_cuotas)
    cuotas_insertadas = guardar_partido_en_db(p_data, duracion_extraccion_ms)

    t_fin = time.perf_counter()
    duracion_total_seg = t_fin - t_inicio
    duracion_total_ms = duracion_total_seg * 1000
    duracion_escritura_ms = (t_fin - t_extraccion) * 1000

    print("\n" + "=" * 68)
    print("           CRONÓMETRO Y RESUMEN DE EXTRACCIÓN (BETPLAY)        ")
    print("=" * 68)
    print(f" Partido:               {p_data['partido']}")
    print(f" Competición:           [{p_data['pais']}] {p_data['competicion']}")
    print(f" Fecha del evento:      {p_data['fecha_partido']}")
    print(f" Link oficial:          {p_data['link_partido']}")
    print(f" Fecha/hora extracción: {p_data['fecha_extraccion']}")
    print(f" Mercados únicos:       {p_data['total_mercados_unicos']} mercados clasificados")
    print(f" Líneas totales Kambi:  {p_data['total_ofertas_kambi']}")
    print(f" Registros en SQLite:   {cuotas_insertadas} cuotas insertadas en DB")
    print(f" Archivo JSON:          {saved_json}")
    print(f" Base de Datos SQLite:  {DB_PATH}")
    print("-" * 68)
    print(" DESGLOSE DE MERCADOS POR CATEGORÍA:")
    for cat, cant in p_data["resumen_categorias"].items():
        print(f"   * {cat:<40}: {cant} mercados")
    print("-" * 68)
    print(f" ⏱ TIEMPO TOTAL DEL SCRAPER: {duracion_total_seg:.4f} s ({duracion_total_ms:.2f} ms)")
    print(f"   ├─ Petición Kambi + Parseo: {duracion_extraccion_ms:.2f} ms")
    print(f"   └─ Almacenamiento JSON + DB: {duracion_escritura_ms:.2f} ms")
    print("=" * 68 + "\n")

    return p_data, duracion_total_seg


def procesar_competicion(comp_info: dict, guardar_individuales: bool = True) -> list:
    """Procesa todos los partidos y mercados de una competición."""
    slug = comp_info["slug"]
    nombre = comp_info["competicion"]
    pais = comp_info["pais"]

    print(f"\n[+] Competición: [{pais}] {nombre} (slug: {slug})")
    events = obtener_partidos_competicion(slug)

    if not events:
        print(f"    (-) No hay partidos disponibles o abiertos en BetPlay en este momento.")
        return []

    print(f"    (i) Partidos encontrados: {len(events)}")
    comp_matches = []

    subfolder = os.path.join(slugify(pais), slugify(nombre))

    for item in events:
        ev = item.get("event", {})
        eid = ev.get("id")
        if not eid:
            continue

        match_name = ev.get("name", "Desconocido")
        print(f"    --> Obteniendo mercados: #{eid} {match_name}...", end="", flush=True)

        match_data = extraer_mercados_de_partido(eid)
        if match_data:
            match_data["pais"] = pais
            match_data["competicion"] = nombre
            m_count = match_data["total_mercados"]
            print(f" OK! ({m_count} mercados)")

            if guardar_individuales:
                guardar_partido(match_data, subfolder=os.path.join(subfolder, "partidos"))

            comp_matches.append(match_data)
        else:
            print(" Falló / Sin cuotas")

        time.sleep(0.15)  # Respetar rate limiting

    # Guardar resumen de la competición
    comp_file = os.path.join(OUTPUT_DIR, subfolder, f"{slugify(nombre)}_todos.json")
    os.makedirs(os.path.dirname(comp_file), exist_ok=True)
    with open(comp_file, "w", encoding="utf-8") as f:
        json.dump({
            "pais": pais,
            "competicion": nombre,
            "slug": slug,
            "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_partidos": len(comp_matches),
            "partidos": comp_matches
        }, f, ensure_ascii=False, indent=2)

    print(f"    [v] Guardado archivo consolidado: {comp_file}")
    return comp_matches


def ejecutar_modo_browser(url_objetivo: str = None):
    """
    Ejecuta el flujo visual paso a paso mediante Playwright:
    Paso 1: Va a https://betplay.com.co/apuestas#sports-hub/football
    Paso 2: Clic en tab 'A-Z Fútbol' (#all-button)
    Paso 3: Navega a la competición o partido
    Paso 4: Extrae mercados interceptando o renderizando
    """
    from playwright.sync_api import sync_playwright

    print("\n[+] Iniciando Modo Browser (Playwright con Microsoft Edge)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        print("[Paso 1] Navegando a https://betplay.com.co/apuestas#sports-hub/football ...")
        page.goto("https://betplay.com.co/apuestas#sports-hub/football", timeout=45000)
        page.wait_for_timeout(3000)

        print("[Paso 2] Buscando botón 'A-Z Fútbol' (#all-button)...")
        try:
            page.wait_for_selector("#all-button, [aria-label='A-Z Fútbol']", timeout=10000)
            btn = page.query_selector("#all-button") or page.query_selector("[aria-label='A-Z Fútbol']")
            if btn:
                btn.click()
                print("         -> Clic realizado en 'A-Z Fútbol'!")
                page.wait_for_timeout(2000)
        except Exception as e:
            print(f"         (!) Error al hacer clic en A-Z: {e}")

        if url_objetivo:
            print(f"[Paso 3 y 4] Navegando a la competición objetivo: {url_objetivo} ...")
            page.goto(url_objetivo, timeout=45000)
            page.wait_for_timeout(4000)

        print("[*] Proceso browser completado. Cerrando navegador.")
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="Scraper de Partidos, Mercados y Cuotas de BetPlay")
    parser.add_argument("--competicion", type=str, help="Nombre o slug de la competición (ej. bundesliga, la_liga, liga_betplay_dimayor)")
    parser.add_argument("--pais", type=str, help="Nombre o slug del país (ej. alemania, colombia, espana)")
    parser.add_argument("--partido", type=str, help="ID o URL del partido de BetPlay (ej. 1028209215 o https://betplay.com.co/apuestas#/event/1028209215)")
    parser.add_argument("--buscar", type=str, help="Busca partidos por nombre de equipo en BetPlay y ejecuta el cronómetro (ej. 'Deportivo' o 'Levante')")
    parser.add_argument("--all", action="store_true", help="Descarga todos los partidos y mercados de todas las competiciones de codigo.md")
    parser.add_argument("--list", action="store_true", help="Lista todas las competiciones disponibles en codigo.md")
    parser.add_argument("--browser", action="store_true", help="Ejecuta la automatización visual con Playwright paso a paso")

    args = parser.parse_args()

    # Si se pide listar competiciones
    if args.list:
        comps = cargar_competiciones_de_codigo_md()
        print(f"\nTotal competiciones registradas en codigo.md: {len(comps)}\n")
        print(f"{'País':<25} | {'Competición':<35} | {'Slug Kambi'}")
        print("-" * 85)
        for c in comps:
            print(f"{c['pais']:<25} | {c['competicion']:<35} | {c['slug']}")
        return

    # Si se pide buscar un partido por nombre de equipo
    if args.buscar:
        q = args.buscar.lower().strip()
        print(f"\n[+] Buscando partidos activos con '{args.buscar}' en BetPlay...")
        comps = cargar_competiciones_de_codigo_md()
        coincidentes = []
        # Buscar en ligas prioritarias (España, Colombia, etc.)
        prioritarias = [c for c in comps if "spain" in c["slug"] or "colombia" in c["slug"]] + comps
        vistos_slugs = set()
        for c in prioritarias:
            slug = c["slug"]
            if slug in vistos_slugs:
                continue
            vistos_slugs.add(slug)
            events = obtener_partidos_competicion(slug)
            for it in events:
                ev = it.get("event", {})
                name = ev.get("name", "")
                if q in name.lower() or q in ev.get("homeName", "").lower() or q in ev.get("awayName", "").lower():
                    eid = ev.get("id")
                    if not any(x["id"] == eid for x in coincidentes):
                        coincidentes.append({
                            "id": eid,
                            "name": name,
                            "pais": c["pais"],
                            "competicion": c["competicion"],
                            "fecha": ev.get("start")
                        })
            if len(coincidentes) >= 5:
                break

        if not coincidentes:
            print(f"(-) No se encontraron partidos con '{args.buscar}'.")
            return

        print(f"\nPartidos encontrados:")
        for i, m in enumerate(coincidentes, 1):
            print(f"  [{i}] #{m['id']} {m['name']} ({m['pais']} - {m['competicion']}) @ {m['fecha']}")

        elegido = coincidentes[0]
        print(f"\n[+] Procesando primer resultado: {elegido['name']} (#{elegido['id']})...")
        raspar_partido_con_cronometro(elegido["id"])
        return

    # Si se pide un partido puntual
    if args.partido:
        match_id = re.search(r"(\d{7,})", args.partido)
        if not match_id:
            print(f"[!] No se pudo extraer un ID numérico de: {args.partido}")
            return
        eid = int(match_id.group(1))
        raspar_partido_con_cronometro(eid)
        return

    # Si se pide el modo browser visual
    if args.browser:
        target_url = None
        if args.competicion:
            comps = cargar_competiciones_de_codigo_md()
            query = args.competicion.lower()
            found = [c for c in comps if query in c["slug"].lower() or query in c["competicion"].lower()]
            if found:
                target_url = found[0]["url"]
        ejecutar_modo_browser(target_url)
        return

    # Si se pide por país
    comps = cargar_competiciones_de_codigo_md()
    if args.pais:
        query = slugify(args.pais)
        filtradas = [c for c in comps if query in c["pais_slug"] or query in slugify(c["pais"])]
        if not filtradas:
            print(f"[!] No se encontraron competiciones para el país: '{args.pais}'")
            return
        print(f"\n[+] Se encontraron {len(filtradas)} competiciones para '{args.pais}':")
        for c in filtradas:
            procesar_competicion(c)
        return

    # Si se pide por competición
    if args.competicion:
        query = args.competicion.lower()
        filtradas = [c for c in comps if query in c["slug"].lower() or query in c["competicion"].lower() or query in c["competicion_slug"].lower()]
        if not filtradas:
            print(f"[!] No se encontró ninguna competición coincidente con: '{args.competicion}'")
            return
        for c in filtradas:
            procesar_competicion(c)
        return

    # Si se pide descargar todo
    if args.all:
        print(f"\n[+] Procesando las {len(comps)} competiciones de codigo.md...")
        total_p = 0
        for i, c in enumerate(comps, 1):
            print(f"\n[{i}/{len(comps)}]", end=" ")
            partidos = procesar_competicion(c)
            total_p += len(partidos)
        print(f"\n=======================================================")
        print(f" Extracción finalizada. Total partidos procesados: {total_p}")
        print(f" Archivos guardados en: {OUTPUT_DIR}")
        print(f"=======================================================")
        return

    # Si se ejecuta sin argumentos, mostrar ayuda y un ejemplo funcional con la Bundesliga
    print("\n" + "=" * 65)
    print("      SCRAPER DE MERCADOS Y CUOTAS BETPLAY (KAMBI ENGINE)     ")
    print("=" * 65)
    print("Uso:")
    print("  python scraper_betplay.py --competicion bundesliga")
    print("  python scraper_betplay.py --competicion liga_betplay_dimayor")
    print("  python scraper_betplay.py --pais alemania")
    print("  python scraper_betplay.py --partido 1028230634")
    print("  python scraper_betplay.py --list")
    print("  python scraper_betplay.py --all")
    print("  python scraper_betplay.py --browser --competicion bundesliga")
    print("-" * 65)
    print("\nEjecutando demostración inmediata con la Bundesliga (Alemania)...")
    bundesliga = next((c for c in comps if "bundesliga" in c["slug"] and "germany" in c["slug"]), None)
    if bundesliga:
        procesar_competicion(bundesliga)


if __name__ == "__main__":
    main()
