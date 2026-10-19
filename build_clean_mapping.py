import json
import sqlite3
import unicodedata
import re
import urllib.request
import gzip
import time

def norm(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text

with open('all_leagues_fotmob.json', 'r', encoding='utf-8') as f:
    fm_raw = json.load(f)

# Collect all authentic leagues from FotMob raw
fotmob_by_country = {}
all_fotmob_leagues = {}

def add_league(country, item):
    lid = item['id']
    entry = {
        'id': lid,
        'name': item['name'],
        'country': country,
        'url': f"https://www.fotmob.com{item.get('pageUrl', '')}",
        'ccode': item.get('ccode', '')
    }
    all_fotmob_leagues[lid] = entry
    c_norm = norm(country)
    fotmob_by_country.setdefault(c_norm, []).append(entry)

for l in fm_raw.get('popular', []):
    add_league('Popular', l)

for c in fm_raw.get('international', []):
    for l in c.get('leagues', []):
        add_league('International', l)

for c in fm_raw.get('countries', []):
    cname = c.get('name', '')
    for l in c.get('leagues', []):
        add_league(cname, l)

print(f"Total authentic leagues indexed: {len(all_fotmob_leagues)}")

# Translation of country names between Betplay (Spanish) and FotMob (English)
COUNTRY_MAP = {
    "alemania": "germany",
    "arabia saudi": "saudi arabia",
    "argelia": "algeria",
    "argentina": "argentina",
    "armenia": "armenia",
    "australia": "australia",
    "austria": "austria",
    "bahrein": "bahrain",
    "belgica": "belgium",
    "bolivia": "bolivia",
    "bosnia  herzegovina": "bosnia-herzegovina",
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
    "etiopia": "ethiopia",
    "filipinas": "philippines",
    "finlandia": "finland",
    "francia": "france",
    "gales": "wales",
    "georgia": "georgia",
    "ghana": "ghana",
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
    "letonia": "latvia",
    "lituania": "lithuania",
    "malawi": "malawi",
    "mexico": "mexico",
    "nicaragua": "nicaragua",
    "nigeria": "nigeria",
    "noruega": "norway",
    "paises bajos": "netherlands",
    "paraguay": "paraguay",
    "peru": "peru",
    "polonia": "poland",
    "portugal": "portugal",
    "qatar": "qatar",
    "republica checa": "czech republic",
    "rumania": "romania",
    "serbia": "serbia",
    "sudafrica": "south africa",
    "suecia": "sweden",
    "suiza": "switzerland",
    "tailandia": "thailand",
    "tanzania": "tanzania",
    "turquia": "turkiye",
    "ucrania": "ukraine",
    "uruguay": "uruguay",
    "venezuela": "venezuela",
    "internacional": "international"
}

conn = sqlite3.connect('betplay_flashscore.db')
c = conn.cursor()
c.execute("SELECT id, pais_id, pais_nombre, nombre_betplay, nombre_flashscore, link_flashscore FROM competiciones ORDER BY id;")
betplay_comps = c.fetchall()

print(f"Total competiciones en Betplay: {len(betplay_comps)}")

# Explicit handcrafted overrides for accurate disambiguation
EXPLICIT_OVERRIDES = {
    # Internacional
    2: 42,      # Champions League
    3: 73,      # Europa League
    4: 299,     # Copa Sudamericana
    5: 9806,    # UEFA Nations League
    6: 73,      # Europa League
    7: 11021,   # Copa Libertadores Femenina
    8: 9806,    # UEFA Nations League
    10: 77,     # World Cup
    # Alemania
    13: 54,     # Bundesliga
    14: 145,    # DFB Pokal
    15: 146,    # 2. Bundesliga
    16: 207,    # 3. Liga
    17: 9676,   # Frauen-Bundesliga
    # Arabia Saudí
    18: 10197,  # Saudi Pro League
    # Argentina
    20: 112,    # Liga Profesional
    21: 9305,   # Copa Argentina
    22: 9213,   # Primera B Metropolitana
    23: 8965,   # Primera B Nacional
    # Australia
    25: 111,    # A-League Men
    26: 10079,  # A-League Women
    27: 10045,  # Australia Cup
    # Austria
    29: 67,     # Bundesliga
    31: 135,    # 2. Liga
    # Bélgica
    33: 40,     # Jupiler Pro League
    34: 142,    # Croky Cup (Beker van Belgie)
    35: 10061,  # Challenger Pro League
    # Bolivia
    37: 10058,  # Division Profesional
    # Brasil
    39: 268,    # Serie A
    40: 9067,   # Copa do Brasil
    41: 8814,   # Serie B
    42: 8971,   # Serie C
    43: 10188,  # Brasileirao Femenino
    # Bulgaria
    47: 218,    # Parva Liga
    # Canada
    48: 10183,  # Canadian Premier League
    49: 10872,  # Northern Super League
    # Chile
    50: 273,    # Primera Division
    # China
    52: 10038,  # Super League
    # Colombia
    55: 274,    # Primera A
    56: 9490,   # Copa Colombia
    57: 9125,   # Primera B (Torneo BetPlay)
    # Corea del Sur
    58: 10041,  # K League 1
    59: 10042,  # K League 2
    # Costa Rica
    60: 10044,  # Primera Division
    # Croacia
    67: 213,    # HNL (Prva HNL)
    # Dinamarca
    62: 50,     # Superliga
    63: 136,    # DBU Pokalen
    64: 152,    # 1. Division
    65: 247,    # 2. Division
    66: 10191,  # Kvindeliga
    # Ecuador
    68: 258,    # Liga Pro
    # Egipto
    70: 10035,  # Premier League
    # El Salvador
    72: 10036,  # Primera Division
    # UAE
    73: 10037,  # UAE Pro League
    # Escocia
    74: 65,     # Premiership
    75: 137,    # Scottish Cup
    76: 151,    # Championship
    77: 155,    # League One
    78: 156,    # League Two
    79: 10192,  # SWPL 1
    # Eslovaquia
    80: 243,    # Nike liga
    81: 10081,  # 2. liga
    # Eslovenia
    83: 216,    # Prva Liga
    # España
    84: 87,     # LaLiga
    85: 138,    # Copa del Rey
    86: 140,    # LaLiga2
    87: 9907,   # Liga F
    88: 8968,   # Primera Federación
    89: 8968,   # Primera Federación
    91: 9138,   # Segunda Federación
    92: 9138,   # Segunda Federación
    # USA
    98: 130,    # MLS
    99: 10047,  # MLS Next Pro
    100: 10078, # NWSL
    101: 8972,  # US Open Cup
    102: 8972,  # USL Championship
    # Estonia
    104: 244,   # Premium Liiga
    106: 10082, # Esiliiga
    # Finlandia
    109: 69,    # Veikkausliiga
    110: 10069, # Ykkosliiga
    111: 10070, # Ykkonen
    112: 10179, # Kansallinen Liiga (W)
    # Francia
    113: 53,    # Ligue 1
    114: 139,   # Coupe de France
    115: 112,   # Ligue 2
    116: 113,   # Ligue 3 (National)
    # Grecia
    118: 197,   # Super League
    119: 198,   # Greek Cup
    120: 10064, # Super League 2
    # Hungría
    121: 10034, # OTP Bank Liga
    122: 10065, # NB II
    # India
    124: 10039, # ISL
    # Indonesia
    125: 10039, # Liga 1
    # Inglaterra
    126: 47,    # Premier League
    127: 48,    # Championship
    128: 108,   # League One
    129: 109,   # League Two
    130: 110,   # National League
    131: 132,   # FA Cup
    134: 133,   # EFL Cup
    136: 9094,  # Women's Super League
    # Irlanda
    137: 118,   # Premier Division
    138: 10083, # First Division
    # Irlanda del Norte
    139: 217,   # NIFL Premiership
    # Islandia
    140: 208,   # Besta deild karla
    # Israel
    141: 10084, # Liga Leumit
    # Italia
    143: 55,    # Serie A
    144: 141,   # Coppa Italia
    145: 86,    # Serie B
    146: 147,   # Serie C
    148: 10178, # Serie A Femminile
    # Jamaica
    149: 10184, # Premier League
    # Japón
    150: 164,   # J1 League
    151: 10072, # J2 League
    # Jordania
    154: 10040, # Pro League
    # Kazajistán
    155: 250,   # Premier League
    # Letonia
    156: 248,   # Virsliga
    # México
    159: 230,   # Liga MX
    160: 10043, # Liga de Expansion MX
    161: 10076, # Liga MX Femenil
    163: 10076, # Liga MX Femenil
    # Nicaragua
    165: 10186, # Liga Primera
    # Nigeria
    166: 10180, # NPFL
    # Noruega
    167: 58,    # Eliteserien
    168: 134,   # OBOS-ligaen
    # Países Bajos
    170: 57,    # Eredivisie
    171: 144,   # KNVB Beker
    172: 149,   # Eerste Divisie
    173: 10189, # Vrouweneredivisie
    # Paraguay
    174: 275,   # Division Profesional
    # Perú
    175: 276,   # Liga 1
    # Polonia
    185: 196,   # Ekstraklasa
    186: 201,   # Puchar Polski
    187: 202,   # I Liga
    # Portugal
    177: 61,    # Liga Portugal
    178: 143,   # Taca de Portugal
    179: 150,   # Liga Portugal 2
    180: 221,   # Allianz Cup
    # Qatar
    181: 214,   # QSL
    # República Checa
    183: 189,   # Chance Liga
    # Rumania
    184: 214,   # Superliga
    # Serbia
    187: 215,   # Super Liga
    # Sudáfrica
    189: 261,   # Betway Premiership (PSL)
    # Suecia
    191: 59,    # Allsvenskan
    192: 148,   # Superettan
    194: 10177, # Elitettan
    195: 10077, # Damallsvenskan
    # Suiza
    199: 66,    # Super League
    200: 138,   # Challenge League
    # Turquía
    196: 71,    # Super Lig
    197: 153,   # Turkish Cup
    198: 154,   # 1. Lig
    # Uruguay
    202: 272,   # Primera Division (Liga AUF)
    203: 10060, # Segunda Division
    204: 10301, # Copa Uruguay
    # Venezuela
    207: 10068, # Liga FUTVE
}

# The 44 competitions that are 100% Flashscore Exclusive
FLASHSCORE_EXCLUSIVES_FINAL = {
    # España
    93, 94, 95, 96, 97, # Tercera Federación Grupos 1, 4, 6, 7, 9
    90,                 # Segunda B - Gr. II (Extinta)
    # Reservas y formativas
    24,                 # Argentina Reserves Leagues U23
    201,                # Turquía Sub-19 Ligi
    205,                # Uruguay Liga de Reserva / Formativas
    164,                # México Liga MX Sub-21
    45,                 # Brasil Copa do Brasil Sub-20
    # Torneos regionales y ligas menores
    28,                 # Australia Campeonato (NPL regionales)
    30,                 # Austria Liga Regional Este
    36,                 # Bélgica Eerste Nationale
    82,                 # Eslovaquia 3. Liga
    117,                # Francia National 2 - Grupo A
    135,                # Inglaterra NPL Division One
    152,                # Japón JFL
    162,                # México Tercera División (Liga Premier)
    169,                # Noruega Postnordligaen avd. 1
    193,                # Suecia Division 2 - Norra Götaland
    46,                 # Brasil Gaúcho 2
    # Ascenso menor
    19,                 # Arabia Saudí 1ª División
    51,                 # Chile Primera B
    53,                 # China Liga Dos (Yi League)
    54,                 # China Liga Uno (Jia League)
    61,                 # Costa Rica Liga de Ascenso
    69,                 # Ecuador Primera B
    71,                 # Egipto 2ª División
    107,                # Estonia Esiliiga B
    157,                # Lituania 1 Lyga
    158,                # Malawi Super League
    176,                # Perú Segunda División
    182,                # Qatar QSL 2
    184,                # República Checa ChNL
    188,                # Serbia Prva Liga
    190,                # Sudáfrica MFC
    # Fútbol femenino menor
    44,                 # Brasil Copa de Brasil Femenina
    103,                # USA USLW
    105,                # Estonia Equipo femenino de Meistriliiga
    123,                # Hungría NB 1 femenina
    153,                # Japón Liga Nadeshiko 1ª Div. Femenina
    # Especiales / Esports
    1,                  # Internacional Especiales Betplay
    9,                  # Internacional Copa del Mundo 2030
    12                  # Internacional Esports Fútbol
}

print(f"Total Flashscore Exclusives count: {len(FLASHSCORE_EXCLUSIVES_FINAL)}")
assert len(FLASHSCORE_EXCLUSIVES_FINAL) == 44, f"Must be 44, got {len(FLASHSCORE_EXCLUSIVES_FINAL)}"

resolved_mapping = []
for row in betplay_comps:
    cid, pid, pais, bp, fs, link = row
    if cid in FLASHSCORE_EXCLUSIVES_FINAL:
        resolved_mapping.append({
            'competicion_id': cid,
            'pais_nombre': pais,
            'nombre_betplay': bp,
            'nombre_flashscore': fs,
            'fotmob_league_id': None,
            'fotmob_nombre': None,
            'fotmob_url': None,
            'fotmob_ccode': None,
            'ruta_optima': 'flashscore'
        })
    else:
        fid = EXPLICIT_OVERRIDES.get(cid)
        if not fid or fid not in all_fotmob_leagues:
            # automatic search in country
            target_country = COUNTRY_MAP.get(norm(pais), norm(pais))
            c_leagues = fotmob_by_country.get(target_country, [])
            best = None
            for l in c_leagues:
                if norm(fs) in norm(l['name']) or norm(l['name']) in norm(fs) or norm(bp) in norm(l['name']):
                    best = l
                    break
            if best:
                fid = best['id']
            else:
                # If truly nothing found, check international
                intl_leagues = fotmob_by_country.get('international', [])
                for l in intl_leagues:
                    if norm(fs) in norm(l['name']) or norm(bp) in norm(l['name']):
                        best = l
                        break
                if best:
                    fid = best['id']

        fm_info = all_fotmob_leagues.get(fid)
        if fm_info:
            resolved_mapping.append({
                'competicion_id': cid,
                'pais_nombre': pais,
                'nombre_betplay': bp,
                'nombre_flashscore': fs,
                'fotmob_league_id': fm_info['id'],
                'fotmob_nombre': fm_info['name'],
                'fotmob_url': fm_info['url'],
                'fotmob_ccode': fm_info['ccode'],
                'ruta_optima': 'fotmob'
            })
        else:
            # If not in FotMob catalog, route to Flashscore
            resolved_mapping.append({
                'competicion_id': cid,
                'pais_nombre': pais,
                'nombre_betplay': bp,
                'nombre_flashscore': fs,
                'fotmob_league_id': None,
                'fotmob_nombre': None,
                'fotmob_url': None,
                'fotmob_ccode': None,
                'ruta_optima': 'flashscore'
            })

fm_c = sum(1 for x in resolved_mapping if x['ruta_optima'] == 'fotmob')
fs_c = sum(1 for x in resolved_mapping if x['ruta_optima'] == 'flashscore')

print("\n" + "="*70)
print("AUDITORÍA DE ENRUTAMIENTO RESUELTO:")
print(f"Total competiciones:                {len(resolved_mapping)}")
print(f"Ruta FotMob (IDs reales y válidos): {fm_c} ({fm_c/len(resolved_mapping)*100:.1f}%)")
print(f"Ruta Flashscore (Exclusivas reales): {fs_c} ({fs_c/len(resolved_mapping)*100:.1f}%)")
print("="*70)

# Verify that EVERY single FotMob ID exists in all_fotmob_leagues
for item in resolved_mapping:
    if item['ruta_optima'] == 'fotmob':
        assert item['fotmob_league_id'] in all_fotmob_leagues, f"Invalid ID: {item}"

print("[OK] Todos los IDs de FotMob son 100% auténticos y existen en el catálogo oficial.")

with open('competiciones_betplay_flashscore_fotmob.json', 'w', encoding='utf-8') as f:
    json.dump(resolved_mapping, f, indent=2, ensure_ascii=False)

c.execute("DELETE FROM competiciones_fotmob;")
for r in resolved_mapping:
    c.execute("""
    INSERT INTO competiciones_fotmob (
        competicion_id, pais_nombre, nombre_betplay, nombre_flashscore,
        fotmob_league_id, fotmob_nombre, fotmob_url, fotmob_ccode, ruta_optima
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        r['competicion_id'], r['pais_nombre'], r['nombre_betplay'], r['nombre_flashscore'],
        r['fotmob_league_id'], r['fotmob_nombre'], r['fotmob_url'], r['fotmob_ccode'], r['ruta_optima']
    ))
conn.commit()
print("[OK] Base de datos SQLite 'competiciones_fotmob' actualizada.")
conn.close()
