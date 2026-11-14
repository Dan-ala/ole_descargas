# 🇨🇴 OLE · Extractor y Consolidador de Movilidad Laboral

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Encoding](https://img.shields.io/badge/encoding-UTF--8%20with%20BOM-brightgreen.svg)](#-codificación-y-compatibilidad-con-excel)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](#)
[![Status](https://img.shields.io/badge/status-Production%20Ready-success.svg)](#)

Sistema modular automatizado para la **extracción, estandarización, saneamiento y consolidación de datos de Movilidad Laboral Intermunicipal** a partir de la plataforma oficial de inteligencia de negocios (**O3 Web**) del **Observatorio Laboral para la Educación (OLE)** del Ministerio de Educación Nacional de Colombia.

---

## 📌 Contexto y Propósito

El Observatorio Laboral para la Educación (OLE) almacena información fundamental sobre la transición al mercado laboral de los egresados de educación superior en Colombia. Sin embargo, su plataforma web opera sobre un visor de cubos OLAP (O3 Web) con importantes limitaciones operativas:
1. **Descarga fragmentada:** Los datos de movilidad saliente se dividen por departamentos y múltiples particiones (como Bogotá D.C. en 4 particiones).
2. **Inconsistencias estructurales:** El orden y nomenclatura de las medidas en el cubo varía según la entidad territorial.
3. **Metadatos OLAP redundantes:** Las exportaciones brutas incluyen encabezados jerárquicos multinivel que impiden la ingesta directa en pipelines de datos y herramientas de BI.
4. **Problemas de codificación (Mojibake):** El servidor exporta en Windows ANSI (Latin-1 / CP1252), desdoblando acentos y la letra `ñ` (`Ã¡`, `Ã±`, `Ã³`) al abrirse en Microsoft Excel para Windows u otros entornos modernos sin cabecera BOM.

Este proyecto resuelve de forma integral todas estas dificultades, ofreciendo una solución con interfaz gráfica moderna y capacidades de ejecución por consola (CLI).

---

## 📋 Estructura Oficial de Datos (9 Columnas Estandarizadas)

Todos los reportes generados contienen de manera estricta y limpia las 9 columnas oficiales de OLE:

| # | Nombre de Columna Oficial | Tipo de Dato | Descripción |
|---|---|---|---|
| **1** | `Periodo de graduacion` | Texto / Año | Cohorte de graduación (ej. `2017`, `2022` o rango de cohorte). |
| **2** | `Año de corte` | Entero / Año | Año de cotización laboral en la base de datos de OLE (ej. `2023`). |
| **3** | `Municipio de origen` | Texto | Código DANE y nombre del municipio de graduación (ej. `19001-Popayán`). |
| **4** | `Programa academico` | Texto | Código SNIES y nombre del programa académico cursado. |
| **5** | `Sexo` | Texto | `Femenino` o `Masculino`. |
| **6** | `Municipio en el que labora` | Texto | Código DANE y municipio donde cotiza el egresado (ej. `11001-Bogotá, D.C.`). |
| **7** | `Numero de graduados` | Entero | Cantidad de egresados titulados en dicho cruce. |
| **8** | `Los que cotizan` | Entero | Egresados que cotizan activamente a seguridad social (PILAS). |
| **9** | `Cotizantes dependientes` | Entero | Subconjunto de graduados cotizantes vinculados laboralmente de forma dependiente. |

---

## 🔍 Integridad de Datos frente a OLE (Explicación de Filas)

Al comparar los archivos generados con las exportaciones directas del cubo OLE, los datos son **100% idénticos**:

### ¿Por qué existe una diferencia aparente de 2 filas?
* **Exportación en Bruto de OLE (3 filas de encabezados):**
  * *Fila 1:* `,,,,,,Measures,,` (etiqueta de medida del cubo OLAP).
  * *Fila 2:* `Periodo graduación,Año de corte,Lugar de grado,...` (nombres de dimensiones).
  * *Fila 3:* `Año,Año,Municipio,Código programa,...` (nombres de niveles).
  * *Filas 4 en adelante:* Registros reales de datos.
* **Archivo Normalizado del Sistema (1 única fila de encabezado):**
  * *Fila 1:* Las 9 columnas oficiales estandarizadas.
  * *Filas 2 en adelante:* Registros reales de datos.

### Validación Matemática
| Departamento | Filas de Datos (OLE Bruto) | Filas de Datos (Sistema) | Sumatoria Graduados (OLE) | Sumatoria Graduados (Sistema) | Coincidencia |
|---|:---:|:---:|:---:|:---:|:---:|
| **Amazonas** | 337 | 337 | 683 | 683 | ✔ 100% Exacto |
| **Arauca** | 1.054 | 1.054 | 2.730 | 2.730 | ✔ 100% Exacto |
| **Caquetá** | 3.329 | 3.329 | 8.893 | 8.893 | ✔ 100% Exacto |
| **Cauca** | 14.412 | 14.412 | 54.129 | 54.129 | ✔ 100% Exacto |
| **Bolívar** | 21.416 | 21.416 | 108.972 | 108.972 | ✔ 100% Exacto |

---

## 🔡 Codificación y Compatibilidad con Excel

Para evitar cualquier tipo de corrupción de caracteres (*mojibake*):
1. **Autodetección de Lectura:** El analizador prueba `utf-8-sig`, `latin-1` y `cp1252` para abrir correctamente cualquier fuente.
2. **Saneador de Cadenas (`reparar_mojibake`):** Restaura de forma automática cualquier carácter desdoblado (`Ã¡` $\rightarrow$ `á`, `Ã±` $\rightarrow$ `ñ`, etc.).
3. **Escritura UTF-8 con BOM (`utf-8-sig`):** Todos los archivos de salida incluyen la marca de orden de bytes (**BOM**), permitiendo que Microsoft Excel para Windows abra el archivo con doble clic mostrando inmediatamente las tildes y eñes sin requerir configuración manual de importación.

---

## 🏛 Arquitectura del Proyecto

```text
OLE_DESCARGAS/
├── config/
│   ├── __init__.py
│   └── settings.py          # Configuración, URLs de OLE, rutas OneDrive/locales y parámetros
├── src/
│   ├── __init__.py
│   ├── auth.py              # Sesiones, autenticación CAS y descarga directa vía Playwright
│   ├── extractor.py         # Orquestador del pipeline de extracción (saliente/entrante)
│   ├── transformer.py       # Resolvedor de fuentes, limpieza, saneador mojibake y consolidación
│   └── gui.py               # Dashboard de usuario en Tkinter con diseño Dark Modern
├── data/
│   └── salida/              # Directorio de salida local por defecto (.gitkeep)
├── .anios_ole_cache.json     # Caché local de cortes disponibles detectados en OLE
├── main.py                  # Punto de entrada universal (CLI / GUI)
├── iniciar_ole.bat          # Lanzador directo de escritorio para Windows
├── requirements.txt         # Dependencias del proyecto
├── .gitignore               # Exclusiones optimizadas para Git
└── README.md                # Documentación oficial del repositorio
```

---

## 🚀 Instalación y Puesta en Marcha

### 1. Requisitos del Sistema
* **Python:** 3.10 o superior (compatible con Python 3.13 en Windows/Linux/macOS).
* Conectividad a Internet con acceso a `bi.mineducacion.gov.co:8080`.

### 2. Clonar el Repositorio e Instalar Dependencias
```bash
# Clonar repositorio
git clone <URL_DEL_REPOSITORIO>
cd OLE_DESCARGAS

# Crear y activar entorno virtual (opcional pero recomendado)
python -m venv venv
venv\Scripts\activate       # En Windows
source venv/bin/activate    # En Linux / macOS

# Instalar librerías requeridas
pip install -r requirements.txt

# Instalar navegador para Playwright (requerido para descargas automáticas)
playwright install chromium
```

---

## 💻 Modos de Uso

### 1. Modo Interfaz Gráfica (Dashboard Recomendado)
Puedes ejecutar el aplicativo haciendo doble clic en `iniciar_ole.bat` o desde la terminal:
```bash
python main.py
```

* **Selector de Territorio:** Elige un departamento individual (ej. `Bolívar`, `Cauca`) o **`🇨🇴 Toda Colombia (Consolidado Nacional)`**.
* **Selector Dinámico de Año de Corte:** Selección del año analítico (por defecto: `2023 - Más reciente`).
* **Botón `🔄 Sincronizar OLE`:** Realiza una consulta directa al servidor del Ministerio de Educación. Cuando se publique el **corte 2024**, la sincronización lo detecta y lo añade automáticamente al desplegable.
* **Selector de Cohorte:** Permite filtrar entre **`Desde 2017 (Histórico acumulado)`** o cohortes específicas individuales (`2022`, `2021`, etc.).
* **Ruta de Destino:** Configurada por defecto en tu carpeta compartida de OneDrive/SharePoint o carpeta local seleccionable mediante el botón **Examinar...**.

### 2. Modo Consola (CLI / Automatización)
Ideal para tareas programadas de Windows (Task Scheduler), pipelines cron o entornos sin interfaz gráfica:

```bash
# Procesar un departamento específico (ej. Bolívar, corte 2023, cohortes Desde 2017)
python main.py --cli --departamento Bolívar

# Procesar con filtros temporales específicos
python main.py --cli --departamento Cauca --cohorte 2022 --anio-corte 2023

# Generar el Consolidado Nacional de toda Colombia (32 departamentos + Bogotá D.C.)
python main.py --cli --departamento Colombia

# Especificar carpeta de salida personalizada
python main.py --cli --departamento Antioquia --output-dir "C:/MisDatos/OLE"
```

---

## 🔒 Notas Técnicas de Seguridad y Red
* **Automatización con navegador estándar:** Automatización con navegador estándar, respetando las condiciones de uso de la fuente. OLE ofrece acceso abierto con credenciales públicas.
* **Variables de Entorno:** Puedes sobrescribir credenciales o rutas configurando las variables de entorno `OLE_BASE_URL`, `OLE_USER`, `OLE_PASSWORD` o editando [config/settings.py](file:///c:/Users/daniel.alarcon.f/Desktop/CADIT/OLE_DESCARGAS/config/settings.py).

---

## 👥 Contribución y Control de Versiones

```bash
# Inicializar repositorio git local
git init

# Vincular con el repositorio remoto en GitHub
git remote add origin https://github.com/TU_ORGANIZACION/OLE_DESCARGAS.git

# Preparar y realizar el commit inicial
git add .
git commit -m "feat: release inicial OLE_DESCARGAS v1.0.0 (GUI, CLI, saneador mojibake y consolidación nacional)"

# Subir a la rama principal
git branch -M main
git push -u origin main
```
