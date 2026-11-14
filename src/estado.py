"""
Módulo para el control de estado de la fuente OLE y verificación de actualizaciones.
Genera y actualiza estado.json dentro de la carpeta ETL/.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Union

from config.settings import (
    FRECUENCIA_VERIFICACION_DIAS,
    FRECUENCIA_PUBLICACION,
    obtener_anios_corte_disponibles,
    ANIOS_CACHE_PATH
)
from src.registro import resolver_carpeta_etl, BOGOTA_TZ

# Lista oficial de los 4 productos soportados en OLE
PRODUCTOS_OFICIALES = [
    "movilidad_saliente",
    "movilidad_entrante",
    "salarios_saliente",
    "salarios_entrante"
]

# Orden de gravedad para el estado global (de mayor gravedad a menor)
ORDEN_GRAVEDAD = ["fallida", "datos_nuevos", "vencida", "sin_descarga", "al_dia"]


def extraer_corte_mas_reciente(anios: list) -> Optional[str]:
    """
    Calcula el año más reciente con el máximo numérico de la lista
    (convierte a entero), evitando guiarse únicamente por el primer elemento.
    """
    if not anios:
        return None
    anios_numericos = []
    for a in anios:
        match = re.search(r"\b(20\d{2})\b", str(a))
        if match:
            try:
                anios_numericos.append(int(match.group(1)))
            except (ValueError, TypeError):
                pass
        else:
            try:
                anios_numericos.append(int(str(a).strip()))
            except (ValueError, TypeError):
                pass
    if anios_numericos:
        return str(max(anios_numericos))
    return None


def _es_mayor(corte_disp: Optional[Union[str, int]], corte_desc: Optional[Union[str, int]]) -> bool:
    """
    Comprueba si corte_disponible es estrictamente mayor que corte_descargado.
    Si cualquiera es None o null, retorna False.
    """
    if corte_disp is None or corte_desc is None:
        return False
    str_disp = str(corte_disp).strip()
    str_desc = str(corte_desc).strip()
    if not str_disp or not str_desc or str_disp.lower() in ("none", "null") or str_desc.lower() in ("none", "null"):
        return False
    try:
        return int(str_disp) > int(str_desc)
    except (ValueError, TypeError):
        return str_disp > str_desc


def calcular_estado_global(productos: Dict[str, Dict[str, Any]]) -> str:
    """Determina el estado global de la fuente según el peor estado de sus productos."""
    if not productos:
        return "sin_descarga"
    estados_presentes = {
        p.get("estado") for p in productos.values() if isinstance(p, dict) and p.get("estado")
    }
    for gravedad in ORDEN_GRAVEDAD:
        if gravedad in estados_presentes:
            return gravedad
    return "al_dia"


def _evaluar_estado_producto(
    corte_descargado: Optional[str],
    corte_disponible: Optional[str],
    proxima_verificacion_iso: Optional[str],
    fue_fallida_fuente: bool = False
) -> str:
    """
    Evalúa las reglas de estado para un producto específico:
    1. 'fallida': la última ejecución nacional de ese producto falló con tipo_error 'fuente'.
    2. 'sin_descarga': no hay ninguna descarga nacional exitosa todavía.
    3. 'datos_nuevos': corte_disponible es mayor que corte_descargado.
       Si corte_disponible es null / None, no se compara ni causa datos_nuevos.
    4. 'vencida': la fecha actual pasó proxima_verificacion.
    5. 'al_dia': ninguna de las anteriores.
    """
    if fue_fallida_fuente:
        return "fallida"

    if not corte_descargado:
        return "sin_descarga"

    # Regla 5: Si corte_disponible es null no se compara ni causa datos_nuevos
    if corte_disponible is not None and _es_mayor(corte_disponible, corte_descargado):
        return "datos_nuevos"

    if proxima_verificacion_iso:
        try:
            dt_prox = datetime.fromisoformat(proxima_verificacion_iso)
            if dt_prox.tzinfo is None:
                dt_prox = dt_prox.replace(tzinfo=BOGOTA_TZ)
            if datetime.now(BOGOTA_TZ) > dt_prox:
                return "vencida"
        except Exception:
            pass

    return "al_dia"


def _inicializar_productos_vacios(corte_disponible: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Crea la estructura inicial por defecto para los 4 productos oficiales.
    Para salarios, corte_disponible se inicia en None con nota explicativa.
    """
    productos: Dict[str, Dict[str, Any]] = {}
    for prod in PRODUCTOS_OFICIALES:
        es_sal = "salarios" in prod
        productos[prod] = {
            "corte_descargado": None,
            "corte_disponible": None if es_sal else corte_disponible,
            "ultima_ejecucion_exitosa": None,
            "ultima_verificacion": None,
            "proxima_verificacion": None,
            "frecuencia_publicacion": FRECUENCIA_PUBLICACION,
            "estado": "sin_descarga"
        }
        if es_sal:
            productos[prod]["nota"] = "no verificado de forma independiente"
    return productos


def escribir_estado(
    output_dir: Optional[Union[Path, str]] = None,
    resultado: str = "exitoso",
    fecha_ejecucion: Optional[Union[datetime, str]] = None,
    anio_corte: Optional[str] = None,
    corte_disponible: Optional[str] = None,
    departamento: Optional[str] = None,
    es_nacional: Optional[bool] = None,
    estudio: str = "movilidad",
    modo: str = "saliente",
    tipo_error: Optional[str] = None
) -> Optional[Path]:
    """
    Actualiza estado.json en la carpeta ETL/ de la fuente OLE.
    
    Reglas aplicadas:
    - tipo_error 'entrada' NO modifica estado.json.
    - Ejecuciones de un solo departamento NO modifican estado.json.
    - SOLO una ejecución nacional (exitosa o fallida por fuente) actualiza el producto correspondiente.
    """
    # Regla 2: Una ejecución con tipo_error 'entrada' no modifica estado.json
    if str(tipo_error).lower() == "entrada":
        return None

    # Determinar si el alcance es nacional
    if es_nacional is None:
        if departamento:
            es_nacional = str(departamento).strip().lower() in ["colombia", "nacional", "todos", "all", "toda colombia"]
        else:
            es_nacional = True

    # Regla 4: Las ejecuciones de un solo departamento se registran en el log, pero no cambian el estado
    if not es_nacional:
        return None

    etl_dir = resolver_carpeta_etl(output_dir)
    estado_path = etl_dir / "estado.json"

    # Identificador del producto (<estudio>_<modo>)
    estudio_norm = "salarios" if "salario" in str(estudio).lower() else "movilidad"
    modo_norm = "entrante" if "entrante" in str(modo).lower() else "saliente"
    clave_producto = f"{estudio_norm}_{modo_norm}"
    es_salarios = (estudio_norm == "salarios")

    # Resolver corte disponible por defecto si no se pasa explícitamente (solo para movilidad)
    if not corte_disponible and not es_salarios:
        anios = obtener_anios_corte_disponibles()
        corte_disponible = extraer_corte_mas_reciente(anios)

    # Leer estado previo si ya existe
    estado_previo: Dict[str, Any] = {}
    if estado_path.exists():
        try:
            with open(estado_path, "r", encoding="utf-8") as f:
                estado_previo = json.load(f)
        except Exception:
            estado_previo = {}

    productos: Dict[str, Dict[str, Any]] = estado_previo.get("productos", {})

    # Garantizar que los 4 productos siempre existan en el objeto
    for prod in PRODUCTOS_OFICIALES:
        es_prod_sal = "salarios" in prod
        if prod not in productos or not isinstance(productos[prod], dict):
            productos[prod] = {
                "corte_descargado": None,
                "corte_disponible": None if es_prod_sal else corte_disponible,
                "ultima_ejecucion_exitosa": None,
                "ultima_verificacion": None,
                "proxima_verificacion": None,
                "frecuencia_publicacion": FRECUENCIA_PUBLICACION,
                "estado": "sin_descarga"
            }
            if es_prod_sal:
                productos[prod]["nota"] = "no verificado de forma independiente"
        else:
            # Asegurar campo frecuencia_publicacion
            if "frecuencia_publicacion" not in productos[prod]:
                productos[prod]["frecuencia_publicacion"] = FRECUENCIA_PUBLICACION
            if es_prod_sal:
                productos[prod]["corte_disponible"] = None
                productos[prod]["nota"] = "no verificado de forma independiente"

    # Normalizar fecha_ejecucion a America/Bogota
    if fecha_ejecucion is None:
        dt_ejecucion = datetime.now(BOGOTA_TZ)
    elif isinstance(fecha_ejecucion, datetime):
        if fecha_ejecucion.tzinfo is None:
            dt_ejecucion = fecha_ejecucion.replace(tzinfo=BOGOTA_TZ)
        else:
            dt_ejecucion = fecha_ejecucion.astimezone(BOGOTA_TZ)
    else:
        try:
            dt_ejecucion = datetime.fromisoformat(str(fecha_ejecucion))
            if dt_ejecucion.tzinfo is None:
                dt_ejecucion = dt_ejecucion.replace(tzinfo=BOGOTA_TZ)
            else:
                dt_ejecucion = dt_ejecucion.astimezone(BOGOTA_TZ)
        except Exception:
            dt_ejecucion = datetime.now(BOGOTA_TZ)

    fecha_ejecucion_iso = dt_ejecucion.isoformat()
    resultado_normalizado = "exitoso" if str(resultado).lower() == "exitoso" else "fallido"

    prod_actual = productos[clave_producto]

    if resultado_normalizado == "exitoso":
        # Regla 4 y 5: Actualiza corte_descargado, ultima_ejecucion_exitosa y proxima_verificacion
        corte_limpio = str(anio_corte).split()[0].strip() if anio_corte else prod_actual.get("corte_descargado")
        dt_proxima = dt_ejecucion + timedelta(days=FRECUENCIA_VERIFICACION_DIAS)
        
        prod_actual["corte_descargado"] = corte_limpio
        if es_salarios:
            prod_actual["corte_disponible"] = None
            prod_actual["nota"] = "no verificado de forma independiente"
        else:
            if corte_disponible:
                prod_actual["corte_disponible"] = corte_disponible
            prod_actual.pop("nota", None)

        prod_actual["ultima_ejecucion_exitosa"] = fecha_ejecucion_iso
        prod_actual["ultima_verificacion"] = fecha_ejecucion_iso
        prod_actual["proxima_verificacion"] = dt_proxima.isoformat()
        prod_actual["frecuencia_publicacion"] = FRECUENCIA_PUBLICACION
        prod_actual["estado"] = _evaluar_estado_producto(
            corte_descargado=prod_actual["corte_descargado"],
            corte_disponible=prod_actual["corte_disponible"],
            proxima_verificacion_iso=prod_actual["proxima_verificacion"],
            fue_fallida_fuente=False
        )
    else:
        # Falla nacional por fuente
        if str(tipo_error).lower() == "fuente":
            if not es_salarios and corte_disponible:
                prod_actual["corte_disponible"] = corte_disponible
            prod_actual["estado"] = "fallida"

    productos[clave_producto] = prod_actual
    estado_global = calcular_estado_global(productos)

    nuevo_estado = {
        "fuente": "OLE",
        "esquema_version": 1,
        "estado": estado_global,
        "ultimo_error_verificacion": estado_previo.get("ultimo_error_verificacion", None),
        "productos": productos
    }

    with open(estado_path, "w", encoding="utf-8") as f:
        json.dump(nuevo_estado, f, indent=2, ensure_ascii=False)

    return estado_path


def verificar_actualizaciones_ole(
    output_dir: Optional[Union[Path, str]] = None,
    logger=None,
    estudio: str = "movilidad",
    modo: str = "saliente"
) -> Path:
    """
    Ejecuta la verificación de cortes en OLE (CLI --verificar):
    - Consulta los años de corte disponibles en OLE en vivo (O3 Web).
    - Asigna a los productos de movilidad el año de corte más reciente (máximo numérico).
    - Asigna a los productos de salarios corte_disponible en null con nota 'no verificado de forma independiente'.
    - Si OLE es inaccesible o falla, NO cambia corte_disponible ni avanza ultima_verificacion,
      guarda ultimo_error_verificacion en estado.json, registra en ejecuciones.jsonl como fallido (fuente)
      y termina con código de salida distinto de 0.
    """
    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[VERIFICAR-OLE] {msg}")

    log("Iniciando verificación de cortes disponibles en OLE (Mineducación)...")

    fecha_inicio = datetime.now(BOGOTA_TZ)
    etl_dir = resolver_carpeta_etl(output_dir)
    estado_path = etl_dir / "estado.json"

    anios_obtenidos = []
    error_verificacion = None

    try:
        from src.auth import consultar_anios_disponibles_ole_web
        anios_obtenidos = consultar_anios_disponibles_ole_web(headless=True, logger=log)
        if not anios_obtenidos:
            error_verificacion = "No se pudieron obtener años de corte desde la plataforma OLE (lista vacía)."
    except Exception as e:
        error_verificacion = str(e)

    # 1. Si no se puede obtener la lista de años en vivo desde OLE (falla/inaccesible)
    if error_verificacion or not anios_obtenidos:
        fecha_fin = datetime.now(BOGOTA_TZ)
        fecha_fin_iso = fecha_fin.isoformat()
        mensaje_error = error_verificacion or "No se pudieron obtener años de corte desde la plataforma OLE."
        log(f"❌ Falló la verificación de cortes en OLE: {mensaje_error}")

        # El fallback local que lee .anios_ole_cache.json o escanea CSVs es meramente informativo:
        # nunca se usa para fijar corte_disponible ni para concluir 'al_dia'
        anios_locales = obtener_anios_corte_disponibles()
        corte_conocido = extraer_corte_mas_reciente(anios_locales) or "Desconocido"
        log(f"ℹ Último corte conocido localmente (informativo): {corte_conocido}")

        estado_previo: Dict[str, Any] = {}
        if estado_path.exists():
            try:
                with open(estado_path, "r", encoding="utf-8") as f:
                    estado_previo = json.load(f)
            except Exception:
                estado_previo = {}

        productos = estado_previo.get("productos")
        if not productos or not isinstance(productos, dict):
            productos = _inicializar_productos_vacios()

        # NO calcules ni cambies corte_disponible
        # NO avances ultima_verificacion
        # Guarda en estado.json el campo ultimo_error_verificacion (texto del error y fecha)
        estado_previo["fuente"] = "OLE"
        estado_previo["esquema_version"] = 1
        estado_previo["productos"] = productos
        estado_previo["ultimo_error_verificacion"] = {
            "error": mensaje_error,
            "fecha": fecha_fin_iso
        }
        if "estado" not in estado_previo:
            estado_previo["estado"] = calcular_estado_global(productos)

        try:
            with open(estado_path, "w", encoding="utf-8") as f:
                json.dump(estado_previo, f, indent=2, ensure_ascii=False)
            log(f"✔ Error de verificación registrado en estado.json:\n  {estado_path}")
        except Exception as e_write:
            log(f"⚠ No se pudo escribir estado.json: {e_write}")

        # Registra la ejecución en ejecuciones.jsonl con resultado 'fallido' y tipo_error 'fuente'
        try:
            from src.registro import registrar_ejecucion
            parametros_reg = {
                "accion": "verificar",
                "departamento": "Colombia",
                "modo": modo,
                "tipo_estudio": estudio
            }
            ruta_reg = registrar_ejecucion(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                resultado="fallido",
                parametros=parametros_reg,
                archivos_generados=[],
                error=mensaje_error,
                output_dir=output_dir,
                tipo_error="fuente"
            )
            log(f"✔ Registro de auditoría (fallido) guardado en:\n  {ruta_reg}")
        except Exception as e_reg:
            log(f"⚠ No se pudo registrar en ejecuciones.jsonl: {e_reg}")

        # Terminar con código de salida distinto de 0
        raise RuntimeError(f"Verificación de cortes fallida: {mensaje_error}")

    # 2. Caso Exitoso: Se obtuvo la lista de años en vivo desde OLE
    # Calcula el año más reciente con el máximo numérico de la lista (convierte a entero)
    corte_maximo = extraer_corte_mas_reciente(anios_obtenidos)
    if not corte_maximo:
        raise RuntimeError("No se pudo determinar el año de corte numérico más reciente desde OLE.")

    log(f"✔ Cortes detectados en vivo desde OLE: {anios_obtenidos}")
    log(f"✔ Año de corte más reciente determinado: {corte_maximo}")

    estado_previo = {}
    if estado_path.exists():
        try:
            with open(estado_path, "r", encoding="utf-8") as f:
                estado_previo = json.load(f)
        except Exception:
            estado_previo = {}

    productos = estado_previo.get("productos")
    if not productos or not isinstance(productos, dict):
        productos = _inicializar_productos_vacios()

    now_bogota = datetime.now(BOGOTA_TZ)
    dt_proxima = now_bogota + timedelta(days=FRECUENCIA_VERIFICACION_DIAS)
    now_iso = now_bogota.isoformat()
    proxima_iso = dt_proxima.isoformat()

    # Asignación de cortes según el tipo de producto:
    # - Movilidad: asigna el corte obtenido de su propio cubo
    # - Salarios: corte_disponible en null con nota 'no verificado de forma independiente'
    for prod in PRODUCTOS_OFICIALES:
        es_sal = "salarios" in prod
        if prod not in productos or not isinstance(productos[prod], dict):
            productos[prod] = {
                "corte_descargado": None,
                "corte_disponible": None if es_sal else corte_maximo,
                "ultima_ejecucion_exitosa": None,
                "ultima_verificacion": now_iso,
                "proxima_verificacion": proxima_iso,
                "frecuencia_publicacion": FRECUENCIA_PUBLICACION,
                "estado": "sin_descarga"
            }
            if es_sal:
                productos[prod]["nota"] = "no verificado de forma independiente"
        else:
            p = productos[prod]
            if es_sal:
                p["corte_disponible"] = None
                p["nota"] = "no verificado de forma independiente"
            else:
                p["corte_disponible"] = corte_maximo
                p.pop("nota", None)

            p["ultima_verificacion"] = now_iso
            p["proxima_verificacion"] = proxima_iso
            p["frecuencia_publicacion"] = FRECUENCIA_PUBLICACION
            fue_fallida = p.get("estado") == "fallida"
            p["estado"] = _evaluar_estado_producto(
                corte_descargado=p.get("corte_descargado"),
                corte_disponible=p.get("corte_disponible"),
                proxima_verificacion_iso=proxima_iso,
                fue_fallida_fuente=fue_fallida
            )

    estado_global = calcular_estado_global(productos)

    nuevo_estado = {
        "fuente": "OLE",
        "esquema_version": 1,
        "estado": estado_global,
        "ultimo_error_verificacion": None,
        "productos": productos
    }

    with open(estado_path, "w", encoding="utf-8") as f:
        json.dump(nuevo_estado, f, indent=2, ensure_ascii=False)

    # Registrar en ejecuciones.jsonl como exitoso
    try:
        from src.registro import registrar_ejecucion
        parametros_reg = {
            "accion": "verificar",
            "departamento": "Colombia",
            "modo": modo,
            "tipo_estudio": estudio
        }
        registrar_ejecucion(
            fecha_inicio=fecha_inicio,
            fecha_fin=now_bogota,
            resultado="exitoso",
            parametros=parametros_reg,
            archivos_generados=[],
            error="",
            output_dir=output_dir,
            tipo_error=""
        )
    except Exception as e_reg:
        log(f"⚠ No se pudo registrar en ejecuciones.jsonl: {e_reg}")

    log("✔ Verificación completada exitosamente.")
    log(f"  Estado global de la fuente: {estado_global}")
    for k in PRODUCTOS_OFICIALES:
        p = productos[k]
        nota_str = f" | Nota={p.get('nota')}" if p.get("nota") else ""
        log(f"  Producto '{k}': Estado={p.get('estado')} | Corte descargado={p.get('corte_descargado')} | Corte disp={p.get('corte_disponible')}{nota_str}")
    log(f"✔ Estado de la fuente guardado en:\n  {estado_path}")

    return estado_path
