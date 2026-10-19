"""
Scraper FotMob - Integración Relacional con Betplay y Flashscore
==============================================================
Arquitectura de extracción directa vía API de datos de FotMob.
Filtra estrictamente las competiciones cubiertas por Betplay y Flashscore,
asociando países, ligas, jornadas (rounds), partidos y sus estadísticas completas:
- Árbitro (promedio amarillas, faltas, rojas, penales)
- Estadio (nombre, ciudad, capacidad, aforo real, superficie/césped)
- Clima (temperatura, condición meteorológica)
- Momentum, eventos y estadísticas por periodo (All, FirstHalf, SecondHalf)
- xG (Expected Goals), xGOT y tiros espaciales con coordenadas métricas
- Alineaciones, entrenadores, suplentes y jugadores no disponibles
- Mapas de calor (Heatmaps) vectoriales por jugador (coordenadas x, y)
- Checkpoints para reanudar sin duplicar y modo incremental
"""

import os
import re
import json
import sqlite3
import unicodedata
import urllib.request
import gzip
import time
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "betplay_flashscore.db")
ALL_LEAGUES_CACHE = os.path.join(BASE_DIR, "all_leagues_fotmob.json")
OUTPUT_MAPPING_JSON = os.path.join(BASE_DIR, "competiciones_betplay_flashscore_fotmob.json")
FOTMOB_DETALLES_DIR = os.path.join(BASE_DIR, "partidos_detalles_fotmob")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.fotmob.com/",
    "Origin": "https://www.fotmob.com"
}

# Diccionario de normalización de nombres de países (Español Betplay/Flashscore -> Inglés FotMob)
COUNTRY_TRANSLATIONS = {
    "internacional": "international",
    "alemania": "germany",
    "arabia saudi": "saudi arabia",
    "argelia": "algeria",
    "armenia": "armenia",
    "australia": "australia",
    "austria": "austria",
    "bahrein": "bahrain",
    "belgica": "belgium",
    "bolivia": "bolivia",
    "bosnia y herzegovina": "bosnia-herzegovina",
    "brasil": "brazil",
    "bulgaria": "bulgaria",
    "canada": "canada",
    "chile": "chile",
    "china": "china",
    "chipre": "cyprus",
    "colombia": "colombia",
    "corea del sur": "korea republic",
    "costa rica": "costa rica",
    "croacia": "croatia",
    "dinamarca": "denmark",
    "ecuador": "ecuador",
    "egipto": "egypt",
    "el salvador": "el salvador",
    "emiratos arabes unidos": "united arab emirates",
    "escocia": "scotland",
    "eslovaquia": "slovakia",
    "eslovenia": "slovenia",
    "espana": "spain",
    "estados unidos": "usa",
    "estonia": "estonia",
    "filipinas": "philippines",
    "finlandia": "finland",
    "francia": "france",
    "gales": "wales",
    "georgia": "georgia",
    "ghana": "ghana",
    "gibraltar": "gibraltar",
    "grecia": "greece",
    "guatemala": "guatemala",
    "honduras": "honduras",
    "hungria": "hungary",
    "india": "india",
    "indonesia": "indonesia",
    "inglaterra": "england",
    "irlanda": "ireland",
    "irlanda del norte": "northern ireland",
    "islandia": "iceland",
    "israel": "israel",
    "italia": "italy",
    "jamaica": "jamaica",
    "japon": "japan",
    "jordania": "jordan",
    "kazajistan": "kazakhstan",
    "kenia": "kenya",
    "kosovo": "kosovo",
    "kuwait": "kuwait",
    "letonia": "latvia",
    "lituania": "lithuania",
    "luxemburgo": "luxembourg",
    "macedonia del norte": "north macedonia",
    "malasia": "malaysia",
    "marruecos": "morocco",
    "mexico": "mexico",
    "montenegro": "montenegro",
    "nicaragua": "nicaragua",
    "nigeria": "nigeria",
    "noruega": "norway",
    "nueva zelanda": "new zealand",
    "paises bajos": "netherlands",
    "holanda": "netherlands",
    "panama": "panama",
    "paraguay": "paraguay",
    "peru": "peru",
    "polonia": "poland",
    "portugal": "portugal",
    "qatar": "qatar",
    "republica checa": "czech republic",
    "rumania": "romania",
    "rusia": "russia",
    "san marino": "san marino",
    "serbia": "serbia",
    "singapur": "singapore",
    "sudafrica": "south africa",
    "suecia": "sweden",
    "suiza": "switzerland",
    "tailandia": "thailand",
    "tunez": "tunisia",
    "turquia": "turkiye",
    "ucrania": "ukraine",
    "uruguay": "uruguay",
    "uzbekistan": "uzbekistan",
    "venezuela": "venezuela",
    "vietnam": "vietnam"
}

def normalize_str(s: str) -> str:
    """Elimina acentos y caracteres especiales para comparación segura."""
    if not s:
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r'[^a-z0-9\s]', '', s)
    return s

def parse_circles(circles_str: str) -> List[Dict[str, float]]:
    """Extrae las coordenadas (x, y) de los tags <circle cx='...' cy='...'/> del heatmap."""
    coords = []
    pattern = re.compile(r'cx="([\d\.]+)"\s+cy="([\d\.]+)"')
    for m in pattern.finditer(circles_str):
        coords.append({"x": float(m.group(1)), "y": float(m.group(2))})
    return coords

def http_get_json(url: str, retries: int = 3, delay: float = 0.8) -> Optional[Any]:
    """Descarga JSON de forma eficiente manejando compresión gzip."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                return None

class FotMobScraper:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.all_leagues_data = None
        os.makedirs(FOTMOB_DETALLES_DIR, exist_ok=True)
        self._init_database_schema()

    def _get_connection(self, timeout: float = 60.0) -> sqlite3.Connection:
        """Crea una conexion SQLite con modo WAL y busy_timeout extendido."""
        conn = sqlite3.connect(self.db_path, timeout=timeout)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
        except Exception:
            pass
        return conn

    def _init_database_schema(self):
        """Asegura que existan las tablas relacionales y checkpoints para FotMob."""
        conn = self._get_connection(timeout=30.0)
        cur = conn.cursor()
        
        # 1. Tabla de mapeo de competiciones Betplay ↔ Flashscore ↔ FotMob
        cur.execute("""
        CREATE TABLE IF NOT EXISTS competiciones_fotmob (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competicion_id INTEGER NOT NULL UNIQUE,
            pais_nombre TEXT NOT NULL,
            nombre_betplay TEXT NOT NULL,
            nombre_flashscore TEXT NOT NULL,
            fotmob_league_id INTEGER,
            fotmob_nombre TEXT,
            fotmob_url TEXT,
            fotmob_ccode TEXT,
            ruta_optima TEXT DEFAULT 'fotmob',
            FOREIGN KEY (competicion_id) REFERENCES competiciones(id)
        );
        """)

        # 2. Tabla de partidos y fixtures por jornada
        cur.execute("""
        CREATE TABLE IF NOT EXISTS fotmob_partidos (
            match_id TEXT PRIMARY KEY,
            fotmob_league_id INTEGER NOT NULL,
            round TEXT,
            round_name TEXT,
            fecha_utc TEXT,
            home_team_id TEXT,
            home_team_name TEXT,
            home_score INTEGER,
            away_team_id TEXT,
            away_team_name TEXT,
            away_score INTEGER,
            status TEXT,
            page_url TEXT,
            FOREIGN KEY (fotmob_league_id) REFERENCES competiciones_fotmob(fotmob_league_id)
        );
        """)

        # 3. Tabla de detalles técnicos de partido (Árbitro, Estadio, Clima, xG y archivo JSON)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS fotmob_detalles_partido (
            match_id TEXT PRIMARY KEY,
            arbitro_nombre TEXT,
            arbitro_pais TEXT,
            arbitro_amarillas_partido REAL,
            arbitro_rojas_total INTEGER,
            arbitro_faltas_partido REAL,
            arbitro_penales_total INTEGER,
            estadio_nombre TEXT,
            estadio_ciudad TEXT,
            estadio_capacidad INTEGER,
            estadio_aforo INTEGER,
            estadio_superficie TEXT,
            clima_temperatura REAL,
            clima_condicion TEXT,
            json_path TEXT,
            xg_local REAL,
            xg_visitante REAL,
            actualizado_el TEXT,
            FOREIGN KEY (match_id) REFERENCES fotmob_partidos(match_id)
        );
        """)

        # 4. Tabla de estadísticas colectivas de partidos (por periodo y sección)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS fotmob_partidos_estadisticas (
            match_id TEXT NOT NULL,
            periodo TEXT NOT NULL,
            seccion TEXT NOT NULL,
            metrica TEXT NOT NULL,
            valor_local TEXT,
            valor_visitante TEXT,
            PRIMARY KEY (match_id, periodo, seccion, metrica),
            FOREIGN KEY (match_id) REFERENCES fotmob_partidos(match_id) ON DELETE CASCADE
        );
        """)

        # 5. Tabla de incidentes y eventos de partidos (goles, tarjetas, cambios)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS fotmob_partidos_incidentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id TEXT NOT NULL,
            periodo TEXT,
            minuto TEXT,
            equipo TEXT,
            tipo TEXT,
            jugador TEXT,
            jugador_sale TEXT,
            nota TEXT,
            FOREIGN KEY (match_id) REFERENCES fotmob_partidos(match_id) ON DELETE CASCADE
        );
        """)

        # 6. Checkpoints de detalles de partidos fotmob (control incremental sin duplicar)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints_fotmob_detalles (
            match_id TEXT PRIMARY KEY,
            fotmob_league_id INTEGER,
            estado TEXT NOT NULL,
            error_msg TEXT,
            actualizado_el TEXT NOT NULL
        );
        """)

        # Migración segura de columnas en fotmob_detalles_partido si faltasen
        cur.execute("PRAGMA table_info(fotmob_detalles_partido);")
        existing_cols = [c[1] for c in cur.fetchall()]
        if "json_path" not in existing_cols:
            cur.execute("ALTER TABLE fotmob_detalles_partido ADD COLUMN json_path TEXT;")
        if "xg_local" not in existing_cols:
            cur.execute("ALTER TABLE fotmob_detalles_partido ADD COLUMN xg_local REAL;")
        if "xg_visitante" not in existing_cols:
            cur.execute("ALTER TABLE fotmob_detalles_partido ADD COLUMN xg_visitante REAL;")
        if "actualizado_el" not in existing_cols:
            cur.execute("ALTER TABLE fotmob_detalles_partido ADD COLUMN actualizado_el TEXT;")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_fotmob_partidos_league ON fotmob_partidos(fotmob_league_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fotmob_partidos_round ON fotmob_partidos(round);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fotmob_stats_partido ON fotmob_partidos_estadisticas(match_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fotmob_incidentes_partido ON fotmob_partidos_incidentes(match_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fotmob_checkpoints_estado ON checkpoints_fotmob_detalles(estado);")

        conn.commit()
        conn.close()

    def load_all_leagues(self) -> Dict:
        """Carga el catálogo maestro de ligas de FotMob (con caché local)."""
        if self.all_leagues_data:
            return self.all_leagues_data

        if os.path.exists(ALL_LEAGUES_CACHE):
            try:
                with open(ALL_LEAGUES_CACHE, "r", encoding="utf-8") as f:
                    self.all_leagues_data = json.load(f)
                    return self.all_leagues_data
            except Exception:
                pass

        url = "https://www.fotmob.com/api/data/allLeagues"
        data = http_get_json(url)
        if data:
            self.all_leagues_data = data
            with open(ALL_LEAGUES_CACHE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        return self.all_leagues_data or {}

    def map_betplay_to_fotmob(self, force_refresh: bool = False) -> List[Dict]:
        """
        Cruza las competiciones de Betplay con las de FotMob,
        filtrando estrictamente sólo las que cubre Betplay.
        Si ya existe el mapeo curado de 163 competiciones en JSON/DB, lo preserva.
        """
        conn = self._get_connection(timeout=30.0)
        cur = conn.cursor()

        # Si ya existe el mapping curado en JSON, cargarlo y sincronizar con la DB
        if not force_refresh and os.path.exists(OUTPUT_MAPPING_JSON):
            try:
                with open(OUTPUT_MAPPING_JSON, "r", encoding="utf-8") as f:
                    cached_mapping = json.load(f)
                if isinstance(cached_mapping, list) and len(cached_mapping) >= 200:
                    cur.execute("SELECT count(*) FROM competiciones_fotmob;")
                    count_db = cur.fetchone()[0]
                    if count_db == len(cached_mapping):
                        conn.close()
                        total_mapped = len([m for m in cached_mapping if m.get("fotmob_league_id")])
                        return cached_mapping

                    cur.execute("DELETE FROM competiciones_fotmob;")
                    for m in cached_mapping:
                        cur.execute("""
                        INSERT INTO competiciones_fotmob 
                        (competicion_id, pais_nombre, nombre_betplay, nombre_flashscore, fotmob_league_id, fotmob_nombre, fotmob_url, fotmob_ccode, ruta_optima)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """, (
                            m["competicion_id"], m["pais_nombre"], m["nombre_betplay"], m["nombre_flashscore"],
                            m.get("fotmob_league_id"), m.get("fotmob_nombre"), m.get("fotmob_url"), m.get("fotmob_ccode"),
                            m.get("ruta_optima", "fotmob" if m.get("fotmob_league_id") else "flashscore")
                        ))
                    conn.commit()
                    conn.close()
                    total_mapped = len([m for m in cached_mapping if m.get("fotmob_league_id")])
                    print(f"[MAPEO] {total_mapped}/{len(cached_mapping)} competiciones sincronizadas desde {os.path.basename(OUTPUT_MAPPING_JSON)}.")
                    return cached_mapping
            except Exception as e:
                print(f"[!] Aviso al leer mapping cache: {e}")

        cur.execute("""
            SELECT c.id, c.pais_nombre, c.nombre_betplay, c.nombre_flashscore, c.link_flashscore
            FROM competiciones c
            WHERE c.link_flashscore LIKE 'http%'
            ORDER BY c.pais_nombre, c.nombre_betplay;
        """)
        betplay_comps = cur.fetchall()
        
        fotmob_catalog = self.load_all_leagues()
        countries_data = fotmob_catalog.get("countries", [])
        popular_data = fotmob_catalog.get("popular", [])
        intl_data = fotmob_catalog.get("international", [])

        # Indexar ligas de FotMob por país
        fotmob_by_country = {}
        for c in countries_data:
            cname_norm = normalize_str(c.get("name", ""))
            c_code = c.get("ccode", "")
            leagues = c.get("leagues", [])
            fotmob_by_country[cname_norm] = leagues
            if c_code:
                fotmob_by_country[c_code.lower()] = leagues

        all_intl_leagues = []
        for grp in intl_data:
            all_intl_leagues.extend(grp.get("leagues", []))
        fotmob_by_country["international"] = all_intl_leagues

        mapped_results = []
        for row in betplay_comps:
            c_id, pais, nom_betplay, nom_flashscore, link_flashscore = row
            pais_norm = normalize_str(pais)
            fotmob_country_key = COUNTRY_TRANSLATIONS.get(pais_norm, pais_norm)
            candidate_leagues = fotmob_by_country.get(fotmob_country_key, [])

            target_norm_b = normalize_str(nom_betplay)
            target_norm_f = normalize_str(nom_flashscore)

            best_match = None
            best_score = 0.0

            for f_league in candidate_leagues:
                f_name = f_league.get("name", "")
                f_norm = normalize_str(f_name)

                if f_norm == target_norm_b or f_norm == target_norm_f:
                    best_match = f_league
                    best_score = 1.0
                    break

                if target_norm_b in f_norm or target_norm_f in f_norm or f_norm in target_norm_b or f_norm in target_norm_f:
                    score = len(set(f_norm.split()) & set(target_norm_b.split())) / max(len(f_norm.split()), 1)
                    if score > best_score:
                        best_score = score
                        best_match = f_league

            if not best_match:
                for p_league in popular_data:
                    p_ccode = (p_league.get("ccode") or "").lower()
                    if p_ccode in [fotmob_country_key, pais_norm] or (fotmob_country_key == "international" and p_ccode == "int"):
                        p_norm = normalize_str(p_league.get("name", ""))
                        if p_norm == target_norm_b or p_norm == target_norm_f:
                            best_match = p_league
                            break

            mapped_results.append({
                "competicion_id": c_id,
                "pais_nombre": pais,
                "nombre_betplay": nom_betplay,
                "nombre_flashscore": nom_flashscore,
                "fotmob_league_id": best_match.get("id") if best_match else None,
                "fotmob_nombre": best_match.get("name") if best_match else None,
                "fotmob_url": f"https://www.fotmob.com{best_match.get('pageUrl')}" if best_match and best_match.get("pageUrl") else None,
                "fotmob_ccode": best_match.get("ccode") if best_match else None,
                "ruta_optima": "fotmob" if best_match else "flashscore"
            })

        cur.execute("DELETE FROM competiciones_fotmob;")
        for m in mapped_results:
            cur.execute("""
            INSERT INTO competiciones_fotmob 
            (competicion_id, pais_nombre, nombre_betplay, nombre_flashscore, fotmob_league_id, fotmob_nombre, fotmob_url, fotmob_ccode, ruta_optima)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                m["competicion_id"], m["pais_nombre"], m["nombre_betplay"], m["nombre_flashscore"],
                m["fotmob_league_id"], m["fotmob_nombre"], m["fotmob_url"], m["fotmob_ccode"],
                m.get("ruta_optima", "fotmob" if m.get("fotmob_league_id") else "flashscore")
            ))
        conn.commit()
        conn.close()

        with open(OUTPUT_MAPPING_JSON, "w", encoding="utf-8") as f:
            json.dump(mapped_results, f, indent=2, ensure_ascii=False)

        total_mapped = len([m for m in mapped_results if m["fotmob_league_id"]])
        print(f"[MAPEO] {total_mapped}/{len(mapped_results)} competiciones de Betplay vinculadas a FotMob exitosamente.")
        return mapped_results

    def scrape_league_fixtures(self, league_id: int, league_slug: str = "league") -> List[Dict]:
        """
        Extrae todos los partidos y jornadas de una liga en FotMob.
        Obtiene la lista completa de partidos con su jornada/round en un solo request.
        """
        url_league = f"https://www.fotmob.com/api/data/leagues?id={league_id}"
        league_data = http_get_json(url_league)
        data = None
        if league_data and isinstance(league_data, dict):
            data = league_data.get("fixtures", {}).get("allMatches")
        
        if not data:
            url_fixtures = f"https://www.fotmob.com/api/data/fixtures?id={league_id}"
            data = http_get_json(url_fixtures)

        if not data or not isinstance(data, list):
            url_page = f"https://www.fotmob.com/leagues/{league_id}/fixtures/{league_slug}"
            try:
                req = urllib.request.Request(url_page, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode('utf-8')
                    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
                    if m:
                        props = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
                        data = props.get("fixtures", {}).get("allMatches", [])
            except urllib.error.HTTPError as e:
                print(f"[AVISO] Liga {league_id} no disponible en FotMob (HTTP {e.code}), omitiendo.")
                return []
            except Exception as e:
                print(f"[AVISO] No se pudieron obtener fixtures de liga {league_id}: {e}")
                return []

        parsed_matches = []
        conn = self._get_connection(timeout=30.0)
        cur = conn.cursor()

        for item in (data or []):
            match_id = str(item.get("id"))
            page_url = item.get("pageUrl")
            home = item.get("home", {})
            away = item.get("away", {})
            status = item.get("status", {})
            round_raw = item.get("round") or item.get("roundName") or ""
            round_val = str(round_raw).strip()
            round_name = str(item.get("roundName") or round_val).strip()

            m_obj = {
                "match_id": match_id,
                "fotmob_league_id": league_id,
                "round": round_val,
                "round_name": round_name,
                "fecha_utc": status.get("utcTime"),
                "home_team_id": str(home.get("id")),
                "home_team_name": home.get("name"),
                "home_score": home.get("score"),
                "away_team_id": str(away.get("id")),
                "away_team_name": away.get("name"),
                "away_score": away.get("score"),
                "status": status.get("reason", {}).get("short", "FT" if status.get("finished") else "-"),
                "page_url": f"https://www.fotmob.com{page_url}" if page_url else None
            }

            cur.execute("""
            INSERT OR REPLACE INTO fotmob_partidos 
            (match_id, fotmob_league_id, round, round_name, fecha_utc, home_team_id, home_team_name, home_score, away_team_id, away_team_name, away_score, status, page_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                m_obj["match_id"], m_obj["fotmob_league_id"], m_obj["round"], m_obj["round_name"],
                m_obj["fecha_utc"], m_obj["home_team_id"], m_obj["home_team_name"], m_obj["home_score"],
                m_obj["away_team_id"], m_obj["away_team_name"], m_obj["away_score"], m_obj["status"], m_obj["page_url"]
            ))
            parsed_matches.append(m_obj)

        conn.commit()
        conn.close()
        print(f"[FIXTURES] Liga {league_id}: {len(parsed_matches)} partidos extraídos y almacenados.")
        return parsed_matches

    def scrape_match_full_details_and_stats(self, match_id: str, download_heatmaps: bool = True) -> Optional[Dict]:
        """
        Extrae los detalles técnicos y las estadísticas completas del partido:
        - Árbitro (nombre, país, amarillas, faltas, etc.)
        - Estadio (nombre, ciudad, capacidad, aforo real, superficie)
        - Clima (temperatura, condiciones)
        - Momentum, eventos y estadísticas por periodo
        - Shotmap con coordenadas espaciales y xG
        - Alineaciones completas con entrenadores y notas
        - Mapas de calor (Heatmaps) de jugadores con coordenadas vectoriales
        - Guarda el JSON estructurado en partidos_detalles_fotmob/{league_id}/{match_id}.json
        - Registra checkpoint en SQLite
        """
        url = f"https://www.fotmob.com/api/data/matchDetails?matchId={match_id}"
        mdata = http_get_json(url)
        if not isinstance(mdata, dict):
            self._record_checkpoint(match_id, estado="error", error_msg="HTTP 404 o timeout")
            return None

        content = mdata.get("content") or {}
        if not isinstance(content, dict):
            content = {}
        general = mdata.get("general") or {}
        if not isinstance(general, dict):
            general = {}
        header = mdata.get("header") or {}
        if not isinstance(header, dict):
            header = {}

        raw_teams = header.get("teams") or []
        teams = [t for t in raw_teams if isinstance(t, dict)]
        home_team = teams[0] if len(teams) > 0 else {}
        away_team = teams[1] if len(teams) > 1 else {}
        home_name = home_team.get("name") or "Local"
        away_name = away_team.get("name") or "Visitante"
        home_score = home_team.get("score")
        away_score = away_team.get("score")

        mf = content.get("matchFacts") or {}
        if not isinstance(mf, dict):
            mf = {}
        info_box = mf.get("infoBox") or {}
        if not isinstance(info_box, dict):
            info_box = {}

        ref = info_box.get("Referee") or {}
        if not isinstance(ref, dict):
            ref = {}
        stadium = info_box.get("Stadium") or {}
        if not isinstance(stadium, dict):
            stadium = {}
        attendance = info_box.get("Attendance")
        weather = content.get("weather") or {}
        if not isinstance(weather, dict):
            weather = {}

        ref_stats = {}
        for s in (ref.get("stats") or []):
            if isinstance(s, dict) and s.get("type"):
                ref_stats[s.get("type")] = {
                    "value": s.get("value"),
                    "valueType": s.get("valueType"),
                    "total": s.get("total")
                }

        league_id = general.get("leagueId")
        match_info = {
            "matchId": str(general.get("matchId") or match_id),
            "matchName": f"{home_name} vs {away_name}",
            "competition": general.get("leagueName") or "",
            "leagueId": league_id,
            "round": general.get("matchRound") or general.get("leagueRoundName"),
            "dateTimeUTC": general.get("matchTimeUTC"),
            "score": {
                "home": {"name": home_name, "score": home_score},
                "away": {"name": away_name, "score": away_score}
            },
            "stadium": {
                "name": stadium.get("name"),
                "city": stadium.get("city"),
                "capacity": stadium.get("capacity"),
                "attendance": attendance,
                "surface": stadium.get("surface")
            },
            "referee": {
                "name": ref.get("text"),
                "country": ref.get("country"),
                "stats": ref_stats
            },
            "weather": {
                "temperature": weather.get("temperature"),
                "condition": weather.get("description")
            }
        }

        # Eventos y Momentum
        events_container = mf.get("events") or {}
        events_raw = events_container.get("events") if isinstance(events_container, dict) else []
        if not isinstance(events_raw, list):
            events_raw = []
        parsed_events = []
        for e in events_raw:
            if not isinstance(e, dict):
                continue
            p_obj = e.get("player")
            player_name = p_obj.get("name") if isinstance(p_obj, dict) else (str(p_obj) if p_obj is not None else "")
            raw_swap = e.get("swap") or []
            swap_list = [s.get("name") for s in raw_swap if isinstance(s, dict) and s.get("name")] if isinstance(raw_swap, list) else None
            parsed_events.append({
                "minute": e.get("time"),
                "addedTime": e.get("overloadTime"),
                "type": e.get("type"),
                "team": home_name if e.get("isHome") else away_name,
                "player": player_name,
                "card": e.get("card"),
                "swap": swap_list
            })

        mom = content.get("momentum")
        momentum_data = []
        if isinstance(mom, dict):
            main_m = mom.get("main")
            if isinstance(main_m, dict):
                momentum_data = main_m.get("data", []) or []

        # Estadísticas por periodo
        st = content.get("stats")
        periods_raw = {}
        if isinstance(st, dict):
            p_obj = st.get("Periods")
            if isinstance(p_obj, dict):
                periods_raw = p_obj

        parsed_stats = {}
        xg_home = None
        xg_away = None
        for period_key in ["FirstHalf", "SecondHalf", "All"]:
            p_data = periods_raw.get(period_key)
            if not isinstance(p_data, dict):
                continue
            period_stats = {}
            for cat in (p_data.get("stats") or []):
                if not isinstance(cat, dict):
                    continue
                cat_title = cat.get("title")
                cat_dict = {}
                for item in (cat.get("stats") or []):
                    if not isinstance(item, dict):
                        continue
                    val = item.get("stats")
                    title = item.get("title")
                    if val and val != [None, None]:
                        cat_dict[title] = {"home": val[0], "away": val[1]}
                        if period_key == "All" and "Expected goals" in (title or ""):
                            try:
                                xg_home = float(val[0])
                                xg_away = float(val[1])
                            except Exception:
                                pass
                if cat_dict:
                    period_stats[cat_title] = cat_dict
            if period_stats:
                parsed_stats[period_key] = period_stats

        # Alineaciones
        lineup_raw = content.get("lineup") if isinstance(content.get("lineup"), dict) else {}
        def process_lineup(t_key):
            t = lineup_raw.get(t_key)
            if not isinstance(t, dict):
                return None
            coach = t.get("coach") if isinstance(t.get("coach"), dict) else {}
            starters = []
            for p in (t.get("starters") or []):
                if not isinstance(p, dict):
                    continue
                perf = p.get("performance") if isinstance(p.get("performance"), dict) else {}
                starters.append({
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "shirtNumber": p.get("shirtNumber"),
                    "position": p.get("usualPlayingPositionId"),
                    "rating": perf.get("rating"),
                    "distanceCoveredMeters": perf.get("totalDistanceCovered"),
                    "topSpeedKmh": perf.get("topSpeed")
                })
            subs = []
            for p in (t.get("subs") or []):
                if not isinstance(p, dict):
                    continue
                perf = p.get("performance") if isinstance(p.get("performance"), dict) else {}
                subs.append({
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "shirtNumber": p.get("shirtNumber"),
                    "rating": perf.get("rating")
                })
            return {
                "name": t.get("name"),
                "formation": t.get("formation"),
                "coach": coach.get("name"),
                "starters": starters,
                "substitutes": subs
            }

        lineups = {
            "home": process_lineup("homeTeam"),
            "away": process_lineup("awayTeam")
        } if lineup_raw else None

        # Shotmap con coordenadas
        shotmap_obj = content.get("shotmap") or {}
        shots_raw = shotmap_obj.get("shots") if isinstance(shotmap_obj, dict) else []
        if not isinstance(shots_raw, list):
            shots_raw = []
        parsed_shots = []
        home_team_id = home_team.get("id")
        for s in shots_raw:
            if not isinstance(s, dict):
                continue
            parsed_shots.append({
                "id": s.get("id"),
                "minute": s.get("min"),
                "period": s.get("period"),
                "isHome": (s.get("teamId") == home_team_id) if home_team_id is not None else None,
                "playerName": s.get("fullName"),
                "eventType": s.get("eventType"),
                "x": round(float(s.get("x") or 0), 2),
                "y": round(float(s.get("y") or 0), 2),
                "expectedGoals": round(float(s.get("expectedGoals") or 0), 4),
                "onGoalShot": s.get("onGoalShot")
            })

        # Mapas de calor (Heatmaps)
        heatmaps_result = None
        heatmap_url = content.get("heatmapUrl")
        if download_heatmaps and heatmap_url:
            full_hm_url = f"https://www.fotmob.com{heatmap_url}"
            hm_data = http_get_json(full_hm_url)
            if isinstance(hm_data, dict) and isinstance(hm_data.get("players"), dict):
                players_hm = {}
                for opta_key, circles_str in hm_data["players"].items():
                    if not isinstance(circles_str, str):
                        continue
                    coords = parse_circles(circles_str)
                    players_hm[opta_key] = {
                        "totalTouches": len(coords),
                        "coordinates": coords
                    }
                heatmaps_result = {
                    "dimensions": {"lengthMeters": 105.0, "widthMeters": 68.0},
                    "players": players_hm
                }

        # Guardar archivo JSON completo
        league_folder = os.path.join(FOTMOB_DETALLES_DIR, str(league_id or "general"))
        os.makedirs(league_folder, exist_ok=True)
        json_file_path = os.path.join(league_folder, f"{match_id}.json")

        full_dataset = {
            "match": match_info,
            "facts": {
                "events": parsed_events,
                "momentum": momentum_data
            },
            "stats": parsed_stats,
            "shotmap": parsed_shots,
            "lineups": lineups,
            "heatmaps": heatmaps_result,
            "xg": {"home": xg_home, "away": xg_away}
        }

        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(full_dataset, f, indent=2, ensure_ascii=False)

        # Actualizar base de datos SQLite con tolerancia a bloqueos y reintentos
        now_iso = datetime.now(timezone.utc).isoformat()
        max_db_retries = 5
        for attempt in range(max_db_retries):
            try:
                conn = self._get_connection(timeout=60.0)
                cur = conn.cursor()
                # 1. Detalles técnicos de partido
                cur.execute("""
                INSERT OR REPLACE INTO fotmob_detalles_partido
                (match_id, arbitro_nombre, arbitro_pais, arbitro_amarillas_partido, arbitro_rojas_total, arbitro_faltas_partido, arbitro_penales_total,
                 estadio_nombre, estadio_ciudad, estadio_capacidad, estadio_aforo, estadio_superficie, clima_temperatura, clima_condicion,
                 json_path, xg_local, xg_visitante, actualizado_el)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    str(match_id), ref.get("text"), ref.get("country"),
                    (ref_stats.get("yellowCards") or {}).get("value"),
                    (ref_stats.get("redCards") or {}).get("total"),
                    (ref_stats.get("fouls") or {}).get("value"),
                    (ref_stats.get("penalties") or {}).get("total"),
                    stadium.get("name"), stadium.get("city"), stadium.get("capacity"),
                    attendance, stadium.get("surface"),
                    weather.get("temperature"), weather.get("description"),
                    json_file_path, xg_home, xg_away, now_iso
                ))

                # 2. Estadísticas de los partidos (Posesión, Tiros, xG, Córneres, Pases, Faltas por periodo)
                stats_rows = []
                period_map = {
                    "All": "partido_completo",
                    "FirstHalf": "1er_tiempo",
                    "SecondHalf": "2o_tiempo"
                }
                for p_key, p_name in period_map.items():
                    p_data = periods_raw.get(p_key)
                    if not isinstance(p_data, dict):
                        continue
                    for cat in (p_data.get("stats") or []):
                        if not isinstance(cat, dict):
                            continue
                        sec_name = cat.get("title", "General")
                        for item in (cat.get("stats") or []):
                            if not isinstance(item, dict):
                                continue
                            met_name = item.get("title")
                            vals = item.get("stats")
                            if met_name and vals and vals != [None, None]:
                                stats_rows.append((
                                    str(match_id),
                                    p_name,
                                    sec_name,
                                    met_name,
                                    str(vals[0]),
                                    str(vals[1])
                                ))
                if stats_rows:
                    cur.executemany("""
                    INSERT OR REPLACE INTO fotmob_partidos_estadisticas
                    (match_id, periodo, seccion, metrica, valor_local, valor_visitante)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """, stats_rows)

                # 3. Incidentes y eventos del partido (Goles, Tarjetas, Sustituciones)
                incidents_rows = []
                for e in events_raw:
                    if not isinstance(e, dict):
                        continue
                    side = "home" if e.get("isHome") else "away"
                    swap = e.get("swap") or []
                    p_sale = None
                    p_entra = None
                    if isinstance(swap, list):
                        if len(swap) > 1 and isinstance(swap[1], dict):
                            p_sale = swap[1].get("name")
                        if len(swap) > 0 and isinstance(swap[0], dict):
                            p_entra = swap[0].get("name")
                    if not p_entra:
                        p_obj = e.get("player")
                        p_entra = p_obj.get("name") if isinstance(p_obj, dict) else (str(p_obj) if p_obj is not None else None)

                    incidents_rows.append((
                        str(match_id),
                        "1er_tiempo" if (e.get("time") or 0) <= 45 else "2o_tiempo",
                        str(e.get("time", "")),
                        side,
                        e.get("type", "evento"),
                        p_entra,
                        p_sale,
                        e.get("card") or ("Lesión" if e.get("injuredPlayerOut") else "")
                    ))
                if incidents_rows:
                    cur.execute("DELETE FROM fotmob_partidos_incidentes WHERE match_id = ?;", (str(match_id),))
                    cur.executemany("""
                    INSERT INTO fotmob_partidos_incidentes
                    (match_id, periodo, minuto, equipo, tipo, jugador, jugador_sale, nota)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """, incidents_rows)

                # 4. Checkpoint en la misma transacción para evitar bloqueo de base de datos
                cur.execute("""
                INSERT OR REPLACE INTO checkpoints_fotmob_detalles (match_id, fotmob_league_id, estado, error_msg, actualizado_el)
                VALUES (?, ?, ?, ?, ?);
                """, (str(match_id), league_id, "completado", None, now_iso))

                conn.commit()
                conn.close()
                break
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_db_retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    raise

        return full_dataset

    def scrape_match_details(self, match_id: str) -> Optional[Dict]:
        """Alias retrocompatible: extrae detalles completos y devuelve resumen técnico."""
        full_data = self.scrape_match_full_details_and_stats(match_id, download_heatmaps=False)
        if not full_data:
            return None
        m = full_data.get("match") or {}
        r = m.get("referee") or {}
        s = m.get("stadium") or {}
        w = m.get("weather") or {}
        return {
            "match_id": str(match_id),
            "arbitro_nombre": r.get("name"),
            "arbitro_pais": r.get("country"),
            "arbitro_faltas_partido": (r.get("stats") or {}).get("fouls", {}).get("value") if isinstance(r.get("stats"), dict) else None,
            "estadio_nombre": s.get("name"),
            "estadio_capacidad": s.get("capacity"),
            "estadio_aforo": s.get("attendance"),
            "estadio_superficie": s.get("surface"),
            "clima_temperatura": w.get("temperature"),
            "clima_condicion": w.get("condition")
        }

    def _record_checkpoint(self, match_id: str, league_id: Optional[int] = None, estado: str = "completado", error_msg: Optional[str] = None):
        """Registra checkpoint en SQLite para trazabilidad y reanudación con reintentos."""
        now_iso = datetime.now(timezone.utc).isoformat()
        for attempt in range(5):
            try:
                conn = self._get_connection(timeout=30.0)
                cur = conn.cursor()
                cur.execute("""
                INSERT OR REPLACE INTO checkpoints_fotmob_detalles (match_id, fotmob_league_id, estado, error_msg, actualizado_el)
                VALUES (?, ?, ?, ?, ?);
                """, (str(match_id), league_id, estado, error_msg, now_iso))
                conn.commit()
                conn.close()
                break
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < 4:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    break
            except Exception:
                break

    def sync_all_fixtures(self) -> int:
        """Sincroniza los calendarios y jornadas de todas las ligas mapeadas."""
        self.map_betplay_to_fotmob()
        conn = self._get_connection(timeout=30.0)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT fotmob_league_id, fotmob_nombre FROM competiciones_fotmob WHERE ruta_optima = 'fotmob' AND fotmob_league_id IS NOT NULL ORDER BY fotmob_nombre;")
        leagues = cur.fetchall()
        conn.close()

        print(f"\n[SYNC-FIXTURES] Sincronizando {len(leagues)} ligas de Betplay...")
        total_matches = 0
        for idx, (lid, lname) in enumerate(leagues, 1):
            try:
                print(f"[{idx}/{len(leagues)}] {lname} (ID: {lid})...")
                matches = self.scrape_league_fixtures(lid)
                total_matches += len(matches)
                time.sleep(0.15)
            except Exception as e:
                print(f"[WARN] Error en liga {lname} (ID: {lid}): {e}")
                time.sleep(0.3)
        print(f"\n[SYNC-FIXTURES] Finalizado: {total_matches:,} partidos indexados.")
        return total_matches

    def sync_stats_pending(self, limit: Optional[int] = None, download_heatmaps: bool = True) -> int:
        """
        Descarga las estadísticas completas de partidos finalizados (FT)
        que aún no han sido procesados según los checkpoints.
        """
        conn = self._get_connection(timeout=30.0)
        cur = conn.cursor()
        query = """
            SELECT fp.match_id, fp.home_team_name, fp.away_team_name, fp.fotmob_league_id
            FROM fotmob_partidos fp
            LEFT JOIN checkpoints_fotmob_detalles c ON fp.match_id = c.match_id
            WHERE fp.status = 'FT' AND (c.estado IS NULL OR c.estado != 'completado')
            ORDER BY fp.fecha_utc DESC
        """
        if limit:
            query += f" LIMIT {int(limit)}"
            
        cur.execute(query)
        pending_matches = cur.fetchall()
        conn.close()

        total = len(pending_matches)
        if total == 0:
            print("[STATS] No hay partidos finalizados pendientes de procesar.")
            return 0

        print(f"\n[STATS] Procesando estadísticas completas de {total} partidos pendientes...")
        processed = 0
        for idx, (mid, h, a, lid) in enumerate(pending_matches, 1):
            try:
                t0 = time.time()
                res = self.scrape_match_full_details_and_stats(mid, download_heatmaps=download_heatmaps)
                elapsed = time.time() - t0
                if res:
                    processed += 1
                    shots = len(res.get("shotmap") or [])
                    hms = len((res.get("heatmaps") or {}).get("players") or {}) if res.get("heatmaps") else 0
                    print(f"[{idx}/{total}] Part {mid}: {h} vs {a} | Tiros: {shots} | Heatmaps: {hms} ({elapsed:.2f}s)")
                else:
                    print(f"[{idx}/{total}] Part {mid}: {h} vs {a} | Sin datos detallados")
                time.sleep(0.1)
            except Exception as e:
                print(f"[ERROR] Partido {mid}: {e}")
                time.sleep(0.2)

        print(f"\n[STATS] Finalizado: {processed}/{total} partidos con estadísticas completas almacenadas.")
        return processed

    def sync_competition(self, comp_query: str, download_stats: bool = True, limit_stats: Optional[int] = None, download_heatmaps: bool = True):
        """Sincroniza una competición puntual (por ID de liga o por nombre)."""
        conn = self._get_connection(timeout=30.0)
        cur = conn.cursor()
        if comp_query.isdigit():
            cur.execute("SELECT fotmob_league_id, fotmob_nombre, pais_nombre FROM competiciones_fotmob WHERE fotmob_league_id = ? LIMIT 1", (int(comp_query),))
        else:
            norm = f"%{comp_query.strip().lower()}%"
            cur.execute("SELECT fotmob_league_id, fotmob_nombre, pais_nombre FROM competiciones_fotmob WHERE lower(fotmob_nombre) LIKE ? OR lower(nombre_betplay) LIKE ? LIMIT 1", (norm, norm))
        row = cur.fetchone()
        conn.close()

        if not row or not row[0]:
            print(f"[ERROR] Competición '{comp_query}' no encontrada en el mapeo de Betplay.")
            return

        lid, lname, pais = row
        print(f"\n>>> Sincronizando competición: {pais} - {lname} (ID: {lid})")
        matches = self.scrape_league_fixtures(lid)

        if download_stats:
            conn = self._get_connection(timeout=30.0)
            cur = conn.cursor()
            cur.execute("SELECT match_id FROM checkpoints_fotmob_detalles WHERE estado = 'completado';")
            done_ids = set(r[0] for r in cur.fetchall())
            conn.close()

            finished = [m for m in matches if m["status"] == "FT" and m["match_id"] not in done_ids]
            already_done = len([m for m in matches if m["status"] == "FT" and m["match_id"] in done_ids])
            if already_done > 0:
                print(f"[CHECKPOINTS] {already_done} partidos ya completados previamente (omitidos).")
            if limit_stats:
                finished = finished[:limit_stats]
            print(f"\n[STATS] Extrayendo estadísticas de {len(finished)} partidos pendientes...")
            for idx, m in enumerate(finished, 1):
                mid = m["match_id"]
                try:
                    t0 = time.time()
                    res = self.scrape_match_full_details_and_stats(mid, download_heatmaps=download_heatmaps)
                    elapsed = time.time() - t0
                    shots = len(res.get("shotmap") or []) if res else 0
                    print(f"  [{idx}/{len(finished)}] {m['home_team_name']} vs {m['away_team_name']} | Tiros: {shots} ({elapsed:.2f}s)")
                except Exception as e:
                    print(f"  [{idx}/{len(finished)}] [WARN] Error en partido {mid} ({m['home_team_name']} vs {m['away_team_name']}): {e}")
                time.sleep(0.1)

    def sync_country(self, country_name: str, download_stats: bool = True, limit_stats_per_league: Optional[int] = None, download_heatmaps: bool = True):
        """Sincroniza todas las competiciones y partidos de un país puntual."""
        conn = self._get_connection(timeout=30.0)
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT fotmob_league_id, fotmob_nombre, pais_nombre 
            FROM competiciones_fotmob 
            WHERE lower(pais_nombre) LIKE ? AND fotmob_league_id IS NOT NULL;
        """, (f"%{country_name.strip().lower()}%",))
        leagues = cur.fetchall()
        conn.close()

        if not leagues:
            print(f"[ERROR] No se encontraron ligas para el país '{country_name}'.")
            return

        print(f"\n>>> Sincronizando {len(leagues)} competiciones de {country_name.capitalize()}...")
        for lid, lname, p in leagues:
            print(f"\n--- {p} | {lname} (ID: {lid}) ---")
            matches = self.scrape_league_fixtures(lid)
            if download_stats:
                finished = [m for m in matches if m["status"] == "FT"]
                if limit_stats_per_league:
                    finished = finished[:limit_stats_per_league]
                for idx, m in enumerate(finished, 1):
                    self.scrape_match_full_details_and_stats(m["match_id"], download_heatmaps=download_heatmaps)
                    time.sleep(0.1)

    def sync_all_pipeline(self, download_stats: bool = True, limit_stats_per_league: Optional[int] = 5, download_heatmaps: bool = True):
        """
        Flujo maestro:
        1. Sincroniza fixtures de todas las 105 competiciones de Betplay.
        2. Enseguida descarga estadísticas avanzadas de los partidos finalizados.
        """
        print("=" * 65)
        print("  INICIANDO FLUJO MAESTRO FOTMOB: PARTIDOS + ESTADÍSTICAS")
        print("=" * 65)
        self.sync_all_fixtures()

        if download_stats:
            print("\n[PASO 2] Descargando estadísticas técnicas y avanzadas...")
            conn = self._get_connection(timeout=30.0)
            cur = conn.cursor()
            
            cur.execute("SELECT count(*) FROM checkpoints_fotmob_detalles WHERE estado = 'completado';")
            chk_ok = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) 
                FROM fotmob_partidos fp
                LEFT JOIN checkpoints_fotmob_detalles c ON fp.match_id = c.match_id
                WHERE fp.status = 'FT' AND (c.estado IS NULL OR c.estado != 'completado');
            """)
            pendientes_totales = cur.fetchone()[0]
            print(f"[CHECKPOINTS] Partidos ya completados en histórico: {chk_ok:,}")
            print(f"[INCREMENTAL] Partidos nuevos/pendientes por procesar: {pendientes_totales:,}")
            
            if pendientes_totales == 0:
                print("\n[✓] Todos los partidos finalizados ya tienen detalles y estadísticas completas en SQLite.")
                conn.close()
                return

            cur.execute("""
                SELECT DISTINCT cf.fotmob_league_id, cf.fotmob_nombre, cf.pais_nombre 
                FROM competiciones_fotmob cf 
                WHERE cf.ruta_optima = 'fotmob' AND cf.fotmob_league_id IS NOT NULL
                ORDER BY cf.pais_nombre, cf.fotmob_nombre;
            """)
            leagues = cur.fetchall()

            total_stats = 0
            for idx, (lid, lname, pais) in enumerate(leagues, 1):
                cur.execute("""
                    SELECT fp.match_id, fp.home_team_name, fp.away_team_name 
                    FROM fotmob_partidos fp
                    LEFT JOIN checkpoints_fotmob_detalles c ON fp.match_id = c.match_id
                    WHERE fp.fotmob_league_id = ? AND fp.status = 'FT' AND (c.estado IS NULL OR c.estado != 'completado')
                    ORDER BY fp.fecha_utc DESC
                """ + (f" LIMIT {int(limit_stats_per_league)}" if limit_stats_per_league else ""), (lid,))
                partidos = cur.fetchall()

                if not partidos:
                    continue

                print(f"\n[{idx}/{len(leagues)}] {pais} | {lname} (ID: {lid}) -> {len(partidos)} partidos pendientes...")
                for p_idx, (mid, h, a) in enumerate(partidos, 1):
                    try:
                        t0 = time.time()
                        res = self.scrape_match_full_details_and_stats(mid, download_heatmaps=download_heatmaps)
                        elapsed = time.time() - t0
                        shots = len(res.get("shotmap") or []) if res else 0
                        print(f"  [{p_idx}/{len(partidos)}] {h} vs {a} | Tiros: {shots} ({elapsed:.2f}s)")
                        if res:
                            total_stats += 1
                    except Exception as e:
                        print(f"  [{p_idx}/{len(partidos)}] [WARN] Error en partido {mid}: {e}")
                    time.sleep(0.1)

            conn.close()
            print(f"\n[FLUJO MAESTRO] Proceso completado exitosamente con {total_stats} partidos detallados almacenados.")

    def get_status_summary(self):
        """Imprime métricas y estado completo de FotMob en la base de datos."""
        conn = self._get_connection(timeout=30.0)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT fotmob_league_id) FROM competiciones_fotmob WHERE fotmob_league_id IS NOT NULL;")
        leagues = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM fotmob_partidos;")
        partidos = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM fotmob_partidos WHERE status = 'FT';")
        partidos_ft = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM checkpoints_fotmob_detalles WHERE estado = 'completado';")
        completados = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM fotmob_detalles_partido;")
        detalles = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM fotmob_partidos_estadisticas;")
        filas_stats = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM fotmob_partidos_incidentes;")
        filas_incidents = cur.fetchone()[0]
        conn.close()

        pct = (completados / partidos_ft * 100) if partidos_ft > 0 else 0
        print("=" * 65)
        print("               ESTADO DE DATOS FOTMOB (BETPLAY)                  ")
        print("=" * 65)
        print(f" Ligas Betplay sincronizadas:    {leagues}")
        print(f" Partidos indexados en DB:       {partidos:,}")
        print(f" Partidos finalizados (FT):      {partidos_ft:,}")
        print(f" Detalles técnicos extraídos:    {detalles:,}")
        print(f" Estadísticas de partido (filas):{filas_stats:,}")
        print(f" Incidentes y eventos en DB:     {filas_incidents:,}")
        print(f" Partidos con JSON completo:     {completados:,} ({pct:.1f}%)")
        print(f" Directorio de almacenamiento:   {FOTMOB_DETALLES_DIR}")
        print("=" * 65)

# ================= PRUEBA UNITARIA / DEMO =================
def run_tests():
    print("=== INICIANDO PRUEBAS DE INTEGRACIÓN FOTMOB - BETPLAY ===")
    scraper = FotMobScraper()
    
    # 1. Catálogo
    catalog = scraper.load_all_leagues()
    assert "countries" in catalog, "Catálogo debe incluir países"
    print("✓ [PASS] Catálogo maestro de FotMob cargado.")

    # 2. Mapeo
    mapping = scraper.map_betplay_to_fotmob()
    assert len(mapping) > 0, "Debe mapear competiciones"
    pl_entry = next((m for m in mapping if m["pais_nombre"] == "Inglaterra" and m["nombre_betplay"] == "Premier League"), None)
    assert pl_entry is not None and pl_entry["fotmob_league_id"] == 47, "Premier League debe tener ID 47"
    print(f"✓ [PASS] Mapeo verificado: {pl_entry['pais_nombre']} - {pl_entry['nombre_betplay']} -> FotMob ID {pl_entry['fotmob_league_id']}")

    # 3. Fixtures y Jornadas
    fixtures = scraper.scrape_league_fixtures(47, "premier-league")
    assert len(fixtures) >= 300, "Premier League debe tener 380 partidos"
    rounds = set(f["round"] for f in fixtures if f["round"])
    assert len(rounds) >= 30, f"Debe tener al menos 30 rondas distintas, encontradas: {len(rounds)}"
    print(f"✓ [PASS] Fixtures y jornadas verificados: {len(fixtures)} partidos y {len(rounds)} rondas.")

    # 4. Extracción completa de estadísticas y mapas de calor (5795478)
    full_data = scraper.scrape_match_full_details_and_stats("5795478", download_heatmaps=True)
    assert full_data is not None, "Datos completos no deben ser nulos"
    assert full_data["match"]["referee"]["name"] is not None, "Árbitro debe estar presente"
    assert full_data["match"]["stadium"]["name"] is not None, "Estadio debe estar presente"
    assert len(full_data["shotmap"]) > 0, "Debe tener tiros con coordenadas"
    assert full_data["heatmaps"] is not None and len(full_data["heatmaps"]["players"]) > 0, "Debe incluir mapas de calor"
    print(f"✓ [PASS] Dataset completo verificado: {full_data['match']['matchName']}")
    print(f"       - Tiros registrados: {len(full_data['shotmap'])}")
    print(f"       - Mapas de calor: {len(full_data['heatmaps']['players'])} jugadores")

    print("\n=== TODAS LAS PRUEBAS PASARON EXITOSAMENTE ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper FotMob con filtro Betplay")
    parser.add_argument("--test", action="store_true", help="Ejecuta pruebas de integridad")
    parser.add_argument("--map", action="store_true", help="Mapea competiciones Betplay a FotMob")
    parser.add_argument("--all", action="store_true", help="Descargar partidos y enseguida estadísticas de todas las competiciones")
    parser.add_argument("--fixtures-only", action="store_true", help="Sincronizar solo fixtures y partidos")
    parser.add_argument("--stats-only", action="store_true", help="Descargar solo estadísticas de partidos pendientes")
    parser.add_argument("--incremental", action="store_true", help="Descargar solo partidos pendientes sin re-sincronizar fixtures")
    parser.add_argument("--league", type=str, help="ID o nombre de liga para sincronizar")
    parser.add_argument("--pais", type=str, help="Nombre de país para sincronizar todas sus ligas")
    parser.add_argument("--match", type=str, help="ID de partido puntual para descargar detalles y estadísticas")
    parser.add_argument("--limit", type=int, help="Límite de partidos a procesar estadísticas")
    parser.add_argument("--status", action="store_true", help="Muestra el estado de datos en SQLite")
    parser.add_argument("--no-heatmaps", action="store_true", help="Omitir la descarga de mapas de calor")

    args = parser.parse_args()
    scraper = FotMobScraper()

    if args.status:
        scraper.get_status_summary()
    elif args.all:
        scraper.sync_all_pipeline(download_stats=True, limit_stats_per_league=args.limit, download_heatmaps=not args.no_heatmaps)
    elif args.fixtures_only:
        scraper.sync_all_fixtures()
    elif args.stats_only or args.incremental:
        scraper.sync_stats_pending(limit=args.limit, download_heatmaps=not args.no_heatmaps)
    elif args.league:
        scraper.sync_competition(args.league, download_stats=True, limit_stats=args.limit, download_heatmaps=not args.no_heatmaps)
    elif args.pais:
        scraper.sync_country(args.pais, download_stats=True, limit_stats_per_league=args.limit, download_heatmaps=not args.no_heatmaps)
    elif args.match:
        res = scraper.scrape_match_full_details_and_stats(args.match, download_heatmaps=not args.no_heatmaps)
        if res:
            print(json.dumps({
                "match": res["match"]["matchName"],
                "stadium": res["match"]["stadium"],
                "referee": res["match"]["referee"],
                "xg": res["xg"],
                "shots": len(res["shotmap"]),
                "heatmaps": len(res.get("heatmaps", {}).get("players", {})) if res.get("heatmaps") else 0
            }, indent=2, ensure_ascii=False))
    elif args.map:
        scraper.map_betplay_to_fotmob()
    elif args.test:
        run_tests()
    else:
        scraper.get_status_summary()
