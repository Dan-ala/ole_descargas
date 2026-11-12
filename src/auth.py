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
    import time
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
            
            # Espera activa y elástica para detectar el frame del cubo (hasta 5 minutos)
            f2 = None
            start_t = time.time()
            while time.time() - start_t < 300:
                for f in page.frames:
                    if "dispatcher" in f.url or "view-grid" in f.url:
                        f2 = f
                        break
                if f2:
                    break
                page.wait_for_timeout(1000)
                    
            if not f2 and len(page.frames) > 2:
                f2 = page.frames[2]
                
            if f2:
                log("Accediendo a la dimensión 'Año de corte' en el cubo OLAP...")
                btn_corte = f2.locator("div.ovfH:has-text('Año de corte')").first
                try:
                    btn_corte.wait_for(state="visible", timeout=30000)
                    btn_corte.click()
                    page.wait_for_timeout(2500)
                except Exception:
                    pass
                    
                # Extraer años de todos los frames que contienen el árbol
                for f in page.frames:
                    try:
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
                    except Exception:
                        pass
                                
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


def abrir_vista_situacion_laboral_si_es_portal(page: Page, log) -> bool:
    """
    Si la página se encuentra en el portal inicial de O3 Web ('Cubos y Vistas'),
    localiza y hace clic automáticamente en 'Situación laboral' o 'VISTA_MIGRACIÓN_VL'.
    """
    for f in page.frames:
        try:
            # Buscar en árbol del portal o enlaces de cubos
            elem = f.locator("text=/Situaci[oó]n.*laboral/i, a:has-text('Situacion laboral'), a:has-text('Situación laboral'), span:has-text('Situación laboral'), text=/VISTA_MIGRACI[OÓ]N/i").first
            if elem.count() > 0 and elem.is_visible():
                log("Detectado enlace a 'Situación laboral' en el portal. Abriendo automáticamente...")
                elem.click()
                page.wait_for_timeout(2000)
                try:
                    elem.dblclick(timeout=1000)
                except Exception:
                    pass
                return True
        except Exception:
            continue
    return False


def buscar_boton_exportar_en_frames(page: Page):
    """
    Escanea todos los frames de Ideasoft O3 Web buscando el botón o icono
    de exportación a planilla / CSV / Excel mediante títulos, imágenes y atributos.
    """
    js_detector = """() => {
        const all = Array.from(document.querySelectorAll('img, a, span, td, div, button, input'));
        for (const el of all) {
            const title = (el.getAttribute('title') || '').toLowerCase();
            const alt = (el.getAttribute('alt') || '').toLowerCase();
            const src = (el.getAttribute('src') || '').toLowerCase();
            const value = (el.getAttribute('value') || '').toLowerCase();
            const text = (el.innerText || '').toLowerCase();
            
            if (
                title.includes('exportar') || title.includes('planilla') || title.includes('excel') || title.includes('csv') ||
                alt.includes('exportar') || alt.includes('planilla') ||
                src.includes('export') || src.includes('excel') || src.includes('csv') || src.includes('grid_save') ||
                value.includes('exportar')
            ) {
                return { found: true, title: title || alt || src || text || value };
            }
        }
        return { found: false };
    }"""
    
    for f in page.frames:
        try:
            res = f.evaluate(js_detector)
            if res and res.get("found"):
                for sel in [
                    "span[title*='Exportar' i]", "img[title*='Exportar' i]", "*[title*='Exportar Planilla' i]",
                    "*[title*='Planilla' i]", "*[title*='Excel' i]", "*[title*='CSV' i]",
                    "img[src*='export' i]", "img[src*='excel' i]", "img[src*='csv' i]",
                    "a[title*='Exportar' i]", "input[value*='Exportar' i]"
                ]:
                    loc = f.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        return f, loc, res.get("title", "Exportar")
        except Exception:
            continue
    return None, None, None


def descargar_departamento_ole_web(departamento: str, output_dir: Path, logger=None) -> Path:
    """
    Descarga directamente desde la plataforma OLE (O3 Web) el reporte
    oficial de movilidad laboral para el departamento solicitado.
    Automatiza la navegación inicial si está en el portal y detecta
    de forma universal la opción de exportación en Ideasoft O3.
    """
    import time

    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[OLE-DOWNLOADER] {msg}")

    log(f"Iniciando descarga web automatizada para '{departamento}' desde O3 Web...")
    
    with sync_playwright() as p:
        browser, context, page = ensure_authenticated_context(p, headless=False)
        
        log("Supervisando visor del cubo OLAP en O3 Web...")
        target_frame = None
        btn_export = None
        btn_title = ""
        start_time = time.time()
        last_log_time = start_time
        
        while time.time() - start_time < 300:
            # 1. Si está en el portal inicial, hacer clic automático en Situación Laboral
            abrir_vista_situacion_laboral_si_es_portal(page, log)
            
            # 2. Buscar el botón de exportación en todos los frames
            target_frame, btn_export, btn_title = buscar_boton_exportar_en_frames(page)
            if btn_export:
                break
                
            elapsed = int(time.time() - start_time)
            if time.time() - last_log_time >= 15:
                # Extraer herramientas detectadas para diagnóstico en tiempo real
                titles_seen = []
                for f in page.frames:
                    try:
                        t = f.evaluate("() => Array.from(document.querySelectorAll('*[title]')).map(e => e.getAttribute('title')).filter(Boolean).slice(0, 5)")
                        if t:
                            titles_seen.extend(t)
                    except Exception:
                        pass
                if titles_seen:
                    log(f"Herramientas activas en pantalla: {titles_seen[:5]} ({elapsed}s)")
                else:
                    log(f"Cargando visor OLAP en O3 Web... ({elapsed}s transcurridos)")
                last_log_time = time.time()
                
            page.wait_for_timeout(1500)
            
        if btn_export:
            log(f"✔ Opción de exportación detectada ({btn_title}). Activando descarga...")
            export_page = None
            
            try:
                with page.context.expect_page(timeout=15000) as new_page_info:
                    btn_export.click()
                export_page = new_page_info.value
                log("Ventana emergente de exportación abierta con éxito.")
            except Exception:
                log("Buscando diálogo de exportación en la misma ventana...")
                
            download = None
            if export_page:
                export_page.wait_for_load_state("domcontentloaded", timeout=30000)
                log("Confirmando generación del reporte oficial CSV...")
                with export_page.expect_download(timeout=300000) as download_info:
                    btn_aplicar = export_page.locator("input[value='Aplicar'], button:has-text('Aplicar'), input[type='submit'], input[value*='Exportar'], button:has-text('Exportar')").first
                    btn_aplicar.click()
                download = download_info.value
            else:
                # Descarga directa o modal interno
                log("Confirmando diálogo de exportación en visor...")
                with page.expect_download(timeout=300000) as download_info:
                    aplicado = False
                    for f in page.frames:
                        try:
                            btn_aplicar = f.locator("input[value='Aplicar'], button:has-text('Aplicar'), input[type='submit']").first
                            if btn_aplicar.count() > 0 and btn_aplicar.is_visible():
                                btn_aplicar.click()
                                aplicado = True
                                break
                        except Exception:
                            continue
                    if not aplicado:
                        btn_export.click()
                download = download_info.value
                
            nombre_salida = f"OLE_Movilidad_{departamento}_Saliente_desde_2017_solo_2023_MPIO.csv"
            output_dir.mkdir(parents=True, exist_ok=True)
            ruta_guardado = output_dir / nombre_salida
            download.save_as(str(ruta_guardado))
            log(f"✔ Descarga completada exitosamente desde OLE: {nombre_salida}")
            browser.close()
            return ruta_guardado
            
        browser.close()
        raise RuntimeError("No se pudo interactuar con el visor del cubo OLAP en O3 Web (Tiempo de espera de 5 minutos agotado al cargar los frames del servidor).")



