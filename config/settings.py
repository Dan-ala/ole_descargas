import os
from pathlib import Path

# Directorios base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOCAL_OUTPUT_DIR = DATA_DIR / "salida"
LOCAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Rutas oficiales en OneDrive / SharePoint (Resueltas dinámicamente según el usuario de Windows)
def _resolver_ruta_oficial(subcarpeta: str) -> Path:
    # 1. Variable de entorno personalizada si el usuario o pipeline la define
    env_dir = os.getenv(f"OLE_{subcarpeta.upper()}_DIR") or os.getenv("OLE_OUTPUT_DIR")
    if env_dir:
        try:
            p_env = Path(env_dir)
            if p_env.exists():
                return p_env
        except (OSError, PermissionError):
            pass

    # 2. Rutas dinámicas en OneDrive / SharePoint del usuario activo o cualquier perfil local
    rel_path = Path("uniminuto.edu") / "G- Storage OEDE - VAC - FUENTES_T" / "OLE" / "Archivos" / "MOVILIDAD" / subcarpeta
    candidatos = [
        Path.home() / rel_path,
        Path.home() / "OneDrive - UNIMINUTO" / "G- Storage OEDE - VAC - FUENTES_T" / "OLE" / "Archivos" / "MOVILIDAD" / subcarpeta,
    ]
    
    # Escaneo en perfiles de C:\Users por si la máquina es compartida
    try:
        users_root = Path("C:/Users")
        if users_root.exists():
            for u in users_root.iterdir():
                cand = u / rel_path
                if cand not in candidatos:
                    candidatos.append(cand)
    except Exception:
        pass

    for c in candidatos:
        try:
            if c.exists():
                return c
        except (OSError, PermissionError):
            continue

    # 3. Fallback universal garantizado: siempre la carpeta local del proyecto
    return LOCAL_OUTPUT_DIR

DEFAULT_ENTRANTES_DIR = _resolver_ruta_oficial("ENTRANTES")
DEFAULT_SALIENTES_DIR = _resolver_ruta_oficial("SALIENTES")
DEFAULT_USER_OUTPUT_DIR = DEFAULT_SALIENTES_DIR

# Rutas para el Módulo de Salarios
def _resolver_ruta_salarios(subcarpeta: str) -> Path:
    env_dir = os.getenv(f"OLE_SALARIOS_{subcarpeta.upper()}_DIR")
    if env_dir:
        try:
            p_env = Path(env_dir)
            if p_env.exists():
                return p_env
        except (OSError, PermissionError):
            pass
        
    rel_path = Path("uniminuto.edu") / "G- Storage OEDE - VAC - FUENTES_T" / "OLE" / "Archivos" / "SALARIOS" / subcarpeta
    candidatos = [
        Path.home() / rel_path,
        Path.home() / "OneDrive - UNIMINUTO" / "G- Storage OEDE - VAC - FUENTES_T" / "OLE" / "Archivos" / "SALARIOS" / subcarpeta,
        LOCAL_OUTPUT_DIR / "SALARIOS" / subcarpeta,
        LOCAL_OUTPUT_DIR
    ]
    for c in candidatos:
        try:
            if c.exists():
                return c
        except (OSError, PermissionError):
            continue
    return LOCAL_OUTPUT_DIR

DEFAULT_SALARIOS_SALIENTES_DIR = _resolver_ruta_salarios("SALIENTES")
DEFAULT_SALARIOS_ENTRANTES_DIR = _resolver_ruta_salarios("ENTRANTES")

# Archivos de persistencia de sesión y caché de cortes OLE
AUTH_STATE_PATH = BASE_DIR / ".session_state.json"
ANIOS_CACHE_PATH = BASE_DIR / ".anios_ole_cache.json"

# URLs de la plataforma OLE (Mineducación)
BASE_URL = os.getenv("OLE_BASE_URL", "http://bi.mineducacion.gov.co:8080/o3web/")
CUBE_URL = os.getenv(
    "OLE_CUBE_URL",
    "http://bi.mineducacion.gov.co:8080/o3web/viewdesktop.jsp?cmnd=open&source=Situacion_laboral%2FVista_Migraci%F3n_vl%23_public"
)

# Credenciales públicas de acceso abierto de OLE (publicadas por la fuente). Se pueden sobrescribir con las variables de entorno OLE_USER y OLE_PASSWORD.
DEFAULT_USERNAME = os.getenv("OLE_USER", "user")
DEFAULT_PASSWORD = os.getenv("OLE_PASSWORD", "user")


def obtener_anios_corte_disponibles() -> list[str]:
    """
    Obtiene la lista de años de corte disponibles en OLE.
    Consulta el archivo de caché generado desde la plataforma O3 Web de Mineducación
    y escanea las carpetas de datos locales para detectar cualquier nuevo corte publicado.
    Garantiza que el año más alto siempre quede en la posición 0 con la etiqueta '(Más reciente)'.
    """
    import json
    import re
    
    anios_set = {"2023", "2022", "2021", "2020", "2019", "2018", "2017"}
    
    # 1. Leer desde el caché de sincronización web de OLE
    if ANIOS_CACHE_PATH.exists():
        try:
            with open(ANIOS_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                anios_cache = data.get("anios_disponibles", [])
                for a in anios_cache:
                    if str(a).isdigit() and int(a) >= 2017:
                        anios_set.add(str(a))
        except Exception:
            pass

    # 2. Escanear carpeta local de archivos por si se descargó un corte nuevo (ej. 2024)
    if DEFAULT_SALIENTES_DIR.exists():
        try:
            for p in DEFAULT_SALIENTES_DIR.glob("*.csv"):
                encontrados = re.findall(r"solo_(\d{4})", p.name)
                for a in encontrados:
                    if int(a) >= 2017:
                        anios_set.add(a)
        except Exception:
            pass

    # Ordenar de mayor a menor (el año más reciente siempre primero)
    anios_ordenados = sorted(list(anios_set), key=lambda x: int(x), reverse=True)
    
    # Formatear el primer elemento con '(Más reciente)'
    resultado = [f"{anios_ordenados[0]} (Más reciente)"] + anios_ordenados[1:]
    return resultado


# Listas analíticas dinámicas
LISTA_ANIOS_CORTE = obtener_anios_corte_disponibles()
ANIO_CORTE_PREDETERMINADO = LISTA_ANIOS_CORTE[0].split()[0]
ANIO_CORTE = os.getenv("OLE_ANIO_CORTE", ANIO_CORTE_PREDETERMINADO)
COHORTE_PREDETERMINADA = "Desde 2017"
DEPARTAMENTO_OBJETIVO = os.getenv("OLE_DEPARTAMENTO", "Cauca")

LISTA_COHORTES = [
    "Desde 2017 (Histórico acumulado)",
    "2022",
    "2021",
    "2020",
    "2019",
    "2018",
    "2017"
]

# Plantillas de nombres de archivo
FILENAME_TEMPLATE_ENTRANTE = "OLE_Movilidad_{departamento}_Entrante_desde_2017_solo_2023_MPIO.csv"
FILENAME_TEMPLATE_ENTRANTE_NACIONAL = "OLE_Movilidad_Colombia_Consolidado_Entrante_desde_2017_solo_2023_MPIO.csv"
FILENAME_TEMPLATE_SALIENTE = "OLE_Movilidad_{departamento}_Saliente_desde_2017_solo_2023_MPIO.csv"
FILENAME_TEMPLATE_SALIENTE_NACIONAL = "OLE_Movilidad_Colombia_Consolidado_Saliente_desde_2017_solo_2023_MPIO.csv"


def obtener_nombre_archivo_saliente(departamento: str, cohorte: str = "Desde 2017", anio_corte: str = "2023") -> str:
    """Genera el nombre de archivo CSV estandarizado para un departamento según cohorte y corte."""
    cohorte_clean = "desde_2017" if "desde" in str(cohorte).lower() else f"cohorte_{cohorte}"
    corte_clean = str(anio_corte).split()[0].strip()
    return f"OLE_Movilidad_{departamento}_Saliente_{cohorte_clean}_solo_{corte_clean}_MPIO.csv"


def obtener_nombre_archivo_saliente_nacional(cohorte: str = "Desde 2017", anio_corte: str = "2023") -> str:
    """Genera el nombre de archivo CSV consolidado nacional según cohorte y corte."""
    cohorte_clean = "desde_2017" if "desde" in str(cohorte).lower() else f"cohorte_{cohorte}"
    corte_clean = str(anio_corte).split()[0].strip()
    return f"OLE_Movilidad_Colombia_Consolidado_Saliente_{cohorte_clean}_solo_{corte_clean}_MPIO.csv"


def obtener_nombre_archivo_entrante(departamento: str, cohorte: str = "Desde 2017", anio_corte: str = "2023") -> str:
    """Genera el nombre de archivo CSV estandarizado para movilidad entrante según cohorte y corte."""
    cohorte_clean = "desde_2017" if "desde" in str(cohorte).lower() else f"cohorte_{cohorte}"
    corte_clean = str(anio_corte).split()[0].strip()
    return f"OLE_Movilidad_{departamento}_Entrante_{cohorte_clean}_solo_{corte_clean}_MPIO.csv"


def obtener_nombre_archivo_entrante_nacional(cohorte: str = "Desde 2017", anio_corte: str = "2023") -> str:
    """Genera el nombre de archivo CSV consolidado nacional entrante según cohorte y corte."""
    cohorte_clean = "desde_2017" if "desde" in str(cohorte).lower() else f"cohorte_{cohorte}"
    corte_clean = str(anio_corte).split()[0].strip()
    return f"OLE_Movilidad_Colombia_Consolidado_Entrante_{cohorte_clean}_solo_{corte_clean}_MPIO.csv"


# ------------------------------------------------------------------------------
# Plantillas y Nombres de Archivo para SALARIOS (8 Columnas Oficiales)
# ------------------------------------------------------------------------------
FILENAME_TEMPLATE_SALARIO_SALIENTE = "OLE_SALARIO_{departamento}_Saliente_desde_2017_solo_2023_MPIO.csv"
FILENAME_TEMPLATE_SALARIO_ENTRANTE = "OLE_SALARIO_{departamento}_Entrante_desde_2017_solo_2023_MPIO.csv"
FILENAME_TEMPLATE_SALARIO_SALIENTE_NACIONAL = "OLE_SALARIO_Colombia_Consolidado_Saliente_desde_2017_solo_2023_MPIO.csv"
FILENAME_TEMPLATE_SALARIO_ENTRANTE_NACIONAL = "OLE_SALARIO_Colombia_Consolidado_Entrante_desde_2017_solo_2023_MPIO.csv"


def obtener_nombre_archivo_salario_saliente(departamento: str, cohorte: str = "Desde 2017", anio_corte: str = "2023") -> str:
    """Genera el nombre de archivo CSV estandarizado de salarios salientes."""
    cohorte_clean = "desde_2017" if "desde" in str(cohorte).lower() else f"cohorte_{cohorte}"
    corte_clean = str(anio_corte).split()[0].strip()
    return f"OLE_SALARIO_{departamento}_Saliente_{cohorte_clean}_solo_{corte_clean}_MPIO.csv"


def obtener_nombre_archivo_salario_entrante(departamento: str, cohorte: str = "Desde 2017", anio_corte: str = "2023") -> str:
    """Genera el nombre de archivo CSV estandarizado de salarios entrantes."""
    cohorte_clean = "desde_2017" if "desde" in str(cohorte).lower() else f"cohorte_{cohorte}"
    corte_clean = str(anio_corte).split()[0].strip()
    return f"OLE_SALARIO_{departamento}_Entrante_{cohorte_clean}_solo_{corte_clean}_MPIO.csv"


def obtener_nombre_archivo_salario_saliente_nacional(cohorte: str = "Desde 2017", anio_corte: str = "2023") -> str:
    """Genera el nombre de archivo CSV consolidado nacional de salarios salientes."""
    cohorte_clean = "desde_2017" if "desde" in str(cohorte).lower() else f"cohorte_{cohorte}"
    corte_clean = str(anio_corte).split()[0].strip()
    return f"OLE_SALARIO_Colombia_Consolidado_Saliente_{cohorte_clean}_solo_{corte_clean}_MPIO.csv"


def obtener_nombre_archivo_salario_entrante_nacional(cohorte: str = "Desde 2017", anio_corte: str = "2023") -> str:
    """Genera el nombre de archivo CSV consolidado nacional de salarios entrantes."""
    cohorte_clean = "desde_2017" if "desde" in str(cohorte).lower() else f"cohorte_{cohorte}"
    corte_clean = str(anio_corte).split()[0].strip()
    return f"OLE_SALARIO_Colombia_Consolidado_Entrante_{cohorte_clean}_solo_{corte_clean}_MPIO.csv"

