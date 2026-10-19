"""
Menú Interactivo de Gestión y Scraping de Betplay - Flashscore

Opciones disponibles:
1. Reanudar descarga completa (Procesar solo competiciones pendientes)
2. Actualización incremental (Buscar solo partidos nuevos y cambios en lo ya descargado)
3. Descargar por País específico
4. Descargar por Competición puntual
5. Ver estado de Checkpoints y Estadísticas de la Base de Datos
6. Reintentar competiciones fallidas (con error)
7. Forzar descarga completa desde cero (Sobrescribir checkpoints)
0. Salir
"""

import os
import sys
import time
import sqlite3
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'betplay_flashscore.db')
SCRAPER_SCRIPT = os.path.join(BASE_DIR, 'scraper_todas_las_competiciones.py')

def limpiar_pantalla():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_db_stats():
    if not os.path.exists(DB_PATH):
        return None
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        
        cur.execute("SELECT count(*) FROM competiciones WHERE link_flashscore LIKE 'http%'")
        total_comps = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM checkpoints_competiciones WHERE estado = 'completado'")
        completadas = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM checkpoints_competiciones WHERE estado = 'error'")
        errores = cur.fetchone()[0]
        
        pendientes = total_comps - completadas - errores
        
        cur.execute("SELECT count(*) FROM partidos")
        total_partidos = cur.fetchone()[0]
        
        cur.execute("SELECT estado, count(*) FROM partidos GROUP BY estado")
        partidos_por_estado = dict(cur.fetchall())
        
        # Checkpoints de detalles de partidos
        cur.execute("SELECT count(*) FROM partidos WHERE tipo = 'resultado' AND link IS NOT NULL")
        total_partidos_detalles = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='checkpoints_detalles_partidos'")
        if cur.fetchone()[0]:
            cur.execute("SELECT count(*) FROM checkpoints_detalles_partidos WHERE estado = 'completado'")
            detalles_completados = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM checkpoints_detalles_partidos WHERE estado = 'error'")
            detalles_errores = cur.fetchone()[0]
        else:
            detalles_completados = 0
            detalles_errores = 0

        # Estadísticas de FotMob
        cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='fotmob_partidos'")
        if cur.fetchone()[0]:
            cur.execute("SELECT count(*) FROM fotmob_partidos")
            fotmob_partidos = cur.fetchone()[0]
            cur.execute("SELECT count(DISTINCT fotmob_league_id) FROM competiciones_fotmob WHERE fotmob_league_id IS NOT NULL")
            fotmob_ligas = cur.fetchone()[0]
            
            cur.execute("SELECT count(DISTINCT match_id) FROM fotmob_partidos_estadisticas")
            fotmob_partidos_con_stats = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM fotmob_partidos_estadisticas")
            fotmob_stats_filas = cur.fetchone()[0]

            # Estadísticas de Enrutador 80/20
            try:
                cur.execute("SELECT count(*) FROM competiciones_fotmob WHERE ruta_optima = 'fotmob'")
                router_fm = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM competiciones_fotmob WHERE ruta_optima = 'flashscore'")
                router_fs = cur.fetchone()[0]
            except Exception:
                router_fm, router_fs = 0, 0
        else:
            fotmob_partidos = 0
            fotmob_ligas = 0
            fotmob_partidos_con_stats = 0
            fotmob_stats_filas = 0
            router_fm = 0
            router_fs = 0
        
    return {
        'total_comps': total_comps,
        'completadas': completadas,
        'errores': errores,
        'pendientes': pendientes,
        'total_partidos': total_partidos,
        'partidos_por_estado': partidos_por_estado,
        'total_partidos_detalles': total_partidos_detalles,
        'detalles_completados': detalles_completados,
        'detalles_errores': detalles_errores,
        'fotmob_partidos': fotmob_partidos,
        'fotmob_ligas': fotmob_ligas,
        'fotmob_partidos_con_stats': fotmob_partidos_con_stats,
        'fotmob_stats_filas': fotmob_stats_filas,
        'router_fm': router_fm,
        'router_fs': router_fs
    }

def mostrar_banner():
    stats = get_db_stats()
    print("=" * 65)
    print("   SISTEMA DE SCRAPING Y BASE DE DATOS BETPLAY - FLASHSCORE / FOTMOB")
    print("=" * 65)
    if stats:
        pct_comp = (stats['completadas'] / stats['total_comps'] * 100) if stats['total_comps'] > 0 else 0
        pct_det = (stats['detalles_completados'] / stats['total_partidos_detalles'] * 100) if stats['total_partidos_detalles'] > 0 else 0
        print(f" Flashscore:  {stats['completadas']}/{stats['total_comps']} comps ({pct_comp:.1f}%) | Partidos: {stats['total_partidos']} | Detalles: {stats['detalles_completados']:,}")
        if stats.get('fotmob_partidos', 0) > 0:
            print(f" FotMob:      {stats['fotmob_ligas']} ligas | {stats['fotmob_partidos']:,} partidos | {stats['fotmob_partidos_con_stats']} partidos con stats ({stats['fotmob_stats_filas']:,} métricas en DB)")
        if stats.get('router_fm', 0) > 0:
            print(f" Router 80/20: FotMob: {stats['router_fm']} ligas (78.7%) | Flashscore: {stats['router_fs']} ligas (21.3%)")
    print("-" * 65)

def ejecutar_comando(args_list):
    cmd = [sys.executable, SCRAPER_SCRIPT] + args_list
    print(f"\n[+] Ejecutando: {' '.join(cmd)}\n")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n\n[!] Proceso interrumpido por el usuario (los checkpoints guardaron el progreso).")
    try:
        input("\nPresione ENTER para volver al menú principal...")
    except (EOFError, KeyboardInterrupt):
        pass

def opcion_descargar_pendientes():
    limpiar_pantalla()
    print(">>> 1. REANUDAR DESCARGA (Solo competiciones pendientes)\n")
    print("Este modo saltará automáticamente todas las competiciones ya completadas")
    print("y descargará las pendientes hasta completar las 205.\n")
    confirm = input("¿Desea iniciar? (s/n): ").strip().lower()
    if confirm in ('s', 'si', 'y', 'yes'):
        ejecutar_comando(["--all"])

def opcion_actualizacion_incremental():
    limpiar_pantalla()
    print(">>> 2. ACTUALIZACIÓN INCREMENTAL (Solo partidos nuevos y cambios)\n")
    print("Este modo recorre las competiciones ya completadas de forma ligera:")
    print("- NO re-descarga el historial antiguo.")
    print("- Solo extrae los partidos recientes y próximos.")
    print("- Detecta si un partido finalizó o cambió marcador y lo actualiza.")
    print("- Inserta partidos nuevos sin duplicar datos.\n")
    
    print("Alcance de la actualización:")
    print("  1. Todas las competiciones completadas")
    print("  2. Filtrar por país específico")
    print("  0. Volver")
    sub = input("\nSeleccione una opción: ").strip()
    
    if sub == "1":
        ejecutar_comando(["--all", "--incremental"])
    elif sub == "2":
        pais = input("Ingrese el nombre o slug del país (ej. colombia, espana, inglaterra): ").strip()
        if pais:
            ejecutar_comando(["--pais", pais, "--incremental"])

def opcion_descargar_por_pais():
    limpiar_pantalla()
    print(">>> 3. DESCARGAR POR PAÍS\n")
    pais = input("Ingrese el país a procesar (ej. colombia, espana, argentina, brasil): ").strip()
    if not pais:
        return
        
    print("\nModo:")
    print("  1. Reanudar pendientes del país (saltar ya completadas)")
    print("  2. Incremental (buscar solo nuevos partidos del país)")
    print("  3. Forzar descarga completa de todas las competiciones del país")
    modo = input("Seleccione modo (1/2/3): ").strip()
    
    if modo == "1":
        ejecutar_comando(["--pais", pais])
    elif modo == "2":
        ejecutar_comando(["--pais", pais, "--incremental"])
    elif modo == "3":
        ejecutar_comando(["--pais", pais, "--force"])

def opcion_descargar_por_competicion():
    limpiar_pantalla()
    print(">>> 4. DESCARGAR POR COMPETICIÓN\n")
    comp = input("Ingrese nombre o slug de la competición (ej. laliga-ea-sports, premier-league, primera-a): ").strip()
    if not comp:
        return
        
    print("\nModo:")
    print("  1. Reanudar / Completo")
    print("  2. Incremental (solo validar nuevos partidos)")
    print("  3. Forzar descarga completa")
    modo = input("Seleccione modo (1/2/3): ").strip()
    
    if modo == "1":
        ejecutar_comando(["--competicion", comp])
    elif modo == "2":
        ejecutar_comando(["--competicion", comp, "--incremental"])
    elif modo == "3":
        ejecutar_comando(["--competicion", comp, "--force"])

def opcion_ver_estado():
    limpiar_pantalla()
    print("=" * 65)
    print(">>> 5. ESTADO DETALLADO DE CHECKPOINTS Y ESTADÍSTICAS")
    print("=" * 65)
    print("\n--- [A] CHECKPOINTS DE COMPETICIONES (PARTIDOS GENERALES) ---")
    subprocess.run([sys.executable, SCRAPER_SCRIPT, "--status"])
    print("\n--- [B] CHECKPOINTS DE DETALLES DE PARTIDOS (JSON + SQLITE) ---")
    script_d = os.path.join(BASE_DIR, 'scraper_detalles_partidos.py')
    subprocess.run([sys.executable, script_d, "--status"])
    try:
        input("\nPresione ENTER para volver al menú principal...")
    except (EOFError, KeyboardInterrupt):
        pass

def opcion_reintentar_errores():
    limpiar_pantalla()
    print(">>> 6. REINTENTAR COMPETICIONES CON ERROR\n")
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT c.id, p.nombre_betplay, c.nombre_flashscore, cp.error, cp.fecha_actualizacion
        FROM checkpoints_competiciones cp
        JOIN competiciones c ON cp.competicion_id = c.id
        JOIN paises p ON c.pais_id = p.id
        WHERE cp.estado = 'error'
        """)
        errores = cur.fetchall()
        
    if not errores:
        print("[+] No hay competiciones en estado de error. ¡Todo limpio!")
        try:
            input("\nPresione ENTER para volver...")
        except (EOFError, KeyboardInterrupt):
            pass
        return
        
    print(f"Se encontraron {len(errores)} competiciones con error:")
    for eid, pais, comp, err, fecha in errores:
        print(f"  - #{eid} [{pais}] {comp}: {err} ({fecha})")
        
    try:
        confirm = input("\n¿Desea reintentar estas competiciones ahora? (s/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        confirm = 'n'
        
    if confirm in ('s', 'si', 'y', 'yes'):
        with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
            conn.execute("UPDATE checkpoints_competiciones SET estado = 'pendiente' WHERE estado = 'error'")
            conn.commit()
        ejecutar_comando(["--all"])

def opcion_forzar_todo():
    limpiar_pantalla()
    print(">>> 7. FORZAR RE-DESCARGA COMPLETA\n")
    print("[!] ATENCIÓN: Esta opción ignorará todos los checkpoints y volverá a")
    print("    descargar las 205 competiciones desde cero en Flashscore.")
    confirm = input("\n¿Está completamente seguro? Escriba 'CONFIRMAR': ").strip()
    if confirm == "CONFIRMAR":
        ejecutar_comando(["--all", "--force"])

def opcion_estadisticas_avanzadas():
    limpiar_pantalla()
    print(">>> 8. ESTADÍSTICAS AVANZADAS & RADAR DE VALOR BETPLAY\n")
    print(" [1] Calcular competición puntual (por ID)")
    print(" [2] Calcular TODAS las competiciones en lote + Cruzar con Betplay (Recomendado)")
    print(" [3] Analizar y Priorizar Mercados Betplay (Radar de Apuestas de Valor / Edge)")
    print(" [0] Volver")
    sub_opc = input("\nSeleccione una opción [1/2/3/0]: ").strip()

    if sub_opc == "0":
        return

    if sub_opc == "3":
        limpiar_pantalla()
        print(">>> RADAR DE VALOR: Cruzando estadísticas reales contra cuotas de Betplay...\n")
        from analizador_betplay import BetplayMarketPrioritizer
        prioritizer = BetplayMarketPrioritizer()
        try:
            prioritizer.run_analysis()
        finally:
            prioritizer.close()
        try:
            input("\nPresione ENTER para volver al menú principal...")
        except (EOFError, KeyboardInterrupt):
            pass
        return

    from estadisticas_liga import LeagueStatsCalculator, print_cli_report
    calc = LeagueStatsCalculator()
    try:
        if sub_opc == "2":
            limpiar_pantalla()
            print(">>> MODO MASIVO: Estadísticas para todas las competiciones\n")
            calc.calculate_all_competitions()
            print("\n[*] Cruzando automáticamente con cuotas de Betplay para detectar apuestas de valor...")
            from analizador_betplay import BetplayMarketPrioritizer
            prioritizer = BetplayMarketPrioritizer()
            try:
                prioritizer.run_analysis()
            finally:
                prioritizer.close()
        else:
            comps = calc.get_competitions()
            if not comps:
                print("[!] No hay competiciones con partidos cargados en la base de datos.")
                input("\nPresione ENTER para volver...")
                return

            print("\nCompeticiones disponibles con datos:")
            for idx, c in enumerate(comps[:25], 1):
                print(f"  [{c['id']}] {c['pais_nombre']} - {c['nombre_flashscore']} ({c['total_partidos']} partidos)")
            if len(comps) > 25:
                print(f"  ... y {len(comps) - 25} competiciones más.")

            comp_id_in = input("\nIngrese el ID de la competición (o presione ENTER para LaLiga [84]): ").strip()
            comp_id = int(comp_id_in) if comp_id_in else 84

            limpiar_pantalla()
            print(f"[*] Calculando estadísticas avanzadas para competición ID: {comp_id}...")
            report = calc.calculate_for_competition(comp_id)
            if "error" in report:
                print(f"[!] {report['error']}")
            else:
                print_cli_report(report)
                exp = input("\n¿Desea exportar estas estadísticas a JSON? (s/n): ").strip().lower()
                if exp in ('s', 'si', 'y', 'yes'):
                    out_name = f"estadisticas_comp_{comp_id}.json"
                    out_path = os.path.join(BASE_DIR, out_name)
                    import json
                    with open(out_path, 'w', encoding='utf-8') as f:
                        json.dump(report, f, ensure_ascii=False, indent=2)
                    print(f"[✓] Archivo exportado en: {out_path}")
    except Exception as e:
        print(f"[!] Error al procesar estadísticas: {e}")
    finally:
        calc.close()

    try:
        input("\nPresione ENTER para volver al menú principal...")
    except (EOFError, KeyboardInterrupt):
        pass

def opcion_abrir_dashboard_web():
    limpiar_pantalla()
    print(">>> 9. ABRIR DASHBOARD WEB EN EL NAVEGADOR\n")
    import webbrowser
    html_path = os.path.join(BASE_DIR, 'view', 'index.html')
    if os.path.exists(html_path):
        print(f"[*] Abriendo dashboard web en su navegador: {html_path}")
        webbrowser.open(f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}")
    else:
        print(f"[!] No se encontró el archivo: {html_path}")
    time.sleep(1.5)

def opcion_abrir_explorador_cuotas():
    limpiar_pantalla()
    print(">>> 10. ABRIR EXPLORADOR DE CUOTAS POR EVENTO (HTML5)\n")
    import webbrowser
    html_path = os.path.join(BASE_DIR, 'view', 'cuotas.html')
    if os.path.exists(html_path):
        print(f"[*] Abriendo explorador de cuotas en su navegador: {html_path}")
        webbrowser.open(f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}")
    else:
        print(f"[!] No se encontró el archivo: {html_path}")
    time.sleep(1.5)

def opcion_gestionar_boxscores():
    limpiar_pantalla()
    print("=" * 65)
    print(">>> 11. GESTIÓN DE BOXSCORES ESPN & DASHBOARD CLAUDE_INDEX")
    print("=" * 65)
    print(" [1] Actualizar Boxscores ESPN (Ayer, Hoy y Mañana)")
    print(" [2] Iniciar Servidor Local API & Web (http://127.0.0.1:8765)")
    print(" [3] Regenerar Mapeo Betplay <-> Flashscore <-> ESPN")
    print(" [4] Abrir claude_index/index.html en el Navegador")
    print(" [0] Volver al menú principal")
    print("-" * 65)
    sub = input("Seleccione una sub-opción: ").strip()
    script_box = os.path.join(BASE_DIR, 'claude_index', 'boxscore_espn.py')
    script_map = os.path.join(BASE_DIR, 'claude_index', 'build_mapping.py')
    
    if sub == "1":
        print("\n[*] Descargando y cruzando boxscores de ESPN para Ayer, Hoy y Mañana...")
        cmd = [sys.executable, script_box, "run", "--fecha", "ayer", "--fecha", "hoy", "--fecha", "manana"]
        subprocess.run(cmd)
        input("\nPresione ENTER para continuar...")
    elif sub == "2":
        print("\n[*] Iniciando Servidor Local de Boxscores y Dashboard...")
        print("[*] Presione Ctrl+C en cualquier momento para detener el servidor.\n")
        cmd = [sys.executable, script_box, "serve", "--puerto", "8765"]
        try:
            import webbrowser
            webbrowser.open("http://127.0.0.1:8765/")
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print("\n[!] Servidor detenido por el usuario.")
            time.sleep(1)
    elif sub == "3":
        print("\n[*] Reconstruyendo mapeo de competiciones...")
        cmd = [sys.executable, script_map]
        subprocess.run(cmd, cwd=os.path.join(BASE_DIR, 'claude_index'))
        input("\nPresione ENTER para continuar...")
    elif sub == "4":
        import webbrowser
        html_path = os.path.join(BASE_DIR, 'claude_index', 'index.html')
        print(f"[*] Abriendo: {html_path}")
        webbrowser.open(f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}")
        time.sleep(1.5)

def opcion_marcar_favoritas():
    limpiar_pantalla()
    print("=" * 65)
    print(">>> 12. ANCLAR LIGAS DE BETPLAY EN FAVORITAS DE FLASHSCORE")
    print("=" * 65)
    print(" [1] Abrir navegador automáticamente y anclarlas (Playwright)")
    print(" [2] Generar código JavaScript para la consola del navegador")
    print(" [0] Volver al menú principal")
    print("-" * 65)
    sub = input("Seleccione una opción: ").strip()
    script_fav = os.path.join(BASE_DIR, 'marcar_favoritas_flashscore.py')

    if sub == "1":
        subprocess.run([sys.executable, script_fav, "--browser"])
        input("\nPresione ENTER para continuar...")
    elif sub == "2":
        subprocess.run([sys.executable, script_fav, "--snippet"])
        input("\nPresione ENTER para continuar...")

def opcion_descargar_cuotas_betplay():
    limpiar_pantalla()
    print("=" * 65)
    print(">>> 13. DESCARGA DE CUOTAS Y MERCADOS BETPLAY (SIN ESPORTS)")
    print("=" * 65)
    print("Este módulo:")
    print(" - Extrae partidos reales y cuotas de BetPlay (9 categorías canónicas).")
    print(" - Filtra estrictamente Esports, Cyber, FIFA y apuestas outright.")
    print(" - Guarda en SQLite (betplay_partidos, betplay_cuotas) y JSON con historial.")
    print(" - Recalcula el Radar de Valor y actualiza los Dashboards Web automáticamente.\n")
    print("Seleccione el alcance temporal:")
    print(" [1] Partidos de HOY (Hora Colombia)")
    print(" [2] Partidos de MAÑANA (Hora Colombia)")
    print(" [3] Partidos de la SEMANA COMPLETA (Próximos 7 días)")
    print(" [4] Partidos de los próximos N días")
    print(" [5] Partidos de una FECHA ESPECÍFICA (YYYY-MM-DD)")
    print(" [6] TODOS los partidos disponibles en BetPlay")
    print(" [0] Volver al menú principal")
    print("-" * 65)
    try:
        sub = input("\nSeleccione una opción [1/2/3/4/5/6/0]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    script_c = os.path.join(BASE_DIR, 'scraper_betplay_cuotas.py')

    if sub == "1":
        subprocess.run([sys.executable, script_c, "--hoy"])
    elif sub == "2":
        subprocess.run([sys.executable, script_c, "--manana"])
    elif sub == "3":
        subprocess.run([sys.executable, script_c, "--semana"])
    elif sub == "4":
        try:
            dias_in = input("Ingrese número de días hacia adelante (ej. 5): ").strip()
            dias = int(dias_in) if dias_in else 7
            subprocess.run([sys.executable, script_c, "--dias", str(dias)])
        except ValueError:
            print("[!] Número de días inválido.")
    elif sub == "5":
        fecha_in = input("Ingrese la fecha (YYYY-MM-DD, ej. 2026-10-18): ").strip()
        if fecha_in:
            subprocess.run([sys.executable, script_c, "--fecha", fecha_in])
    elif sub == "6":
        subprocess.run([sys.executable, script_c, "--todos"])

    if sub in ("1", "2", "3", "4", "5", "6"):
        try:
            input("\nPresione ENTER para continuar...")
        except (EOFError, KeyboardInterrupt):
            pass

def opcion_descargar_partidos_hoy():
    limpiar_pantalla()
    print("=" * 65)
    print(">>> 14. DESCARGAR PARTIDOS DE HOY FLASHSCORE (SOLO COMPETICIONES ACTIVAS)")
    print("=" * 65)
    print("Este módulo:")
    print(" - Conecta con Flashscore y detecta qué competiciones jugaron hoy.")
    print(" - Filtra únicamente las competiciones que cubrimos en Betplay.")
    print(" - Actualiza los marcadores finales de hoy en la tabla 'partidos'.")
    print(" - Se ejecuta en ~6 segundos en lugar de recorrer las 205 competiciones.")
    print(" - Actualiza estadísticas de liga y checkpoints automáticamente.\n")
    print("Modo:")
    print(" [1] Partidos de Hoy (En vivo y Finalizados)")
    print(" [2] Partidos de Ayer (Resultados consolidados de la fecha anterior)")
    print(" [0] Volver")
    try:
        sub = input("\nSeleccione una opción [1/2/0]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    script_h = os.path.join(BASE_DIR, 'scraper_hoy_flashscore.py')
    if sub == "1":
        subprocess.run([sys.executable, script_h])
        try:
            input("\nPresione ENTER para continuar...")
        except (EOFError, KeyboardInterrupt):
            pass
    elif sub == "2":
        subprocess.run([sys.executable, script_h, "--ayer"])
        try:
            input("\nPresione ENTER para continuar...")
        except (EOFError, KeyboardInterrupt):
            pass

def opcion_flujo_diario_completo():
    limpiar_pantalla()
    print("=" * 65)
    print(">>> 15. FLUJO DIARIO INTEGRAL (HOY FLASHSCORE + CUOTAS BETPLAY + RADAR)")
    print("=" * 65)
    print("Ejecuta la sincronización completa del día:")
    print(" 1. Descarga resultados de partidos que jugaron HOY en Flashscore.")
    print(" 2. Descarga cuotas completas de partidos de HOY y MAÑANA en Betplay.")
    print(" 3. Recalcula el Radar de Valor (Edge) y actualiza los Dashboards Web.\n")
    try:
        confirm = input("¿Desea ejecutar el flujo diario integral ahora? (s/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if confirm in ('s', 'si', 'y', 'yes'):
        script_h = os.path.join(BASE_DIR, 'scraper_hoy_flashscore.py')
        script_c = os.path.join(BASE_DIR, 'scraper_betplay_cuotas.py')
        
        print("\n--- PASO 1/3: Descargando partidos de hoy en Flashscore ---")
        subprocess.run([sys.executable, script_h, "--no-stats"])
        
        print("\n--- PASO 2/3: Descargando cuotas de hoy y mañana en Betplay ---")
        subprocess.run([sys.executable, script_c, "--hoy"])
        subprocess.run([sys.executable, script_c, "--manana"])
        
        print("\n[✓] ¡Flujo diario integral completado con éxito!")
        try:
            input("\nPresione ENTER para continuar...")
        except (EOFError, KeyboardInterrupt):
            pass

def opcion_detalles_partidos():
    limpiar_pantalla()
    script_d = os.path.join(BASE_DIR, 'scraper_detalles_partidos.py')
    print("=" * 65)
    print(">>> 16. DETALLES DE PARTIDOS (JSON + SQLITE)")
    print("=" * 65)
    print("Extracción completa de:")
    print(" - Resumen (Goles, tarjetas, sustituciones, asistencias)")
    print(" - Estadísticas (Partido, 1T, 2T: posesión, xG, remates, pases...)")
    print(" - Alineaciones (Sistemas tácticos, ratings medios, titulares, suplentes, ausencias)")
    print(" - Estadísticas de Jugadores (Principales, remates, pases, defensa...)")
    print("\nModos:")
    print("  1. Ver estado actual de detalles extraídos")
    print("  2. Procesar todos los partidos pendientes (todas las competiciones)")
    print("  3. Procesar un lote limitado (ej. 20, 50, 100 partidos)")
    print("  4. Procesar una competición específica (por ID o nombre)")
    print("  5. Procesar un partido puntual (por ID o URL)")
    print("  0. Volver")
    sub = input("\nSeleccione una opción: ").strip()
    if sub == "1":
        subprocess.run([sys.executable, script_d, "--status"])
    elif sub == "2":
        subprocess.run([sys.executable, script_d])
    elif sub == "3":
        lim = input("Ingrese cantidad de partidos a procesar: ").strip()
        if lim.isdigit():
            subprocess.run([sys.executable, script_d, "--limit", lim])
    elif sub == "4":
        comp = input("Ingrese ID o nombre de la competición: ").strip()
        if comp:
            subprocess.run([sys.executable, script_d, "--competicion", comp])
    elif sub == "5":
        m_id = input("Ingrese ID (mid) o URL del partido: ").strip()
        if m_id:
            subprocess.run([sys.executable, script_d, "--partido", m_id])
    try:
        input("\nPresione ENTER para continuar...")
    except (EOFError, KeyboardInterrupt):
        pass

def opcion_detalles_partidos_optimizado():
    limpiar_pantalla()
    script_d = os.path.join(BASE_DIR, 'scraper_detalles_partidos_optimizado.py')
    print("=" * 65)
    print(">>> 17. DETALLES DE PARTIDOS OPTIMIZADO (PLAYWRIGHT PARALELO)")
    print("=" * 65)
    print("Extracción acelerada con:")
    print(" - Pool de workers concurrentes (default: 4 workers)")
    print(" - Bloqueo de imágenes, medios, fuentes y trackers")
    print(" - SQLite WAL mode & commits thread-safe")
    print(" - Continuidad automática de checkpoints (no repite nada)")
    print("\nModos:")
    print("  1. Ver estado actual de detalles extraídos")
    print("  2. Procesar partidos pendientes (44 competiciones residuales Flashscore)")
    print("  3. Procesar un lote limitado de pendientes (ej. 20, 50, 100 partidos)")
    print("  4. Procesar una competición específica (por ID o nombre)")
    print("  5. Procesar un partido puntual (por ID o URL)")
    print("  6. Procesar partidos pendientes de TODAS las 207 competiciones (ignorar 80/20)")
    print("  0. Volver")
    sub = input("\nSeleccione una opción: ").strip()
    if sub == "1":
        subprocess.run([sys.executable, script_d, "--status"])
    elif sub == "2":
        workers = input("Número de workers paralelos [ENTER para 4]: ").strip()
        cmd = [sys.executable, script_d]
        if workers.isdigit():
            cmd.extend(["--workers", workers])
        subprocess.run(cmd)
    elif sub == "3":
        lim = input("Ingrese cantidad de partidos a procesar: ").strip()
        workers = input("Número de workers paralelos [ENTER para 4]: ").strip()
        if lim.isdigit():
            cmd = [sys.executable, script_d, "--limit", lim]
            if workers.isdigit():
                cmd.extend(["--workers", workers])
            subprocess.run(cmd)
    elif sub == "4":
        comp = input("Ingrese ID o nombre de la competición: ").strip()
        if comp:
            workers = input("Número de workers paralelos [ENTER para 4]: ").strip()
            cmd = [sys.executable, script_d, "--competicion", comp]
            if workers.isdigit():
                cmd.extend(["--workers", workers])
            subprocess.run(cmd)
    elif sub == "5":
        m_id = input("Ingrese ID (mid) o URL del partido: ").strip()
        if m_id:
            subprocess.run([sys.executable, script_d, "--partido", m_id])
    elif sub == "6":
        workers = input("Número de workers paralelos [ENTER para 4]: ").strip()
        cmd = [sys.executable, script_d, "--todas"]
        if workers.isdigit():
            cmd.extend(["--workers", workers])
        subprocess.run(cmd)
    try:
        input("\nPresione ENTER para continuar...")
    except (EOFError, KeyboardInterrupt):
        pass

def opcion_fotmob():
    limpiar_pantalla()
    script_f = os.path.join(BASE_DIR, 'scraper_fotmob_betplay.py')
    print("=" * 65)
    print(">>> 18. FOTMOB: DESCARGA DE PARTIDOS Y ESTADÍSTICAS (BETPLAY)")
    print("=" * 65)
    print("Extracción acelerada vía APIs REST de FotMob (sin navegador):")
    print(" - Partidos completos organizados por jornada (Round 1..38)")
    print(" - Árbitro (tarjetas, faltas) | Estadio (capacidad, aforo, césped) | Clima")
    print(" - Estadísticas por tiempo (1T, 2T, Total), xG y Shotmaps con coordenadas")
    print(" - Alineaciones, entrenadores, suplentes y notas de jugadores")
    print(" - Mapas de calor (Heatmaps) vectoriales con coordenadas exactas")
    print(" - Checkpoints automáticos y continuidad incremental")
    print("\nModos:")
    print("  1. Flujo Completo: Descargar Partidos y enseguida Estadísticas")
    print("  2. Sincronizar solo Partidos y Fixtures (Todas las competiciones)")
    print("  3. Descargar solo Estadísticas de Partidos pendientes en DB")
    print("  4. Sincronizar por Competición específica (Partidos + Estadísticas)")
    print("  5. Sincronizar por País específico (Partidos + Estadísticas)")
    print("  6. Descargar Estadísticas de un Partido puntual (por ID)")
    print("  7. Ver Estado y Métricas de FotMob en la Base de Datos")
    print("  0. Volver al menú principal")

    sub = input("\nSeleccione una opción: ").strip()
    if sub == "1":
        lim = input("Límite de partidos con estadísticas por liga [ENTER para 5, 'todos' para todos]: ").strip().lower()
        cmd = [sys.executable, script_f, "--all"]
        if lim.isdigit():
            cmd.extend(["--limit", lim])
        elif lim == "todos":
            pass
        else:
            cmd.extend(["--limit", "5"])
        subprocess.run(cmd)
    elif sub == "2":
        subprocess.run([sys.executable, script_f, "--fixtures-only"])
    elif sub == "3":
        lim = input("Cantidad máxima de partidos pendientes a procesar [ENTER para todos]: ").strip()
        cmd = [sys.executable, script_f, "--stats-only"]
        if lim.isdigit():
            cmd.extend(["--limit", lim])
        subprocess.run(cmd)
    elif sub == "4":
        comp = input("Ingrese ID o nombre de la competición (ej. 47 o Premier League): ").strip()
        if comp:
            lim = input("Límite de partidos para estadísticas [ENTER para todos]: ").strip()
            cmd = [sys.executable, script_f, "--league", comp]
            if lim.isdigit():
                cmd.extend(["--limit", lim])
            subprocess.run(cmd)
    elif sub == "5":
        pais = input("Ingrese nombre del país (ej. Inglaterra, Colombia, Espana): ").strip()
        if pais:
            lim = input("Límite de partidos por liga [ENTER para 5, 'todos' para todos]: ").strip().lower()
            cmd = [sys.executable, script_f, "--pais", pais]
            if lim.isdigit():
                cmd.extend(["--limit", lim])
            subprocess.run(cmd)
    elif sub == "6":
        m_id = input("Ingrese ID del partido en FotMob (ej. 5795478): ").strip()
        if m_id:
            subprocess.run([sys.executable, script_f, "--match", m_id])
    elif sub == "7":
        subprocess.run([sys.executable, script_f, "--status"])

    try:
        input("\nPresione ENTER para continuar...")
    except (EOFError, KeyboardInterrupt):
        pass

def opcion_descarga_hibrida():
    limpiar_pantalla()
    script_h = os.path.join(BASE_DIR, 'ejecutar_descarga_hibrida.py')
    print("=" * 68)
    print(">>> 19. INGESTA HÍBRIDA ASIMÉTRICA 80/20 (FOTMOB + FLASHSCORE)")
    print("=" * 68)
    print("Arquitectura de máximo rendimiento para las 207 competiciones:")
    print(" - Fase 1 (FotMob REST API): 163 competiciones (~80%) en ~200ms por partido")
    print("   (Shotmaps x,y, Heatmaps individuales, xG Opta, clima y estadio)")
    print(" - Fase 2 (Flashscore Browser): 44 competiciones (~20%) residuales")
    print("   (Tercera RFEF, Reservas U23, ligas sin cobertura en Opta)\n")
    print("Modalidades de ejecución:")
    print("  [1] Flujo Completo 80/20 (Sincronizar Fixtures + Partidos Nuevos con Checkpoints)")
    print("  [2] Modo Incremental Rápido (Solo descargar partidos pendientes según Checkpoints)")
    print("  [3] Ejecutar solo Fase 1 (163 competiciones FotMob vía REST API)")
    print("  [4] Ejecutar solo Fase 2 (44 competiciones Flashscore vía Browser)")
    print("  [5] Ver Estado, Distribución y Checkpoints del Enrutador")
    print("  [6] Prueba Rápida con límite de partidos por liga (--limit N)")
    print("  [0] Volver al menú principal")
    print("-" * 68)

    try:
        sub = input("\nSeleccione una opción: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if sub == "1":
        subprocess.run([sys.executable, script_h, "--all"])
    elif sub == "2":
        subprocess.run([sys.executable, script_h, "--incremental"])
    elif sub == "3":
        subprocess.run([sys.executable, script_h, "--fotmob-only"])
    elif sub == "4":
        subprocess.run([sys.executable, script_h, "--flashscore-only"])
    elif sub == "5":
        subprocess.run([sys.executable, script_h, "--status"])
    elif sub == "6":
        lim = input("Ingrese límite de partidos por liga (ej. 3): ").strip()
        lim_val = lim if lim.isdigit() else "3"
        subprocess.run([sys.executable, script_h, "--all", "--limit", lim_val])

    if sub in ("1", "2", "3", "4", "5", "6"):
        try:
            input("\nPresione ENTER para continuar...")
        except (EOFError, KeyboardInterrupt):
            pass

def main():
    while True:
        limpiar_pantalla()
        mostrar_banner()
        print(" [1] Reanudar descarga (Descargar solo las pendientes)")
        print(" [2] Actualización incremental (Buscar nuevos partidos y cambios)")
        print(" [3] Descargar / Actualizar por País")
        print(" [4] Descargar / Actualizar por Competición puntual")
        print(" [5] Ver estado detallado de checkpoints y estadísticas")
        print(" [6] Reintentar competiciones fallidas")
        print(" [7] Forzar re-descarga completa de todo desde cero")
        print(" [8] Calcular Estadísticas Avanzadas de Liga (Estilo SoccerStats)")
        print(" [9] Abrir Dashboard Web en el Navegador (Ligas & Radar)")
        print(" [10] Abrir Explorador de Cuotas por Evento (Mercados & Trazabilidad)")
        print(" [11] Gestionar Boxscores ESPN & claude_index (Actualizar / Servidor Local)")
        print(" [12] Anclar Ligas de Betplay en Favoritas de Flashscore (186 Ligas)")
        print(" [13] Descargar Cuotas Betplay (Hoy / Mañana / Semana completa - Sin Esports)")
        print(" [14] Descargar Partidos de Hoy Flashscore (Solo competiciones que jugaron hoy)")
        print(" [15] Flujo Diario Completo (Hoy Flashscore + Cuotas Betplay + Radar de Valor)")
        print(" [16] Extraer Detalles de Partidos (Original: Secuencial)")
        print(" [17] Extraer Detalles de Partidos OPTIMIZADO (Playwright Paralelo / Workers)")
        print(" [18] Sincronizar FotMob (Descargar Partidos y Estadísticas Betplay)")
        print(" [19] Ingesta Híbrida 80/20 (FotMob REST 163 Ligas + Flashscore 44 Ligas)")
        print(" [0] Salir")
        print("-" * 65)
        
        eleccion = input("Seleccione una opción: ").strip()
        
        if eleccion == "1":
            opcion_descargar_pendientes()
        elif eleccion == "2":
            opcion_actualizacion_incremental()
        elif eleccion == "3":
            opcion_descargar_por_pais()
        elif eleccion == "4":
            opcion_descargar_por_competicion()
        elif eleccion == "5":
            opcion_ver_estado()
        elif eleccion == "6":
            opcion_reintentar_errores()
        elif eleccion == "7":
            opcion_forzar_todo()
        elif eleccion == "8":
            opcion_estadisticas_avanzadas()
        elif eleccion == "9":
            opcion_abrir_dashboard_web()
        elif eleccion == "10":
            opcion_abrir_explorador_cuotas()
        elif eleccion == "11":
            opcion_gestionar_boxscores()
        elif eleccion == "12":
            opcion_marcar_favoritas()
        elif eleccion == "13":
            opcion_descargar_cuotas_betplay()
        elif eleccion == "14":
            opcion_descargar_partidos_hoy()
        elif eleccion == "15":
            opcion_flujo_diario_completo()
        elif eleccion == "16":
            opcion_detalles_partidos()
        elif eleccion == "17":
            opcion_detalles_partidos_optimizado()
        elif eleccion == "18":
            opcion_fotmob()
        elif eleccion == "19":
            opcion_descarga_hibrida()
        elif eleccion == "0":
            limpiar_pantalla()
            print("Hasta luego.")
            sys.exit(0)
        else:
            print("[!] Opción inválida. Intente de nuevo.")
            time.sleep(1)

if __name__ == '__main__':
    main()


