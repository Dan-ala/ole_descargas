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
    ANIO_CORTE_PREDETERMINADO,
    COHORTE_PREDETERMINADA,
    obtener_nombre_archivo_saliente,
    obtener_nombre_archivo_saliente_nacional,
    obtener_nombre_archivo_salario_saliente,
    obtener_nombre_archivo_salario_saliente_nacional,
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
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    context = None
    if AUTH_STATE_PATH.exists():
        try:
            context = browser.new_context(user_agent=user_agent, storage_state=str(AUTH_STATE_PATH))
            page = context.new_page()
            page.goto(BASE_URL, timeout=15000)
            
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
    context = browser.new_context(user_agent=user_agent)
    page = context.new_page()
    
    print(f"[AUTH] Autenticando usuario '{username}' en la plataforma OLE...")
    page.goto(BASE_URL, timeout=30000)
    
    if "cas/login" in page.url or page.locator("#username").is_visible():
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("input.btn-submit")
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    
    # Guardar estado de la sesión para próximas ejecuciones
    try:
        context.storage_state(path=str(AUTH_STATE_PATH))
        print(f"[AUTH] Sesión autenticada y guardada en {AUTH_STATE_PATH.name}")
    except Exception:
        pass
    
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
    Si la página se encuentra en el portal inicial de O3 Web ('main.jsp' o 'index.jsp'),
    navega directamente al visor oficial del cubo de 'Situación laboral' (Vista_Migración_vl)
    que contiene tanto los datos de movilidad laboral como de salarios.
    """
    # Si ya se encuentra en el visor del cubo o cargando el dispatcher, no hacer nada
    if "viewdesktop" in page.url or any("dispatcher" in f.url for f in page.frames):
        return True

    try:
        if "main.jsp" in page.url or "o3web" in page.url:
            log("En portal O3 Web. Accediendo automáticamente al visor oficial del cubo (Situación laboral)...")
            page.goto(CUBE_URL, timeout=30000, wait_until="domcontentloaded")
            return True
    except Exception:
        pass

    for f in page.frames:
        try:
            if "main.jsp" in f.url or "o3web" in f.url:
                log("En portal O3 Web (frame). Accediendo automáticamente al visor oficial del cubo (Situación laboral)...")
                f.evaluate(f"window.top.location.href = '{CUBE_URL}'")
                page.wait_for_timeout(2000)
                return True
        except Exception:
            continue
    return False


def buscar_boton_exportar_en_frames(page: Page):
    """
    Escanea todos los frames de Ideasoft O3 Web buscando el botón o icono
    de exportación a planilla / CSV / Excel mediante títulos, imágenes y atributos
    tanto en inglés (idioma del servidor O3) como en español,
    excluyendo explícitamente PDF e impresión.
    """
    js_detector = """() => {
        const all = Array.from(document.querySelectorAll('img, a, span, td, div, button, input'));
        let bestCandidate = null;

        for (const el of all) {
            const title = (el.getAttribute('title') || '').toLowerCase().trim();
            const alt = (el.getAttribute('alt') || '').toLowerCase().trim();
            const src = (el.getAttribute('src') || '').toLowerCase().trim();
            const onclick = (el.getAttribute('onclick') || '').toLowerCase().trim();
            const value = (el.getAttribute('value') || '').toLowerCase().trim();

            // Descartar explícitamente PDF e impresión
            const esPdf = title.includes('pdf') || alt.includes('pdf') || src.includes('pdf');
            const esImprimir = title.includes('imprimir') || alt.includes('imprimir') || title.includes('print') || src.includes('print');
            if (esPdf || esImprimir) continue;

            // 1. Coincidencia exacta de alta prioridad: Hoja de cálculo / Planilla / Spreadsheet
            const esSpreadsheetExacto = (
                title === 'export spreadsheet' || title.includes('spreadsheet') ||
                title.includes('planilla') || alt.includes('spreadsheet') || alt.includes('planilla') ||
                src.includes('grid_save') || src.includes('spreadsheet') ||
                title.includes('cálculo') || title.includes('calculo') ||
                onclick.includes('spreadsheet') || onclick.includes('planilla')
            );

            // 2. Coincidencia secundaria: Exportar genérico a datos (pero no PDF)
            const esExportGenerico = (
                title.includes('excel') || title.includes('csv') ||
                src.includes('excel') || src.includes('csv') || src.includes('xls') ||
                onclick.includes('excel') || onclick.includes('csv') ||
                (title.includes('export') && !title.includes('pdf')) ||
                (title.includes('exportar') && !title.includes('pdf')) ||
                (value.includes('export') && !value.includes('pdf'))
            );

            const rect = el.getBoundingClientRect();
            const isVisible = rect.width > 0 && rect.height > 0;

            if (isVisible) {
                if (esSpreadsheetExacto) {
                    el.setAttribute('data-ole-export', 'primary');
                    return { found: true, priority: 'primary', title: el.getAttribute('title') || el.getAttribute('alt') || 'Export Spreadsheet' };
                } else if (esExportGenerico && !bestCandidate) {
                    el.setAttribute('data-ole-export', 'secondary');
                    bestCandidate = { found: true, priority: 'secondary', title: el.getAttribute('title') || el.getAttribute('alt') || 'Export' };
                }
            }
        }
        return bestCandidate || { found: false };
    }"""

    # Priorizar frames: primero el despachador de la grilla (dispatcher) y escritorio
    sorted_frames = sorted(
        page.frames,
        key=lambda f: 0 if "dispatcher" in f.url else (1 if "jdesktop" in f.url else 2)
    )

    for f in sorted_frames:
        try:
            res = f.evaluate(js_detector)
            if res and res.get("found"):
                priority = res.get("priority", "primary")
                loc = f.locator(f"[data-ole-export='{priority}']").first
                if loc.count() > 0:
                    return f, loc, res.get("title", "Export Spreadsheet")
        except Exception:
            continue
    return None, None, None


def descargar_departamento_ole_web(
    departamento: str,
    output_dir: Path,
    tipo_estudio: str = "movilidad",
    anio_corte: str = ANIO_CORTE_PREDETERMINADO,
    cohorte: str = COHORTE_PREDETERMINADA,
    logger=None,
    headless: bool = False
) -> Path:
    """
    Descarga directamente desde la plataforma OLE (O3 Web) el reporte
    oficial de movilidad laboral o salarios para el departamento solicitado (o Toda Colombia).
    Automatiza la navegación inicial si está en el portal y detecta
    de forma universal la opción de exportación en Ideasoft O3.
    """
    import time

    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[OLE-DOWNLOADER] {msg}")

    estudio_tag = "SALARIOS" if tipo_estudio.lower() in ["salario", "salarios"] else "MOVILIDAD"
    log(f"Iniciando descarga web automatizada ({estudio_tag}) para '{departamento}' desde O3 Web...")
    
    with sync_playwright() as p:
        browser, context, page = ensure_authenticated_context(p, headless=headless)
        
        # Escuchar descargas globales en todo el navegador
        captured_downloads = []
        def _on_download(d):
            log(f"Capturada descarga oficial desde OLE: {d.suggested_filename}")
            captured_downloads.append(d)
        context.on("download", _on_download)

        # Si aterrizó en portal inicial, saltar directamente a la vista del cubo
        abrir_vista_situacion_laboral_si_es_portal(page, log)

        log("Supervisando visor del cubo OLAP en todas las ventanas activas...")
        target_page = None
        target_frame = None
        btn_export = None
        btn_title = ""
        start_time = time.time()
        last_log_time = start_time
        
        while time.time() - start_time < 300:
            # 1. Si alguna página está en el portal inicial, hacer clic o navegar a Situación Laboral
            for p_curr in list(context.pages):
                try:
                    abrir_vista_situacion_laboral_si_es_portal(p_curr, log)
                except Exception:
                    pass
            
            # 2. Buscar el botón de exportación en TODAS las páginas abiertas y sus frames
            for p_curr in list(context.pages):
                try:
                    tf, btn, btitle = buscar_boton_exportar_en_frames(p_curr)
                    if btn:
                        target_page = p_curr
                        target_frame = tf
                        btn_export = btn
                        btn_title = btitle
                        break
                except Exception:
                    continue

            if btn_export:
                break
                
            elapsed = int(time.time() - start_time)
            if time.time() - last_log_time >= 15:
                total_pages = len(context.pages)
                log(f"Esperando visor OLAP en O3 Web... ({total_pages} ventana(s) activas, {elapsed}s transcurridos)")
                last_log_time = time.time()
                
            page.wait_for_timeout(1500)
            
        if btn_export:
            log(f"✔ Opción de exportación detectada ({btn_title}). Activando descarga...")
            export_page = None

            try:
                with context.expect_page(timeout=5000) as new_page_info:
                    btn_export.click(force=True)
                export_page = new_page_info.value
                log("Ventana emergente de exportación abierta con éxito.")
            except Exception:
                try:
                    btn_export.click(force=True)
                except Exception:
                    pass

            if export_page:
                try:
                    export_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    log("Confirmando generación del reporte oficial...")
                    btn_aplicar = export_page.locator("input[value*='Aplicar'], button:has-text('Aplicar'), input[value*='Export'], button:has-text('Export'), input[type='submit']").first
                    if btn_aplicar.count() > 0:
                        try:
                            with export_page.expect_download(timeout=20000) as dl_info:
                                btn_aplicar.click(force=True)
                            dl = dl_info.value
                            captured_downloads.append(dl)
                        except Exception:
                            btn_aplicar.click(force=True)
                except Exception as e:
                    log(f"Aviso en ventana de exportación: {e}")
            else:
                page.wait_for_timeout(1000)
                for p_check in list(context.pages):
                    for f in p_check.frames:
                        try:
                            btn_aplicar = f.locator("input[value*='Aplicar'], button:has-text('Aplicar'), input[value*='Export'], button:has-text('Export'), input[type='submit']").first
                            if btn_aplicar.count() > 0 and btn_aplicar.is_visible():
                                btn_aplicar.click(force=True)
                                break
                        except Exception:
                            continue

            # Esperar a que la descarga capturada se complete
            start_dl_wait = time.time()
            download = None
            while time.time() - start_dl_wait < 60:
                if captured_downloads:
                    download = captured_downloads[0]
                    break
                page.wait_for_timeout(1000)

            if not download:
                browser.close()
                raise RuntimeError("Se activó la exportación pero el servidor no completó la descarga a tiempo.")

            es_nacional = any(n in departamento.lower() for n in ["colombia", "nacional", "todos", "all"])
            es_salarios = tipo_estudio.lower() in ["salario", "salarios"]
            corte_clean = str(anio_corte).split()[0].strip()

            if es_salarios:
                if es_nacional:
                    nombre_salida = obtener_nombre_archivo_salario_saliente_nacional(anio_corte=corte_clean, cohorte=cohorte)
                else:
                    nombre_salida = obtener_nombre_archivo_salario_saliente(departamento, anio_corte=corte_clean, cohorte=cohorte)
            else:
                if es_nacional:
                    nombre_salida = obtener_nombre_archivo_saliente_nacional(anio_corte=corte_clean, cohorte=cohorte)
                else:
                    nombre_salida = obtener_nombre_archivo_saliente(departamento, anio_corte=corte_clean, cohorte=cohorte)

            output_dir.mkdir(parents=True, exist_ok=True)
            ruta_guardado = output_dir / nombre_salida
            download.save_as(str(ruta_guardado))
            log(f"✔ Descarga completada exitosamente desde OLE: {nombre_salida}")
            browser.close()
            return ruta_guardado
            
        browser.close()
        raise RuntimeError("No se pudo interactuar con el visor del cubo OLAP en O3 Web (Tiempo de espera de 5 minutos agotado al cargar los frames del servidor).")



