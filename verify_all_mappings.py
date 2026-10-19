import json
import sqlite3
import unicodedata
import re
import urllib.request
import time

def norm(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return " ".join(text.split())

# 1. Cargar catálogo FotMob
with open('all_leagues_fotmob.json', 'r', encoding='utf-8') as f:
    fm_raw = json.load(f)

# Indexar por id y por (country_norm, name_norm)
fotmob_by_id = {}
fotmob_by_country = {}

def register(item, cname):
    lid = item['id']
    name = item['name']
    url = f"https://www.fotmob.com{item.get('pageUrl', '')}"
    ccode = item.get('ccode', '')
    obj = {'id': lid, 'name': name, 'country': cname, 'url': url, 'ccode': ccode}
    fotmob_by_id[lid] = obj
    c_norm = norm(cname)
    if c_norm not in fotmob_by_country:
        fotmob_by_country[c_norm] = []
    fotmob_by_country[c_norm].append(obj)

for item in fm_raw.get('popular', []):
    register(item, 'Popular')

for c in fm_raw.get('international', []):
    cname = c.get('name', 'International')
    for item in c.get('leagues', []):
        register(item, 'International')

for c in fm_raw.get('countries', []):
    cname = c.get('name', '')
    for item in c.get('leagues', []):
        register(item, cname)

PAIS_MAP = {
    "alemania": "germany",
    "arabia saudi": "saudi arabia",
    "argentina": "argentina",
    "armenia": "armenia",
    "australia": "australia",
    "austria": "austria",
    "azerbaiyan": "azerbaijan",
    "bahrein": "bahrain",
    "bangladesh": "bangladesh",
    "belgica": "belgium",
    "bielorrusia": "belarus",
    "bolivia": "bolivia",
    "bosnia y herzegovina": "bosnia and herzegovina",
    "botsuana": "botswana",
    "brasil": "brazil",
    "bulgaria": "bulgaria",
    "camboya": "cambodia",
    "canada": "canada",
    "chile": "chile",
    "china": "china",
    "chipre": "cyprus",
    "colombia": "colombia",
    "corea del sur": "south korea",
    "costa de marfil": "ivory coast",
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
    "etiopia": "ethiopia",
    "filipinas": "philippines",
    "finlandia": "finland",
    "fiyi": "fiji",
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
    "turquia": "turkey",
    "turkiye": "turkey",
    "ucrania": "ukraine",
    "uruguay": "uruguay",
    "uzbekistan": "uzbekistan",
    "venezuela": "venezuela",
    "vietnam": "vietnam",
    "internacional": "international",
    "europa": "international",
    "sudamerica": "international",
    "mundo": "international"
}

# Overrides explícitos verificados 100% por competicion_id en DB
EXPLICIT_OVERRIDES = {
    # Internacionales
    2: 42,     # Champions League -> Champions League (42)
    3: 45,     # Copa Libertadores -> Copa Libertadores (45)
    4: 299,    # Copa Sudamericana -> Copa Sudamericana (299)
    5: 9806,   # UEFA Nations League -> UEFA Nations League A (9806)
    6: 73,     # Europa League -> Europa League (73)
    7: 526,    # CAF Champions League Qualification / CAF CL -> CAF Champions League (526)
    8: 10216,  # Conference League -> Conference League (10216)
    9: 77,     # Copa del Mundo 2030 -> World Cup (77)
    10: 11021, # Copa Libertadores (F) -> Copa Libertadores Femenina (11021)
    11: 50,    # Euro 2028 -> EURO (50)
    1: None,   # Especiales Betplay -> Flashscore / None
    12: None,  # Esports Futbol -> Flashscore / None

    # Colombia
    61: 274,   # Liga BetPlay Dimayor -> Primera A (274)
    62: 9490,  # Copa BetPlay Dimayor -> Copa Colombia (9490)
    63: 9125,  # Torneo BetPlay Dimayor -> Primera B (9125)

    # Argentina
    20: 112,   # Liga Profesional -> Liga Profesional (112)
    21: 9305,  # Copa Argentina -> Copa Argentina (9305)
    22: 9213,  # Primera B Metropolitana -> Primera B Metr. (9213)
    23: 8965,  # Primera Nacional -> Primera B Nacional (8965)
    24: None,  # Reserves Leagues U23 -> Flashscore (None)
    25: None,  # Torneo Federal A -> Flashscore (None)

    # Brasil
    45: 268,   # Serie A -> Serie A (268)
    46: 8814,  # Serie B -> Serie B (8814)
    47: 9046,  # Copa de Brasil -> Copa do Brasil (9046)
    48: 9172,  # Campeonato Paulista -> Paulista A1 (9172)
    49: 9173,  # Campeonato Carioca -> Carioca Taca Guanabara (9173)

    # España
    86: 87,    # LaLiga -> LaLiga (87)
    87: 140,   # LaLiga2 -> LaLiga2 (140)
    88: 138,   # Copa del Rey -> Copa del Rey (138)
    89: 8968,  # Primera Federación -> Primera Federación (8968)
    90: 9138,  # Segunda Federación -> Segunda Federación (9138)
    91: None,  # Tercera RFEF Grupo 1 -> Flashscore
    92: None,  # Tercera RFEF Grupo 2 -> Flashscore
    93: None,  # Tercera RFEF Grupo 3 -> Flashscore
    94: None,  # Tercera RFEF Grupo 4 -> Flashscore
    95: None,  # Tercera RFEF Grupo 5 -> Flashscore
    96: None,  # Tercera RFEF Grupo 6 -> Flashscore
    97: None,  # Tercera RFEF Grupo 7 -> Flashscore
    98: None,  # Tercera RFEF Grupo 8 -> Flashscore
    99: None,  # Tercera RFEF Grupo 9 -> Flashscore
    100: None, # Tercera RFEF Grupo 10 -> Flashscore
    101: 9907, # Liga F -> Liga F (9907)

    # Inglaterra
    124: 47,   # Premier League -> Premier League (47)
    125: 132,  # FA Cup -> FA Cup (132)
    126: 133,  # EFL Cup -> EFL Cup (133)
    127: 48,   # Championship -> Championship (48)
    128: 108,  # League One -> League One (108)
    129: 109,  # League Two -> League Two (109)
    130: 9484, # National League -> National League (9484)
    131: None, # Sub-21 Premier League 2 -> Flashscore
    132: 9811, # WSL Femenina -> Women's Super League (9811)
}

conn = sqlite3.connect('betplay_flashscore.db')
c = conn.cursor()
c.execute("SELECT id, pais_nombre, nombre_betplay, nombre_flashscore, link_flashscore FROM competiciones ORDER BY id;")
db_comps = c.fetchall()
conn.close()

results = []
for comp in db_comps:
    cid, pais, nom_b, nom_f, link = comp
    pais_clean = norm(pais)
    target_fm_country = PAIS_MAP.get(pais_clean, pais_clean)

    # Si hay override manual
    if cid in EXPLICIT_OVERRIDES:
        override_id = EXPLICIT_OVERRIDES[cid]
        if override_id is not None and override_id in fotmob_by_id:
            fm_obj = fotmob_by_id[override_id]
            results.append({
                "competicion_id": cid,
                "pais_nombre": pais,
                "nombre_betplay": nom_b,
                "nombre_flashscore": nom_f,
                "link_flashscore": link,
                "fotmob_league_id": fm_obj['id'],
                "fotmob_nombre": fm_obj['name'],
                "fotmob_url": fm_obj['url'],
                "fotmob_ccode": fm_obj['ccode'],
                "ruta_optima": "fotmob",
                "metodo": "override_manual"
            })
            continue
        elif override_id is None:
            results.append({
                "competicion_id": cid,
                "pais_nombre": pais,
                "nombre_betplay": nom_b,
                "nombre_flashscore": nom_f,
                "link_flashscore": link,
                "fotmob_league_id": None,
                "fotmob_nombre": None,
                "fotmob_url": None,
                "fotmob_ccode": None,
                "ruta_optima": "flashscore",
                "metodo": "override_flashscore"
            })
            continue

    # Si no, buscar dentro de las ligas del MISMO PAÍS en FotMob
    leagues_in_country = fotmob_by_country.get(target_fm_country, [])
    
    # También chequear si está en 'popular'
    pop_leagues = fotmob_by_country.get('popular', [])

    nb_norm = norm(nom_b)
    nf_norm = norm(nom_f)

    match = None
    # 1. Match exacto de nombre en el país
    for l in leagues_in_country:
        ln_norm = norm(l['name'])
        if ln_norm == nb_norm or ln_norm == nf_norm:
            match = l
            break

    # 2. Match de palabras clave en el país
    if not match:
        for l in leagues_in_country:
            ln_norm = norm(l['name'])
            # Coincidencia parcial estricta dentro del mismo país
            if ln_norm in nb_norm or nb_norm in ln_norm or ln_norm in nf_norm or nf_norm in ln_norm:
                match = l
                break

    # 3. Match en popular si coincide país
    if not match:
        for l in pop_leagues:
            ln_norm = norm(l['name'])
            if ln_norm == nb_norm or ln_norm == nf_norm:
                match = l
                break

    if match:
        results.append({
            "competicion_id": cid,
            "pais_nombre": pais,
            "nombre_betplay": nom_b,
            "nombre_flashscore": nom_f,
            "link_flashscore": link,
            "fotmob_league_id": match['id'],
            "fotmob_nombre": match['name'],
            "fotmob_url": match['url'],
            "fotmob_ccode": match['ccode'],
            "ruta_optima": "fotmob",
            "metodo": "pais_estricto"
        })
    else:
        results.append({
            "competicion_id": cid,
            "pais_nombre": pais,
            "nombre_betplay": nom_b,
            "nombre_flashscore": nom_f,
            "link_flashscore": link,
            "fotmob_league_id": None,
            "fotmob_nombre": None,
            "fotmob_url": None,
            "fotmob_ccode": None,
            "ruta_optima": "flashscore",
            "metodo": "sin_cobertura_fotmob"
        })

fotmob_total = len([r for r in results if r['ruta_optima'] == 'fotmob'])
flashscore_total = len([r for r in results if r['ruta_optima'] == 'flashscore'])

print(f"Total procesadas: {len(results)}")
print(f"Total enrutadas a FotMob: {fotmob_total}")
print(f"Total enrutadas a Flashscore: {flashscore_total}")

with open('mapping_verificado_test.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
