"""
Parser de Detalle de Partidos Flashscore
Extrae:
1. Resumen (incidencias, goles, tarjetas, cambios)
2. Estadísticas (partido completo, 1er tiempo, 2o tiempo)
3. Alineaciones (sistemas tácticos, notas medias, titulares, suplentes, ausencias, entrenadores)
4. Estadísticas de jugadores (tablas de principales, remates, ataque, pases, defensa, paradas, general)
"""

import re
from bs4 import BeautifulSoup

def parse_resumen(html):
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    container = soup.find('div', class_='smv__verticalSections') or soup
    
    incidents = []
    current_period = "General"
    
    # Buscamos encabezados de periodo y listas
    for section in container.find_all('div', recursive=False):
        classes = section.get('class', [])
        # Cabecera de periodo
        if 'wclHeaderSection--summary' in ' '.join(classes) or 'wcl-headerSection_SGpOR' in ' '.join(classes):
            txt = section.get_text(separator=' ', strip=True)
            if txt:
                current_period = txt
                
    # También recorremos los bloques directos
    sections = soup.find_all(['div', 'ol'])
    for el in sections:
        classes = ' '.join(el.get('class', []))
        if 'wclHeaderSection--summary' in classes:
            period_spans = el.find_all('span', attrs={'data-testid': 'wcl-overline-02'})
            if period_spans:
                p_name = period_spans[0].get_text(strip=True)
                p_score = period_spans[1].get_text(strip=True) if len(period_spans) > 1 else ""
                current_period = f"{p_name} ({p_score})".strip()
        elif 'smv__period-list' in classes:
            for row in el.find_all('li', class_='smv__participantRow'):
                row_classes = row.get('class', [])
                side = "home" if 'smv__homeParticipant' in row_classes else ("away" if 'smv__awayParticipant' in row_classes else "neutral")
                
                # Minuto
                time_box = row.find('div', class_='smv__timeBox')
                minuto = time_box.get_text(strip=True) if time_box else ""
                
                # Tipo de incidencia
                tipo = "evento"
                svg = row.find('svg')
                if svg:
                    title_tag = svg.find('title')
                    if title_tag:
                        tipo = title_tag.get_text(strip=True)
                    else:
                        aria = svg.get('aria-label')
                        if aria:
                            tipo = aria
                        elif 'yellowCard-ico' in ' '.join(svg.get('class', [])):
                            tipo = "Tarjeta amarilla"
                        elif 'redCard-ico' in ' '.join(svg.get('class', [])):
                            tipo = "Tarjeta roja"
                
                # Jugador principal
                player_tag = row.find('a', class_='smv__playerName')
                player_name = player_tag.get_text(strip=True) if player_tag else ""
                player_href = player_tag.get('href', '') if player_tag else ""
                player_id = player_href.strip('/').split('/')[-1] if player_href else ""
                
                # Sustitución (quién sale)
                sub_out_tag = row.find('div', class_='smv__incidentSubOut')
                sub_out_name = ""
                sub_out_id = ""
                if sub_out_tag:
                    a_out = sub_out_tag.find('a', class_='smv__playerName')
                    if a_out:
                        sub_out_name = a_out.get_text(strip=True)
                        href_out = a_out.get('href', '')
                        sub_out_id = href_out.strip('/').split('/')[-1] if href_out else ""
                        
                # Nota adicional (ej: Lesión, Penal, etc.)
                sub_inc = row.find('div', class_='smv__subIncident')
                nota = sub_inc.get_text(strip=True) if sub_inc else ""
                
                incidents.append({
                    'periodo': current_period,
                    'minuto': minuto,
                    'equipo': side,
                    'tipo': tipo,
                    'jugador': player_name,
                    'jugador_id': player_id,
                    'jugador_sale': sub_out_name,
                    'jugador_sale_id': sub_out_id,
                    'nota': nota
                })
                
    return incidents

def parse_estadisticas(html):
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    container = soup.find('div', class_='statisticsContent') or soup
    
    sections_data = {}
    for sec in container.find_all('div', class_='section'):
        hdr = sec.find(['div', 'span'], class_=lambda c: c and 'sectionHeader' in c)
        sec_name = hdr.get_text(strip=True) if hdr else "General"
        
        metrics = {}
        for row in sec.find_all('div', attrs={'data-testid': 'wcl-statistics'}):
            label_row = row.find('div', class_=lambda c: c and 'labelRow' in c)
            if not label_row:
                continue
            
            # Nombre métrica
            lbl = label_row.find('div', class_=lambda c: c and 'wcl-label_' in c)
            metrica = lbl.find('span', attrs={'data-testid': 'wcl-simple-text-01'}) if lbl else None
            metrica_name = metrica.get_text(strip=True) if metrica else (lbl.get_text(strip=True) if lbl else "")
            if not metrica_name:
                continue
                
            # Valor Local (primer valor)
            first_val_box = label_row.find('div', recursive=False)
            val_local_tag = first_val_box.find('div', class_=lambda c: c and 'wcl-value_' in c) if first_val_box else None
            val_local = val_local_tag.get_text(strip=True) if val_local_tag else ""
            
            # Valor Visitante (awayValue)
            away_box = label_row.find('div', class_=lambda c: c and 'wcl-awayValue_' in c)
            val_away_tag = away_box.find('div', class_=lambda c: c and 'wcl-value_' in c) if away_box else None
            val_away = val_away_tag.get_text(strip=True) if val_away_tag else ""
            
            metrics[metrica_name] = {
                'local': val_local,
                'visitante': val_away
            }
            
        if metrics:
            sections_data[sec_name] = metrics
            
    return sections_data

def parse_alineaciones(html):
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Sistemas tácticos y notas promedio
    sistema_local = ""
    sistema_visitante = ""
    form_div = soup.find('div', class_=lambda c: c and 'fp-headerFormation_' in c)
    if form_div:
        spans = form_div.find_all('span', attrs={'data-testid': 'wcl-overline-02'})
        if len(spans) >= 3:
            sistema_local = spans[0].get_text(strip=True)
            sistema_visitante = spans[2].get_text(strip=True)
            
    avg_home = soup.find('div', class_=lambda c: c and 'fp-home_' in c and 'fp-averageRating_' in c)
    rating_home = avg_home.find('span', attrs={'data-testid': 'wcl-caption-05'}).get_text(strip=True) if avg_home else ""
    
    avg_away = soup.find('div', class_=lambda c: c and 'fp-away_' in c and 'fp-averageRating_' in c)
    rating_away = avg_away.find('span', attrs={'data-testid': 'wcl-caption-05'}).get_text(strip=True) if avg_away else ""
    
    # 2. Grupos de jugadores (Alineaciones iniciales, Sustituidos, Suplentes, Ausentes, Entrenadores)
    grupos = {
        'titulares': [],
        'sustituidos': [],
        'suplentes': [],
        'ausentes': [],
        'entrenadores': {'local': '', 'visitante': ''}
    }
    
    for grp in soup.find_all('div', attrs={'data-testid': 'wcl-lineupsGroup'}):
        hdr = grp.find('div', attrs={'data-testid': 'wcl-headerSection-text'})
        hdr_title = hdr.get_text(strip=True) if hdr else ""
        
        # Mapeamos nombre del grupo
        target_key = None
        if "iniciales" in hdr_title.lower():
            target_key = 'titulares'
        elif "sustituidos" in hdr_title.lower():
            target_key = 'sustituidos'
        elif "suplentes" in hdr_title.lower():
            target_key = 'suplentes'
        elif "ausentes" in hdr_title.lower():
            target_key = 'ausentes'
        elif "entrenadores" in hdr_title.lower():
            target_key = 'entrenadores'
            
        sides = grp.find_all('div', class_='wcl-side_R64pI')
        for i, side_box in enumerate(sides):
            side_type = "home" if i == 0 else "away"
            
            # Si son entrenadores
            if target_key == 'entrenadores':
                dt_tag = side_box.find('span', attrs={'data-testid': 'wcl-simple-text-01'})
                if dt_tag:
                    grupos['entrenadores']['local' if side_type == 'home' else 'visitante'] = dt_tag.get_text(strip=True)
                continue
                
            for p_item in side_box.find_all('div', class_='wcl-participant_YylQz'):
                # Player ID
                p_el = p_item.find(['div', 'figure'], attrs={'data-analytics-player-id': True})
                p_id = p_el.get('data-analytics-player-id', '') if p_el else ""
                
                # Dorsal
                dorsal_tag = p_item.find('span', class_=lambda c: c and 'wcl-number_' in c)
                dorsal = dorsal_tag.get_text(strip=True) if dorsal_tag else ""
                
                # Nombre
                name_tag = p_item.find('span', class_=lambda c: c and 'wcl-name_' in c)
                name = name_tag.get_text(strip=True) if name_tag else ""
                
                # Roles ((G), (C))
                roles_tag = p_item.find('div', class_=lambda c: c and 'wcl-roles_' in c)
                rol_desc = roles_tag.get_text(strip=True) if roles_tag else ""
                
                # Calificación
                badge = p_item.find('div', attrs={'data-testid': 'wcl-badgeRating'})
                rating = badge.find('span', attrs={'data-testid': 'wcl-caption-05'}).get_text(strip=True) if badge else ""
                
                # Minuto de sustitución si aplica
                minuto_salida = ""
                min_tag = p_item.find('span', class_=lambda c: c and 'wcl-minute_' in c)
                if min_tag:
                    minuto_salida = min_tag.get_text(strip=True)
                    
                # Motivo de ausencia si aplica
                motivo = ""
                desc_tag = p_item.find('span', class_=lambda c: c and 'wcl-description_' in c)
                if desc_tag:
                    motivo = desc_tag.get_text(strip=True)
                    
                if target_key:
                    grupos[target_key].append({
                        'equipo': side_type,
                        'jugador_id': p_id,
                        'dorsal': dorsal,
                        'nombre': name,
                        'rol': rol_desc,
                        'calificacion': rating,
                        'minuto_salida': minuto_salida,
                        'motivo_ausencia': motivo
                    })
                    
    return {
        'sistema_local': sistema_local,
        'sistema_visitante': sistema_visitante,
        'rating_medio_local': rating_home,
        'rating_medio_visitante': rating_away,
        'titulares': grupos['titulares'],
        'sustituidos': grupos['sustituidos'],
        'suplentes': grupos['suplentes'],
        'ausentes': grupos['ausentes'],
        'entrenadores': grupos['entrenadores']
    }

def parse_jugadores_stats_table(html):
    """
    Parser dinámico para cualquier tabla de estadísticas de jugadores (principales, remates, ataque, etc.)
    Usa 'data-analytics-alias' en cada <th>.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', attrs={'data-testid': 'wcl-table'})
    if not table:
        return []
        
    thead = table.find('thead')
    tbody = table.find('tbody')
    if not thead or not tbody:
        return []
        
    # Cabeceras
    col_aliases = []
    for th in thead.find_all('th'):
        alias = th.get('data-analytics-alias')
        if not alias:
            # Primera columna (jugador)
            alias = "PLAYER_INFO"
        col_aliases.append(alias)
        
    rows_data = []
    for tr in tbody.find_all('tr', attrs={'data-testid': 'wcl-tableBodyRow'}):
        tds = tr.find_all('td')
        if not tds:
            continue
            
        row_dict = {}
        for idx, td in enumerate(tds):
            if idx >= len(col_aliases):
                break
            col_name = col_aliases[idx]
            
            if col_name == "PLAYER_INFO":
                fig = td.find('figure', attrs={'data-analytics-player-id': True})
                p_id = fig.get('data-analytics-player-id', '') if fig else ""
                
                name_el = td.find('div', class_=lambda c: c and 'fp-playerName_' in c)
                p_name = name_el.get_text(strip=True) if name_el else ""
                
                pos_el = td.find('span', class_=lambda c: c and 'wcl-position_' in c)
                p_pos = pos_el.get_text(strip=True) if pos_el else ""
                
                row_dict['jugador_id'] = p_id
                row_dict['nombre'] = p_name
                row_dict['posicion'] = p_pos
            else:
                # Valor de la celda
                val = td.get_text(strip=True)
                row_dict[col_name] = val
                
        rows_data.append(row_dict)
        
    return rows_data
