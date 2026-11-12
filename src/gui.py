"""
Módulo de Interfaz Gráfica de Usuario (GUI) Moderna para OLE_DESCARGAS.
Diseño Dashboard Profesional con tema oscuro elegante, selector de flujo
(Movilidad Saliente vs Movilidad Entrante), selector de departamento / Toda Colombia,
barra de progreso y consola en tiempo real.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
from datetime import datetime

from config.settings import (
    DEFAULT_SALIENTES_DIR,
    DEFAULT_ENTRANTES_DIR,
    LOCAL_OUTPUT_DIR,
    DEPARTAMENTO_OBJETIVO,
    ANIO_CORTE_PREDETERMINADO,
    COHORTE_PREDETERMINADA,
    LISTA_ANIOS_CORTE,
    LISTA_COHORTES,
    obtener_anios_corte_disponibles,
)

LISTA_DEPARTAMENTOS_COLOMBIA = [
    "🇨🇴 Toda Colombia (Consolidado Nacional)",
    "Antioquia",
    "Atlántico",
    "Bogotá D.C.",
    "Bolívar",
    "Boyacá",
    "Caldas",
    "Caquetá",
    "Casanare",
    "Cauca",
    "Cesar",
    "Chocó",
    "Córdoba",
    "Cundinamarca",
    "Guainía",
    "Guaviare",
    "Huila",
    "La Guajira",
    "Magdalena",
    "Meta",
    "Nariño",
    "Norte de Santander",
    "Putumayo",
    "Quindío",
    "Risaralda",
    "San Andrés",
    "Santander",
    "Sucre",
    "Tolima",
    "Valle del Cauca",
    "Vaupés",
    "Vichada",
    "Amazonas",
    "Arauca"
]


class OLEApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("OLE · Extractor y Consolidador de Movilidad Laboral (Colombia)")
        self.geometry("920x730")
        self.minsize(840, 640)
        
        # Paleta de colores Dark Modern Dashboard (Slate / Indigo)
        self.BG_MAIN = "#0F172A"       # Slate 900
        self.BG_CARD = "#1E293B"       # Slate 800
        self.BG_INPUT = "#334155"      # Slate 700
        self.TEXT_PRIMARY = "#F8FAFC"   # Slate 50
        self.TEXT_MUTED = "#94A3B8"     # Slate 400
        self.ACCENT_BLUE = "#3B82F6"    # Blue 500
        self.ACCENT_GREEN = "#10B981"   # Emerald 500
        self.BORDER_COLOR = "#475569"   # Slate 600

        self.modo_var = tk.StringVar(value="saliente")
        self.depto_var = tk.StringVar(value=LISTA_DEPARTAMENTOS_COLOMBIA[0])
        self.corte_var = tk.StringVar(value=LISTA_ANIOS_CORTE[0])
        self.cohorte_var = tk.StringVar(value=LISTA_COHORTES[0])
        self.extractor_thread = None
        self.en_ejecucion = False

        self.configure(bg=self.BG_MAIN)
        self._configurar_estilos()
        self._crear_interfaz()
        self._actualizar_vista_por_modo()

    def _configurar_estilos(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        
        self.style.configure(
            "Modern.Horizontal.TProgressbar",
            troughcolor=self.BG_INPUT,
            background=self.ACCENT_BLUE,
            bordercolor=self.BORDER_COLOR,
            lightcolor=self.ACCENT_BLUE,
            darkcolor=self.ACCENT_BLUE,
            thickness=14
        )

        self.style.configure(
            "TCombobox",
            fieldbackground=self.BG_INPUT,
            background=self.BG_CARD,
            foreground=self.TEXT_PRIMARY,
            darkcolor=self.BORDER_COLOR,
            lightcolor=self.BORDER_COLOR
        )

    def _crear_interfaz(self):
        # 1. ENCABEZADO
        header_frame = tk.Frame(self, bg=self.BG_MAIN, pady=14, padx=24)
        header_frame.pack(fill="x")
        
        title_row = tk.Frame(header_frame, bg=self.BG_MAIN)
        title_row.pack(fill="x")
        
        lbl_titulo = tk.Label(
            title_row,
            text="Observatorio Laboral para la Educación (OLE)",
            font=("Segoe UI", 16, "bold"),
            bg=self.BG_MAIN,
            fg=self.TEXT_PRIMARY
        )
        lbl_titulo.pack(side="left")
        
        self.badge = tk.Label(
            title_row,
            text=" v3.0 · Colombia Nacional ",
            font=("Segoe UI", 9, "bold"),
            bg="#312E81",
            fg="#A5B4FC",
            padx=10,
            pady=3
        )
        self.badge.pack(side="right")
        
        self.lbl_sub = tk.Label(
            header_frame,
            text="Automatización de datos oficiales: Cohortes desde 2017 · Corte solo 2023 · Análisis Nacional e Intermunicipal",
            font=("Segoe UI", 9),
            bg=self.BG_MAIN,
            fg=self.TEXT_MUTED
        )
        self.lbl_sub.pack(anchor="w", pady=(4, 0))

        # 2. SELECTOR DE MODO Y ALCANCE
        selector_card = tk.Frame(self, bg=self.BG_CARD, padx=16, pady=12, relief="flat", highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        selector_card.pack(fill="x", padx=24, pady=(0, 10))

        top_sel_box = tk.Frame(selector_card, bg=self.BG_CARD)
        top_sel_box.pack(fill="x", pady=(0, 8))

        lbl_sel_title = tk.Label(
            top_sel_box,
            text="Tipo de Movilidad:",
            font=("Segoe UI", 10, "bold"),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY
        )
        lbl_sel_title.pack(side="left")

        # Alcance / Selector de Departamento
        self.lbl_depto_title = tk.Label(
            top_sel_box,
            text="Territorio / Departamento:",
            font=("Segoe UI", 10, "bold"),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY
        )
        self.lbl_depto_title.pack(side="right", padx=(0, 190))

        modes_row = tk.Frame(selector_card, bg=self.BG_CARD)
        modes_row.pack(fill="x")

        # Radiobuttons de Modo
        rb_box = tk.Frame(modes_row, bg=self.BG_CARD)
        rb_box.pack(side="left", fill="y")

        self.rb_saliente = tk.Radiobutton(
            rb_box,
            text="📤 Saliente (Hacia dónde laboran - 9 Columnas)",
            variable=self.modo_var,
            value="saliente",
            font=("Segoe UI", 9, "bold"),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY,
            selectcolor=self.BG_INPUT,
            activebackground=self.BG_CARD,
            activeforeground="white",
            command=self._actualizar_vista_por_modo
        )
        self.rb_saliente.pack(anchor="w", pady=1)

        self.rb_entrante = tk.Radiobutton(
            rb_box,
            text="📥 Entrante (Graduados que ingresan a laborar)",
            variable=self.modo_var,
            value="entrante",
            font=("Segoe UI", 9),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY,
            selectcolor=self.BG_INPUT,
            activebackground=self.BG_CARD,
            activeforeground="white",
            command=self._actualizar_vista_por_modo
        )
        self.rb_entrante.pack(anchor="w", pady=1)

        # Combobox de Departamentos
        combo_box = tk.Frame(modes_row, bg=self.BG_CARD)
        combo_box.pack(side="right", fill="y")

        self.combo_depto = ttk.Combobox(
            combo_box,
            textvariable=self.depto_var,
            values=LISTA_DEPARTAMENTOS_COLOMBIA,
            state="readonly",
            width=36,
            font=("Segoe UI", 9)
        )
        self.combo_depto.pack(anchor="e", ipady=4)
        self.combo_depto.bind("<<ComboboxSelected>>", lambda e: self._actualizar_vista_por_modo())

        # Fila de Parámetros Temporales (Año de corte y Cohorte)
        temporal_row = tk.Frame(selector_card, bg=self.BG_CARD)
        temporal_row.pack(fill="x", pady=(10, 2))

        # Selector de Año de Corte
        corte_box = tk.Frame(temporal_row, bg=self.BG_CARD)
        corte_box.pack(side="left")

        lbl_corte_title = tk.Label(
            corte_box,
            text="📅 Año de Corte (Predeterminado: Más reciente):",
            font=("Segoe UI", 9, "bold"),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY
        )
        lbl_corte_title.pack(anchor="w", pady=(0, 2))

        corte_input_row = tk.Frame(corte_box, bg=self.BG_CARD)
        corte_input_row.pack(anchor="w")

        self.combo_corte = ttk.Combobox(
            corte_input_row,
            textvariable=self.corte_var,
            values=LISTA_ANIOS_CORTE,
            state="readonly",
            width=22,
            font=("Segoe UI", 9)
        )
        self.combo_corte.pack(side="left", ipady=3)
        self.combo_corte.bind("<<ComboboxSelected>>", lambda e: self._actualizar_vista_por_modo())

        self.btn_sync_ole = tk.Button(
            corte_input_row,
            text="🔄 Sincronizar OLE",
            font=("Segoe UI", 8, "bold"),
            bg=self.BG_INPUT,
            fg="#93C5FD",
            activebackground=self.BORDER_COLOR,
            activeforeground="white",
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._sincronizar_anios_ole
        )
        self.btn_sync_ole.pack(side="left", padx=(8, 0))

        # Selector de Cohorte de Graduación
        cohorte_box = tk.Frame(temporal_row, bg=self.BG_CARD)
        cohorte_box.pack(side="right")

        lbl_cohorte_title = tk.Label(
            cohorte_box,
            text="🎓 Cohorte de Graduación:",
            font=("Segoe UI", 9, "bold"),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY
        )
        lbl_cohorte_title.pack(anchor="e", pady=(0, 2))

        self.combo_cohorte = ttk.Combobox(
            cohorte_box,
            textvariable=self.cohorte_var,
            values=LISTA_COHORTES,
            state="readonly",
            width=32,
            font=("Segoe UI", 9)
        )
        self.combo_cohorte.pack(anchor="e", ipady=3)
        self.combo_cohorte.bind("<<ComboboxSelected>>", lambda e: self._actualizar_vista_por_modo())

        # 3. TARJETA DE FILTRO ACTIVO
        self.filtro_card = tk.Frame(self, bg=self.BG_CARD, padx=16, pady=10, relief="flat", highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        self.filtro_card.pack(fill="x", padx=24, pady=(0, 10))
        
        self.lbl_info_filtro = tk.Label(
            self.filtro_card,
            text="",
            font=("Segoe UI", 9, "bold"),
            bg=self.BG_CARD,
            fg="#34D399"
        )
        self.lbl_info_filtro.pack(anchor="w")

        # 4. TARJETA DE CONFIGURACIÓN Y RUTA
        card_config = tk.Frame(self, bg=self.BG_CARD, padx=18, pady=14, relief="flat", highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        card_config.pack(fill="x", padx=24, pady=(0, 10))
        
        lbl_path_title = tk.Label(
            card_config,
            text="Carpeta de Destino (Archivos CSV):",
            font=("Segoe UI", 10, "bold"),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY
        )
        lbl_path_title.pack(anchor="w", pady=(0, 6))
        
        path_box = tk.Frame(card_config, bg=self.BG_CARD)
        path_box.pack(fill="x", pady=(0, 10))
        
        self.txt_output_dir = tk.Entry(
            path_box,
            font=("Segoe UI", 9),
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            insertbackground="white",
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR
        )
        self.txt_output_dir.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))
        
        btn_examinar = tk.Button(
            path_box,
            text="📁 Examinar...",
            font=("Segoe UI", 9, "bold"),
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            activebackground=self.BORDER_COLOR,
            activeforeground="white",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._seleccionar_directorio
        )
        btn_examinar.pack(side="right")
        
        # Botones de Acción
        btn_box = tk.Frame(card_config, bg=self.BG_CARD)
        btn_box.pack(fill="x", pady=(4, 0))
        
        self.btn_iniciar = tk.Button(
            btn_box,
            text="🚀 Iniciar",
            font=("Segoe UI", 10, "bold"),
            bg=self.ACCENT_BLUE,
            fg="#FFFFFF",
            activebackground="#2563EB",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=self._iniciar_extraccion
        )
        self.btn_iniciar.pack(side="left", padx=(0, 12))
        
        self.btn_abrir_carpeta = tk.Button(
            btn_box,
            text="📂 Abrir Carpeta",
            font=("Segoe UI", 9),
            bg=self.BG_INPUT,
            fg=self.TEXT_PRIMARY,
            activebackground=self.BORDER_COLOR,
            activeforeground="white",
            relief="flat",
            padx=14,
            pady=7,
            cursor="hand2",
            command=self._abrir_carpeta_salida
        )
        self.btn_abrir_carpeta.pack(side="left")

        # 5. BARRA DE PROGRESO DINÁMICA
        progress_card = tk.Frame(self, bg=self.BG_MAIN, padx=24, pady=2)
        progress_card.pack(fill="x")
        
        prog_labels = tk.Frame(progress_card, bg=self.BG_MAIN)
        prog_labels.pack(fill="x", pady=(0, 4))
        
        self.lbl_progress_status = tk.Label(
            prog_labels,
            text="Estado: Listo para iniciar",
            font=("Segoe UI", 9),
            bg=self.BG_MAIN,
            fg=self.TEXT_MUTED
        )
        self.lbl_progress_status.pack(side="left")
        
        self.lbl_progress_pct = tk.Label(
            prog_labels,
            text="0%",
            font=("Segoe UI", 9, "bold"),
            bg=self.BG_MAIN,
            fg=self.ACCENT_BLUE
        )
        self.lbl_progress_pct.pack(side="right")
        
        self.progress_bar = ttk.Progressbar(
            progress_card,
            orient="horizontal",
            mode="determinate",
            style="Modern.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill="x")

        # 6. CONSOLA DE EVENTOS Y REGISTRO
        console_frame = tk.Frame(self, bg=self.BG_MAIN, padx=24, pady=6)
        console_frame.pack(fill="both", expand=True)
        
        lbl_consola = tk.Label(
            console_frame,
            text="Registro de Operación en Tiempo Real:",
            font=("Segoe UI", 9, "bold"),
            bg=self.BG_MAIN,
            fg=self.TEXT_MUTED
        )
        lbl_consola.pack(anchor="w", pady=(0, 4))
        
        self.txt_log = ScrolledText(
            console_frame,
            wrap="word",
            font=("Consolas", 9),
            bg="#0B1120",
            fg="#E2E8F0",
            insertbackground="white",
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR
        )
        self.txt_log.pack(fill="both", expand=True)

    def _actualizar_vista_por_modo(self):
        modo = self.modo_var.get()
        depto_sel = self.depto_var.get()
        es_nacional = "Colombia" in depto_sel
        corte_raw = self.corte_var.get()
        corte_sel = corte_raw.split()[0].strip()
        cohorte_raw = self.cohorte_var.get()
        cohorte_tag = "Desde 2017" if "desde" in cohorte_raw.lower() else f"Cohorte {cohorte_raw.split()[0]}"

        if modo == "saliente":
            if es_nacional:
                self.badge.config(text=f" v3.1 · Toda Colombia ({corte_sel}) ", bg="#312E81", fg="#A5B4FC")
                self.lbl_info_filtro.config(
                    text=f"📌 Filtro Activo: Saliente NACIONAL | Cohorte: {cohorte_tag} | Corte: {corte_sel} | 9 Columnas Oficiales OLE"
                )
                self.btn_iniciar.config(text=f"🚀 Consolidar Toda Colombia ({corte_sel})")
            else:
                self.badge.config(text=f" v3.1 · {depto_sel} ({corte_sel}) ", bg="#312E81", fg="#A5B4FC")
                self.lbl_info_filtro.config(
                    text=f"📌 Filtro Activo: Movilidad Saliente ({depto_sel}) | Cohorte: {cohorte_tag} | Corte: {corte_sel} | 9 Columnas Oficiales OLE"
                )
                self.btn_iniciar.config(text=f"🚀 Procesar Saliente ({depto_sel} · {corte_sel})")

            ruta_defecto = str(DEFAULT_SALIENTES_DIR) if DEFAULT_SALIENTES_DIR.exists() else str(LOCAL_OUTPUT_DIR)
        else:
            self.badge.config(text=f" v3.1 · Entrante ({corte_sel}) ", bg="#065F46", fg="#A7F3D0")
            self.lbl_info_filtro.config(
                text=f"📌 Filtro Activo: Movilidad Entrante (Graduados que laboran en Cauca) | Cobertura: 42 Municipios | Corte: {corte_sel}"
            )
            ruta_defecto = str(DEFAULT_ENTRANTES_DIR) if DEFAULT_ENTRANTES_DIR.exists() else str(LOCAL_OUTPUT_DIR)
            self.btn_iniciar.config(text=f"🚀 Descargar Todos los Municipios (Entrante · {corte_sel})")

        self.txt_output_dir.delete(0, tk.END)
        self.txt_output_dir.insert(0, os.path.normpath(ruta_defecto))

    def _sincronizar_anios_ole(self):
        """
        Ejecuta en segundo plano la consulta al cubo OLAP del Ministerio de Educación
        para detectar si se ha publicado un nuevo año de corte (ej. 2024).
        """
        def _hilo_sync():
            try:
                self.btn_sync_ole.config(state="disabled", text="⏳ Consultando...")
                self.log("Iniciando consulta en vivo al servidor O3 Web del OLE (Mineducación)...")
                from src.auth import consultar_anios_disponibles_ole_web
                
                anios_obtenidos = consultar_anios_disponibles_ole_web(headless=False, logger=self.log)
                nuevos_anios = obtener_anios_corte_disponibles()
                
                self.combo_corte["values"] = nuevos_anios
                self.corte_var.set(nuevos_anios[0])
                self._actualizar_vista_por_modo()
                
                mas_reciente = nuevos_anios[0].split()[0]
                self.log(f"✔ Sincronización completada con éxito. Corte más reciente: {mas_reciente} (Total: {len(nuevos_anios)})")
                messagebox.showinfo(
                    "Sincronización OLE Exitosa",
                    f"¡Sincronización con el Ministerio de Educación completada con éxito!\n\n"
                    f"Corte más reciente disponible: {mas_reciente}\n"
                    f"Total cortes detectados en OLE: {len(nuevos_anios)}\n\n"
                    f"El selector ha sido actualizado automáticamente al corte más reciente."
                )
            except Exception as e:
                self.log(f"⚠ Aviso en sincronización: {e}")
                messagebox.showwarning(
                    "Aviso de Sincronización",
                    f"No se pudo completar la consulta en vivo:\n{e}\n\nSe conservan los cortes almacenados en caché."
                )
            finally:
                self.btn_sync_ole.config(state="normal", text="🔄 Sincronizar OLE")

        threading.Thread(target=_hilo_sync, daemon=True).start()

    def _seleccionar_directorio(self):
        carpeta = filedialog.askdirectory(
            initialdir=self.txt_output_dir.get(),
            title="Seleccionar Carpeta de Destino"
        )
        if carpeta:
            self.txt_output_dir.delete(0, tk.END)
            self.txt_output_dir.insert(0, os.path.normpath(carpeta))
            self.log(f"Destino actualizado a: {carpeta}")

    def _abrir_carpeta_salida(self):
        ruta = Path(self.txt_output_dir.get().strip())
        if not ruta.exists():
            ruta.mkdir(parents=True, exist_ok=True)
        os.startfile(str(ruta))

    def log(self, mensaje: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_log.insert(tk.END, f"[{timestamp}] {mensaje}\n")
        self.txt_log.see(tk.END)

    def _actualizar_progreso(self, actual: int, total: int, detalle: str):
        pct = int((actual / total) * 100) if total > 0 else 0
        self.progress_bar["value"] = pct
        self.lbl_progress_pct.config(text=f"{pct}%")
        self.lbl_progress_status.config(text=f"{detalle} ({pct}%)")
        self.update_idletasks()

    def _iniciar_extraccion(self):
        if self.en_ejecucion:
            messagebox.showinfo("En Proceso", "Ya hay un proceso en curso.")
            return
            
        ruta_salida = Path(self.txt_output_dir.get().strip())
        try:
            ruta_salida.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error de Ruta", f"No se pudo crear o acceder a la carpeta:\n{e}")
            return
            
        self.en_ejecucion = True
        modo = self.modo_var.get()
        depto = "Colombia" if "Colombia" in self.depto_var.get() else self.depto_var.get()
        anio_corte_sel = self.corte_var.get().split()[0].strip()
        cohorte_sel = self.cohorte_var.get()
        
        self.btn_iniciar.config(state="disabled", text="⏳ Procesando datos...")
        self.progress_bar["value"] = 0
        self.lbl_progress_pct.config(text="0%")
        
        self.extractor_thread = threading.Thread(
            target=self._hilo_extraccion,
            args=(ruta_salida, modo, depto, anio_corte_sel, cohorte_sel),
            daemon=True
        )
        self.extractor_thread.start()

    def _hilo_extraccion(self, ruta_salida: Path, modo: str, depto: str, anio_corte: str, cohorte: str):
        try:
            self.log(f"Iniciando proceso: MODO={modo.upper()} | OBJETIVO={depto} | CORTE={anio_corte} | COHORTE={cohorte}...")
            from src.extractor import extraer_datos_situacion_laboral
            
            archivos = extraer_datos_situacion_laboral(
                output_dir=ruta_salida,
                departamento=depto,
                anio_corte=anio_corte,
                cohorte=cohorte,
                modo=modo,
                logger=self.log,
                progress_callback=self._actualizar_progreso
            )
            self.log("¡Proceso finalizado con total éxito!")
            self.lbl_progress_status.config(text="Estado: ¡Completado exitosamente (100%)!")
            messagebox.showinfo(
                "Proceso Completo",
                f"Se ha procesado exitosamente la información en:\n{ruta_salida}\n\nArchivos consolidados/generados: {len(archivos)}"
            )
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", f"Ocurrió un error en la ejecución:\n{e}")
        finally:
            self.en_ejecucion = False
            self.btn_iniciar.config(state="normal")
            self._actualizar_vista_por_modo()


def run_gui():
    app = OLEApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
