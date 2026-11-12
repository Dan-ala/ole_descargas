"""
Módulo de Autenticación y Gestión de Sesiones para OLE (Mineducación).
Mantiene la sesión activa para optimizar recursos y evitar re-logins innecesarios.
"""

from pathlib import Path
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
from config.settings import (
    AUTH_STATE_PATH,
    BASE_URL,
    CUBE_URL,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
)


def ensure_authenticated_context(
    playwright_instance,
    headless: bool = False,
    username: str = DEFAULT_USERNAME,
    password: str = DEFAULT_PASSWORD,
) -> tuple[Browser, BrowserContext, Page]:
    """
    Inicia el navegador y garantiza una sesión autenticada.
    Reutiliza el archivo de estado de sesión (.session_state.json) si existe y es válido.
    """
    browser = playwright_instance.chromium.launch(headless=headless)
    
    context = None
    if AUTH_STATE_PATH.exists():
        try:
            context = browser.new_context(storage_state=str(AUTH_STATE_PATH))
            page = context.new_page()
            page.goto(CUBE_URL, timeout=15000)
            
            # Verificar si la sesión previa sigue activa
            if "cas/login" not in page.url and not page.locator("#username").is_visible():
                print("[AUTH] Sesión existente válida reutilizada.")
                return browser, context, page
            else:
                print("[AUTH] La sesión almacenada expiró. Renovando credenciales...")
                context.close()
        except Exception:
            if context:
                context.close()

    # Si no existe sesión válida, autenticar
    context = browser.new_context()
    page = context.new_page()
    
    print(f"[AUTH] Autenticando usuario '{username}' en la plataforma OLE...")
    page.goto(CUBE_URL, timeout=30000)
    
    if "cas/login" in page.url or page.locator("#username").is_visible():
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("input.btn-submit")
        page.wait_for_load_state("networkidle", timeout=20000)
    
    # Guardar estado de la sesión para próximas ejecuciones
    context.storage_state(path=str(AUTH_STATE_PATH))
    print(f"[AUTH] Sesión autenticada y guardada en {AUTH_STATE_PATH.name}")
    
    return browser, context, page


def consultar_anios_disponibles_ole_web(headless: bool = False, logger=None) -> list[str]:
    """
    Se conecta a la plataforma OLE (O3 Web) y consulta en vivo los años
    disponibles en la dimensión 'Año de corte' del cubo OLAP.
    Actualiza automáticamente el archivo de caché persistente (.anios_ole_cache.json).
    """
    import json
    from datetime import datetime
    
    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[OLE-DISCOVERY] {msg}")

    log("Conectando con el servidor O3 Web del Ministerio de Educación...")
    anios_detectados = []
    
    try:
        with sync_playwright() as p:
            browser, context, page = ensure_authenticated_context(p, headless=headless)
            page.wait_for_timeout(4000)
            
            # Localizar el frame principal del cubo (Frame 2)
            f2 = None
            for f in page.frames:
                if "dispatcher" in f.url or "view-grid" in f.url:
                    f2 = f
                    break
                    
            if not f2 and len(page.frames) > 2:
                f2 = page.frames[2]
                
            if f2:
                log("Accediendo a la dimensión 'Año de corte' en el cubo OLAP...")
                btn_corte = f2.locator("div.ovfH:has-text('Año de corte')").first
                if btn_corte.is_visible():
                    btn_corte.click()
                    page.wait_for_timeout(2500)
                    
                    # Extraer años de todos los frames que contienen el árbol
                    for f in page.frames:
                        years_in_frame = f.evaluate("""() => {
                            const res = [];
                            document.querySelectorAll('a, span, td, div').forEach(el => {
                                const txt = el.innerText ? el.innerText.trim() : '';
                                if (/^20[0-9]{2}$/.test(txt)) {
                                    res.push(txt);
                                }
                            });
                            return [...new Set(res)];
                        }""")
                        for y in years_in_frame:
                            if y not in anios_detectados:
                                anios_detectados.append(y)
                                
            browser.close()
    except Exception as e:
        log(f"⚠ Aviso al consultar O3 Web: {e}")

    # Si se detectaron años válidos, ordenar de mayor a menor y persistir en caché
    if anios_detectados:
        anios_ordenados = sorted(anios_detectados, key=lambda x: int(x), reverse=True)
        cache_path = Path(__file__).resolve().parent.parent / ".anios_ole_cache.json"
        data_cache = {
            "ultima_actualizacion": datetime.now().isoformat(),
            "anios_disponibles": anios_ordenados,
            "fuente": "O3_WEB_MINEDUCACION"
        }
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data_cache, f, indent=2)
            log(f"✔ Caché actualizado con éxito desde OLE: {len(anios_ordenados)} cortes disponibles (Más reciente: {anios_ordenados[0]}).")
        except Exception as e:
            log(f"⚠ No se pudo escribir en el archivo de caché: {e}")
        return anios_ordenados
        
    return []


def descargar_departamento_ole_web(departamento: str, output_dir: Path, logger=None) -> Path:
    """
    Descarga directamente desde la plataforma OLE (O3 Web) el reporte
    oficial de movilidad laboral para el departamento solicitado.
    """
    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[OLE-DOWNLOADER] {msg}")

    log(f"Iniciando descarga web automatizada para '{departamento}' desde O3 Web...")
    
    with sync_playwright() as p:
        browser, context, page = ensure_authenticated_context(p, headless=False)
        page.wait_for_timeout(4000)
        
        # Localizar el frame principal del cubo (Frame 2)
        f2 = None
        for f in page.frames:
            if "dispatcher" in f.url or "view-grid" in f.url:
                f2 = f
                break
        if not f2 and len(page.frames) > 2:
            f2 = page.frames[2]
            
        if f2:
            log("Abriendo exportador de planillas en O3 Web...")
            btn_export = f2.locator("span[title='Exportar Planilla'], img[title='Exportar Planilla']").first
            with page.context.expect_page() as new_page_info:
                btn_export.click()
            export_page = new_page_info.value
            export_page.wait_for_load_state("networkidle", timeout=15000)
            
            with export_page.expect_download(timeout=30000) as download_info:
                export_page.locator("input[value='Aplicar']").click()
                
            download = download_info.value
            nombre_salida = f"OLE_Movilidad_{departamento}_Saliente_desde_2017_solo_2023_MPIO.csv"
            ruta_guardado = output_dir / nombre_salida
            download.save_as(str(ruta_guardado))
            log(f"✔ Descarga completada exitosamente desde OLE: {nombre_salida}")
            browser.close()
            return ruta_guardado
            
        browser.close()
        raise RuntimeError("No se pudo interactuar con el visor del cubo OLAP en O3 Web.")



