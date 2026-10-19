import os
import re
import json
import sqlite3
import unicodedata

BASE_DIR = r'c:\Users\SIMANCAS\Documents\rey'
MD_PATH = os.path.join(BASE_DIR, 'competiciones_betplay_flashscore.md')
PAISES_DIR = os.path.join(BASE_DIR, 'paises')
COMPETICIONES_DIR = os.path.join(BASE_DIR, 'competiciones')
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')

os.makedirs(PAISES_DIR, exist_ok=True)
os.makedirs(COMPETICIONES_DIR, exist_ok=True)

def slugify(text):
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text).strip('-')
    return text

def parse_markdown():
    with open(MD_PATH, encoding='utf-8') as f:
        content = f.read()

    sections = re.split(r'\n(?=## )', content)
    paises = []
    
    for sec in sections:
        lines = sec.strip().splitlines()
        if not lines or not lines[0].startswith('## '):
            continue
        country_name = lines[0][3:].strip()
        
        country_link = ""
        country_fs_name = country_name
        for l in lines:
            if '- **Flashscore País**:' in l:
                m = re.search(r'\[(.*?)\]\((.*?)\)', l)
                if m:
                    country_fs_name = m.group(1)
                    country_link = m.group(2)
            elif country_name == 'Internacional':
                country_link = "https://www.flashscore.co/futbol/"
                country_fs_name = "Internacional"

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
                    bp_comp = parts[0]
                    fs_comp = parts[1]
                    fs_link_col = parts[2]
                    
                    m = re.search(r'\[(.*?)\]\((.*?)\)', fs_link_col)
                    if m:
                        link = m.group(2)
                    else:
                        link = fs_link_col if fs_link_col.startswith('http') else None
                    
                    comps.append({
                        'nombre_betplay': bp_comp,
                        'nombre_flashscore': fs_comp,
                        'link_flashscore': link
                    })

        paises.append({
            'nombre_betplay': country_name,
            'nombre_flashscore': country_fs_name,
            'slug': slugify(country_name),
            'link_flashscore': country_link,
            'competiciones': comps
        })
        
    return paises

def export_json(paises):
    # 1. Paises consolidado
    paises_summary = [
        {
            'id': idx + 1,
            'nombre_betplay': p['nombre_betplay'],
            'nombre_flashscore': p['nombre_flashscore'],
            'slug': p['slug'],
            'link_flashscore': p['link_flashscore'],
            'total_competiciones': len(p['competiciones'])
        }
        for idx, p in enumerate(paises)
    ]
    
    with open(os.path.join(PAISES_DIR, 'paises.json'), 'w', encoding='utf-8') as f:
        json.dump(paises_summary, f, ensure_ascii=False, indent=2)

    # 2. Paises individuales
    for idx, p in enumerate(paises):
        country_obj = {
            'id': idx + 1,
            'nombre_betplay': p['nombre_betplay'],
            'nombre_flashscore': p['nombre_flashscore'],
            'slug': p['slug'],
            'link_flashscore': p['link_flashscore'],
            'total_competiciones': len(p['competiciones'])
        }
        with open(os.path.join(PAISES_DIR, f"{p['slug']}.json"), 'w', encoding='utf-8') as f:
            json.dump(country_obj, f, ensure_ascii=False, indent=2)

    # 3. Competiciones consolidado
    all_comps = []
    comp_id = 1
    for idx, p in enumerate(paises):
        pais_id = idx + 1
        for c in p['competiciones']:
            all_comps.append({
                'id': comp_id,
                'pais_id': pais_id,
                'pais_nombre': p['nombre_betplay'],
                'pais_link': p['link_flashscore'],
                'nombre_betplay': c['nombre_betplay'],
                'nombre_flashscore': c['nombre_flashscore'],
                'link_flashscore': c['link_flashscore']
            })
            comp_id += 1

    with open(os.path.join(COMPETICIONES_DIR, 'competiciones.json'), 'w', encoding='utf-8') as f:
        json.dump(all_comps, f, ensure_ascii=False, indent=2)

    # 4. Competiciones por país
    for idx, p in enumerate(paises):
        pais_id = idx + 1
        country_comps = [
            {
                'pais_id': pais_id,
                'pais_nombre': p['nombre_betplay'],
                'nombre_betplay': c['nombre_betplay'],
                'nombre_flashscore': c['nombre_flashscore'],
                'link_flashscore': c['link_flashscore']
            }
            for c in p['competiciones']
        ]
        with open(os.path.join(COMPETICIONES_DIR, f"{p['slug']}.json"), 'w', encoding='utf-8') as f:
            json.dump(country_comps, f, ensure_ascii=False, indent=2)

    print(f"Exported JSON files to '{PAISES_DIR}' and '{COMPETICIONES_DIR}'")
    return paises_summary, all_comps

def build_sqlite(paises_summary, all_comps):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA foreign_keys = ON;")

    # Schema
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

    # Insert paises
    cur.executemany("""
    INSERT INTO paises (id, nombre_betplay, nombre_flashscore, slug, link_flashscore, total_competiciones)
    VALUES (:id, :nombre_betplay, :nombre_flashscore, :slug, :link_flashscore, :total_competiciones);
    """, paises_summary)

    # Insert competiciones
    cur.executemany("""
    INSERT INTO competiciones (id, pais_id, pais_nombre, nombre_betplay, nombre_flashscore, link_flashscore)
    VALUES (:id, :pais_id, :pais_nombre, :nombre_betplay, :nombre_flashscore, :link_flashscore);
    """, all_comps)

    conn.commit()
    conn.close()
    print(f"Database created successfully at '{DB_PATH}'")

if __name__ == '__main__':
    paises = parse_markdown()
    paises_summary, all_comps = export_json(paises)
    build_sqlite(paises_summary, all_comps)
