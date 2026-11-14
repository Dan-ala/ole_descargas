"""
Módulo para el control de estado de la fuente OLE y verificación de actualizaciones.
Genera y actualiza estado.json dentro de la carpeta ETL/.
"""

import json
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


def _es_mayor(corte_disp: Optional[Union[str, int]], corte_desc: Optional[Union[str, int]]) -> bool:
    """Comprueba si corte_disponible es estrictamente mayor que corte_descargado."""
    if not corte_disp or not corte_desc:
        return False
    try:
        return int(str(corte_disp).strip()) > int(str(corte_desc).strip())
    except (ValueError, TypeError):
        return str(corte_disp).strip() > str(corte_desc).strip()


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
    4. 'vencida': la fecha actual pasó proxima_verificacion.
    5. 'al_dia': ninguna de las anteriores.
    """
    if fue_fallida_fuente:
        return "fallida"

    if not corte_descargado:
        return "sin_descarga"

    if _es_mayor(corte_disponible, corte_descargado):
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


def _inicializar_productos_vacios(corte_disponible: str) -> Dict[str, Dict[str, Any]]:
    """Crea la estructura inicial por defecto para los 4 productos oficiales."""
    productos: Dict[str, Dict[str, Any]] = {}
    for prod in PRODUCTOS_OFICIALES:
        productos[prod] = {
            "corte_descargado": None,
            "corte_disponible": corte_disponible,
            "ultima_ejecucion_exitosa": None,
            "ultima_verificacion": None,
            "proxima_verificacion": None,
            "frecuencia_publicacion": FRECUENCIA_PUBLICACION,
            "estado": "sin_descarga"
        }
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

    # Resolver corte disponible por defecto
    if not corte_disponible:
        anios = obtener_anios_corte_disponibles()
        corte_disponible = anios[0].split()[0].strip() if anios else "2023"

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
        if prod not in productos or not isinstance(productos[prod], dict):
            productos[prod] = {
                "corte_descargado": None,
                "corte_disponible": corte_disponible,
                "ultima_ejecucion_exitosa": None,
                "ultima_verificacion": None,
                "proxima_verificacion": None,
                "frecuencia_publicacion": FRECUENCIA_PUBLICACION,
                "estado": "sin_descarga"
            }
        else:
            # Asegurar campo frecuencia_publicacion
            if "frecuencia_publicacion" not in productos[prod]:
                productos[prod]["frecuencia_publicacion"] = FRECUENCIA_PUBLICACION

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
        prod_actual["corte_disponible"] = corte_disponible
        prod_actual["ultima_ejecucion_exitosa"] = fecha_ejecucion_iso
        prod_actual["ultima_verificacion"] = fecha_ejecucion_iso
        prod_actual["proxima_verificacion"] = dt_proxima.isoformat()
        prod_actual["frecuencia_publicacion"] = FRECUENCIA_PUBLICACION
        prod_actual["estado"] = _evaluar_estado_producto(
            corte_descargado=prod_actual["corte_descargado"],
            corte_disponible=corte_disponible,
            proxima_verificacion_iso=prod_actual["proxima_verificacion"],
            fue_fallida_fuente=False
        )
    else:
        # Falla nacional por fuente
        if str(tipo_error).lower() == "fuente":
            prod_actual["corte_disponible"] = corte_disponible
            prod_actual["estado"] = "fallida"

    productos[clave_producto] = prod_actual
    estado_global = calcular_estado_global(productos)

    nuevo_estado = {
        "fuente": "OLE",
        "esquema_version": 1,
        "estado": estado_global,
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
    - Consulta los años de corte disponibles en OLE (O3 Web) y actualiza .anios_ole_cache.json.
    - Actualiza corte_disponible, ultima_verificacion y proxima_verificacion en los 4 productos.
    - NO descarga ningún archivo ni toca Archivos/ ni Guia/.
    """
    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[VERIFICAR-OLE] {msg}")

    log("Iniciando verificación de cortes disponibles en OLE (Mineducación)...")

    corte_disponible = None
    try:
        from src.auth import consultar_anios_disponibles_ole_web
        anios_obtenidos = consultar_anios_disponibles_ole_web(headless=True, logger=log)
        if anios_obtenidos:
            corte_disponible = anios_obtenidos[0].split()[0].strip()
    except Exception as e:
        log(f"⚠ Aviso durante la consulta a OLE Web: {e}")

    if not corte_disponible:
        anios = obtener_anios_corte_disponibles()
        corte_disponible = anios[0].split()[0].strip() if anios else "2023"

    etl_dir = resolver_carpeta_etl(output_dir)
    estado_path = etl_dir / "estado.json"

    estado_previo: Dict[str, Any] = {}
    if estado_path.exists():
        try:
            with open(estado_path, "r", encoding="utf-8") as f:
                estado_previo = json.load(f)
        except Exception:
            estado_previo = {}

    productos: Dict[str, Dict[str, Any]] = estado_previo.get("productos", {})

    now_bogota = datetime.now(BOGOTA_TZ)
    dt_proxima = now_bogota + timedelta(days=FRECUENCIA_VERIFICACION_DIAS)
    now_iso = now_bogota.isoformat()
    proxima_iso = dt_proxima.isoformat()

    # Garantizar que los 4 productos siempre existan
    for prod in PRODUCTOS_OFICIALES:
        if prod not in productos or not isinstance(productos[prod], dict):
            productos[prod] = {
                "corte_descargado": None,
                "corte_disponible": corte_disponible,
                "ultima_ejecucion_exitosa": None,
                "ultima_verificacion": now_iso,
                "proxima_verificacion": proxima_iso,
                "frecuencia_publicacion": FRECUENCIA_PUBLICACION,
                "estado": "sin_descarga"
            }
        else:
            p = productos[prod]
            p["corte_disponible"] = corte_disponible
            p["ultima_verificacion"] = now_iso
            p["proxima_verificacion"] = proxima_iso
            p["frecuencia_publicacion"] = FRECUENCIA_PUBLICACION
            fue_fallida = p.get("estado") == "fallida"
            p["estado"] = _evaluar_estado_producto(
                corte_descargado=p.get("corte_descargado"),
                corte_disponible=corte_disponible,
                proxima_verificacion_iso=proxima_iso,
                fue_fallida_fuente=fue_fallida
            )

    estado_global = calcular_estado_global(productos)

    nuevo_estado = {
        "fuente": "OLE",
        "esquema_version": 1,
        "estado": estado_global,
        "productos": productos
    }

    with open(estado_path, "w", encoding="utf-8") as f:
        json.dump(nuevo_estado, f, indent=2, ensure_ascii=False)

    log(f"✔ Verificación completada.")
    log(f"  Estado global de la fuente: {estado_global}")
    for k in PRODUCTOS_OFICIALES:
        p = productos[k]
        log(f"  Producto '{k}': Estado={p.get('estado')} | Corte descargado={p.get('corte_descargado')} | Corte disp={p.get('corte_disponible')}")
    log(f"✔ Estado de la fuente guardado en:\n  {estado_path}")

    return estado_path
