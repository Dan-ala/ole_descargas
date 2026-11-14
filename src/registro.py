"""
Módulo para el registro y auditoría de ejecuciones (exitosas y fallidas)
para la fuente OLE (Mineducación / CADIT UNIMINUTO).
Genera líneas JSON en el archivo ETL/ejecuciones.jsonl.
"""

import os
import json
import getpass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Configuración de zona horaria oficial de Colombia (America/Bogota)
try:
    from zoneinfo import ZoneInfo
    BOGOTA_TZ = ZoneInfo("America/Bogota")
except Exception:
    from datetime import timezone, timedelta
    BOGOTA_TZ = timezone(timedelta(hours=-5))

from config.settings import DEFAULT_SALIENTES_DIR, LOCAL_OUTPUT_DIR


def resolver_carpeta_etl(output_dir: Optional[Union[Path, str]] = None) -> Path:
    """
    Resuelve la carpeta 'ETL/' para almacenar ejecuciones.jsonl.
    - Si se especifica explícitamente output_dir (ej. con --output-dir), crea ETL/ dentro de esa ruta.
    - Si pertenece a la estructura oficial institucional de OLE (con 'Archivos'),
      resuelve 'ETL/' como hermana de 'Archivos/' y 'Guia/'.
    - Si se usa el fallback local ('data/salida'), escribe en 'data/salida/ETL/'.
    - Si no existe la carpeta, la crea.
    """
    if output_dir:
        out_path = Path(output_dir)
        curr = out_path.resolve() if out_path.is_absolute() else out_path
        while curr != curr.parent:
            if curr.name.lower() == "archivos":
                etl_dir = curr.parent / "ETL"
                etl_dir.mkdir(parents=True, exist_ok=True)
                return etl_dir
            curr = curr.parent
        etl_dir = out_path / "ETL"
        etl_dir.mkdir(parents=True, exist_ok=True)
        return etl_dir

    target = DEFAULT_SALIENTES_DIR
    try:
        if target.resolve() == LOCAL_OUTPUT_DIR.resolve() or LOCAL_OUTPUT_DIR.resolve() in target.resolve().parents:
            etl_dir = LOCAL_OUTPUT_DIR / "ETL"
            etl_dir.mkdir(parents=True, exist_ok=True)
            return etl_dir
    except Exception:
        pass

    curr = target.resolve() if target.is_absolute() else target
    while curr != curr.parent:
        if curr.name.lower() == "archivos":
            etl_dir = curr.parent / "ETL"
            etl_dir.mkdir(parents=True, exist_ok=True)
            return etl_dir
        curr = curr.parent

    etl_dir = target / "ETL"
    etl_dir.mkdir(parents=True, exist_ok=True)
    return etl_dir


def _contar_filas_datos(archivo: Path) -> int:
    """Cuenta el número de filas de datos en un archivo delimitado, descontando la cabecera."""
    if not archivo.exists() or not archivo.is_file():
        return 0
    try:
        with open(archivo, "r", encoding="utf-8-sig", errors="replace") as f:
            lineas = [linea for linea in f if linea.strip()]
            return max(0, len(lineas) - 1)
    except Exception:
        try:
            with open(archivo, "r", encoding="latin-1", errors="replace") as f:
                lineas = [linea for linea in f if linea.strip()]
                return max(0, len(lineas) - 1)
        except Exception:
            return 0


def registrar_ejecucion(
    fecha_inicio: Union[datetime, str],
    fecha_fin: Union[datetime, str],
    resultado: str,
    parametros: Union[Dict[str, Any], Any],
    archivos_generados: Optional[List[Union[Path, str]]] = None,
    error: Optional[str] = None,
    output_dir: Optional[Union[Path, str]] = None,
    filas_por_departamento: Optional[Dict[str, int]] = None
) -> Path:
    """
    Añade UNA línea JSON al archivo ejecuciones.jsonl dentro de la carpeta ETL/.
    
    Campos registrados:
    - fuente: "OLE"
    - fecha_inicio: Formato ISO con hora local de Colombia
    - fecha_fin: Formato ISO con hora local de Colombia
    - resultado: "exitoso" o "fallido"
    - responsable: OLE_RESPONSABLE o usuario del sistema
    - parametros: diccionario sanitizado (departamento, cohorte, anio_corte, modo, tipo_estudio)
    - archivos: lista de archivos con nombre y número de filas
    - error: texto del error si falló, cadena vacía "" si fue exitoso
    - filas_por_departamento: (opcional, consolidación nacional) desglose de filas por territorio
    """
    # 1. Normalizar fechas a ISO en zona horaria America/Bogota
    if isinstance(fecha_inicio, datetime):
        if fecha_inicio.tzinfo is None:
            fecha_inicio = fecha_inicio.replace(tzinfo=BOGOTA_TZ)
        fecha_inicio_iso = fecha_inicio.astimezone(BOGOTA_TZ).isoformat()
    else:
        fecha_inicio_iso = str(fecha_inicio)

    if isinstance(fecha_fin, datetime):
        if fecha_fin.tzinfo is None:
            fecha_fin = fecha_fin.replace(tzinfo=BOGOTA_TZ)
        fecha_fin_iso = fecha_fin.astimezone(BOGOTA_TZ).isoformat()
    else:
        fecha_fin_iso = str(fecha_fin)

    # 2. Responsable (misma regla de LEEME)
    try:
        user_sistema = getpass.getuser()
    except Exception:
        user_sistema = os.getenv("USERNAME") or os.getenv("USER") or "sistema"
    responsable = os.getenv("OLE_RESPONSABLE") or user_sistema

    # 3. Sanitizar parámetros (nunca guardar credenciales, contraseñas ni cookies)
    if hasattr(parametros, "__dict__") and not isinstance(parametros, dict):
        p_raw = vars(parametros)
    elif isinstance(parametros, dict):
        p_raw = parametros
    else:
        p_raw = {}

    parametros_limpios = {
        "departamento": str(p_raw.get("departamento", "Colombia")),
        "cohorte": str(p_raw.get("cohorte", "Desde 2017")),
        "anio_corte": str(p_raw.get("anio_corte") or p_raw.get("anio", "2023")).split()[0],
        "modo": str(p_raw.get("modo", "saliente")).lower(),
        "tipo_estudio": str(p_raw.get("tipo_estudio") or p_raw.get("estudio", "movilidad")).lower()
    }

    # 4. Lista de archivos con número de filas
    archivos_lista = []
    if archivos_generados:
        for a in archivos_generados:
            p = Path(a)
            filas = _contar_filas_datos(p)
            archivos_lista.append({
                "nombre": p.name,
                "filas": filas
            })

    # 5. Estructura final del registro
    registro = {
        "fuente": "OLE",
        "fecha_inicio": fecha_inicio_iso,
        "fecha_fin": fecha_fin_iso,
        "resultado": "exitoso" if str(resultado).lower() == "exitoso" else "fallido",
        "responsable": responsable,
        "parametros": parametros_limpios,
        "archivos": archivos_lista,
        "error": str(error) if error else ""
    }

    if filas_por_departamento is not None:
        registro["filas_por_departamento"] = filas_por_departamento

    # 6. Escribir una sola línea JSON en ejecuciones.jsonl
    etl_dir = resolver_carpeta_etl(output_dir)
    jsonl_path = etl_dir / "ejecuciones.jsonl"

    linea_json = json.dumps(registro, ensure_ascii=False) + "\n"

    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(linea_json)

    return jsonl_path

