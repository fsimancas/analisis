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

fotmob_by_id = {}
fotmob_by_country = {}

def add_league(item, country):
    lid = item['id']
    name = item['name']
    url = f"https://www.fotmob.com{item.get('pageUrl', '')}"
    ccode = item.get('ccode', '')
    obj = {'id': lid, 'name': name, 'country': country, 'url': url, 'ccode': ccode}
    fotmob_by_id[lid] = obj
    c_norm = norm(country)
    if c_norm not in fotmob_by_country:
        fotmob_by_country[c_norm] = []
    fotmob_by_country[c_norm].append(obj)

for item in fm_raw.get('popular', []):
    add_league(item, 'Popular')

for c in fm_raw.get('international', []):
    cname = c.get('name', 'International')
    for item in c.get('leagues', []):
        add_league(item, 'International')

for c in fm_raw.get('countries', []):
    cname = c.get('name', '')
    for item in c.get('leagues', []):
        add_league(item, cname)

print(f"Total ligas unicas en FotMob: {len(fotmob_by_id)}")

# 2. Diccionario de traduccion de paises Betplay -> FotMob
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
    "asia": "international",
    "africa": "international",
    "norteamerica": "international"
}

# 3. Leer competiciones de Betplay de SQLite
conn = sqlite3.connect('betplay_flashscore.db')
c = conn.cursor()
c.execute("SELECT id, pais_nombre, nombre_betplay, nombre_flashscore, link_flashscore FROM competiciones ORDER BY id;")
db_comps = c.fetchall()
conn.close()

print(f"Total competiciones a enrutar: {len(db_comps)}")
