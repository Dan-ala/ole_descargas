"""
Módulo de Autenticación y Gestión de Sesiones para OLE (Mineducación).
Mantiene la sesión activa para optimizar recursos y evitar re-logins innecesarios.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
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
    forzar_nuevo_login: bool = False,
) -> tuple[Browser, BrowserContext, Page]:
    """
    Inicia el navegador y garantiza una sesión autenticada.
    Reutiliza el archivo de estado de sesión (.session_state.json) si existe y es válido,
    a menos que forzar_nuevo_login sea True.
    Marca context._fue_reutilizada = True o False.
    NO guarda .session_state.json aquí: solo se guarda cuando se confirma la carga del visor (Requisito 4).
    """
    browser = playwright_instance.chromium.launch(headless=headless)
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    context = None
    if forzar_nuevo_login and AUTH_STATE_PATH.exists():
        try:
            AUTH_STATE_PATH.unlink(missing_ok=True)
        except Exception:
            pass

    if not forzar_nuevo_login and AUTH_STATE_PATH.exists():
        try:
            context = browser.new_context(user_agent=user_agent, storage_state=str(AUTH_STATE_PATH))
            page = context.new_page()
            page.goto(BASE_URL, timeout=15000)
            
            # Verificar si la sesión previa sigue activa
            if "cas/login" not in page.url and not page.locator("#username").is_visible():
                print("[AUTH] Sesión existente válida reutilizada.")
                context._fue_reutilizada = True
                return browser, context, page
            else:
                print("[AUTH] La sesión almacenada expiró. Renovando credenciales...")
                context.close()
                context = None
        except Exception as e:
            if context:
                context.close()
                context = None
            err_str = str(e)
            if "ERR_CONNECTION" in err_str or "ECONNREFUSED" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str:
                browser.close()
                raise RuntimeError(f"No se pudo conectar con la plataforma OLE ({BASE_URL}): {e}") from e

    # Si no existe sesión válida o se forzó nuevo login, autenticar
    context = browser.new_context(user_agent=user_agent)
    page = context.new_page()
    
    print(f"[AUTH] Autenticando usuario '{username}' en la plataforma OLE...")
    try:
        page.goto(BASE_URL, timeout=30000)
    except Exception as e:
        browser.close()
        raise RuntimeError(f"No se pudo conectar con la plataforma OLE ({BASE_URL}): {e}") from e
    
    if "cas/login" in page.url or page.locator("#username").is_visible():
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("input.btn-submit")
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    
    # Requisito 4: NO guardar .session_state.json aquí.
    # Se guarda únicamente cuando el visor del cubo carga con éxito.
    context._fue_reutilizada = False
    return browser, context, page


def guardar_sesion_si_valida(context: BrowserContext, logger=None):
    """
    Guarda .session_state.json únicamente cuando el visor del cubo OLAP
    ha sido detectado e interactivo con éxito (Requisito 4).
    """
    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[AUTH] {msg}")

    try:
        context.storage_state(path=str(AUTH_STATE_PATH))
        log(f"✔ Sesión verificada y persistida en {AUTH_STATE_PATH.name}")
    except Exception as e:
        log(f"⚠ Aviso al persistir sesión: {e}")


def abrir_vista_situacion_laboral_si_es_portal(page: Page, log) -> bool:
    """
    Si la página se encuentra en el portal inicial de O3 Web ('main.jsp' o 'index.jsp') o en una vista
    distinta a Vista_Migración_vl, navega directamente al visor oficial del cubo de 'Situación laboral'
    (Vista_Migración_vl) que contiene tanto los datos de movilidad laboral como de salarios.
    """
    cube_url = os.getenv("OLE_CUBE_URL", CUBE_URL)
    es_vista_correcta = (
        "Vista_Migraci" in page.url or
        any("Vista_Migraci" in f.url for f in page.frames)
    )
    if es_vista_correcta and any("dispatcher" in f.url for f in page.frames):
        return True

    try:
        log("Accediendo al visor oficial del cubo OLAP (Situación laboral - Vista_Migración_vl)...")
        page.goto(cube_url, timeout=35000, wait_until="domcontentloaded")
        return True
    except Exception as e:
        err_str = str(e)
        if "ERR_CONNECTION" in err_str or "ECONNREFUSED" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str:
            raise RuntimeError(f"No se pudo conectar al cubo OLE ({cube_url}): {e}") from e
        pass

    for f in page.frames:
        try:
            if "main.jsp" in f.url or "o3web" in f.url:
                log("En portal O3 Web (frame). Accediendo automáticamente al visor oficial del cubo (Situación laboral)...")
                f.evaluate(f"window.top.location.href = '{cube_url}'")
                page.wait_for_timeout(2000)
                return True
        except Exception as e:
            err_str = str(e)
            if "ERR_CONNECTION" in err_str or "ECONNREFUSED" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str:
                raise RuntimeError(f"No se pudo conectar al cubo OLE ({cube_url}): {e}") from e
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


def esperar_visor_cubo_olap(
    context: BrowserContext,
    timeout_segundos: int = 90,
    logger=None
) -> tuple[Optional[Page], Optional[Any], Optional[Any], str]:
    """
    Supervisa activamente todas las ventanas y marcos de Playwright hasta que el visor
    oficial del cubo OLAP (Ideasoft O3) esté completamente cargado e interactivo.
    
    Rutina compartida entre el flujo de descarga y el flujo de verificación (Requisito 2).
    Retorna (target_page, target_frame, btn_export, btn_title).
    Si expira timeout_segundos, retorna (None, None, None, "").
    """
    import time

    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[OLE-VISOR] {msg}")

    target_page = None
    target_frame = None
    btn_export = None
    btn_title = ""
    start_time = time.time()
    last_log_time = start_time

    while time.time() - start_time < timeout_segundos:
        # 1. Si alguna página está en el portal inicial, hacer clic o navegar a Situación Laboral
        for p_curr in list(context.pages):
            try:
                abrir_vista_situacion_laboral_si_es_portal(p_curr, log)
            except Exception:
                pass

        # 2. Buscar el visor / botón de exportación en TODAS las páginas abiertas y sus frames
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

        if context.pages:
            try:
                context.pages[0].wait_for_timeout(1500)
            except Exception:
                time.sleep(1.5)
        else:
            time.sleep(1.5)

    if btn_export:
        elapsed = int(time.time() - start_time)
        log(f"✔ Visor OLAP detectado e interactivo en O3 Web ({btn_title}) tras {elapsed}s.")
        return target_page, target_frame, btn_export, btn_title

    return None, None, None, ""


def _intentar_consulta_anios(
    playwright_instance,
    headless: bool,
    forzar_nuevo_login: bool,
    log
) -> tuple[list[str], bool]:
    """
    Realiza un intento de conexión al cubo y extracción de años de corte.
    Retorna (anios_detectados, fue_sesion_reutilizada).
    """
    import time

    browser, context, page = ensure_authenticated_context(
        playwright_instance,
        headless=headless,
        forzar_nuevo_login=forzar_nuevo_login
    )
    fue_reutilizada = getattr(context, "_fue_reutilizada", False)

    try:
        # 1. Esperar visor con la rutina compartida (máximo 90s, Requisito 2)
        target_page, target_frame, btn_export, btn_title = esperar_visor_cubo_olap(
            context,
            timeout_segundos=90,
            logger=log
        )

        if not target_frame or not target_page:
            browser.close()
            return [], fue_reutilizada

        # 2. Visor confirmado: Guardar sesión válida (Requisito 4)
        guardar_sesion_si_valida(context, log)

        # Pausa breve para asegurar que la grilla y dimensiones terminen de renderizarse
        target_page.wait_for_timeout(2000)

        # 3. Acceder a la dimensión 'Año de corte' en el cubo OLAP
        log("Accediendo a la dimensión 'Año de corte' en el cubo OLAP...")

        # Localizar el marco de la grilla OLAP (dispatcher / view-grid)
        frame_cubo = None
        for f in target_page.frames:
            if "dispatcher" in f.url or "view-grid" in f.url:
                frame_cubo = f
                break
        if not frame_cubo and target_frame:
            frame_cubo = target_frame
        if not frame_cubo and len(target_page.frames) > 2:
            frame_cubo = target_page.frames[2]
        if not frame_cubo and target_page.frames:
            frame_cubo = target_page.frames[0]

        corte_activado = False

        # Estrategia A: Locator nativo directo (método probado en O3 Web)
        if frame_cubo:
            for sel in [
                "div.ovfH:has-text('Año de corte')",
                "div.ovfH:has-text('Año de co')",
                "div.ovfH:has-text('Año')",
                "[title*='Año de corte']",
                "td:has-text('Año de corte')",
                "span:has-text('Año de corte')"
            ]:
                try:
                    cand = frame_cubo.locator(sel).first
                    if cand.count() > 0:
                        cand.wait_for(state="visible", timeout=6000)
                        cand.click(force=True)
                        corte_activado = True
                        log(f"✔ Selector de dimensión 'Año de corte' activado mediante selector '{sel}'.")
                        target_page.wait_for_timeout(2500)
                        break
                except Exception:
                    continue

        # Estrategia B: Escaneo dinámico JS si la Estrategia A no abrió el menú
        if not corte_activado:
            js_buscar_corte = """() => {
                const all = Array.from(document.querySelectorAll('input, button, a, span, td, div, img'));
                let best = null;
                let minLen = 999999;

                for (const el of all) {
                    const val = (el.value || '').toLowerCase().trim();
                    const title = (el.getAttribute('title') || '').toLowerCase().trim();
                    const alt = (el.getAttribute('alt') || '').toLowerCase().trim();
                    const text = (el.innerText || el.textContent || '').toLowerCase().trim();

                    const coincide = val.includes('año de c') || val.includes('ano de c') ||
                                     title.includes('año de c') || title.includes('ano de c') ||
                                     alt.includes('año de c') || alt.includes('ano de c') ||
                                     text.includes('año de co') || text.includes('ano de co') ||
                                     text.includes('año de c') || text.includes('ano de c');

                    if (coincide) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            const len = (val || text || title || alt).length;
                            if (len < minLen) {
                                minLen = len;
                                best = el;
                            }
                        }
                    }
                }

                if (best) {
                    best.setAttribute('data-ole-corte-found', 'true');
                    const clickable = best.closest('button, [role="button"], table, td, div.ovfH') || best;
                    clickable.setAttribute('data-ole-corte-clickable', 'true');

                    // Disparar eventos nativos de mouse en la interfaz de Ideasoft O3
                    clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                    clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                    clickable.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                    if (typeof clickable.click === 'function') {
                        clickable.click();
                    }
                    return { found: true, tag: best.tagName, text: best.innerText || best.value || best.getAttribute('title') };
                }
                return { found: false };
            }"""

            for p_curr in context.pages:
                for f in p_curr.frames:
                    try:
                        res_corte = f.evaluate(js_buscar_corte)
                        if res_corte and res_corte.get("found"):
                            corte_activado = True
                            loc = f.locator("[data-ole-corte-clickable='true'], [data-ole-corte-found='true']").first
                            if loc.count() > 0:
                                try:
                                    loc.click(force=True, timeout=5000)
                                except Exception:
                                    pass
                            break
                    except Exception:
                        continue
                if corte_activado:
                    break

            if corte_activado:
                log("✔ Selector de dimensión 'Año de corte' activado mediante escaneo DOM.")
                target_page.wait_for_timeout(2500)
            else:
                log("Aviso: No se localizó selector específico para 'Año de corte', escaneando DOM directamente...")

        # 4. Extraer años de todos los frames que contienen el árbol o listas (espera elástica hasta 15s)
        anios_detectados = []
        js_extraer_anios = """() => {
            const res = [];
            document.querySelectorAll('a, span, td, div, li, b, label, option, input').forEach(el => {
                const txt = (el.innerText || el.textContent || el.value || '').trim();
                // Coincidencia exacta de 4 dígitos tipo 2023
                if (/^20[0-9]{2}$/.test(txt)) {
                    res.push(txt);
                } else {
                    const m = txt.match(/\\b(20[0-9]{2})\\b/);
                    if (m && txt.length < 25) {
                        res.push(m[1]);
                    }
                }
            });
            return [...new Set(res)];
        }"""

        start_extract = time.time()
        while time.time() - start_extract < 15:
            for p_curr in context.pages:
                for f in p_curr.frames:
                    try:
                        years_in_frame = f.evaluate(js_extraer_anios)
                        for y in years_in_frame:
                            if y.isdigit() and 2000 <= int(y) <= 2035:
                                if y not in anios_detectados:
                                    anios_detectados.append(y)
                    except Exception:
                        continue
            if anios_detectados:
                break
            time.sleep(0.5)

        if anios_detectados:
            log(f"✔ Cortes extraídos exitosamente desde OLE: {len(anios_detectados)} años detectados.")

        browser.close()
        return anios_detectados, fue_reutilizada

    except Exception:
        try:
            browser.close()
        except Exception:
            pass
        raise


def consultar_anios_disponibles_ole_web(headless: bool = False, logger=None) -> list[str]:
    """
    Se conecta a la plataforma OLE (O3 Web) y consulta en vivo los años
    disponibles en la dimensión 'Año de corte' del cubo OLAP.
    Reintenta el acceso completo hasta 3 veces con 5s de pausa (Requisito 3).
    Si una sesión reutilizada falla, la elimina y reintenta con login nuevo (Requisito 5).
    Guarda .session_state.json solo si se carga el visor del cubo (Requisito 4).
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

    MAX_INTENTOS = 3
    anios_finales = []
    ultimo_error = None

    for intento in range(1, MAX_INTENTOS + 1):
        log(f"--- Intento {intento} de {MAX_INTENTOS} para consultar cortes en OLE ---")
        try:
            with sync_playwright() as p:
                anios, fue_reutilizada = _intentar_consulta_anios(
                    p,
                    headless=headless,
                    forzar_nuevo_login=False,
                    log=log
                )

                # Requisito 5: Si una sesión reutilizada falló, borrarla y reintentar UNA vez con login nuevo
                if not anios and fue_reutilizada:
                    log("⚠ La sesión reutilizada no logró cargar el visor ni extraer cortes. Eliminando .session_state.json y reintentando con login nuevo...")
                    if AUTH_STATE_PATH.exists():
                        try:
                            AUTH_STATE_PATH.unlink()
                        except Exception:
                            pass
                    anios, _ = _intentar_consulta_anios(
                        p,
                        headless=headless,
                        forzar_nuevo_login=True,
                        log=log
                    )

                if anios:
                    anios_finales = anios
                    break
                else:
                    ultimo_error = "No se detectaron años de corte en la dimensión 'Año de corte' de OLE."
        except Exception as e:
            err_msg = str(e)
            ultimo_error = err_msg
            log(f"⚠ Error durante el intento {intento}: {err_msg}")
            # Si una sesión reutilizada falló por excepción que no es fallo de conexión del host, limpiar sesión
            if AUTH_STATE_PATH.exists() and "ERR_CONNECTION" not in err_msg and "ECONNREFUSED" not in err_msg:
                try:
                    AUTH_STATE_PATH.unlink()
                except Exception:
                    pass

        if intento < MAX_INTENTOS:
            log("Pausando 5 segundos antes del siguiente intento...")
            time.sleep(5)

    if anios_finales:
        anios_ordenados = sorted(anios_finales, key=lambda x: int(x), reverse=True)
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

    raise RuntimeError(ultimo_error or "No se detectaron años de corte en la dimensión 'Año de corte' de OLE tras reintentos.")


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
        target_page, target_frame, btn_export, btn_title = esperar_visor_cubo_olap(
            context,
            timeout_segundos=300,
            logger=log
        )
        if btn_export:
            guardar_sesion_si_valida(context, log)

            es_salarios = tipo_estudio.lower() in ["salario", "salarios"]
            es_nacional = any(n in departamento.lower() for n in ["colombia", "nacional", "todos", "all"])

            # Si es estudio de Salarios, configurar medida y dimensión oficial en el cubo
            if es_salarios and target_page:
                log("Configurando cubo OLAP para Salarios (Medida 'Graduados cotizantes dependientes' y dimensión '7 Rangos salariales')...")
                disp_frame = None
                for f in target_page.frames:
                    if "dispatcher" in f.url:
                        disp_frame = f
                        break

                if disp_frame:
                    try:
                        # 1. Cambiar medida a Graduados cotizantes dependientes (ID 4)
                        disp_frame.evaluate("""() => {
                            if (typeof submitCommand === 'function') {
                                submitCommand('selectDimensionElements', {
                                    selectedPrefix: '',
                                    dimNumber: 17,
                                    queryType: 1,
                                    _selection: '4'
                                });
                            }
                        }""")
                        target_page.wait_for_timeout(6000)
                    except Exception as e_med:
                        log(f"Aviso al configurar medida de salarios: {e_med}")

                    # Re-localizar dispatcher tras recarga
                    for f in target_page.frames:
                        if "dispatcher" in f.url:
                            disp_frame = f
                            break

                    if disp_frame:
                        try:
                            # 2. Agregar dimensión 12 (7 Rangos salariales) al eje 1 (columnas)
                            disp_frame.evaluate("""() => {
                                if (typeof addDimension === 'function') {
                                    addDimension('o3_0', 1, 12, 0);
                                }
                            }""")
                            target_page.wait_for_timeout(6000)
                        except Exception as e_dim:
                            log(f"Aviso al agregar dimensión de rangos salariales: {e_dim}")

                    # 3. Re-verificar botón de exportación actualizado tras recarga
                    _, _, btn_act, btn_title_act = esperar_visor_cubo_olap(context, timeout_segundos=45, logger=log)
                    if btn_act:
                        btn_export = btn_act
                        btn_title = btn_title_act

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
                    btn_aplicar = export_page.locator("input[type='submit'], input[value*='Apply'], input[value*='Aplicar'], button:has-text('Apply'), button:has-text('Aplicar'), input[value*='Export'], button:has-text('Export')").first
                    if btn_aplicar.count() > 0:
                        try:
                            with export_page.expect_download(timeout=25000) as dl_info:
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
                            btn_aplicar = f.locator("input[type='submit'], input[value*='Apply'], input[value*='Aplicar'], button:has-text('Apply'), button:has-text('Aplicar'), input[value*='Export'], button:has-text('Export')").first
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

            suggested = getattr(download, "suggested_filename", "").lower()
            if (suggested.endswith(".xls") or suggested.endswith(".xlsx")) and nombre_salida.lower().endswith(".csv"):
                ruta_temp = output_dir / f"_temp_{download.suggested_filename}"
                download.save_as(str(ruta_temp))
                try:
                    if es_salarios:
                        from src.transformer import parse_archivo_salarios_individual
                        df_conv = parse_archivo_salarios_individual(ruta_temp, anio_corte=corte_clean, cohorte=cohorte)
                    else:
                        from src.transformer import parse_archivo_saliente_individual
                        df_conv = parse_archivo_saliente_individual(ruta_temp, anio_corte=corte_clean, cohorte=cohorte)
                    df_conv.to_csv(ruta_guardado, index=False, encoding="utf-8-sig")
                finally:
                    if ruta_temp.exists():
                        try:
                            ruta_temp.unlink()
                        except Exception:
                            pass
            else:
                download.save_as(str(ruta_guardado))

            log(f"✔ Descarga completada exitosamente desde OLE: {nombre_salida}")
            browser.close()
            return ruta_guardado
            
        browser.close()
        raise RuntimeError("No se pudo interactuar con el visor del cubo OLAP en O3 Web (Tiempo de espera de 5 minutos agotado al cargar los frames del servidor).")



