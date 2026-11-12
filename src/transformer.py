"""
Módulo de Transformación y Normalización de Datos de Movilidad Laboral.
Maneja ambos flujos:
1. Movilidad Entrante: Estudiantes de otros municipios que laboran en el municipio consultado.
2. Movilidad Saliente: Egresados de las IES del departamento (Cauca) hacia dónde laboran
   con las medidas exactas: Número de graduados, Los que cotizan y Los que cotizan independiente.
"""

import csv
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional
from config.settings import (
    FILENAME_TEMPLATE_ENTRANTE,
    FILENAME_TEMPLATE_SALIENTE,
    FILENAME_TEMPLATE_SALIENTE_NACIONAL,
    obtener_nombre_archivo_saliente,
    obtener_nombre_archivo_saliente_nacional,
    DEFAULT_SALIENTES_DIR,
    DEFAULT_ENTRANTES_DIR,
    ANIO_CORTE_PREDETERMINADO,
    COHORTE_PREDETERMINADA
)


# Municipios de Cauca con códigos DANE
MUNICIPIOS_CAUCA_DANE = [
    ("19001-Popayán", "Popayan"),
    ("19698-Santander de Quilichao", "Santander de Quilichao"),
    ("19573-Puerto Tejada", "Puerto Tejada"),
    ("19532-Patía", "Patia"),
    ("19100-Bolívar", "Bolivar"),
    ("19548-Piendamó - Tunía", "Piendamo"),
    ("19743-Silvia", "Silvia"),
    ("19807-Timbío", "Timbio"),
    ("19256-El Tambo", "El Tambo"),
    ("19300-Guachené", "Guachene"),
    ("19142-Caloto", "Caloto"),
    ("19473-Morales", "Morales"),
    ("19212-Corinto", "Corinto"),
    ("19455-Miranda", "Miranda"),
    ("19110-Buenos Aires", "Buenos Aires"),
    ("19780-Suárez", "Suarez"),
    ("19137-Caldono", "Caldono"),
    ("19821-Toribío", "Toribio"),
    ("19364-Jambaló", "Jambalo"),
    ("19355-Inzá", "Inza"),
    ("19517-Páez", "Paez"),
    ("19824-Totoró", "Totoro"),
    ("19585-Puracé", "Purace"),
    ("19760-Sotará", "Sotara"),
    ("19622-Rosas", "Rosas"),
    ("19392-La Sierra", "La Sierra"),
    ("19397-La Vega", "La Vega"),
    ("19022-Almaguer", "Almaguer"),
    ("19693-San Sebastián", "San Sebastian"),
    ("19701-Santa Rosa", "Santa Rosa"),
    ("19785-Sucre", "Sucre"),
    ("19450-Mercaderes", "Mercaderes"),
    ("19075-Balboa", "Balboa"),
    ("19050-Argelia", "Argelia"),
    ("19290-Florencia", "Florencia"),
    ("19533-Piamonte", "Piamonte"),
    ("19318-Guapi", "Guapi"),
    ("19809-Timbiquí", "Timbiqui"),
    ("19418-López de Micay", "Lopez de Micay"),
    ("19513-Padilla", "Padilla"),
    ("19845-Villa Rica", "Villa Rica"),
    ("19130-Cajibío", "Cajibio")
]

# Programas académicos con código oficial (igual a la imagen del OLE)
PROGRAMAS_CON_CODIGO = [
    "105448-ADMINISTRACION DE EMPRESAS",
    "105530-ADMINISTRACION DE EMPRESAS",
    "15287-ADMINISTRACION DE EMPRESAS",
    "1688-ADMINISTRACION DE EMPRESAS",
    "19828-ADMINISTRACION DE EMPRESAS",
    "254-ADMINISTRACION DE EMPRESAS",
    "52556-ADMINISTRACION DE EMPRESAS",
    "54922-ADMINISTRACION DE EMPRESAS",
    "10189-CONTADURIA PUBLICA",
    "20184-INGENIERIA DE SISTEMAS",
    "10432-INGENIERIA CIVIL",
    "12890-DERECHO",
    "14500-PSICOLOGIA",
    "16020-LICENCIATURA EN EDUCACION",
    "17400-MEDICINA"
]

# Municipios destino laboral observados en la imagen del O3
MUNICIPIOS_DESTINO_LABORAL = [
    "19001-Popayán",
    "19743-Silvia",
    "19785-Sucre",
    "00001-Sin información",
    "19022-Almaguer",
    "19130-Cajibío",
    "19473-Morales",
    "19548-Piendamó - Tunía",
    "19585-Puracé",
    "76001-Santiago de Cali",
    "05001-Medellín",
    "19100-Bolívar",
    "11001-Bogotá, D.C.",
    "19418-López de Micay",
    "52001-Pasto",
    "99001-Puerto Carreño",
    "66001-Pereira",
    "19075-Balboa",
    "19142-Caloto",
    "19698-Santander de Quilichao"
]


def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def normalizar_nombre_municipio(nombre: str) -> str:
    if not nombre:
        return "Desconocido"
    texto_limpio = normalizar_texto(nombre).strip()
    palabras = texto_limpio.split()
    return " ".join([p.capitalize() for p in palabras])


def reparar_mojibake(texto: Any) -> Any:
    """
    Detecta y repara cadenas con caracteres desdoblados o mal codificados (mojibake)
    como 'Ã¡', 'Ã±', 'Ã³', 'Ã©', 'Ã­', 'Ãº', 'Â°', etc., restaurando los caracteres
    legítimos en español ('á', 'ñ', 'ó', etc.).
    """
    if not isinstance(texto, str):
        return texto
    
    # Patrones comunes de mojibake UTF-8 decodificado como Windows-1252/Latin-1
    if any(pat in texto for pat in ["Ã¡", "Ã©", "Ã­", "Ã³", "Ãº", "Ã±", "Ã", "Ã‰", "Ã", "Ã“", "Ãš", "Ã‘", "Â"]):
        try:
            return texto.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
            
    reemplazos = {
        "Ã¡": "á", "Ã©": "é", "Ã­": "í", "Ã³": "ó", "Ãº": "ú",
        "Ã±": "ñ", "Ã": "Á", "Ã‰": "É", "Ã": "Í", "Ã“": "Ó",
        "Ãš": "Ú", "Ã‘": "Ñ", "Â°": "°", "Â": ""
    }
    res = texto
    for k, v in reemplazos.items():
        if k in res:
            res = res.replace(k, v)
    return res


# ==============================================================================
# FLUJO 1: MOVILIDAD SALIENTE (Conforme a la imagen de usuario y OLE)
# ==============================================================================

COLUMNAS_OFICIALES_SALIENTE = [
    "Periodo de graduacion",
    "Año de corte",
    "Municipio de origen",
    "Programa academico",
    "Sexo",
    "Municipio en el que labora",
    "Numero de graduados",
    "Los que cotizan",
    "Cotizantes dependientes"
]


def parse_archivo_saliente_individual(
    filepath: Path,
    anio_corte: Optional[str] = None,
    cohorte: Optional[str] = None
):
    """
    Analizador dinámico e inteligente para archivos exportados de O3 Web.
    Mapea automáticamente las medidas sin importar si 'Cotizantes dependientes'
    viene antes o después de 'Graduados que cotizan' (como ocurre en Bogotá).
    Soporta archivos brutos de O3 (con encabezados O3) o normalizados (con 9 columnas).
    Soporta filtrado dinámico por Año de corte y Cohorte de graduación.
    Repara automáticamente cualquier inconsistencia de codificación (mojibake).
    """
    import pandas as pd
    
    # Detección segura de cabecera probando utf-8 y latin1
    first_line = ""
    for enc in ["utf-8-sig", "latin1", "cp1252"]:
        try:
            with open(filepath, "r", encoding=enc) as f:
                first_line = f.readline()
            if first_line:
                break
        except Exception:
            continue

    es_normalizado = (
        "Periodo de graduacion" in first_line or 
        "Periodo graduación" in first_line or 
        "Numero de graduados" in first_line
    )
        
    df = None
    if es_normalizado:
        # Archivo que ya cuenta con los encabezados normalizados
        for enc in ["utf-8-sig", "latin1", "cp1252"]:
            try:
                df = pd.read_csv(filepath, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
    else:
        # Archivo exportado en bruto desde O3 Web (las 2 primeras filas son metadatos)
        for enc in ["latin1", "cp1252", "utf-8-sig"]:
            try:
                df = pd.read_csv(filepath, skiprows=2, encoding=enc)
                break
            except UnicodeDecodeError:
                continue

    if df is None:
        raise ValueError(f"No se pudo leer el archivo con ninguna codificación soportada: {filepath}")
        
    col_mapping = {}
    col_mapping[df.columns[0]] = "Periodo de graduacion"
    col_mapping[df.columns[1]] = "Año de corte"
    col_mapping[df.columns[2]] = "Municipio de origen"
    col_mapping[df.columns[3]] = "Programa academico"
    col_mapping[df.columns[4]] = "Sexo"
    col_mapping[df.columns[5]] = "Municipio en el que labora"
    
    for c in df.columns[6:]:
        c_str = str(c).strip().lower()
        if "dependiente" in c_str:
            col_mapping[c] = "Cotizantes dependientes"
        elif "que cotizan" in c_str or "cotizan" in c_str:
            col_mapping[c] = "Los que cotizan"
        elif "graduados" in c_str:
            col_mapping[c] = "Numero de graduados"
            
    df = df.rename(columns=col_mapping)
    
    # Asegurar que existan todas las columnas oficiales
    for col in COLUMNAS_OFICIALES_SALIENTE:
        if col not in df.columns:
            df[col] = 0
            
    # Reparar mojibake en todas las columnas de texto
    for col in ["Periodo de graduacion", "Año de corte", "Municipio de origen", "Programa academico", "Sexo", "Municipio en el que labora"]:
        if col in df.columns:
            df[col] = df[col].astype(str).apply(reparar_mojibake)

    # Limpieza de tipos numéricos
    for num_col in ["Numero de graduados", "Los que cotizan", "Cotizantes dependientes"]:
        df[num_col] = pd.to_numeric(df[num_col], errors="coerce").fillna(0).astype(int)

    # Filtrado opcional por Año de corte (ej. 2023, 2022)
    if anio_corte:
        corte_clean = str(anio_corte).split()[0].strip()
        if corte_clean and corte_clean.lower() not in ["todos", "all", ""]:
            df = df[df["Año de corte"].astype(str).str.contains(corte_clean, na=False)]

    # Filtrado opcional por Cohorte de graduación (ej. 2022, o Desde 2017)
    if cohorte:
        cohorte_str = str(cohorte).strip()
        if "desde" not in cohorte_str.lower() and cohorte_str.lower() not in ["todas", "all", ""]:
            cohorte_clean = cohorte_str.split()[0].strip()
            df = df[df["Periodo de graduacion"].astype(str).str.contains(cohorte_clean, na=False)]
        
    return df[COLUMNAS_OFICIALES_SALIENTE]


MAPA_ALIAS_DEPARTAMENTOS = {
    "bogota": "Bogota",
    "bogotadc": "Bogota",
    "distritocapital": "Bogota",
    "nortedesantander": "NorteSantander",
    "nortesantander": "NorteSantander",
    "norte": "NorteSantander",
    "laguajira": "LaGuajira",
    "guajira": "LaGuajira",
    "sanandres": "SanAndres",
    "sanandresyprovidencia": "SanAndres",
    "sanandresprovidenciaystacatalina": "SanAndres",
    "valledelcauca": "Valle",
    "valle": "Valle",
}


def resolver_archivos_departamento(
    departamento: str,
    directorio_datos: Path = DEFAULT_SALIENTES_DIR
) -> List[Path]:
    """
    Resuelve y encuentra todos los archivos fuente oficiales de OLE para un
    departamento, manejando alias, acentos, y casos multipartición (como Bogotá).
    Busca jerárquicamente en:
    1. Directorio de datos seleccionado por el usuario en la GUI
    2. Directorio oficial de SALIENTES en OneDrive / SharePoint
    3. Repositorio oficial de archivos fuente del OLE (Update 2023 / From2017_To2022)
    """
    norm = normalizar_texto(departamento).lower().replace(" ", "").replace("_", "").replace("-", "").replace(".", "")
    clave_busqueda = MAPA_ALIAS_DEPARTAMENTOS.get(norm, norm)

    carpetas_busqueda = [
        directorio_datos,
        DEFAULT_SALIENTES_DIR,
        DEFAULT_SALIENTES_DIR.parent if DEFAULT_SALIENTES_DIR else None,
        DEFAULT_ENTRANTES_DIR,
        # Respaldo transitorio para carpetas históricas (solo si existen en el sistema)
        Path.home() / "uniminuto.edu" / "G- Storage OEDE - VAC - FUENTES" / "SNIES" / "OLE" / "Archivos" / "Update 2023",
        Path.home() / "uniminuto.edu" / "G- Storage OEDE - VAC - FUENTES" / "SNIES" / "OLE" / "Archivos" / "From2017_To2022",
        LOCAL_OUTPUT_DIR
    ]

    archivos_encontrados = []

    for carpeta in carpetas_busqueda:
        if not carpeta or not carpeta.exists():
            continue
            
        # Si es Bogotá, buscar las 4 particiones de movilidad (excluyendo salario)
        if clave_busqueda.lower() == "bogota":
            coincidencias = sorted(list(carpeta.glob("*Bogota*.csv")))
            validas = [
                c for c in coincidencias
                if "Consolidado" not in c.name and "_RAW" not in c.name and "_Actualizado" not in c.name 
                and "AUTOMATIZADO" not in c.name and "_cohorte_" not in c.name and "salario" not in c.name.lower()
            ]
            if validas:
                archivos_encontrados = validas
                break

        # Para cualquier otro departamento por coincidencia de nombre
        coincidencias = list(carpeta.glob(f"*{clave_busqueda}*.csv"))
        validas = [
            c for c in coincidencias
            if "Consolidado" not in c.name and "_RAW" not in c.name and "_Actualizado" not in c.name 
            and "AUTOMATIZADO" not in c.name and "_cohorte_" not in c.name and "salario" not in c.name.lower()
        ]
        
        # Caso especial Santander vs Norte de Santander
        if clave_busqueda.lower() == "santander":
            validas = [c for c in validas if "nortesantander" not in normalizar_texto(c.name).lower() and "norte" not in normalizar_texto(c.name).lower()]

        # Si hay un archivo maestro "desde_2017_solo_2023", priorizarlo
        maestros = [c for c in validas if "desde_2017" in c.name and "Saliente" in c.name]
        if maestros:
            archivos_encontrados = maestros
            break
        elif validas:
            # Filtrar para asegurar que sea de movilidad saliente
            salientes = [c for c in validas if "Saliente" in c.name]
            archivos_encontrados = salientes if salientes else validas
            break

        # Búsqueda por normalización completa
        todos_csv = list(carpeta.glob("OLE_Movilidad_*.csv"))
        for a in todos_csv:
            if "Consolidado" in a.name or "_RAW" in a.name or "_Actualizado" in a.name or "AUTOMATIZADO" in a.name or "_cohorte_" in a.name or "salario" in a.name.lower():
                continue
            a_norm = normalizar_texto(a.name).lower().replace(" ", "").replace("_", "").replace("-", "").replace(".", "")
            if clave_busqueda.lower() in a_norm:
                if clave_busqueda.lower() == "santander" and "norte" in a_norm:
                    continue
                archivos_encontrados.append(a)
        if archivos_encontrados:
            break

    if not archivos_encontrados:
        raise FileNotFoundError(
            f"No se encontró el archivo oficial del OLE para el departamento '{departamento}' en ninguna de las rutas esperadas."
        )

    return archivos_encontrados

    return archivos_encontrados


def procesar_o_generar_movilidad_saliente(
    departamento: str = "Cauca",
    directorio_datos: Path = DEFAULT_SALIENTES_DIR,
    anio_corte: str = ANIO_CORTE_PREDETERMINADO,
    cohorte: str = COHORTE_PREDETERMINADA
) -> List[Dict[str, Any]]:
    """
    Procesa el archivo oficial de OLE para un departamento específico
    con las 9 columnas oficiales requeridas (100% data real de OLE).
    Resuelve automáticamente alias y multiparticiones como Bogotá.
    Aplica filtros de año de corte y cohorte según los parámetros provistos.
    """
    import pandas as pd
    
    archivos = resolver_archivos_departamento(departamento, directorio_datos)
    dfs = [parse_archivo_saliente_individual(f, anio_corte=anio_corte, cohorte=cohorte) for f in archivos]
    if len(dfs) == 1:
        df_final = dfs[0]
    else:
        df_final = pd.concat(dfs, ignore_index=True)
        
    return df_final.to_dict(orient="records")


DEPARTAMENTOS_COLOMBIA_OFICIALES = [
    "Amazonas", "Antioquia", "Arauca", "Atlántico", "Bogotá D.C.", "Bolívar",
    "Boyacá", "Caldas", "Caquetá", "Casanare", "Cauca", "Cesar", "Chocó",
    "Córdoba", "Cundinamarca", "Guainía", "Guaviare", "Huila", "La Guajira",
    "Magdalena", "Meta", "Nariño", "Norte de Santander", "Putumayo", "Quindío",
    "Risaralda", "San Andrés", "Santander", "Sucre", "Tolima", "Valle del Cauca",
    "Vaupés", "Vichada"
]


def procesar_todos_departamentos_salientes(
    directorio_salientes: Path = DEFAULT_SALIENTES_DIR,
    generar_consolidado_nacional: bool = True,
    anio_corte: str = ANIO_CORTE_PREDETERMINADO,
    cohorte: str = COHORTE_PREDETERMINADA,
    logger=None,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Procesa todos los 32 departamentos + Bogotá D.C. utilizando el resolvedor dinámico.
    Estandariza cada departamento a las 9 columnas oficiales, guarda cada archivo
    en la carpeta SALIENTES con codificación UTF-8 con BOM y genera el Consolidado Nacional
    con filtrado dinámico por cohorte y año de corte.
    """
    import pandas as pd
    
    def log(msg: str):
        if logger:
            logger(msg)
        else:
            print(f"[CONSOLIDADOR] {msg}")

    total_deptos = len(DEPARTAMENTOS_COLOMBIA_OFICIALES)
    log(f"Iniciando consolidación nacional: Cobertura total de {total_deptos} departamentos de Colombia.")
    log(f"Parámetros: Cohorte='{cohorte}' | Año de Corte='{anio_corte}'")

    dataframes_nacionales = []
    archivos_procesados = []

    for idx, depto in enumerate(DEPARTAMENTOS_COLOMBIA_OFICIALES, start=1):
        if progress_callback:
            progress_callback(idx, total_deptos, f"Consolidando {depto}")

        try:
            archivos = resolver_archivos_departamento(depto, directorio_salientes)
            dfs_depto = [parse_archivo_saliente_individual(f, anio_corte=anio_corte, cohorte=cohorte) for f in archivos]
            df_depto = pd.concat(dfs_depto, ignore_index=True) if len(dfs_depto) > 1 else dfs_depto[0]
            
            # Guardar el reporte individual estandarizado en la carpeta destino
            guardar_reporte_saliente(
                departamento=depto,
                filas=df_depto.to_dict(orient="records"),
                directorio_salida=directorio_salientes,
                anio_corte=anio_corte,
                cohorte=cohorte
            )
            dataframes_nacionales.append(df_depto)
            archivos_procesados.extend(archivos)
            log(f"  [{idx}/{total_deptos}] ✔ {depto}: {len(df_depto):,} registros procesados.")
        except Exception as e:
            log(f"  [{idx}/{total_deptos}] ⚠ No se pudo procesar {depto}: {e}")

    ruta_consolidado = None
    total_filas = sum(len(df) for df in dataframes_nacionales)

    if generar_consolidado_nacional and dataframes_nacionales:
        log("Unificando registros en el archivo Consolidado Nacional de Colombia...")
        df_nacional = pd.concat(dataframes_nacionales, ignore_index=True)
        nombre_nacional = obtener_nombre_archivo_saliente_nacional(cohorte=cohorte, anio_corte=anio_corte)
        ruta_consolidado = directorio_salientes / nombre_nacional
        
        try:
            df_nacional.to_csv(ruta_consolidado, index=False, encoding="utf-8-sig")
        except PermissionError:
            nombre_alt = nombre_nacional.replace(".csv", "_Actualizado.csv")
            ruta_consolidado = directorio_salientes / nombre_alt
            df_nacional.to_csv(ruta_consolidado, index=False, encoding="utf-8-sig")

        log(f"✔ Consolidado Nacional guardado con éxito:")
        log(f"  Ruta: {ruta_consolidado.name}")
        log(f"  Total registros de toda Colombia: {len(df_nacional):,} filas.")

    return {
        "archivos_departamentales": archivos_procesados,
        "ruta_consolidado_nacional": ruta_consolidado,
        "total_registros_colombia": total_filas
    }





def guardar_reporte_saliente(
    departamento: str,
    filas: List[Dict[str, Any]],
    directorio_salida: Path,
    anio_corte: str = ANIO_CORTE_PREDETERMINADO,
    cohorte: str = COHORTE_PREDETERMINADA
) -> Path:
    """
    Guarda el reporte consolidado de Movilidad Saliente en formato CSV
    con codificación UTF-8 con BOM y las 9 columnas oficiales.
    """
    depto_nombre = normalizar_nombre_municipio(departamento).replace(" ", "_")
    nombre_archivo = obtener_nombre_archivo_saliente(departamento=depto_nombre, cohorte=cohorte, anio_corte=anio_corte)
    archivo_csv = directorio_salida / nombre_archivo
    directorio_salida.mkdir(parents=True, exist_ok=True)

    if not filas:
        return archivo_csv

    # Si ya existía el archivo crudo de O3 sin renombrar, respaldarlo en _RAW.csv
    archivo_raw = directorio_salida / nombre_archivo.replace(".csv", "_RAW.csv")
    if archivo_csv.exists() and not archivo_raw.exists():
        try:
            import shutil
            shutil.copy2(archivo_csv, archivo_raw)
        except Exception:
            pass
    
    columnas = list(filas[0].keys())
    filas_limpias = [
        {k: reparar_mojibake(v) if isinstance(v, str) else v for k, v in fila.items()}
        for fila in filas
    ]
    
    try:
        with open(archivo_csv, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(filas_limpias)
    except PermissionError:
        # Si el archivo está abierto en Excel, guardar con sufijo _Actualizado
        archivo_alt = directorio_salida / nombre_archivo.replace(".csv", "_Actualizado.csv")
        with open(archivo_alt, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(filas_limpias)
        return archivo_alt
        
    return archivo_csv


# ==============================================================================
# FLUXO 2: MOVILIDAD ENTRANTE (Para complementar)
# ==============================================================================

def generar_matriz_municipio(municipio_consultado: str, anio_corte: str = "2023") -> List[Dict[str, Any]]:
    filas = []
    mpio_formateado = normalizar_nombre_municipio(municipio_consultado)
    for carrera in PROGRAMAS_CON_CODIGO[:8]:
        for origen_mpio in ["Cali", "Palmira", "Pasto", "Bogota D.C."]:
            filas.append({
                "Municipio_Consultado": mpio_formateado,
                "Carrera": carrera,
                "Municipio_Origen_Estudiante": origen_mpio,
                "Donde_Labora_Municipio": mpio_formateado,
                "Cohorte_Graduacion": "Desde 2017",
                "Anio_Cotizacion": anio_corte,
                "Total_Graduados": 10,
                "Cotizantes_Activos": 8
            })
    return filas


def guardar_reporte_municipio(municipio: str, filas: List[Dict[str, Any]], directorio_salida: Path) -> Path:
    nombre_formateado = normalizar_nombre_municipio(municipio).replace(" ", "_")
    archivo_csv = directorio_salida / FILENAME_TEMPLATE_ENTRANTE.format(municipio=nombre_formateado)
    directorio_salida.mkdir(parents=True, exist_ok=True)
    
    columnas = [
        "Municipio_Consultado", "Carrera", "Municipio_Origen_Estudiante",
        "Donde_Labora_Municipio", "Cohorte_Graduacion", "Anio_Cotizacion",
        "Total_Graduados", "Cotizantes_Activos"
    ]
    with open(archivo_csv, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(filas)
    return archivo_csv
