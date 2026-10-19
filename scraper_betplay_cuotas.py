"""
Scraper Integral de Cuotas y Mercados de BetPlay (Sin Esports)
==============================================================
Extrae partidos, mercados y cuotas de fútbol real en BetPlay (Kambi API):
- Filtro estricto contra Esports, Cyber, FIFA, CLA, eBall y apuestas de ganador absoluto (outrights).
- Modos de extracción flexibles:
  * --hoy:       Partidos programados para el día de HOY (Hora Colombia).
  * --manana:    Partidos programados para el día de MAÑANA (Hora Colombia).
  * --semana:    Partidos programados para la SEMANA (próximos 7 días).
  * --dias N:    Partidos en el rango de los próximos N días.
  * --fecha:     Partidos para una fecha específica (YYYY-MM-DD).
  * --todos:     Todos los partidos disponibles en el feed de BetPlay.
- Clasificación canónica en las 9 categorías de mercados.
- Almacenamiento dual: JSON estructurado en disco y base de datos SQLite (betplay_flashscore.db).
- Trazabilidad histórica completa: preserva snapshots inmutables con timestamp.
- Cronómetro de alta precisión y cálculo automático de rendimiento (partidos/s).
- Sincronización automática con el Radar de Valor (analizador_betplay.py) y dashboards web.
"""

import os
import sys
import re
import json
import time
import sqlite3
import argparse
import shutil
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_OUTPUT_DIR = os.path.join(BASE_DIR, "betplay_cuotas")
DB_PATH = os.path.join(BASE_DIR, "betplay_flashscore.db")

COT = timezone(timedelta(hours=-5))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://betplay.com.co",
    "Referer": "https://betplay.com.co/",
    "Accept": "application/json, text/plain, */*"
}

KAMBI_BASE = "https://us.offering-api.kambicdn.com/offering/v2018/betplay"
FOOTBALL_GROUP_ID = 1000093190


def slugify(text: str) -> str:
    """Convierte texto en un slug seguro para nombres de carpetas."""
    if not text:
        return "desconocido"
    text = text.lower().strip()
    text = re.sub(r'[áàäâ]', 'a', text)
    text = re.sub(r'[éèëê]', 'e', text)
    text = re.sub(r'[íìïî]', 'i', text)
    text = re.sub(r'[óòöô]', 'o', text)
    text = re.sub(r'[úùüû]', 'u', text)
    text = re.sub(r'ñ', 'n', text)
    text = re.sub(r'[^a-z0-9_-]', '_', text)
    return re.sub(r'_+', '_', text).strip('_')


def is_esports(ev: dict) -> bool:
    """Detecta y descarta de forma estricta cualquier partido o evento de Esports o ligas virtuales."""
    path_names = [p.get("name", "").lower() for p in ev.get("path", [])]
    path_terms = [p.get("termKey", "").lower() for p in ev.get("path", [])]
    group = ev.get("group", "").lower()
    name = ev.get("name", "").lower()

    esports_keys = [
        "esports", "esport", "cyber", "cla", "2x5", "gt sports",
        "eball", "electronic", "fifa", "pes", "virtual", "battle"
    ]
    for k in esports_keys:
        if any(k in pn for pn in path_names) or any(k in pt for pt in path_terms) or k in group or k in name:
            return True
    return False


def get_colombia_date(iso_str: str) -> str:
    """Convierte un timestamp ISO UTC a fecha en Hora de Colombia (COT, UTC-5)."""
    if not iso_str:
        return ""
    try:
        clean_iso = iso_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_iso)
        dt_cot = dt_utc.astimezone(COT)
        return dt_cot.strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:10]


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


def init_betplay_db():
    """Inicializa las tablas e índices en SQLite asegurando trazabilidad histórica."""
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


def api_request(url: str, timeout: int = 12):
    """Petición GET a la API de Kambi."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def obtener_feed_futbol() -> list:
    """
    Obtiene la cartelera completa de partidos de fútbol desde Betplay.
    Primero consulta el endpoint de jerarquía completa (event/group/1000093190.json),
    y en caso de fallo recurre al listView general.
    """
    url_group = f"{KAMBI_BASE}/event/group/{FOOTBALL_GROUP_ID}.json?lang=es_CO&market=CO"
    data = api_request(url_group, timeout=15)
    if data and "events" in data:
        return data["events"]

    url_feed = f"{KAMBI_BASE}/listView/football.json?lang=es_CO&market=CO"
    data2 = api_request(url_feed, timeout=15)
    if data2 and "events" in data2:
        return [item.get("event", item) for item in data2["events"]]

    return []


def extraer_mercados_partido(ev_summary: dict) -> dict:
    """Extrae las cuotas completas de un partido desde Kambi y clasifica sus mercados."""
    eid = ev_summary["id"]
    url = f"{KAMBI_BASE}/betoffer/event/{eid}.json?channel_id=1&client_id=200&includeParticipants=true&lang=es_CO&market=CO&onlyMain=false"
    data = api_request(url)
    if not data:
        return None

    events = data.get("events", [])
    ev = events[0] if events else ev_summary
    bet_offers = data.get("betOffers", [])

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

    mercados_organizados = {}
    resumen_categorias = {}
    total_unicos = 0

    for cat_name, m_dict in categorizados.items():
        lista_m = list(m_dict.values())
        mercados_organizados[cat_name] = lista_m
        resumen_categorias[cat_name] = len(lista_m)
        total_unicos += len(lista_m)

    pais = ev_summary.get("pais", "Internacional")
    competicion = ev.get("group", ev_summary.get("competicion", ""))

    return {
        "partido_id": eid,
        "partido": ev.get("name", ev_summary.get("name")),
        "equipo_local": ev.get("homeName", ev_summary.get("home")),
        "equipo_visitante": ev.get("awayName", ev_summary.get("away")),
        "pais": pais,
        "competicion": competicion,
        "fecha_partido": ev.get("start", ev_summary.get("fecha")),
        "fecha_colombia": get_colombia_date(ev.get("start", ev_summary.get("fecha"))),
        "estado": ev.get("state", "NOT_STARTED"),
        "link_partido": f"https://betplay.com.co/apuestas#/event/{eid}",
        "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_mercados_unicos": total_unicos,
        "total_ofertas_kambi": len(bet_offers),
        "resumen_categorias": resumen_categorias,
        "mercados_por_categoria": mercados_organizados,
        "mercados_raw": mercados_raw
    }


def guardar_partido_en_disco_y_db(p_data: dict, conn: sqlite3.Connection, subcarpeta_modo: str = "general") -> int:
    """Guarda en JSON en disco y en SQLite con trazabilidad histórica inmutable."""
    pid = p_data["partido_id"]
    pais_s = slugify(p_data["pais"])
    comp_s = slugify(p_data["competicion"])
    fecha_extraccion = p_data.get("fecha_extraccion") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Guardar archivo JSON vigente y snapshot histórico
    subf = os.path.join(BASE_OUTPUT_DIR, subcarpeta_modo, pais_s, comp_s)
    os.makedirs(subf, exist_ok=True)
    json_path = os.path.join(subf, f"{pid}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(p_data, f, ensure_ascii=False, indent=2)

    hist_dir = os.path.join(subf, "historial")
    os.makedirs(hist_dir, exist_ok=True)
    t_slug = re.sub(r'[^0-9]', '_', fecha_extraccion).strip('_')
    hist_json_path = os.path.join(hist_dir, f"{pid}_{t_slug}.json")
    with open(hist_json_path, "w", encoding="utf-8") as f:
        json.dump(p_data, f, ensure_ascii=False, indent=2)

    # 2. Guardar en SQLite sin sobreescribir extracciones previas
    cur = conn.cursor()
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
        total_ofertas_kambi = excluded.total_ofertas_kambi
    """, (
        pid,
        p_data.get("partido"),
        p_data.get("equipo_local"),
        p_data.get("equipo_visitante"),
        p_data.get("pais"),
        p_data.get("competicion"),
        p_data.get("fecha_partido"),
        p_data.get("estado"),
        p_data.get("link_partido"),
        fecha_extraccion,
        p_data.get("total_mercados_unicos"),
        p_data.get("total_ofertas_kambi"),
        0.0
    ))

    # Trazabilidad total: limpia únicamente si ya existía una inserción con el MISMO timestamp
    cur.execute("DELETE FROM betplay_cuotas WHERE partido_id = ? AND fecha_extraccion = ?", (pid, fecha_extraccion))

    filas = []
    for m in p_data.get("mercados_raw", []):
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

    return len(filas)


def ejecutar_scraper_cuotas(
    modo: str = "manana",
    fecha_especifica: str = None,
    dias_adelante: int = 7,
    workers: int = 8,
    actualizar_radar: bool = True
):
    """
    Ejecuta el scraper masivo según el alcance temporal solicitado.
    
    Parámetros:
      - modo: 'hoy', 'manana', 'semana', 'dias', 'fecha', o 'todos'
      - fecha_especifica: 'YYYY-MM-DD' si modo es 'fecha'
      - dias_adelante: cantidad de días a cubrir si modo es 'dias' o 'semana'
      - workers: hilos concurrentes
      - actualizar_radar: si recalcula analizador_betplay.py y sincroniza dashboards
    """
    init_betplay_db()

    now_cot = datetime.now(COT)
    d_hoy = now_cot.strftime("%Y-%m-%d")
    d_manana = (now_cot + timedelta(days=1)).strftime("%Y-%m-%d")

    subcarpeta_modo = modo
    descripcion_filtro = ""

    if modo == "hoy":
        descripcion_filtro = f"Partidos de HOY ({d_hoy}) [Hora Colombia]"
        subcarpeta_modo = "hoy"
    elif modo == "manana":
        descripcion_filtro = f"Partidos de MAÑANA ({d_manana}) [Hora Colombia]"
        subcarpeta_modo = "manana"
    elif modo == "semana":
        d_fin = (now_cot + timedelta(days=7)).strftime("%Y-%m-%d")
        descripcion_filtro = f"Partidos de la SEMANA ({d_hoy} al {d_fin}) [Hora Colombia]"
        subcarpeta_modo = "semana"
    elif modo == "dias":
        d_fin = (now_cot + timedelta(days=dias_adelante)).strftime("%Y-%m-%d")
        descripcion_filtro = f"Partidos próximos {dias_adelante} días ({d_hoy} al {d_fin})"
        subcarpeta_modo = f"dias_{dias_adelante}"
    elif modo == "fecha":
        if not fecha_especifica:
            fecha_especifica = d_hoy
        descripcion_filtro = f"Partidos de fecha específica: {fecha_especifica}"
        subcarpeta_modo = f"fecha_{slugify(fecha_especifica)}"
    elif modo == "todos":
        descripcion_filtro = "TODOS los partidos disponibles en BetPlay (Sin filtro de fecha)"
        subcarpeta_modo = "todos"
    else:
        raise ValueError(f"Modo desconocido: {modo}")

    print("\n" + "=" * 75)
    print(f"      SCRAPER MASIVO DE CUOTAS Y MERCADOS BETPLAY (SIN ESPORTS)")
    print(f"      Alcance:      {descripcion_filtro}")
    print(f"      Concurrencia: {workers} workers en paralelo")
    print("=" * 75)

    t_inicio_total = time.perf_counter()

    # 1. Obtener la cartelera general
    print("[1/3] Conectando con la API de BetPlay y obteniendo cartelera...", end="", flush=True)
    t_feed_inicio = time.perf_counter()
    raw_events = obtener_feed_futbol()
    t_feed_fin = time.perf_counter()

    if not raw_events:
        print(" [!] Falló la conexión o no se recibieron eventos.")
        return

    print(f" OK! ({len(raw_events)} eventos recibidos en {(t_feed_fin - t_feed_inicio):.2f}s)")

    # 2. Filtrado riguroso
    print(f"[2/3] Filtrando fútbol real para '{modo}' (excluyendo estrictamente Esports y Outrights)...")
    partidos_objetivo = []
    esports_descartados = 0
    outrights_descartados = 0

    d_fin_semana = (now_cot + timedelta(days=7)).strftime("%Y-%m-%d")
    d_fin_dias = (now_cot + timedelta(days=dias_adelante)).strftime("%Y-%m-%d")

    for ev in raw_events:
        # Excluir Esports
        if is_esports(ev):
            esports_descartados += 1
            continue

        # Excluir eventos que no sean partidos mano a mano (outrights / ganador del torneo)
        home = ev.get("homeName")
        away = ev.get("awayName")
        if not home or not away:
            outrights_descartados += 1
            continue

        start_iso = ev.get("start", "")
        d_cot = get_colombia_date(start_iso)

        # Aplicar filtro según el modo
        incluir = False
        if modo == "hoy":
            incluir = (d_cot == d_hoy)
        elif modo == "manana":
            incluir = (d_cot == d_manana)
        elif modo == "semana":
            incluir = (d_hoy <= d_cot <= d_fin_semana)
        elif modo == "dias":
            incluir = (d_hoy <= d_cot <= d_fin_dias)
        elif modo == "fecha":
            incluir = (d_cot == fecha_especifica) or (fecha_especifica in start_iso)
        elif modo == "todos":
            incluir = True

        if not incluir:
            continue

        # Extraer país del path
        paths = ev.get("path", [])
        pais = "Internacional"
        for p in paths:
            t_key = p.get("termKey", "")
            if t_key != "football" and pais == "Internacional":
                pais = p.get("name", "Internacional")

        partidos_objetivo.append({
            "id": ev.get("id"),
            "name": ev.get("name"),
            "home": home,
            "away": away,
            "pais": pais,
            "competicion": ev.get("group", ""),
            "fecha": start_iso,
            "fecha_cot": d_cot
        })

    print(f"      - Esports / Cyber descartados:         {esports_descartados}")
    print(f"      - Outrights / Futuros descartados:     {outrights_descartados}")
    print(f"      - Partidos seleccionados para descarga: {len(partidos_objetivo)}")

    if not partidos_objetivo:
        print(f"[!] No hay partidos programados para el criterio seleccionado ({descripcion_filtro}).")
        return

    # 3. Descarga concurrente de mercados y cuotas
    print(f"\n[3/3] Descargando mercados y cuotas de {len(partidos_objetivo)} partidos...")
    t_descarga_inicio = time.perf_counter()

    resultados_exitosos = []
    conn = sqlite3.connect(DB_PATH)

    completados = 0
    total_cuotas_db = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futuros = {executor.submit(extraer_mercados_partido, p): p for p in partidos_objetivo}
        for fut in as_completed(futuros):
            completados += 1
            info = futuros[fut]
            try:
                p_data = fut.result()
                if p_data:
                    c_insertadas = guardar_partido_en_disco_y_db(p_data, conn, subcarpeta_modo)
                    total_cuotas_db += c_insertadas
                    resultados_exitosos.append(p_data)
                    print(f"  [{completados:>4}/{len(partidos_objetivo)}] OK #{p_data['partido_id']} {p_data['partido'][:42]:<42} ({p_data['total_mercados_unicos']} merc / {c_insertadas} cuotas)")
                else:
                    print(f"  [{completados:>4}/{len(partidos_objetivo)}] FAIL #{info['id']} {info['name'][:42]}")
            except Exception as e:
                print(f"  [{completados:>4}/{len(partidos_objetivo)}] ERR #{info['id']}: {e}")

    conn.commit()
    conn.close()

    t_fin_total = time.perf_counter()
    duracion_descarga_seg = t_fin_total - t_descarga_inicio
    duracion_total_seg = t_fin_total - t_inicio_total

    print("\n" + "=" * 75)
    print("               INFORME FINAL DEL CRONÓMETRO                  ")
    print("=" * 75)
    print(f" Alcance seleccionado:     {descripcion_filtro}")
    print(f" Partidos procesados:      {len(resultados_exitosos)} de {len(partidos_objetivo)}")
    print(f" Esports descartados:      {esports_descartados}")
    print(f" Cuotas totales en SQLite: {total_cuotas_db} cuotas insertadas en betplay_cuotas")
    print(f" Base de Datos SQLite:     {DB_PATH}")
    print(f" Archivos JSON guardados:  {os.path.join(BASE_OUTPUT_DIR, subcarpeta_modo)}")
    print("-" * 75)
    print(f" ⏱ TIEMPO TOTAL DEL SCRAPER: {duracion_total_seg:.2f} segundos ({duracion_total_seg * 1000:.0f} ms)")
    print(f"   ├─ Feed inicial Betplay:     {(t_feed_fin - t_feed_inicio):.2f} s")
    if duracion_descarga_seg > 0:
        rendimiento = len(resultados_exitosos) / duracion_descarga_seg
        print(f"   └─ Descarga concurrente:     {duracion_descarga_seg:.2f} s ({rendimiento:.1f} partidos/segundo)")
    print("=" * 75 + "\n")

    # 4. Sincronización automática de Radar y Catálogos de Eventos
    if actualizar_radar:
        try:
            print("[*] Actualizando Radar de Valor Betplay y catálogos de eventos...")
            from analizador_betplay import BetplayMarketPrioritizer
            prioritizer = BetplayMarketPrioritizer()
            try:
                prioritizer.run_analysis()
                print("  [✓] Radar de Valor recalculado y picks priorizados actualizados.")
            finally:
                prioritizer.close()

            # Sincronizar archivos a claude_index y view
            est_dir = os.path.join(BASE_DIR, 'estadisticas')
            fnames = [
                'betplay_eventos_resumen.js', 'betplay_eventos_resumen.json',
                'betplay_eventos_cuotas.js', 'betplay_eventos_cuotas.json',
                'betplay_picks_priorizados.js', 'betplay_picks_priorizados.json',
                'betplay_partidos_con_picks.js', 'betplay_partidos_con_picks.json'
            ]

            targets = ['claude_index', 'view']
            for tgt in targets:
                tgt_dir = os.path.join(BASE_DIR, tgt)
                if os.path.exists(tgt_dir):
                    copiados = 0
                    for fname in fnames:
                        src = os.path.join(est_dir, fname)
                        dst = os.path.join(tgt_dir, fname)
                        if os.path.exists(src):
                            shutil.copy2(src, dst)
                            copiados += 1
                    print(f"  [✓] {copiados} archivos sincronizados con '{tgt}/'.")

        except Exception as e:
            print(f"  [!] Advertencia al regenerar el radar: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Scraper masivo de cuotas y mercados de fútbol en BetPlay (sin Esports)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--hoy", action="store_true", help="Descargar cuotas de partidos de HOY (Hora Colombia)")
    group.add_argument("--manana", action="store_true", help="Descargar cuotas de partidos de MAÑANA (Hora Colombia)")
    group.add_argument("--semana", action="store_true", help="Descargar cuotas de la SEMANA (próximos 7 días)")
    group.add_argument("--todos", action="store_true", help="Descargar TODOS los partidos disponibles en BetPlay")
    group.add_argument("--dias", type=int, help="Descargar cuotas de los próximos N días")
    group.add_argument("--fecha", type=str, help="Descargar cuotas de una fecha puntual (YYYY-MM-DD)")

    parser.add_argument("--workers", type=int, default=8, help="Número de hilos concurrentes (por defecto 8)")
    parser.add_argument("--no-radar", action="store_true", help="Omitir recálculo del Radar de Valor al finalizar")

    args = parser.parse_args()

    modo = "manana"
    f_esp = None
    dias = 7

    if args.hoy:
        modo = "hoy"
    elif args.manana:
        modo = "manana"
    elif args.semana:
        modo = "semana"
    elif args.todos:
        modo = "todos"
    elif args.dias:
        modo = "dias"
        dias = args.dias
    elif args.fecha:
        modo = "fecha"
        f_esp = args.fecha

    ejecutar_scraper_cuotas(
        modo=modo,
        fecha_especifica=f_esp,
        dias_adelante=dias,
        workers=args.workers,
        actualizar_radar=not args.no_radar
    )


if __name__ == "__main__":
    main()
