"""
Enrutador de Descarga Híbrida 80/20 (Betplay - FotMob / Flashscore)
==================================================================
Arquitectura de Ingesta Asimétrica con Control Estricto de Checkpoints:
- Fase 1 (FotMob REST API): 163 competiciones (~80%) en ~200ms por partido
  (Shotmaps x,y, Heatmaps individuales, xG Opta, clima y estadio).
  Descarga incremental: Sincroniza calendarios y salta automáticamente
  los partidos ya completados en 'checkpoints_fotmob_detalles'.
- Fase 2 (Flashscore Browser): 44 competiciones (~20%) residuales
  (Tercera RFEF, Reservas U23, ligas sin cobertura en Opta).
  Descarga incremental: Sincroniza resultados pendientes y salta
  automáticamente los partidos ya completados en 'checkpoints_detalles_partidos'.
"""

import os
import sys
import json
import sqlite3
import argparse
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')
ROUTER_JSON = os.path.join(BASE_DIR, 'competiciones_betplay_flashscore_fotmob.json')
FOTMOB_SCRIPT = os.path.join(BASE_DIR, 'scraper_fotmob_betplay.py')
FLASHSCORE_DETALLES_SCRIPT = os.path.join(BASE_DIR, 'scraper_detalles_partidos_optimizado.py')
FLASHSCORE_FIXTURES_SCRIPT = os.path.join(BASE_DIR, 'scraper_todas_las_competiciones.py')

def get_detailed_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Total competiciones enrutadas
    c.execute("SELECT count(*) FROM competiciones_fotmob WHERE ruta_optima = 'fotmob';")
    fotmob_count = c.fetchone()[0]
    c.execute("SELECT count(*) FROM competiciones_fotmob WHERE ruta_optima = 'flashscore';")
    flashscore_count = c.fetchone()[0]
    c.execute("SELECT count(*) FROM competiciones;")
    total_comps = c.fetchone()[0]

    # 2. Checkpoints FotMob
    c.execute("SELECT count(*) FROM fotmob_partidos;")
    fm_partidos = c.fetchone()[0]
    c.execute("SELECT count(*) FROM checkpoints_fotmob_detalles WHERE estado = 'completado';")
    fm_completados = c.fetchone()[0]
    c.execute("""
    SELECT count(*) 
    FROM fotmob_partidos fp
    LEFT JOIN checkpoints_fotmob_detalles chk ON fp.match_id = chk.match_id
    WHERE fp.status = 'FT' AND (chk.estado IS NULL OR chk.estado != 'completado');
    """)
    fm_pendientes = c.fetchone()[0]

    # 3. Checkpoints Flashscore (solo de las 44 competiciones residuales)
    c.execute("""
    SELECT count(p.id) 
    FROM partidos p
    JOIN competiciones_fotmob cf ON p.competicion_id = cf.competicion_id
    WHERE cf.ruta_optima = 'flashscore';
    """)
    fs_partidos = c.fetchone()[0]
    c.execute("""
    SELECT count(chk.partido_id) 
    FROM checkpoints_detalles_partidos chk
    JOIN competiciones_fotmob cf ON chk.competicion_id = cf.competicion_id
    WHERE cf.ruta_optima = 'flashscore' AND chk.estado = 'completado';
    """)
    fs_completados = c.fetchone()[0]
    c.execute("""
    SELECT count(p.id) 
    FROM partidos p
    JOIN competiciones_fotmob cf ON p.competicion_id = cf.competicion_id
    LEFT JOIN checkpoints_detalles_partidos chk ON p.id = chk.partido_id
    WHERE cf.ruta_optima = 'flashscore' AND p.tipo = 'resultado' AND (chk.estado IS NULL OR chk.estado != 'completado');
    """)
    fs_pendientes = c.fetchone()[0]

    conn.close()
    return {
        "total_comps": total_comps,
        "fotmob_comps": fotmob_count,
        "flashscore_comps": flashscore_count,
        "fm_partidos": fm_partidos,
        "fm_completados": fm_completados,
        "fm_pendientes": fm_pendientes,
        "fs_partidos": fs_partidos,
        "fs_completados": fs_completados,
        "fs_pendientes": fs_pendientes
    }

def mostrar_estado():
    s = get_detailed_stats()
    print("\n" + "="*72)
    print("      ESTADO DEL ENRUTADOR HÍBRIDO BETPLAY (80/20) + CHECKPOINTS")
    print("="*72)
    print(f" Catálogo Total Betplay:                {s['total_comps']} competiciones")
    print("\n [1] INGESTA PRIMARIA FOTMOB (REST API):")
    print(f"     • Competiciones cubiertas:         {s['fotmob_comps']} ({s['fotmob_comps']/s['total_comps']*100:.1f}%)")
    print(f"     • Partidos indexados en SQLite:    {s['fm_partidos']:,}")
    print(f"     • Partidos con detalles (DONE):    {s['fm_completados']:,}")
    print(f"     • Partidos finalizados PENDIENTES: {s['fm_pendientes']:,}")
    print("\n [2] INGESTA RESIDUAL FLASHSCORE (BROWSER PLAYWRIGHT):")
    print(f"     • Competiciones cubiertas:         {s['flashscore_comps']} ({s['flashscore_comps']/s['total_comps']*100:.1f}%)")
    print(f"     • Partidos indexados en SQLite:    {s['fs_partidos']:,}")
    print(f"     • Partidos con detalles (DONE):    {s['fs_completados']:,}")
    print(f"     • Partidos finalizados PENDIENTES: {s['fs_pendientes']:,}")
    print("="*72)
    print("\nComandos disponibles:")
    print("  python ejecutar_descarga_hibrida.py --status")
    print("  python ejecutar_descarga_hibrida.py --all           (Flujo completo: Fixtures + Nuevos con Checkpoints)")
    print("  python ejecutar_descarga_hibrida.py --incremental   (Solo partidos nuevos pendientes en checkpoints)")
    print("  python ejecutar_descarga_hibrida.py --fotmob-only")
    print("  python ejecutar_descarga_hibrida.py --flashscore-only")
    print("  python ejecutar_descarga_hibrida.py --all --limit 3 (Prueba acotada)")

def run_fotmob_pipeline(limit=None, incremental=False):
    print("\n" + "="*72)
    print(">>> FASE 1: INGESTA VÍA FOTMOB (163 COMPETICIONES)")
    print("="*72)
    
    if incremental:
        cmd = [sys.executable, FOTMOB_SCRIPT, "--incremental"]
        print("[INFO] Modo Incremental: Procesando únicamente partidos pendientes en checkpoint.")
    else:
        cmd = [sys.executable, FOTMOB_SCRIPT, "--all"]
        effective_limit = 5 if limit is None else (None if limit == 0 else limit)
        if effective_limit:
            cmd.extend(["--limit", str(effective_limit)])
            print(f"[INFO] Límite configurado: {effective_limit} partidos más recientes por liga (use --limit 0 para histórico).")
        else:
            print("[INFO] Modo exhaustivo: Descargando todos los partidos históricos sin límite.")
            
    if limit and incremental:
        cmd.extend(["--limit", str(limit)])

    print(f"Ejecutando: {' '.join(cmd)}")
    subprocess.run(cmd)

def run_flashscore_pipeline(limit=None, sync_fixtures=True):
    print("\n" + "="*72)
    print(">>> FASE 2: INGESTA QUIRÚRGICA VÍA FLASHSCORE (44 COMPETICIONES EXCLUSIVAS)")
    print("="*72)
    
    if sync_fixtures:
        print("\n[PASO 2.1] Sincronización incremental de resultados/próximos (44 ligas residuales)...")
        cmd_sync = [sys.executable, FLASHSCORE_FIXTURES_SCRIPT, "--incremental", "--solo-residuales", "--max-clicks", "2"]
        print(f"Ejecutando: {' '.join(cmd_sync)}")
        subprocess.run(cmd_sync)

    print("\n[PASO 2.2] Extracción optimizada de detalles de partidos pendientes (Checkpoints)...")
    cmd_detalles = [sys.executable, FLASHSCORE_DETALLES_SCRIPT, "--ruta-flashscore"]
    if limit:
        cmd_detalles.extend(["--limit", str(limit)])
    print(f"Ejecutando: {' '.join(cmd_detalles)}")
    subprocess.run(cmd_detalles)

def main():
    parser = argparse.ArgumentParser(description="Enrutador de Descarga Híbrida 80/20 con Checkpoints")
    parser.add_argument("--status", action="store_true", help="Muestra el estado actual del enrutador y estadísticas")
    parser.add_argument("--all", action="store_true", help="Ejecuta ambas fases de descarga (FotMob + Flashscore)")
    parser.add_argument("--incremental", action="store_true", help="Descarga únicamente partidos pendientes según checkpoints")
    parser.add_argument("--fotmob-only", action="store_true", help="Ejecuta únicamente el bloque FotMob (163 ligas)")
    parser.add_argument("--flashscore-only", action="store_true", help="Ejecuta únicamente el bloque Flashscore (44 ligas)")
    parser.add_argument("--no-fixtures", action="store_true", help="Omitir sincronización de calendarios y saltar directo a detalles")
    parser.add_argument("--limit", type=int, default=None, help="Límite de partidos por liga para prueba")
    args = parser.parse_args()

    if args.status or len(sys.argv) == 1:
        mostrar_estado()
        return

    if args.fotmob_only:
        run_fotmob_pipeline(limit=args.limit, incremental=args.incremental)
    elif args.flashscore_only:
        run_flashscore_pipeline(limit=args.limit, sync_fixtures=not args.no_fixtures)
    elif args.incremental:
        run_fotmob_pipeline(limit=args.limit, incremental=True)
        run_flashscore_pipeline(limit=args.limit, sync_fixtures=False)
    elif args.all:
        run_fotmob_pipeline(limit=args.limit, incremental=False)
        run_flashscore_pipeline(limit=args.limit, sync_fixtures=not args.no_fixtures)
    else:
        mostrar_estado()

if __name__ == "__main__":
    main()
