import json

with open('competiciones_betplay_flashscore_fotmob.json', 'r', encoding='utf-8') as f:
    mapping = json.load(f)

print(f"Total en mapping: {len(mapping)}")
with_id = [x for x in mapping if x.get('fotmob_league_id') is not None]
without_id = [x for x in mapping if x.get('fotmob_league_id') is None]

print(f"Mapeadas con FotMob ID: {len(with_id)}")
print(f"SIN FotMob ID (Exclusivas de Betplay + Flashscore): {len(without_id)}")

# Categorize the unmapped
categories = {
    "Divisiones Inferiores / Ascenso Profundo": [],
    "Ligas de Reserva y Torneos Sub-X": [],
    "Fútbol Femenino Menor / Regional": [],
    "Ligas Exóticas o Países Menores": [],
    "Torneos Regionales y Divisiones No Profesionales": [],
    "Mercados Especiales y Esports": []
}

for x in without_id:
    pais = x.get('pais_nombre', '')
    bp = x.get('nombre_betplay', '')
    fs = x.get('nombre_flashscore', '')
    bp_l = bp.lower()
    fs_l = fs.lower()
    
    entry = f"[{pais}] Betplay: '{bp}' | Flashscore: '{fs}'"
    
    if any(k in bp_l or k in fs_l for k in ['reserva', 'sub-19', 'u23', 'u19', 'formativas']):
        categories["Ligas de Reserva y Torneos Sub-X"].append(entry)
    elif any(k in bp_l or k in fs_l for k in ['femenin', '(f)', 'women']):
        categories["Fútbol Femenino Menor / Regional"].append(entry)
    elif any(k in bp_l or k in fs_l for k in ['tercera', 'national 2', 'regionalliga', 'npl', 'jfl', 'division 2', '3. liga']):
        categories["Torneos Regionales y Divisiones No Profesionales"].append(entry)
    elif any(k in bp_l or k in fs_l for k in ['esports', 'especiales']):
        categories["Mercados Especiales y Esports"].append(entry)
    elif any(k in bp_l or k in fs_l for k in ['primera b', 'segunda', '2ª', 'liga 2', 'liga dos', 'esiliiga b', 'liga de ascenso', 'chnl', 'prva liga', 'motsepe']):
        categories["Divisiones Inferiores / Ascenso Profundo"].append(entry)
    else:
        categories["Ligas Exóticas o Países Menores"].append(entry)

print("\n" + "="*80)
print("COMPETICIONES DE BETPLAY CUBIERTAS POR FLASHSCORE PERO NO POR FOTMOB")
print("="*80)

for cat_name, entries in categories.items():
    print(f"\n### {cat_name} ({len(entries)} competiciones):")
    for e in entries:
        print(f"  * {e}")
