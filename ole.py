from playwright.sync_api import sync_playwright
import time

def run_automation():
    url = "http://bi.mineducacion.gov.co:8080/o3web/viewdesktop.jsp?cmnd=open&source=Situacion+laboral"
    
    with sync_playwright() as p:
        # Abrir el navegador en modo visible (headless=False) para supervisar el proceso
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        print(access_msg := "Conectando a la plataforma OLE / Mineducación...")
        page.goto(url)
        
        # Nota: Dependiendo de si la autenticación salta como un popup de credenciales del navegador (HTTP Basic Auth)
        # o un formulario web, el manejo varía. Si es un diálogo de usuario/contraseña del navegador:
        # (Si el login es por formulario HTML, se inspeccionan los selectores de los inputs de usuario y contraseña).
        
        try:
            # Esperar a que cargue la vista o el panel principal
            page.wait_for_load_state("networkidle", timeout=15000)
            print("Página cargada correctamente.")
            
            # Aquí puedes agregar los selectores para hacer clic en los botones de exportar a CSV/Excel
            # Por ejemplo: page.click("text=Exportar") o interactuar con los menús desplegables de departamentos/municipios.
            
            time.sleep(10) # Pausa temporal para revisión visual
            
        except Exception as e:
            print(f"Ocurrió un error durante la automatización: {e}")
            
        finally:
            browser.close()

if __name__ == "__main__":
    run_automation()