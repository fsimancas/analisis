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
    "alemania": "germany", "arabia saudi": "saudi arabia", "argentina": "argentina", "armenia": "armenia",
    "australia": "australia", "austria": "austria", "azerbaiyan": "azerbaijan", "bahrein": "bahrain",
    "bangladesh": "bangladesh", "belgica": "belgium", "bielorrusia": "belarus", "bolivia": "bolivia",
    "bosnia y herzegovina": "bosnia-herzegovina", "botsuana": "botswana", "brasil": "brazil", "bulgaria": "bulgaria",
    "camboya": "cambodia", "canada": "canada", "chile": "chile", "china": "china", "chipre": "cyprus",
    "colombia": "colombia", "corea del sur": "south korea", "costa de marfil": "ivory coast", "costa rica": "costa rica",
    "croacia": "croatia", "dinamarca": "denmark", "ecuador": "ecuador", "egipto": "egypt", "el salvador": "el salvador",
    "emiratos arabes unidos": "united arab emirates", "escocia": "scotland", "eslovaquia": "slovakia",
    "eslovenia": "slovenia", "espana": "spain", "estados unidos": "united states", "estonia": "estonia",
    "etiopia": "ethiopia", "filipinas": "philippines", "finlandia": "finland", "fiyi": "fiji", "francia": "france",
    "gales": "wales", "georgia": "georgia", "ghana": "ghana", "gibraltar": "gibraltar", "grecia": "greece",
    "guatemala": "guatemala", "honduras": "honduras", "hungria": "hungary", "india": "india", "indonesia": "indonesia",
    "inglaterra": "england", "irlanda": "ireland", "irlanda del norte": "northern ireland", "islandia": "iceland",
    "israel": "israel", "italia": "italy", "jamaica": "jamaica", "japon": "japan", "jordania": "jordan",
    "kazajistan": "kazakhstan", "kenia": "kenya", "kosovo": "kosovo", "kuwait": "kuwait", "letonia": "latvia",
    "lituania": "lithuania", "luxemburgo": "luxembourg", "macedonia del norte": "north macedonia", "malasia": "malaysia",
    "marruecos": "morocco", "mexico": "mexico", "montenegro": "montenegro", "nicaragua": "nicaragua",
    "nigeria": "nigeria", "noruega": "norway", "nueva zelanda": "new zealand", "paises bajos": "netherlands",
    "holanda": "netherlands", "panama": "panama", "paraguay": "paraguay", "peru": "peru", "polonia": "poland",
    "portugal": "portugal", "qatar": "qatar", "republica checa": "czechia", "rumania": "romania", "rusia": "russia",
    "san marino": "san marino", "serbia": "serbia", "singapur": "singapore", "sudafrica": "south africa",
    "suecia": "sweden", "suiza": "switzerland", "tailandia": "thailand", "tunez": "tunisia", "turquia": "turkiye",
    "turkiye": "turkiye", "ucrania": "ukraine", "uruguay": "uruguay", "uzbekistan": "uzbekistan",
    "venezuela": "venezuela", "vietnam": "vietnam", "internacional": "international", "europa": "international",
    "sudamerica": "international", "mundo": "international"
}

# Aliases semánticos: (pais_norm, nombre_b_o_f_norm) -> fotmob_id
NAME_OVERRIDES = {
    # Internacional
    ("international", "champions league"): 42,
    ("international", "copa libertadores"): 45,
    ("international", "copa sudamericana"): 299,
    ("international", "uefa nations league"): 9806,
    ("international", "europa league"): 73,
    ("international", "caf champions league"): 526,
    ("international", "conference league"): 10216,
    ("international", "copa del mundo"): 77,
    ("international", "copa libertadores f"): 11021,
    ("international", "copa libertadores femenina"): 11021,
    ("international", "euro 2028"): 50,
    ("international", "eurocopa"): 50,

    # Colombia
    ("colombia", "liga betplay dimayor"): 274,
    ("colombia", "primera a"): 274,
    ("colombia", "copa betplay dimayor"): 9490,
    ("colombia", "copa colombia"): 9490,
    ("colombia", "torneo betplay dimayor"): 9125,
    ("colombia", "primera b"): 9125,

    # Argentina
    ("argentina", "liga profesional argentina"): 112,
    ("argentina", "liga profesional"): 112,
    ("argentina", "copa argentina"): 9305,
    ("argentina", "primera b metropolitana"): 9213,
    ("argentina", "primera nacional"): 8965,

    # Arabia Saudí
    ("saudi arabia", "liga profesional saudi"): 536,
    ("saudi arabia", "saudi professional league"): 536,
    ("saudi arabia", "1 division"): 10721,
    ("saudi arabia", "primera division"): 10721,

    # Bélgica
    ("belgium", "jupiler pro league"): 40,
    ("belgium", "beker van belgie"): 149,
    ("belgium", "copa"): 149,
    ("belgium", "challenger pro league"): 264,

    # Bolivia
    ("bolivia", "liga profesional bolivia"): 144,
    ("bolivia", "division profesional"): 144,

    # Brasil
    ("brazil", "copa de brasil"): 9067,
    ("brazil", "copa do brasil"): 9067,
    ("brazil", "serie a"): 268,
    ("brazil", "serie b"): 8814,
    ("brazil", "serie c"): 8971,
    ("brazil", "campeonato paulista"): 10244,
    ("brazil", "paulista a1"): 10244,
    ("brazil", "campeonato carioca"): 10272,
    ("brazil", "carioca"): 10272,
    ("brazil", "taca guanabara"): 10272,
    ("brazil", "campeonato mineiro"): 10273,
    ("brazil", "campeonato gaucho"): 10274,

    # Bulgaria
    ("bulgaria", "pfl 1"): 270,
    ("bulgaria", "parva liga"): 270,

    # Chile
    ("chile", "primera chile"): 273,
    ("chile", "primera division"): 273,
    ("chile", "primera b"): 9126,

    # China
    ("china", "liga uno"): 9137,
    ("china", "jia league"): 9137,
    ("china", "superliga china"): 120,
    ("china", "super league"): 120,

    # Ecuador
    ("ecuador", "liga pro"): 246,

    # Egipto
    ("egypt", "premier league"): 519,

    # Emiratos Árabes Unidos
    ("united arab emirates", "liga del golfo persico"): 538,
    ("united arab emirates", "uae league"): 538,

    # Eslovaquia
    ("slovakia", "super liga"): 176,
    ("slovakia", "nike liga"): 176,
    ("slovakia", "2 liga"): 8973,

    # Alemania
    ("germany", "bundesliga w"): 9676,
    ("germany", "bundesliga femenina"): 9676,
    ("germany", "frauen bundesliga"): 9676,
    ("germany", "2 bundesliga"): 146,
    ("germany", "3 liga"): 208,
    ("germany", "dfb pokal"): 209,
    ("germany", "bundesliga"): 54,

    # Italia
    ("italy", "serie a w"): 10178,
    ("italy", "serie a femenina"): 10178,
    ("italy", "serie a"): 55,
    ("italy", "serie b"): 86,

    # España
    ("spain", "la liga 2"): 140,
    ("spain", "laliga 2"): 140,
    ("spain", "laliga2"): 140,
    ("spain", "primera division f"): 9907,
    ("spain", "primera division femenina"): 9907,
    ("spain", "liga f"): 9907,
    ("spain", "la liga"): 87,
    ("spain", "laliga"): 87,
    ("spain", "copa del rey"): 138,
    ("spain", "primera federacion"): 8968,
    ("spain", "segunda federacion"): 9138,

    # Estados Unidos
    ("united states", "mls"): 130,
    ("united states", "mls next pro"): 10282,
    ("united states", "nwsl"): 9134,
    ("united states", "nwsl women"): 9134,
    ("united states", "usl championship"): 8972,
    ("united states", "usl league 1"): 9296,
    ("united states", "usl league one"): 9296,

    # Finlandia
    ("finland", "kansallinen liiga f"): 10174,
    ("finland", "kansallinen liiga femenina"): 10174,

    # Francia
    ("france", "ligue 1"): 53,
    ("france", "ligue 2"): 110,
    ("france", "copa de francia"): 134,
    ("france", "national"): 8970,

    # Grecia
    ("greece", "super liga"): 135,
    ("greece", "superliga"): 135,
    ("greece", "greece cup"): 145,

    # Hungría
    ("hungary", "liga hungara"): 212,
    ("hungary", "otp bank liga"): 212,
    ("hungary", "nb 2"): 9117,
    ("hungary", "merkantil bank liga"): 9117,

    # Inglaterra
    ("england", "premier league"): 47,
    ("england", "fa cup"): 132,
    ("england", "efl cup"): 133,
    ("england", "championship"): 48,
    ("england", "league one"): 108,
    ("england", "league two"): 109,
    ("england", "liga dos"): 109,
    ("england", "liga nacional"): 117,
    ("england", "national league"): 117,
    ("england", "superliga f"): 9227,
    ("england", "womens super league"): 9227,

    # Irlanda
    ("ireland", "1 division"): 218,
    ("ireland", "first division"): 218,
    ("ireland", "division de honor"): 126,
    ("ireland", "premier division"): 126,

    # Irlanda del Norte
    ("northern ireland", "nifl premiership"): 129,
    ("northern ireland", "premiership"): 129,

    # Islandia
    ("iceland", "urvalsdeild"): 215,
    ("iceland", "besta deild karla"): 215,

    # Japón
    ("japan", "j1 league"): 223,
    ("japan", "j2 league"): 8974,

    # México
    ("mexico", "liga mx"): 230,
    ("mexico", "liga mx femenil"): 9906,
    ("mexico", "liga de expansion mx"): 8976,

    # Nigeria
    ("nigeria", "premier liga"): 533,
    ("nigeria", "npfl"): 533,

    # Noruega
    ("norway", "eliteserien"): 59,
    ("norway", "obos ligaen"): 203,
    ("norway", "2 divisjon"): 204,
    ("norway", "toppserien"): 331,
    ("norway", "toppserien f"): 331,
    ("norway", "toppserien femenina"): 331,

    # Paraguay
    ("paraguay", "primera paraguay"): 199,
    ("paraguay", "copa de primera"): 199,

    # Perú
    ("peru", "primera division"): 131,
    ("peru", "liga 1"): 131,

    # Qatar
    ("qatar", "qatar stars league"): 535,
    ("qatar", "qsl"): 535,

    # República Checa
    ("czechia", "primera liga de la republica checa"): 122,
    ("czechia", "chance liga"): 122,
    ("czechia", "national football league"): 253,
    ("czechia", "chnl"): 253,

    # Serbia
    ("serbia", "super liga"): 182,

    # Sudáfrica
    ("south africa", "psl"): 537,
    ("south africa", "betway premiership"): 537,

    # Suecia
    ("sweden", "allsvenskan"): 67,
    ("sweden", "superettan"): 168,
    ("sweden", "obos damallsvenskan f"): 9089,
    ("sweden", "allsvenskan femenina"): 9089,
    ("sweden", "elitettan femeninos"): 10308,
    ("sweden", "elitettan"): 10308,

    # Tailandia
    ("thailand", "thai league 1"): 8984,

    # Turquía
    ("turkiye", "super liga"): 71,
    ("turkiye", "super lig"): 71,
    ("turkiye", "1 liga"): 165,
    ("turkiye", "1 lig"): 165,

    # Uruguay
    ("uruguay", "primera division"): 161,
    ("uruguay", "liga auf uruguaya"): 161,

    # Venezuela
    ("venezuela", "liga futve"): 339,
    ("venezuela", "primera division"): 339,
}

# Ligas que son EXCLUSIVAS de Flashscore (sin cobertura en FotMob)
EXCLUSIVAS_FLASHSCORE_NAMES = [
    "especiales", "esports", "reserva", "reserves", "tercera", "segunda rfef", "3 liga",
    "regional este", "eerste nationale", "yi league", "division 2", "jfl", "nadeshiko",
    "1 lyga", "super league malawi", "nicaragua", "jamaica", "jordan", "mfc",
    "u19", "sub 19", "sub 21", "northern league division one", "gaucho 2"
]

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

    nb_norm = norm(nom_b)
    nf_norm = norm(nom_f)

    # 1. Chequear si es claramente exclusiva de Flashscore
    is_exclusive_fs = False
    for exc in EXCLUSIVAS_FLASHSCORE_NAMES:
        if exc in nb_norm or exc in nf_norm:
            is_exclusive_fs = True
            break
    
    match_fid = None
    if not is_exclusive_fs:
        # 2. Chequear en NAME_OVERRIDES (ordenados por longitud descendente para especificidad)
        sorted_overrides = sorted(NAME_OVERRIDES.items(), key=lambda x: len(x[0][1]), reverse=True)
        for (co, na), fid in sorted_overrides:
            if co == target_fm_country:
                if na == nb_norm or na == nf_norm or na in nb_norm or na in nf_norm:
                    match_fid = fid
                    break

        # 3. Si no, buscar dentro del catálogo FotMob de ese país
        if not match_fid:
            leagues_in_country = fotmob_by_country.get(target_fm_country, [])
            for l in leagues_in_country:
                ln_norm = norm(l['name'])
                if ln_norm == nb_norm or ln_norm == nf_norm:
                    match_fid = l['id']
                    break
            if not match_fid:
                for l in leagues_in_country:
                    ln_norm = norm(l['name'])
                    if ln_norm in nb_norm or nb_norm in ln_norm or ln_norm in nf_norm or nf_norm in ln_norm:
                        match_fid = l['id']
                        break

    if match_fid and match_fid in fotmob_by_id:
        fm_obj = fotmob_by_id[match_fid]
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
            "ruta_optima": "fotmob"
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
            "ruta_optima": "flashscore"
        })

fotmob_items = [r for r in results if r['ruta_optima'] == 'fotmob']
flashscore_items = [r for r in results if r['ruta_optima'] == 'flashscore']

print(f"Total competiciones procesadas: {len(results)}")
print(f"Total enrutadas a FotMob: {len(fotmob_items)} ({len(fotmob_items)/len(results)*100:.1f}%)")
print(f"Total enrutadas a Flashscore: {len(flashscore_items)} ({len(flashscore_items)/len(results)*100:.1f}%)")

with open('competiciones_betplay_flashscore_fotmob_curated.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
