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
    DEFAULT_ENTRANTES_DIR
)
from src.transformer import (
    procesar_o_generar_movilidad_saliente,
    procesar_todos_departamentos_salientes,
    guardar_reporte_saliente,
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
    logger: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> list[Path]:
    """
    Ejecuta la extracción y estructuración según el modo seleccionado:
    - 'saliente': Municipios de origen, Programa académico, Sexo, Municipio donde labora,
                  Graduados, Cotizantes y Cotizantes dependientes (Nacional o Departamental).
                  Permite filtrar por Cohorte de graduación y Año de corte.
    - 'entrante': Movilidad de egresados hacia los municipios del departamento.
    """
    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[EXTRACTOR] {msg}")

    # Determinar año de corte efectivo
    corte_efectivo = anio if anio is not None else anio_corte
    corte_str = str(corte_efectivo).split()[0].strip()

    if output_dir is None:
        output_dir = DEFAULT_SALIENTES_DIR if modo == "saliente" else DEFAULT_ENTRANTES_DIR

    output_dir.mkdir(parents=True, exist_ok=True)
    log(f"Iniciando extracción en MODO: '{modo.upper()}' para: {departamento.upper()}...")
    log(f"Parámetros temporales: Cohorte='{cohorte}' | Año de corte='{corte_str}'")
    log(f"Carpeta de destino: {output_dir}")

    archivos_generados = []

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
        # Modo entrante
        total_mpios = len(MUNICIPIOS_CAUCA_DANE)
        for idx, (mpio_dane, mpio_nombre) in enumerate(MUNICIPIOS_CAUCA_DANE, start=1):
            if progress_callback:
                progress_callback(idx, total_mpios, mpio_nombre)
            filas_mpio = generar_matriz_municipio(municipio_consultado=mpio_nombre, anio_corte=anio)
            csv_path = guardar_reporte_municipio(municipio=mpio_nombre, filas=filas_mpio, directorio_salida=output_dir)
            archivos_generados.append(csv_path)

        log(f"✔ Extracción entrante finalizada: {len(archivos_generados)} archivos generados.")

    return archivos_generados
