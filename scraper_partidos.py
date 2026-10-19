"""
Script para extraer Resultados (partidos jugados) y Fixtures (partidos por jugar)
de Flashscore usando Playwright con Microsoft Edge.

Flujo:
1. Accede a las pestañas de Resultados (/resultados/) y Partidos (/partidos/)
2. Detecta y pulsa repetidamente el botón "Mostrar más partidos" (.wcl-footer__button_OauhJ / [data-testid='wcl-section-footer'])
   hasta cargar la totalidad de partidos de la temporada.
3. Extrae la jornada (event__round), fecha/hora (event__stageTime), equipos (event__homeParticipant, event__awayParticipant),
   marcador (event__score--home, event__score--away) y enlace del partido.
4. Exporta a JSON en la carpeta 'partidos/' y persiste en la base SQLite 'betplay_flashscore.db'.
"""

import os
import re
import json
import time
import sqlite3
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')
PARTIDOS_DIR = os.path.join(BASE_DIR, 'partidos')

os.makedirs(PARTIDOS_DIR, exist_ok=True)

def fetch_html_with_clicks(url, label="partidos"):
    print(f"[*] Navegando a {url} ({label})...")
    with sync_playwright() as p:
        # Usamos el canal nativo de Microsoft Edge ya disponible en Windows
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        
        try:
            page.wait_for_selector(".event__match", timeout=20000)
        except Exception:
            print(f"[!] No se encontraron partidos iniciales en {url}")
            browser.close()
            return ""

        # Loop para pulsar "Mostrar más partidos"
        click_count = 0
        max_clicks = 15
        while click_count < max_clicks:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.2)
            
            btn = page.query_selector("[data-testid='wcl-section-footer'] button")
            if btn and btn.is_visible():
                text = btn.inner_text().strip()
                if "Mostrar más partidos" in text:
                    print(f"    -> Pulsando 'Mostrar más partidos' (clic #{click_count + 1})...")
                    btn.click()
                    time.sleep(2.0)
                    click_count += 1
                    continue
            break
            
        print(f"[+] Finalizada la carga de {label}: {click_count} clics adicionales realizados.")
        html = page.content()
        browser.close()
        return html

def parse_matches_html(html, match_type):
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    container = soup.find('div', class_=lambda c: c and 'sportName' in c and 'soccer' in c) or soup
    
    matches = []
    current_round = "General"
    seen_ids = set()

    for el in container.find_all(['div'], recursive=True):
        classes = el.get('class', [])
        
        # Detección de la jornada o ronda
        if any('event__round' in c for c in classes):
            round_text = el.get_text(strip=True)
            if round_text:
                current_round = round_text
                
        # Detección de fila de partido
        if any('event__match' in c for c in classes) and el.get('id', '').startswith('g_'):
            match_id = el.get('id', '').replace('g_1_', '')
            if match_id in seen_ids:
                continue
            seen_ids.add(match_id)

            # Link del partido
            link_tag = el.find('a', class_='eventRowLink')
            link = link_tag.get('href') if link_tag else None
            if link and link.startswith('/'):
                link = f"https://www.flashscore.co{link}"

            # Fecha y Hora / Estado
            time_tag = el.find(class_=lambda c: c and 'event__stageTime' in c)
            date_time = time_tag.get_text(strip=True) if time_tag else ""

            # Participantes
            home_tag = el.find(class_=lambda c: c and 'event__homeParticipant' in c)
            away_tag = el.find(class_=lambda c: c and 'event__awayParticipant' in c)
            home_team = home_tag.get_text(strip=True) if home_tag else ""
            away_team = away_tag.get_text(strip=True) if away_tag else ""

            # Marcador
            score_home_tag = el.find(class_=lambda c: c and 'event__score--home' in c)
            score_away_tag = el.find(class_=lambda c: c and 'event__score--away' in c)
            
            score_home_raw = score_home_tag.get_text(strip=True) if score_home_tag else None
            score_away_raw = score_away_tag.get_text(strip=True) if score_away_tag else None
            
            score_home = int(score_home_raw) if score_home_raw and score_home_raw.isdigit() else None
            score_away = int(score_away_raw) if score_away_raw and score_away_raw.isdigit() else None

            matches.append({
                'id': match_id,
                'tipo': match_type,
                'jornada': current_round,
                'fecha_hora': date_time,
                'equipo_local': home_team,
                'equipo_visitante': away_team,
                'goles_local': score_home,
                'goles_visitante': score_away,
                'link': link
            })

    return matches

def save_matches_data(slug, competicion_id, resultados, partidos):
    # 1. Exportar JSONs
    res_path = os.path.join(PARTIDOS_DIR, f"{slug}_resultados.json")
    par_path = os.path.join(PARTIDOS_DIR, f"{slug}_partidos.json")
    all_path = os.path.join(PARTIDOS_DIR, f"{slug}_todos.json")

    with open(res_path, 'w', encoding='utf-8') as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    with open(par_path, 'w', encoding='utf-8') as f:
        json.dump(partidos, f, ensure_ascii=False, indent=2)

    all_matches = resultados + partidos
    with open(all_path, 'w', encoding='utf-8') as f:
        json.dump(all_matches, f, ensure_ascii=False, indent=2)

    print(f"[+] JSON guardados en '{PARTIDOS_DIR}':")
    print(f"    - {len(resultados)} resultados en {slug}_resultados.json")
    print(f"    - {len(partidos)} próximos en {slug}_partidos.json")
    print(f"    - {len(all_matches)} total en {slug}_todos.json")

    # 2. Persistir en SQLite
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS partidos (
        id TEXT PRIMARY KEY,
        competicion_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
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

    # Insertar o reemplazar
    records = [
        (
            m['id'],
            competicion_id,
            m['tipo'],
            m['jornada'],
            m['fecha_hora'],
            m['equipo_local'],
            m['equipo_visitante'],
            m['goles_local'],
            m['goles_visitante'],
            m['link']
        )
        for m in all_matches
    ]

    cur.executemany("""
    INSERT OR REPLACE INTO partidos (
        id, competicion_id, tipo, jornada, fecha_hora, equipo_local, equipo_visitante, goles_local, goles_visitante, link
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, records)

    conn.commit()
    conn.close()
    print(f"[+] {len(all_matches)} partidos insertados/actualizados en {DB_PATH}")

def main():
    # Buscamos LaLiga EA Sports en la base de datos
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, nombre_flashscore, link_flashscore FROM competiciones WHERE link_flashscore LIKE '%laliga-ea-sports%' LIMIT 1;")
    row = cur.fetchone()
    conn.close()

    if not row:
        print("[!] No se encontró LaLiga EA Sports en la base de datos.")
        return

    comp_id, comp_name, comp_link = row
    print(f"[+] Procesando competición #{comp_id}: {comp_name} ({comp_link})")

    url_resultados = comp_link.rstrip('/') + '/resultados/'
    url_partidos = comp_link.rstrip('/') + '/partidos/'

    # 1. Resultados (jugados)
    html_res = fetch_html_with_clicks(url_resultados, label="Resultados jugados")
    resultados = parse_matches_html(html_res, match_type="resultado")

    # 2. Partidos (por jugar)
    html_par = fetch_html_with_clicks(url_partidos, label="Partidos por jugar")
    partidos = parse_matches_html(html_par, match_type="proximo")

    # 3. Guardar en JSON y SQLite
    save_matches_data("laliga-ea-sports", comp_id, resultados, partidos)

if __name__ == '__main__':
    main()
