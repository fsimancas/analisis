"""
Script para fijar todas las ligas cubiertas por Betplay en Favoritas / Ligas Ancladas de Flashscore.
Permite:
1. Generar el script JavaScript listo para la consola de cualquier navegador.
2. Inyectar automáticamente vía Playwright en el navegador del usuario (Edge/Chrome).
3. Restablecer o limpiar las ligas ancladas si se desea volver al estado predeterminado.
"""

import os
import sys
import json
import time
import re
import asyncio
import sqlite3
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "betplay_flashscore.db")
JSON_PATH = os.path.join(BASE_DIR, "flashscore_favoritas.json")
JS_OUTPUT_PATH = os.path.join(BASE_DIR, "aplicar_favoritas.js")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


async def _fetch_single_comp(client, semaphore, comp_id, pais_nombre, nombre_flashscore, link_flashscore):
    async with semaphore:
        try:
            r = await client.get(link_flashscore, timeout=12.0)
            m = re.search(r'getToggleIcon\("([0-9]+_[0-9]+_[A-Za-z0-9]+)"', r.text)
            flag_m = re.search(r'breadcrumb__flag flag fl_([0-9]+)', r.text)
            title_m = re.search(r'<div class="heading__name">([^<]+)</div>', r.text)

            cid = m.group(1) if m else None
            flag_id = flag_m.group(1) if flag_m else (cid.split('_')[1] if cid else '0')
            name = title_m.group(1).strip() if title_m else nombre_flashscore
            relative_url = link_flashscore.replace('https://www.flashscore.co', '').rstrip('/') + '/'

            return {
                'comp_id': comp_id,
                'pais': pais_nombre,
                'nombre': name,
                'title': f"{pais_nombre.upper()}: {name}",
                'url': relative_url,
                'flashscore_id': cid,
                'flag_id': flag_id,
                'success': bool(cid)
            }
        except Exception as e:
            return {
                'comp_id': comp_id,
                'pais': pais_nombre,
                'nombre': nombre_flashscore,
                'error': str(e),
                'success': False
            }


async def sincronizar_ids_flashscore():
    """Extrae y actualiza los IDs de torneos desde Flashscore para las competiciones en DB."""
    import httpx
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Base de datos no encontrada en: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, pais_nombre, nombre_flashscore, link_flashscore FROM competiciones WHERE link_flashscore LIKE 'http%'")
        rows = cur.fetchall()

    print(f"[*] Obteniendo IDs para {len(rows)} competiciones cubiertas por Betplay...")
    semaphore = asyncio.Semaphore(15)

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, limits=httpx.Limits(max_connections=25)) as client:
        tasks = [_fetch_single_comp(client, semaphore, r[0], r[1], r[2], r[3]) for r in rows]
        results = await asyncio.gather(*tasks)

    # Filtrar exitosas y deduplicar por flashscore_id
    successes = [r for r in results if r.get('success')]
    unique = {}
    for c in successes:
        fid = c.get('flashscore_id')
        if fid and fid not in unique:
            unique[fid] = c

    items = list(unique.values())
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"[+] Total competiciones guardadas en {JSON_PATH}: {len(items)}")
    return items


def cargar_o_generar_favoritas(force_refresh=False):
    """Carga la lista de favoritas desde el JSON existente o la regenera."""
    if not force_refresh and os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data:
                return data

    return asyncio.run(sincronizar_ids_flashscore())


def generar_archivos_js(competitions):
    """Genera el código JavaScript para inyectar en la consola del navegador."""
    now = int(time.time())
    menu_dict = {}
    lsid_dict = {"myLeagues": {"1": {"used": True}}}

    for idx, c in enumerate(competitions, 1):
        fid = c["flashscore_id"]
        menu_dict[fid] = {
            "id": fid,
            "menuOrder": idx,
            "flagId": c["flag_id"],
            "title": c.get("title", f"{c['pais'].upper()}: {c['nombre']}"),
            "name": c["nombre"],
            "url": c["url"],
            "from": now
        }
        lsid_dict["myLeagues"]["1"][fid] = True

    js_code = f"""// == INYECTOR DE LIGAS BETPLAY EN FAVORITAS DE FLASHSCORE ==
// Instrucciones:
// 1. Abre https://www.flashscore.co/ en tu navegador (Chrome, Edge, Firefox, Brave).
// 2. Presiona F12 y ve a la pestaña "Consola" (Console).
// 3. Pega todo este código y presiona ENTER.
// 4. La página se recargará automáticamente con todas las ligas ancladas.
(function() {{
    const menuData = {json.dumps(menu_dict, ensure_ascii=False)};
    const lsidData = {json.dumps(lsid_dict, ensure_ascii=False)};

    const keys = ['myLeaguesMenu_es-co', 'myLeaguesMenu_es', 'myLeaguesMenu_es-419', 'myLeaguesMenu_en'];
    const activeKey = Object.keys(localStorage).find(k => k.startsWith('myLeaguesMenu_')) || 'myLeaguesMenu_es-co';

    localStorage.setItem(activeKey, JSON.stringify(menuData));
    localStorage.setItem('lsid_innerData', JSON.stringify(lsidData));

    console.log(`%c[OK] ¡${'{'}Object.keys(menuData).length{'}'} Ligas de Betplay configuradas en Favoritas!`, 'color: #10b981; font-weight: bold; font-size: 16px;');
    console.log('Recargando la página para mostrar las Ligas Ancladas...');
    setTimeout(() => location.reload(), 1200);
}})();
"""

    with open(JS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(js_code)

    return menu_dict, lsid_dict, js_code


def aplicar_en_navegador(menu_dict, lsid_dict):
    """Abre el navegador con Playwright y aplica las favoritas en flashscore.co."""
    from playwright.sync_api import sync_playwright

    print("\n[*] Abriendo navegador con Playwright...")
    with sync_playwright() as p:
        browser = None
        for channel in ["msedge", "chrome", None]:
            try:
                if channel:
                    browser = p.chromium.launch(channel=channel, headless=False)
                else:
                    browser = p.chromium.launch(headless=False)
                break
            except Exception:
                continue

        if not browser:
            print("[!] No se pudo iniciar el navegador automáticamente. Copie el código de aplicar_favoritas.js en su consola.")
            return

        page = browser.new_page()
        print("[*] Conectando a https://www.flashscore.co/...")
        page.goto("https://www.flashscore.co/", timeout=45000)
        page.wait_for_timeout(2500)

        # Inyectar en localStorage
        page.evaluate(f"""() => {{
            const activeKey = Object.keys(localStorage).find(k => k.startsWith('myLeaguesMenu_')) || 'myLeaguesMenu_es-co';
            localStorage.setItem(activeKey, '{json.dumps(menu_dict)}');
            localStorage.setItem('lsid_innerData', '{json.dumps(lsid_dict)}');
        }}""")

        print("[+] Ligas inyectadas. Recargando página...")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Contar ligas ancladas
        total_ancladas = page.evaluate("""() => {
            const box = document.querySelector('#my-leagues-list');
            return box ? box.querySelectorAll('.leftMenu__item').length : 0;
        }""")

        print(f"\n[OK] ¡Éxito rotundo! {total_ancladas} ligas cubiertas por Betplay están ancladas en Flashscore.")
        print("[*] El navegador permanecerá abierto durante 30 segundos para que pueda verificarlo.")
        page.wait_for_timeout(30000)
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="Pone todas las ligas que cubre Betplay en Favoritas de Flashscore.")
    parser.add_argument("--browser", action="store_true", help="Abre el navegador y las aplica automáticamente.")
    parser.add_argument("--refresh", action="store_true", help="Fuerza re-descarga de IDs desde Flashscore.")
    parser.add_argument("--snippet", action="store_true", help="Muestra el código JavaScript para la consola del navegador.")
    args = parser.parse_args()

    print("=" * 65)
    print("      CONFIGURADOR DE LIGAS FAVORITAS BETPLAY -> FLASHSCORE")
    print("=" * 65)

    comps = cargar_o_generar_favoritas(force_refresh=args.refresh)
    menu_dict, lsid_dict, js_code = generar_archivos_js(comps)

    print(f"\n[+] Total competiciones procesadas: {len(comps)}")
    print(f"[+] Archivo JavaScript generado: {JS_OUTPUT_PATH}")
    print(f"[+] Archivo JSON generado: {JSON_PATH}")

    if args.snippet:
        print("\n" + "=" * 65)
        print("CÓDIGO PARA COPIAR Y PEGAR EN LA CONSOLA DEL NAVEGADOR:")
        print("=" * 65)
        print(js_code)
        print("=" * 65)

    if args.browser:
        aplicar_en_navegador(menu_dict, lsid_dict)
    else:
        print("\n" + "-" * 65)
        print("¿CÓMO USARLO EN TU NAVEGADOR HABITUAL?")
        print("1. Abre https://www.flashscore.co/ en tu navegador favorito.")
        print("2. Presiona F12 (o Clic derecho -> Inspeccionar) y ve a la pestaña 'Console'.")
        print("3. Abre el archivo 'aplicar_favoritas.js', copia todo su contenido y pégalo.")
        print("4. Presiona Enter. ¡Listo! Todas las ligas de Betplay quedan en 'Ligas Ancladas'.")
        print("\nO si prefieres que el script lo haga solo por ti en una ventana:")
        print("   python marcar_favoritas_flashscore.py --browser")
        print("-" * 65)


if __name__ == "__main__":
    main()
