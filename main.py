"""
Punto de Entrada Principal para el Proyecto OLE_DESCARGAS.
Permite ejecutar el proyecto mediante:
1. Interfaz Gráfica (por defecto): `py -3.13 main.py`
2. Modo Línea de Comandos (CLI para scripts y otros ingenieros):
   `py -3.13 main.py --cli --output-dir "ruta/personalizada" --departamento Cauca --anio 2023`
"""

import argparse
import sys
from pathlib import Path

# Agregar raíz del proyecto al path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import (
    DEFAULT_SALIENTES_DIR,
    DEFAULT_ENTRANTES_DIR,
    DEPARTAMENTO_OBJETIVO,
    ANIO_CORTE,
    ANIO_CORTE_PREDETERMINADO,
    COHORTE_PREDETERMINADA
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Automatización de descargas de Situación Laboral (OLE / Mineducación)"
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Ejecuta en modo consola sin abrir la interfaz gráfica."
    )
    parser.add_argument(
        "--modo",
        type=str,
        default="saliente",
        choices=["saliente", "entrante"],
        help="Modo de movilidad laboral a procesar ('saliente' o 'entrante')."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Ruta de la carpeta donde se guardarán los archivos CSV generados."
    )
    parser.add_argument(
        "--departamento",
        type=str,
        default=DEPARTAMENTO_OBJETIVO,
        help="Departamento objetivo para la consulta (ej. Cauca o Colombia)."
    )
    parser.add_argument(
        "--anio",
        type=str,
        default=None,
        help="Año de corte a extraer (ej. 2023)."
    )
    parser.add_argument(
        "--anio-corte",
        type=str,
        default=ANIO_CORTE_PREDETERMINADO,
        help="Año de corte analítico (por defecto: 2023)."
    )
    parser.add_argument(
        "--cohorte",
        type=str,
        default=COHORTE_PREDETERMINADA,
        help="Cohorte de graduación (por defecto: 'Desde 2017' o un año específico ej. 2022)."
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    if args.cli:
        corte_final = args.anio if args.anio is not None else args.anio_corte
        print("=== MODO LÍNEA DE COMANDOS (CLI) ===")
        print(f"Modo: {args.modo.upper()}")
        print(f"Departamento: {args.departamento}")
        print(f"Año de Corte: {corte_final} | Cohorte: {args.cohorte}")
        
        from src.extractor import extraer_datos_situacion_laboral
        out_path = Path(args.output_dir) if args.output_dir else None
        extraer_datos_situacion_laboral(
            output_dir=out_path,
            departamento=args.departamento,
            anio_corte=corte_final,
            cohorte=args.cohorte,
            modo=args.modo,
            logger=print
        )
    else:
        # Iniciar Interfaz Gráfica interactiva
        from src.gui import run_gui
        run_gui()


if __name__ == "__main__":
    main()

