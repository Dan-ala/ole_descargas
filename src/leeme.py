"""
Módulo para la generación automática de la ficha de control LEEME.txt
para la fuente OLE (Mineducación / CADIT UNIMINUTO).
"""

import os
import getpass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from config.settings import BASE_URL, DEFAULT_SALIENTES_DIR, LOCAL_OUTPUT_DIR


def resolver_carpeta_guia(output_dir: Optional[Union[Path, str]] = None) -> Path:
    """
    Resuelve la carpeta 'Guia/' para almacenar LEEME.txt.
    - Si la ruta pertenece a la estructura oficial institucional de OLE (con 'Archivos'),
      resuelve la carpeta 'Guia/' como hermana de 'Archivos/'.
    - Si se usa el fallback local ('data/salida'), escribe en 'data/salida/Guia/'.
    - Si no existe la carpeta, la crea.
    """
    target = Path(output_dir) if output_dir else DEFAULT_SALIENTES_DIR

    # Caso 1: Fallback local (data/salida) o dentro de él
    try:
        if target.resolve() == LOCAL_OUTPUT_DIR.resolve() or LOCAL_OUTPUT_DIR.resolve() in target.resolve().parents:
            guia_dir = LOCAL_OUTPUT_DIR / "Guia"
            guia_dir.mkdir(parents=True, exist_ok=True)
            return guia_dir
    except Exception:
        pass

    # Caso 2: Ruta institucional con carpeta 'Archivos'
    curr = target.resolve() if target.is_absolute() else target
    while curr != curr.parent:
        if curr.name.lower() == "archivos":
            guia_dir = curr.parent / "Guia"
            guia_dir.mkdir(parents=True, exist_ok=True)
            return guia_dir
        curr = curr.parent

    # Caso 3: Fallback directo a Guia dentro de target
    guia_dir = target / "Guia"
    guia_dir.mkdir(parents=True, exist_ok=True)
    return guia_dir


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


def generar_leeme(parametros: Union[Dict[str, Any], Any], archivos_generados: List[Union[Path, str]]) -> Path:
    """
    Genera o actualiza el archivo LEEME.txt en la carpeta Guia/ correspondiente.
    
    Campos obligatorios:
    - Dirección de descarga
    - Fecha de descarga
    - Periodo cubierto
    - Quién descargó
    - Filtros aplicados
    - Lista de archivos generados con número de filas
    
    Si LEEME.txt ya existe, antepone el bloque nuevo separado por una línea de guiones.
    """
    # Normalizar parámetros recibidos
    if hasattr(parametros, "__dict__") and not isinstance(parametros, dict):
        p = vars(parametros)
    elif isinstance(parametros, dict):
        p = parametros
    else:
        p = {}

    departamento = p.get("departamento", "Colombia")
    anio_corte = str(p.get("anio_corte") or p.get("anio", "2023")).split()[0]
    cohorte = str(p.get("cohorte", "Desde 2017"))
    modo = str(p.get("modo", "saliente")).lower()
    estudio = str(p.get("tipo_estudio") or p.get("estudio", "movilidad")).lower()
    
    # Determinar ruta de salida a partir de parámetros o del primer archivo generado
    output_dir = p.get("output_dir")
    archivos_paths: List[Path] = [Path(a) for a in archivos_generados]
    
    if not output_dir and archivos_paths:
        output_dir = archivos_paths[0].parent

    guia_dir = resolver_carpeta_guia(output_dir)
    leeme_path = guia_dir / "LEEME.txt"

    # 1. Dirección de descarga
    direccion_descarga = BASE_URL

    # 2. Fecha de descarga
    fecha_descarga = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 3. Periodo cubierto
    periodo_cubierto = f"Cohorte(s): {cohorte} | Año de corte: {anio_corte}"

    # 4. Quién descargó
    try:
        user_sistema = getpass.getuser()
    except Exception:
        user_sistema = os.getenv("USERNAME") or os.getenv("USER") or "sistema"
    quien_descargo = os.getenv("OLE_RESPONSABLE") or user_sistema

    # 5. Filtros aplicados
    filtros_aplicados = (
        f"Departamento: {departamento} | "
        f"Cohorte: {cohorte} | "
        f"Año de corte: {anio_corte} | "
        f"Modo: {modo} | "
        f"Tipo de estudio: {estudio}"
    )

    # Detalle de archivos generados con conteo de filas
    lineas_archivos = []
    if archivos_paths:
        for a in archivos_paths:
            filas = _contar_filas_datos(a)
            lineas_archivos.append(f"  - {a.name} ({filas:,} filas de datos)")
    else:
        lineas_archivos.append("  - Ningún archivo registrado en esta corrida")

    archivos_bloque = "\n".join(lineas_archivos)

    nuevo_bloque = (
        "================================================================================\n"
        "GUIA OPERATIVA / REGISTRO DE DESCARGA - OLE\n"
        "CADIT - UNIMINUTO (Data Sources Automation - DSA)\n"
        "================================================================================\n"
        f"Dirección de descarga: {direccion_descarga}\n"
        f"Fecha de descarga:     {fecha_descarga}\n"
        f"Periodo cubierto:      {periodo_cubierto}\n"
        f"Quién descargó:        {quien_descargo}\n"
        f"Filtros aplicados:     {filtros_aplicados}\n"
        "\n"
        "Archivos generados:\n"
        f"{archivos_bloque}\n"
    )

    separador = "--------------------------------------------------------------------------------\n\n"

    # Si ya existe, no sobrescribir: anteponer el nuevo bloque al inicio
    if leeme_path.exists():
        try:
            contenido_previo = leeme_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            try:
                contenido_previo = leeme_path.read_text(encoding="latin-1", errors="replace")
            except Exception:
                contenido_previo = ""
        contenido_final = nuevo_bloque + "\n" + separador + contenido_previo.lstrip()
    else:
        contenido_final = nuevo_bloque

    leeme_path.write_text(contenido_final, encoding="utf-8")
    return leeme_path

