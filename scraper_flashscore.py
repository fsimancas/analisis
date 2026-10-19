"""
Script para scrapear Flashscore y exportar a JSON y SQLite
siguiendo la estructura del DOM de Flashscore:
1. Menú lateral de países (#category-left-menu / .lmc__block a.lmc__element)
2. Despliegue de 'Mostrar más' (.lmc__itemMore)
3. Navegación a la URL del país y extracción de competiciones (.leftMenu / #mt a.leftMenu__href)
4. Despliegue de competiciones ocultas (.show-more / .leftMenu__item--hidden)
5. Filtrado por competiciones cubiertas por Betplay
6. Exportación en carpetas paises/, competiciones/ y base de datos SQLite.
"""

import os
import re
import json
import sqlite3
import unicodedata
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://www.flashscore.co"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAISES_DIR = os.path.join(BASE_DIR, 'paises')
COMPETICIONES_DIR = os.path.join(BASE_DIR, 'competiciones')
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')
MD_MAPPING = os.path.join(BASE_DIR, 'competiciones_betplay_flashscore.md')

os.makedirs(PAISES_DIR, exist_ok=True)
os.makedirs(COMPETICIONES_DIR, exist_ok=True)

def slugify(text):
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text

def extraer_paises_home():
    """
    Paso 1, 2 y 3:
    Extrae la lista de países desde el menú lateral (#category-left-menu).
    En el DOM de Flashscore, los elementos ocultos tras 'Mostrar más' (.lmc__itemMore)
    vienen ya inyectados en el HTML inicial o en el contenedor de categorías.
    """
    print(f"[*] Obteniendo países desde {BASE_URL}...")
    resp = httpx.get(BASE_URL, headers=HEADERS, follow_redirects=True, timeout=20.0)
    if resp.status_code != 200:
        raise RuntimeError(f"Error al conectar con {BASE_URL}: status {resp.status_code}")

    soup = BeautifulSoup(resp.text, 'html.parser')
    paises = {}

    # Selector del menú lateral
    menu = soup.find('div', id='category-left-menu')
    if menu:
        for a in menu.find_all('a', class_='lmc__element'):
            href = a.get('href', '').strip()
            name_span = a.find('span', class_='lmc__elementName')
            name = name_span.get_text(strip=True) if name_span else a.get_text(strip=True)
            if href and name and href.startswith('/futbol/'):
                full_url = urljoin(BASE_URL, href)
                slug = href.strip('/').split('/')[-1]
                paises[slug] = {
                    'nombre': name,
                    'slug': slug,
                    'link': full_url
                }

    # Respaldo con contenedor SEO en caso de renderizado diferido
    seo_menu = soup.find('div', class_='left_menu_categories_seo')
    if seo_menu:
        for a in seo_menu.find_all('a', href=True):
            href = a.get('href', '').strip()
            name = a.get_text(strip=True)
            parts = href.strip('/').split('/')
            if len(parts) == 2 and parts[0] == 'futbol' and name:
                slug = parts[1]
                if slug not in paises:
                    paises[slug] = {
                        'nombre': name,
                        'slug': slug,
                        'link': urljoin(BASE_URL, href)
                    }

    print(f"[+] Total países detectados en Flashscore: {len(paises)}")
    return paises

def extraer_competiciones_pais(pais_url, pais_slug):
    """
    Paso 4 y 5:
    Navega a la URL del país y extrae las competiciones desde:
    <div id="mt"> <div class="leftMenu"> <a class="leftMenu__href">...
    Tanto las visibles como las del bloque oculto (.leftMenu__item--hidden / 'Mostrar más').
    """
    resp = httpx.get(pais_url, headers=HEADERS, follow_redirects=True, timeout=15.0)
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    competiciones = []
    prefix = f"/futbol/{pais_slug}/"

    # Buscar en leftMenu__href (incluye elementos visibles y con clase leftMenu__item--hidden)
    seen = set()
    for a in soup.find_all('a', class_='leftMenu__href'):
        href = a.get('href', '')
        if href.startswith(prefix) and href != prefix:
            name = a.get_text(strip=True)
            if name and href not in seen:
                seen.add(href)
                competiciones.append({
                    'nombre_flashscore': name,
                    'link_flashscore': urljoin(BASE_URL, href)
                })

    return competiciones

def cargar_mapeo_betplay():
    """
    Carga el mapeo verificado desde competiciones_betplay_flashscore.md
    para filtrar únicamente las competiciones cubiertas por Betplay.
    """
    if not os.path.exists(MD_MAPPING):
        return []

    with open(MD_MAPPING, encoding='utf-8') as f:
        content = f.read()

    sections = re.split(r'\n(?=## )', content)
    datos = []
    for sec in sections:
        lines = sec.strip().splitlines()
        if not lines or not lines[0].startswith('## '):
            continue
        pais_bp = lines[0][3:].strip()
        
        country_link = ""
        country_fs = pais_bp
        for l in lines:
            if '- **Flashscore País**:' in l:
                m = re.search(r'\[(.*?)\]\((.*?)\)', l)
                if m:
                    country_fs = m.group(1)
                    country_link = m.group(2)
            elif pais_bp == 'Internacional':
                country_link = f"{BASE_URL}/futbol/"
                country_fs = "Internacional"

        in_table = False
        comps = []
        for l in lines:
            if '| Competición Betplay |' in l:
                in_table = True
                continue
            if in_table:
                if l.startswith('|---'):
                    continue
                if not l.startswith('|'):
                    in_table = False
                    continue
                parts = [p.strip() for p in l.split('|')[1:-1]]
                if len(parts) >= 3:
                    m = re.search(r'\[(.*?)\]\((.*?)\)', parts[2])
                    link = m.group(2) if m else (parts[2] if parts[2].startswith('http') else None)
                    comps.append({
                        'nombre_betplay': parts[0],
                        'nombre_flashscore': parts[1],
                        'link_flashscore': link
                    })

        datos.append({
            'nombre_betplay': pais_bp,
            'nombre_flashscore': country_fs,
            'slug': slugify(pais_bp),
            'link_flashscore': country_link,
            'competiciones': comps
        })
    return datos

def guardar_json_y_db(datos_mapeados):
    """
    Paso 6:
    Guarda la información en carpetas paises/, competiciones/ y en la base SQLite.
    """
    paises_json = []
    all_comps_json = []

    comp_id = 1
    for idx, p in enumerate(datos_mapeados):
        pais_id = idx + 1
        p_obj = {
            'id': pais_id,
            'nombre_betplay': p['nombre_betplay'],
            'nombre_flashscore': p['nombre_flashscore'],
            'slug': p['slug'],
            'link_flashscore': p['link_flashscore'],
            'total_competiciones': len(p['competiciones'])
        }
        paises_json.append(p_obj)

        # Archivo individual en paises/<slug>.json
        with open(os.path.join(PAISES_DIR, f"{p['slug']}.json"), 'w', encoding='utf-8') as f:
            json.dump(p_obj, f, ensure_ascii=False, indent=2)

        country_comps = []
        for c in p['competiciones']:
            comp_entry = {
                'id': comp_id,
                'pais_id': pais_id,
                'pais_nombre': p['nombre_betplay'],
                'pais_link': p['link_flashscore'],
                'nombre_betplay': c['nombre_betplay'],
                'nombre_flashscore': c['nombre_flashscore'],
                'link_flashscore': c['link_flashscore']
            }
            all_comps_json.append(comp_entry)
            country_comps.append(comp_entry)
            comp_id += 1

        # Archivo individual en competiciones/<slug>.json
        with open(os.path.join(COMPETICIONES_DIR, f"{p['slug']}.json"), 'w', encoding='utf-8') as f:
            json.dump(country_comps, f, ensure_ascii=False, indent=2)

    # Archivos consolidados
    with open(os.path.join(PAISES_DIR, 'paises.json'), 'w', encoding='utf-8') as f:
        json.dump(paises_json, f, ensure_ascii=False, indent=2)

    with open(os.path.join(COMPETICIONES_DIR, 'competiciones.json'), 'w', encoding='utf-8') as f:
        json.dump(all_comps_json, f, ensure_ascii=False, indent=2)

    print(f"[+] Archivos JSON guardados en '{PAISES_DIR}' y '{COMPETICIONES_DIR}'.")

    # Guardar en SQLite
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    cur.execute("DROP TABLE IF EXISTS competiciones;")
    cur.execute("DROP TABLE IF EXISTS paises;")

    cur.execute("""
    CREATE TABLE paises (
        id INTEGER PRIMARY KEY,
        nombre_betplay TEXT NOT NULL,
        nombre_flashscore TEXT NOT NULL,
        slug TEXT NOT NULL,
        link_flashscore TEXT NOT NULL,
        total_competiciones INTEGER NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE competiciones (
        id INTEGER PRIMARY KEY,
        pais_id INTEGER NOT NULL,
        pais_nombre TEXT NOT NULL,
        nombre_betplay TEXT NOT NULL,
        nombre_flashscore TEXT NOT NULL,
        link_flashscore TEXT,
        FOREIGN KEY (pais_id) REFERENCES paises (id) ON DELETE CASCADE
    );
    """)

    cur.execute("CREATE INDEX idx_competiciones_pais_id ON competiciones (pais_id);")

    cur.executemany("""
    INSERT INTO paises (id, nombre_betplay, nombre_flashscore, slug, link_flashscore, total_competiciones)
    VALUES (:id, :nombre_betplay, :nombre_flashscore, :slug, :link_flashscore, :total_competiciones);
    """, paises_json)

    cur.executemany("""
    INSERT INTO competiciones (id, pais_id, pais_nombre, nombre_betplay, nombre_flashscore, link_flashscore)
    VALUES (:id, :pais_id, :pais_nombre, :nombre_betplay, :nombre_flashscore, :link_flashscore);
    """, all_comps_json)

    conn.commit()
    conn.close()
    print(f"[+] Base de datos SQLite creada en '{DB_PATH}'")

def main():
    datos = cargar_mapeo_betplay()
    guardar_json_y_db(datos)

if __name__ == '__main__':
    main()
