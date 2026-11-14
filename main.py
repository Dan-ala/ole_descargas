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
        "--estudio",
        "--tipo-estudio",
        type=str,
        default="movilidad",
        choices=["movilidad", "salarios", "salario"],
        help="Tipo de estudio a procesar ('movilidad' de 9 columnas o 'salarios' de 8 columnas con 7 rangos SMMLV)."
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
    parser.add_argument(
        "--verificar",
        action="store_true",
        help="Consulta los años de corte disponibles en OLE, actualiza corte_disponible y estado.json sin descargar archivos."
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    if args.verificar:
        print("=== MODO VERIFICACIÓN DE ACTUALIZACIONES OLE ===")
        out_path = Path(args.output_dir) if args.output_dir else None
        from src.estado import verificar_actualizaciones_ole
        verificar_actualizaciones_ole(output_dir=out_path, logger=print, estudio=args.estudio, modo=args.modo)
        return

    if args.cli:
        corte_final = args.anio if args.anio is not None else args.anio_corte
        print("=== MODO LÍNEA DE COMANDOS (CLI) ===")
        print(f"Estudio: {args.estudio.upper()}")
        print(f"Modo: {args.modo.upper()}")
        print(f"Departamento: {args.departamento}")
        print(f"Año de Corte: {corte_final} | Cohorte: {args.cohorte}")
        
        from datetime import datetime
        from src.extractor import extraer_datos_situacion_laboral, obtener_ultimas_filas_por_departamento
        from src.leeme import generar_leeme
        from src.registro import registrar_ejecucion, BOGOTA_TZ

        out_path = Path(args.output_dir) if args.output_dir else None
        fecha_inicio = datetime.now(BOGOTA_TZ)
        archivos = []
        error_msg = ""
        resultado = "fallido"
        tipo_error = ""

        try:
            archivos = extraer_datos_situacion_laboral(
                output_dir=out_path,
                departamento=args.departamento,
                anio_corte=corte_final,
                cohorte=args.cohorte,
                modo=args.modo,
                tipo_estudio=args.estudio,
                logger=print
            )
            resultado = "exitoso"

            parametros = {
                "departamento": args.departamento,
                "anio_corte": corte_final,
                "cohorte": args.cohorte,
                "modo": args.modo,
                "tipo_estudio": args.estudio,
                "output_dir": out_path
            }
            leeme_generado = generar_leeme(parametros, archivos)
            print(f"\n✔ Documento LEEME generado/actualizado exitosamente en:\n  {leeme_generado}")
        except Exception as e:
            resultado = "fallido"
            error_msg = str(e)
            if "departamento no válido" in error_msg.lower() or "departamento no valido" in error_msg.lower():
                tipo_error = "entrada"
            else:
                tipo_error = "fuente"
            print(f"\n❌ Error durante la ejecución: {e}", file=sys.stderr)
        finally:
            fecha_fin = datetime.now(BOGOTA_TZ)
            parametros_reg = {
                "departamento": args.departamento,
                "cohorte": args.cohorte,
                "anio_corte": corte_final,
                "modo": args.modo,
                "tipo_estudio": args.estudio
            }
            filas_por_depto = obtener_ultimas_filas_por_departamento()
            try:
                ruta_registro = registrar_ejecucion(
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    resultado=resultado,
                    parametros=parametros_reg,
                    archivos_generados=archivos,
                    error=error_msg,
                    output_dir=out_path,
                    filas_por_departamento=filas_por_depto,
                    tipo_error=tipo_error
                )
                print(f"✔ Registro de ejecución guardado en:\n  {ruta_registro}")
            except Exception as reg_err:
                print(f"⚠ Error al registrar ejecución: {reg_err}", file=sys.stderr)

            # Actualizar estado de la fuente OLE (solo para consolidación nacional y errores de fuente)
            from src.estado import escribir_estado
            try:
                ruta_estado = escribir_estado(
                    output_dir=out_path,
                    resultado=resultado,
                    fecha_ejecucion=fecha_fin,
                    anio_corte=corte_final,
                    departamento=args.departamento,
                    estudio=args.estudio,
                    modo=args.modo,
                    tipo_error=tipo_error
                )
                if ruta_estado:
                    print(f"✔ Estado de la fuente guardado en:\n  {ruta_estado}")
            except Exception as est_err:
                print(f"⚠ Error al escribir estado: {est_err}", file=sys.stderr)

        if resultado != "exitoso":
            sys.exit(1)
    else:
        # Iniciar Interfaz Gráfica interactiva
        from src.gui import run_gui
        run_gui()


if __name__ == "__main__":
    main()

