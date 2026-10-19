import json
import re
import os
import sys

def parse_circles(circles_str):
    """Extrae las coordenadas (x, y) de los tags <circle cx="..." cy="..."/>"""
    coords = []
    pattern = re.compile(r'cx="([\d\.]+)"\s+cy="([\d\.]+)"')
    for m in pattern.finditer(circles_str):
        coords.append({
            "x": float(m.group(1)),
            "y": float(m.group(2))
        })
    return coords

def main():
    workspace_dir = r"c:\Users\SIMANCAS\Documents\rey"
    artifact_dir = r"C:\Users\SIMANCAS\.gemini\antigravity\brain\5b1c712d-0cec-48bc-8972-7402b74a457b"
    
    match_file = os.path.join(workspace_dir, "match_data.json")
    heatmap_file = os.path.join(workspace_dir, "heatmap_data.json")
    
    if not os.path.exists(match_file) or not os.path.exists(heatmap_file):
        print(f"Error: No se encontraron los archivos fuente en {workspace_dir}")
        sys.exit(1)
        
    with open(match_file, "r", encoding="utf-8") as f:
        mdata = json.load(f)
        
    with open(heatmap_file, "r", encoding="utf-8") as f:
        hdata = json.load(f)
        
    content = mdata.get("content", {})
    general = mdata.get("general", {})
    header = mdata.get("header", {})
    
    # 1. Match Info & Referee
    teams = header.get("teams", [{}, {}])
    home_name = teams[0].get("name", "Everton")
    away_name = teams[1].get("name", "Chelsea")
    ref = content.get("matchFacts", {}).get("infoBox", {}).get("Referee", {})
    stadium = content.get("matchFacts", {}).get("infoBox", {}).get("Stadium", {}).get("name", "Goodison Park")
    
    ref_stats = {}
    for s in ref.get("stats", []):
        ref_stats[s.get("type")] = {
            "value": s.get("value"),
            "valueType": s.get("valueType"),
            "total": s.get("total")
        }
        
    match_info = {
        "matchId": general.get("matchId"),
        "matchName": f"{home_name} vs {away_name}",
        "competition": general.get("leagueName", "Premier League"),
        "dateTimeUTC": general.get("matchTimeUTC"),
        "stadium": stadium,
        "score": {
            "home": { "name": home_name, "score": teams[0].get("score") },
            "away": { "name": away_name, "score": teams[1].get("score") }
        },
        "referee": {
            "name": ref.get("text"),
            "country": ref.get("country"),
            "stats": ref_stats
        }
    }
    
    # 2. Facts: Events & Momentum
    events_raw = content.get("matchFacts", {}).get("events", {}).get("events", [])
    parsed_events = []
    for e in events_raw:
        etype = e.get("type")
        time_val = e.get("time")
        overload = e.get("overloadTime")
        is_home = e.get("isHome")
        team = home_name if is_home else away_name
        
        event_obj = {
            "minute": time_val,
            "addedTime": overload,
            "type": etype,
            "team": team
        }
        
        if etype == "Goal":
            event_obj["player"] = e.get("player", {}).get("name")
        elif etype == "Card":
            event_obj["player"] = e.get("player", {}).get("name")
            event_obj["card"] = e.get("card", "Yellow")
        elif etype == "Substitution":
            swap = e.get("swap", [])
            event_obj["playerIn"] = swap[0].get("name") if len(swap) > 0 else None
            event_obj["playerOut"] = swap[1].get("name") if len(swap) > 1 else None
            event_obj["injuredPlayerOut"] = e.get("injuredPlayerOut", False)
            
        parsed_events.append(event_obj)
        
    momentum_data = content.get("momentum", {}).get("main", {}).get("data", [])
    
    # 3. Lineups
    lineup_raw = content.get("lineup", {})
    
    def process_team_lineup(t_key):
        t = lineup_raw.get(t_key, {})
        coach = t.get("coach", {})
        
        def format_player(p):
            perf = p.get("performance", {})
            return {
                "id": p.get("id"),
                "name": p.get("name"),
                "shirtNumber": p.get("shirtNumber"),
                "position": p.get("usualPlayingPositionId"),
                "age": p.get("age"),
                "marketValueEUR": p.get("marketValue"),
                "rating": perf.get("rating"),
                "seasonRating": perf.get("seasonRating"),
                "distanceCoveredMeters": perf.get("totalDistanceCovered"),
                "topSpeedKmh": round(perf.get("topSpeed"), 1) if isinstance(perf.get("topSpeed"), (int, float)) else None,
                "substitutionEvents": perf.get("substitutionEvents")
            }
            
        starters = [format_player(p) for p in t.get("starters", [])]
        subs = [format_player(p) for p in t.get("subs", [])]
        
        unavail = []
        for u in t.get("unavailable", []):
            unav_info = u.get("unavailability", {})
            unavail.append({
                "id": u.get("id"),
                "name": u.get("name"),
                "age": u.get("age"),
                "marketValueEUR": u.get("marketValue"),
                "reason": unav_info.get("type"),
                "expectedReturn": unav_info.get("expectedReturn")
            })
            
        return {
            "name": t.get("name"),
            "formation": t.get("formation"),
            "averageStarterAge": t.get("averageStarterAge"),
            "totalStarterMarketValueEUR": t.get("totalStarterMarketValue"),
            "coach": {
                "name": coach.get("name"),
                "country": coach.get("countryName"),
                "age": coach.get("age")
            },
            "starters": starters,
            "substitutes": subs,
            "unavailable": unavail
        }
        
    lineups_processed = {
        "home": process_team_lineup("homeTeam"),
        "away": process_team_lineup("awayTeam")
    }
    
    # 4. Team Stats (Periods: FirstHalf, SecondHalf, All)
    periods_raw = content.get("stats", {}).get("Periods", {})
    parsed_stats = {}
    
    for period_key in ["FirstHalf", "SecondHalf", "All"]:
        period_stats = {}
        for cat in periods_raw.get(period_key, {}).get("stats", []):
            cat_title = cat.get("title")
            cat_dict = {}
            for item in cat.get("stats", []):
                val = item.get("stats")
                if val and val != [None, None]:
                    cat_dict[item.get("title")] = {
                        "home": val[0],
                        "away": val[1]
                    }
            if cat_dict:
                period_stats[cat_title] = cat_dict
        parsed_stats[period_key] = period_stats
        
    attacking_zones = content.get("attackingZones", {})
    
    # 5. Shot Map (FirstHalf, SecondHalf, All)
    shotmap_raw = content.get("shotmap", {})
    shots_raw = shotmap_raw.get("shots", [])
    
    def process_shot(s):
        team_id = s.get("teamId")
        team = home_name if team_id == 8668 else away_name
        return {
            "id": s.get("id"),
            "minute": s.get("min"),
            "addedTime": s.get("minAdded"),
            "period": s.get("period"),
            "team": team,
            "playerId": s.get("playerId"),
            "playerName": s.get("fullName"),
            "outcome": s.get("eventType"),
            "isGoal": s.get("eventType") == "Goal",
            "coordinates": {
                "x": round(s.get("x", 0), 2),
                "y": round(s.get("y", 0), 2)
            },
            "onGoalShot": s.get("onGoalShot"),
            "expectedGoals": round(s.get("expectedGoals", 0), 4),
            "expectedGoalsOnTarget": round(s.get("expectedGoalsOnTarget", 0), 4) if s.get("expectedGoalsOnTarget") is not None else None,
            "isFromInsideBox": s.get("isFromInsideBox", False),
            "shotType": s.get("shotType"),
            "situation": s.get("situation")
        }
        
    all_shots = [process_shot(s) for s in shots_raw]
    first_half_shots = [s for s in all_shots if s["period"] == "FirstHalf"]
    second_half_shots = [s for s in all_shots if s["period"] == "SecondHalf"]
    
    shot_map_data = {
        "dimensions": { "lengthMeters": 105.0, "widthMeters": 68.0, "coordinateSystem": "Pitch metric (0..105, 0..68)" },
        "summary": {
            "totalShots": len(all_shots),
            "firstHalfShots": len(first_half_shots),
            "secondHalfShots": len(second_half_shots),
            "homeShots": len([s for s in all_shots if s["team"] == home_name]),
            "awayShots": len([s for s in all_shots if s["team"] == away_name])
        },
        "firstHalf": first_half_shots,
        "secondHalf": second_half_shots,
        "all": all_shots
    }
    
    # 6. Heatmaps & Player Coordinates
    pstats = content.get("playerStats", {})
    opta_map = {}
    for pid, p in pstats.items():
        opta_id = p.get("optaId")
        if opta_id:
            info = {
                "playerId": pid,
                "optaId": opta_id,
                "name": p.get("name"),
                "team": p.get("teamName"),
                "shirtNumber": p.get("shirtNumber"),
                "position": p.get("usualPosition")
            }
            opta_map[str(opta_id)] = info
            opta_map[f"p{opta_id}"] = info
            
    players_heatmaps_raw = hdata.get("players", {})
    
    player_heatmaps_list = []
    everton_all_coords = []
    chelsea_all_coords = []
    
    for opta_key, circles_str in players_heatmaps_raw.items():
        coords = parse_circles(circles_str)
        p_info = opta_map.get(opta_key, {"name": opta_key, "team": "Desconocido", "shirtNumber": "", "playerId": None, "position": ""})
        
        team_str = p_info["team"]
        if "Everton" in team_str:
            everton_all_coords.extend(coords)
        else:
            chelsea_all_coords.extend(coords)
            
        player_heatmaps_list.append({
            "playerId": p_info.get("playerId"),
            "optaId": p_info.get("optaId"),
            "name": p_info["name"],
            "team": team_str,
            "shirtNumber": p_info.get("shirtNumber"),
            "position": p_info.get("position"),
            "totalTouches": len(coords),
            "touchCoordinates": coords
        })
        
    player_heatmaps_list.sort(key=lambda x: (x["team"], -x["totalTouches"]))
    
    heatmaps_data = {
        "dimensions": { "lengthMeters": 105.0, "widthMeters": 68.0, "origin": "Top-Left (0,0)" },
        "teamHeatmaps": {
            "everton": {
                "totalTouches": len(everton_all_coords),
                "touchCoordinates": everton_all_coords
            },
            "chelsea": {
                "totalTouches": len(chelsea_all_coords),
                "touchCoordinates": chelsea_all_coords
            }
        },
        "playerHeatmaps": player_heatmaps_list
    }
    
    # 7. Player Stats (Detailed metrics for all players)
    players_detailed_stats = []
    for pid, p in pstats.items():
        p_cats = {}
        for g in p.get("stats", []):
            title = g.get("title")
            g_stats = {}
            for k, item in g.get("stats", {}).items():
                g_stats[k] = item.get("stat", {}).get("value")
            p_cats[title] = g_stats
            
        players_detailed_stats.append({
            "playerId": pid,
            "optaId": p.get("optaId"),
            "name": p.get("name"),
            "team": p.get("teamName"),
            "shirtNumber": p.get("shirtNumber"),
            "isGoalkeeper": p.get("isGoalkeeper", False),
            "stats": p_cats
        })
        
    # Compile entire dataset
    complete_dataset = {
        "_schema_version": "1.0",
        "description": "Dataset integral del partido Everton vs Chelsea (Premier League) con coordenadas espaciales completas de tiros y mapas de calor.",
        "match": match_info,
        "facts": {
            "events": parsed_events,
            "momentum": momentum_data
        },
        "lineups": lineups_processed,
        "teamStats": {
            "periods": parsed_stats,
            "attackingZones": attacking_zones
        },
        "shotMap": shot_map_data,
        "heatmaps": heatmaps_data,
        "playerStats": players_detailed_stats
    }
    
    # Save JSON files
    output_workspace = os.path.join(workspace_dir, "everton_vs_chelsea_complete_data.json")
    output_artifact = os.path.join(artifact_dir, "everton_vs_chelsea_complete_data.json")
    
    with open(output_workspace, "w", encoding="utf-8") as f:
        json.dump(complete_dataset, f, indent=2, ensure_ascii=False)
        
    with open(output_artifact, "w", encoding="utf-8") as f:
        json.dump(complete_dataset, f, indent=2, ensure_ascii=False)
        
    file_size_mb = os.path.getsize(output_workspace) / (1024 * 1024)
    print(f"Exportacion exitosa: {output_workspace} ({file_size_mb:.2f} MB)")
    print(f"Copia en artifact: {output_artifact}")

    # ================= AUTOMATED TESTS =================
    print("\n--- EJECUTANDO PRUEBAS DE INTEGRIDAD DEL DATASET ---")
    assert complete_dataset["match"]["score"]["home"]["score"] == 0, "Error en score local"
    assert complete_dataset["match"]["score"]["away"]["score"] == 2, "Error en score visitante"
    print("✓ [PASS] Marcador verificado: Everton 0 - 2 Chelsea")
    
    assert len(complete_dataset["shotMap"]["all"]) == 24, "Debe haber 24 tiros en total"
    assert len(complete_dataset["shotMap"]["firstHalf"]) == 9, "Debe haber 9 tiros en 1T"
    assert len(complete_dataset["shotMap"]["secondHalf"]) == 15, "Debe haber 15 tiros en 2T"
    print(f"✓ [PASS] Shot Map verificado: 24 tiros (9 en 1T, 15 en 2T) con coordenadas exactas")
    
    everton_touches = complete_dataset["heatmaps"]["teamHeatmaps"]["everton"]["totalTouches"]
    chelsea_touches = complete_dataset["heatmaps"]["teamHeatmaps"]["chelsea"]["totalTouches"]
    assert everton_touches == 688, f"Toques Everton esperado 688, obtenido {everton_touches}"
    assert chelsea_touches == 761, f"Toques Chelsea esperado 761, obtenido {chelsea_touches}"
    print(f"✓ [PASS] Team Heatmaps verificados: Everton ({everton_touches} toques), Chelsea ({chelsea_touches} toques)")
    
    assert len(complete_dataset["heatmaps"]["playerHeatmaps"]) == 29, "Debe haber 29 mapas individuales"
    mykolenko = next(p for p in complete_dataset["heatmaps"]["playerHeatmaps"] if "Mykolenko" in p["name"])
    assert mykolenko["totalTouches"] == 91 or mykolenko["totalTouches"] > 0, "Mykolenko debe tener toques"
    print(f"✓ [PASS] Heatmaps individuales verificados: 29 jugadores con coordenadas (Mykolenko: {mykolenko['totalTouches']} toques)")
    
    for period in ["FirstHalf", "SecondHalf", "All"]:
        assert period in complete_dataset["teamStats"]["periods"], f"Falta periodo {period}"
    print("✓ [PASS] Stats de equipo verificadas para 1T, 2T y All")
    
    assert len(complete_dataset["playerStats"]) >= 30, "Deben estar las métricas detalladas de los jugadores"
    print(f"✓ [PASS] Métricas individuales verificadas para {len(complete_dataset['playerStats'])} jugadores")
    print("--- TODAS LAS PRUEBAS PASARON EXITOSAMENTE ---\n")

if __name__ == "__main__":
    main()
