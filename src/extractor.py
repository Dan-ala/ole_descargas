"""
Módulo de Extracción para Situación Laboral (OLE / Mineducación).
Soporta:
- modo="saliente": Egresados del departamento -> Dónde laboran (conforme a la imagen).
- modo="entrante": Egresados que ingresan a laborar al departamento.
"""

import os
import time
import unicodedata
from pathlib import Path
from typing import Callable, Optional, Dict, Any

from config.settings import (
    CUBE_URL,
    DEFAULT_USERNAME,
    DEFAULT_PASSWORD,
    ANIO_CORTE,
    ANIO_CORTE_PREDETERMINADO,
    COHORTE_PREDETERMINADA,
    DEPARTAMENTO_OBJETIVO,
    DEFAULT_SALIENTES_DIR,
    DEFAULT_ENTRANTES_DIR,
    DEFAULT_SALARIOS_SALIENTES_DIR,
    DEFAULT_SALARIOS_ENTRANTES_DIR
)
from src.transformer import (
    procesar_o_generar_movilidad_saliente,
    procesar_todos_departamentos_salientes,
    guardar_reporte_saliente,
    procesar_o_generar_movilidad_entrante,
    guardar_reporte_entrante,
    procesar_o_generar_salarios_saliente,
    guardar_reporte_salarios_saliente,
    procesar_o_generar_salarios_entrante,
    guardar_reporte_salarios_entrante,
    generar_matriz_municipio,
    guardar_reporte_municipio,
    MUNICIPIOS_CAUCA_DANE,
    DEPARTAMENTOS_COLOMBIA_OFICIALES
)

# Variable global para registrar filas por departamento en la consolidación nacional
ULTIMAS_FILAS_POR_DEPARTAMENTO: Optional[Dict[str, int]] = None


def obtener_ultimas_filas_por_departamento() -> Optional[Dict[str, int]]:
    """Devuelve el desglose de filas por territorio de la última consolidación nacional."""
    global ULTIMAS_FILAS_POR_DEPARTAMENTO
    return ULTIMAS_FILAS_POR_DEPARTAMENTO


def _normalizar_texto_comparacion(texto: str) -> str:
    """Normaliza quitando tildes, símbolos y espacios superfluos en minúsculas."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(texto))
    sin_tildes = "".join([c for c in nfkd if not unicodedata.combining(c)])
    limpio = "".join([c for c in sin_tildes.lower() if c.isalnum() or c.isspace()])
    return " ".join(limpio.split())


# Mapa oficial de validación: 32 departamentos + Bogotá D.C. + la opción Colombia
MAPA_VALIDACION_TERRITORIOS: Dict[str, str] = {}
for _depto in DEPARTAMENTOS_COLOMBIA_OFICIALES:
    MAPA_VALIDACION_TERRITORIOS[_normalizar_texto_comparacion(_depto)] = _depto

# Variantes y alias comunes aceptados
MAPA_VALIDACION_TERRITORIOS["bogota"] = "Bogotá D.C."
MAPA_VALIDACION_TERRITORIOS["bogota dc"] = "Bogotá D.C."
MAPA_VALIDACION_TERRITORIOS["distrito capital"] = "Bogotá D.C."
MAPA_VALIDACION_TERRITORIOS["san andres"] = "San Andrés"
MAPA_VALIDACION_TERRITORIOS["san andres y providencia"] = "San Andrés"
MAPA_VALIDACION_TERRITORIOS["san andres y providencia y santa catalina"] = "San Andrés"
MAPA_VALIDACION_TERRITORIOS["valle"] = "Valle del Cauca"
MAPA_VALIDACION_TERRITORIOS["norte de santander"] = "Norte de Santander"
MAPA_VALIDACION_TERRITORIOS["la guajira"] = "La Guajira"
MAPA_VALIDACION_TERRITORIOS["guajira"] = "La Guajira"

# Opción nacional oficial
MAPA_VALIDACION_TERRITORIOS["colombia"] = "Colombia"
MAPA_VALIDACION_TERRITORIOS["toda colombia"] = "Colombia"
MAPA_VALIDACION_TERRITORIOS["nacional"] = "Colombia"
MAPA_VALIDACION_TERRITORIOS["todos"] = "Colombia"
MAPA_VALIDACION_TERRITORIOS["all"] = "Colombia"


def validar_departamento_objetivo(departamento: str) -> str:
    """
    Comprueba si el departamento pedido está en la lista oficial
    (32 departamentos + Bogotá D.C. + la opción 'Colombia').
    La comparación ignora tildes y mayúsculas.
    Si no está, termina de inmediato con error 'Departamento no válido: <nombre>'.
    """
    norm = _normalizar_texto_comparacion(departamento)
    if norm in MAPA_VALIDACION_TERRITORIOS:
        return MAPA_VALIDACION_TERRITORIOS[norm]
    raise ValueError(f"Departamento no válido: {departamento}")


def _contar_filas_archivo(archivo: Path) -> int:
    """Cuenta el número de filas de datos en un CSV descartando la cabecera."""
    if not archivo.exists() or not archivo.is_file():
        return 0
    for enc in ["utf-8-sig", "latin-1", "utf-8"]:
        try:
            with open(archivo, "r", encoding=enc, errors="replace") as f:
                lineas = [l for l in f if l.strip()]
                return max(0, len(lineas) - 1)
        except Exception:
            continue
    return 0


def extraer_datos_situacion_laboral(
    output_dir: Optional[Path] = None,
    departamento: str = "Colombia",
    anio: Optional[str] = None,
    anio_corte: str = ANIO_CORTE_PREDETERMINADO,
    cohorte: str = COHORTE_PREDETERMINADA,
    modo: str = "saliente",
    tipo_estudio: str = "movilidad",
    logger: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> list[Path]:
    """
    Ejecuta la extracción y estructuración según el tipo de estudio y modo:
    - tipo_estudio='movilidad': 9 columnas oficiales (Graduados, Cotizantes y Dependientes).
    - tipo_estudio='salarios': 8 columnas oficiales (7 Rangos Salariales SMMLV y Dependientes).
    - modo='saliente' vs 'entrante'.
    """
    # 1. Validación de departamento (antes de abrir navegador o descargar)
    depto_canonico = validar_departamento_objetivo(departamento)

    global ULTIMAS_FILAS_POR_DEPARTAMENTO
    ULTIMAS_FILAS_POR_DEPARTAMENTO = None

    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[EXTRACTOR] {msg}")

    # Determinar año de corte efectivo
    corte_efectivo = anio if anio is not None else anio_corte
    corte_str = str(corte_efectivo).split()[0].strip()
    es_salarios = str(tipo_estudio).lower() in ["salario", "salarios"]

    if output_dir is None:
        if es_salarios:
            output_dir = DEFAULT_SALARIOS_SALIENTES_DIR if modo == "saliente" else DEFAULT_SALARIOS_ENTRANTES_DIR
        else:
            output_dir = DEFAULT_SALIENTES_DIR if modo == "saliente" else DEFAULT_ENTRANTES_DIR

    output_dir.mkdir(parents=True, exist_ok=True)
    estudio_label = "SALARIOS (7 RANGOS SMMLV)" if es_salarios else "MOVILIDAD LABORAL"
    log(f"Iniciando extracción en MODO: '{modo.upper()}' | ESTUDIO: '{estudio_label}' para: {departamento.upper()}...")
    log(f"Parámetros temporales: Cohorte='{cohorte}' | Año de corte='{corte_str}'")
    log(f"Carpeta de destino: {output_dir}")

    archivos_generados = []

    # =========================================================================
    # CASO A: MÓDULO DE SALARIOS (8 Columnas Oficiales)
    # =========================================================================
    if es_salarios:
        log("Estructurando reporte oficial de Salarios (8 Columnas - 7 Rangos SMMLV)...")
        log("Columnas: Periodo de graduacion, Año de corte, Municipio de origen, Programa academico, Sexo, Municipio en el que labora, Rango salarial, Cotizantes dependientes")
        
        if modo == "saliente":
            if progress_callback:
                progress_callback(30, 100, f"Procesando salarios salientes ({departamento})")
            try:
                filas_salarios = procesar_o_generar_salarios_saliente(
                    departamento=departamento,
                    directorio_datos=output_dir,
                    anio_corte=corte_str,
                    cohorte=cohorte
                )
            except FileNotFoundError:
                log(f"El archivo local de Salarios para '{departamento}' no fue encontrado. Iniciando conexión con OLE (O3 Web) para descarga automatizada...")
                if progress_callback:
                    progress_callback(50, 100, f"Descargando Salarios ({departamento}) desde OLE Web...")
                from src.auth import descargar_departamento_ole_web
                descargar_departamento_ole_web(
                    departamento=departamento,
                    output_dir=output_dir,
                    tipo_estudio="salarios",
                    anio_corte=corte_str,
                    cohorte=cohorte,
                    logger=log
                )
                filas_salarios = procesar_o_generar_salarios_saliente(
                    departamento=departamento,
                    directorio_datos=output_dir,
                    anio_corte=corte_str,
                    cohorte=cohorte
                )

            if progress_callback:
                progress_callback(80, 100, "Guardando archivo CSV normalizado")
            csv_sal = guardar_reporte_salarios_saliente(
                departamento=departamento,
                filas=filas_salarios,
                directorio_salida=output_dir,
                anio_corte=corte_str,
                cohorte=cohorte
            )
        else:
            # Modo entrante salarios
            if progress_callback:
                progress_callback(30, 100, f"Procesando salarios entrantes ({departamento})")
            try:
                filas_salarios = procesar_o_generar_salarios_entrante(
                    departamento=departamento,
                    directorio_datos=output_dir,
                    anio_corte=corte_str,
                    cohorte=cohorte
                )
            except FileNotFoundError:
                log(f"No se encontró la base nacional de Salarios para derivar la movilidad entrante de '{departamento}'. Conectando a OLE (O3 Web) para descarga automatizada...")
                if progress_callback:
                    progress_callback(50, 100, "Descargando base de Salarios desde OLE Web...")
                from src.auth import descargar_departamento_ole_web
                descargar_departamento_ole_web(
                    departamento="Colombia",
                    output_dir=output_dir,
                    tipo_estudio="salarios",
                    anio_corte=corte_str,
                    cohorte=cohorte,
                    logger=log
                )
                filas_salarios = procesar_o_generar_salarios_entrante(
                    departamento=departamento,
                    directorio_datos=output_dir,
                    anio_corte=corte_str,
                    cohorte=cohorte
                )

            if progress_callback:
                progress_callback(80, 100, "Guardando archivo CSV normalizado")
            csv_sal = guardar_reporte_salarios_entrante(
                departamento=departamento,
                filas=filas_salarios,
                directorio_salida=output_dir,
                anio_corte=corte_str,
                cohorte=cohorte
            )
            
        archivos_generados.append(csv_sal)
        if len(filas_salarios) == 0 or _contar_filas_archivo(csv_sal) == 0:
            raise ValueError("Descarga vacía (0 filas)")
        if progress_callback:
            progress_callback(100, 100, "Completado")
        log(f"✔ Reporte de Salarios generado exitosamente: {csv_sal.name}")
        log(f"  Total cruces registrados: {len(filas_salarios):,} filas oficiales de OLE.")
        return archivos_generados

    # =========================================================================
    # CASO B: MÓDULO DE MOVILIDAD LABORAL (9 Columnas Oficiales)
    # =========================================================================
    if modo == "saliente":
        log("Estructurando reporte oficial de Movilidad Saliente (OLE)...")
        log("Columnas: Periodo de graduacion, Año de corte, Municipio de origen, Programa academico, Sexo, Municipio en el que labora, Numero de graduados, Los que cotizan, Cotizantes dependientes")
        
        es_nacional = departamento.strip().lower() in ["colombia", "nacional", "todos", "all"]

        if es_nacional:
            log("Alcance Seleccionado: TODA COLOMBIA (32 Departamentos + Bogotá D.C.)")
            resultado_nacional = procesar_todos_departamentos_salientes(
                directorio_salientes=output_dir,
                generar_consolidado_nacional=True,
                anio_corte=corte_str,
                cohorte=cohorte,
                logger=log,
                progress_callback=progress_callback
            )
            ULTIMAS_FILAS_POR_DEPARTAMENTO = resultado_nacional.get("filas_por_departamento")
            if resultado_nacional["total_registros_colombia"] == 0:
                raise ValueError("Descarga vacía (0 filas)")
            if resultado_nacional["ruta_consolidado_nacional"]:
                archivos_generados.append(resultado_nacional["ruta_consolidado_nacional"])
            log(f"✔ Consolidación Nacional Finalizada: {resultado_nacional['total_registros_colombia']:,} registros procesados.")
        else:
            if progress_callback:
                progress_callback(30, 100, f"Localizando datos de movilidad ({departamento})")
                
            try:
                filas_salientes = procesar_o_generar_movilidad_saliente(
                    departamento=departamento,
                    directorio_datos=output_dir,
                    anio_corte=corte_str,
                    cohorte=cohorte
                )
            except FileNotFoundError:
                log(f"El archivo local de '{departamento}' no fue encontrado en caché. Iniciando descarga automatizada desde OLE...")
                if progress_callback:
                    progress_callback(50, 100, f"Descargando {departamento} desde OLE Web...")
                from src.auth import descargar_departamento_ole_web
                descargar_departamento_ole_web(departamento=departamento, output_dir=output_dir, logger=log)
                filas_salientes = procesar_o_generar_movilidad_saliente(
                    departamento=departamento,
                    directorio_datos=output_dir,
                    anio_corte=corte_str,
                    cohorte=cohorte
                )
            
            if progress_callback:
                progress_callback(80, 100, "Guardando archivo CSV normalizado")
                
            csv_saliente = guardar_reporte_saliente(
                departamento=departamento,
                filas=filas_salientes,
                directorio_salida=output_dir,
                anio_corte=corte_str,
                cohorte=cohorte
            )
            archivos_generados.append(csv_saliente)
            if len(filas_salientes) == 0 or _contar_filas_archivo(csv_saliente) == 0:
                raise ValueError("Descarga vacía (0 filas)")
            
            if progress_callback:
                progress_callback(100, 100, "Completado")
                
            log(f"✔ Reporte de Movilidad Saliente generado exitosamente: {csv_saliente.name}")
            log(f"  Total cruces registrados: {len(filas_salientes):,} filas oficiales de OLE.")

    else:
        # Modo entrante (100% Real OLE basado en Municipio en el que labora)
        log("Estructurando reporte oficial de Movilidad Entrante (OLE)...")
        log("Columnas: Periodo de graduacion, Año de corte, Municipio de origen, Programa academico, Sexo, Municipio en el que labora, Numero de graduados, Los que cotizan, Cotizantes dependientes")
        
        if progress_callback:
            progress_callback(30, 100, f"Localizando profesionales laborando en {departamento}")
            
        filas_entrantes = procesar_o_generar_movilidad_entrante(
            departamento=departamento,
            directorio_datos=DEFAULT_SALIENTES_DIR,
            anio_corte=corte_str,
            cohorte=cohorte
        )
        
        if progress_callback:
            progress_callback(80, 100, "Guardando archivo CSV normalizado")
            
        csv_entrante = guardar_reporte_entrante(
            departamento=departamento,
            filas=filas_entrantes,
            directorio_salida=output_dir,
            anio_corte=corte_str,
            cohorte=cohorte
        )
        archivos_generados.append(csv_entrante)
        if len(filas_entrantes) == 0 or _contar_filas_archivo(csv_entrante) == 0:
            raise ValueError("Descarga vacía (0 filas)")
        
        if progress_callback:
            progress_callback(100, 100, "Completado")
            
        log(f"✔ Reporte de Movilidad Entrante generado exitosamente: {csv_entrante.name}")
        log(f"  Total cruces registrados: {len(filas_entrantes):,} filas oficiales de OLE.")

    if not archivos_generados:
        raise ValueError("Descarga vacía (0 filas)")
    for arch in archivos_generados:
        if _contar_filas_archivo(arch) == 0:
            raise ValueError("Descarga vacía (0 filas)")

    return archivos_generados
