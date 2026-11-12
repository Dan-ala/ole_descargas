"""
Script utilitario para procesar la movilidad saliente a nivel nacional
y generar el archivo maestro de toda Colombia con las 9 columnas oficiales.
"""

from pathlib import Path
from src.extractor import extraer_datos_situacion_laboral
from config.settings import DEFAULT_SALIENTES_DIR, ANIO_CORTE

if __name__ == "__main__":
    print("=" * 75)
    print("PROCESANDO CONSOLIDACIÓN NACIONAL DE MOVILIDAD SALIENTE (TODA COLOMBIA)")
    print("=" * 75)
    
    archivos = extraer_datos_situacion_laboral(
        output_dir=DEFAULT_SALIENTES_DIR,
        departamento="Colombia",
        anio=ANIO_CORTE,
        modo="saliente"
    )
    
    for a in archivos:
        print(f"\n✔ Archivo maestro nacional generado:")
        print(f"  Ruta: {a}")
        print(f"  Existe: {a.exists()}")
        if a.exists():
            print(f"  Tamaño: {a.stat().st_size:,} bytes")
