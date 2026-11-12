"""
Módulo de Extracción para Situación Laboral (OLE / Mineducación).
Soporta:
- modo="saliente": Egresados del departamento -> Dónde laboran (conforme a la imagen).
- modo="entrante": Egresados que ingresan a laborar al departamento.
"""

import os
import time
from pathlib import Path
from typing import Callable, Optional

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
    MUNICIPIOS_CAUCA_DANE
)


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
        
        if progress_callback:
            progress_callback(100, 100, "Completado")
            
        log(f"✔ Reporte de Movilidad Entrante generado exitosamente: {csv_entrante.name}")
        log(f"  Total cruces registrados: {len(filas_entrantes):,} filas oficiales de OLE.")

    return archivos_generados
