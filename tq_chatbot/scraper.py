"""
scraper.py
Web scraping COMPLETO de Tecnoquimicas - MODO PACIENCIA NINJA (Stealth Extremo)
Motor: undetected_chromedriver + requests + BeautifulSoup
"""

import os
import json
import re
import time
import random
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# El arma secreta anti-bots
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

# ══════════════════════════════════════════════════════════════════════════════
# URLS DE TQ CONFIABLE (AHORA CON HTTPS - PUERTA SEGURA)
# ══════════════════════════════════════════════════════════════════════════════
URLS_SELENIUM = {
    "quien_es_tq":   "https://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/quien-es-tq/",
    "mision":        "https://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/mision/",
    "vision":        "https://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/vision/",
    "credo":         "https://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/credo/",
    "historia":      "https://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/historia/",
    "proposito":     "https://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/nuestro-prop%C3%B3sito/",
    "planeta":       "https://www.tqconfiable.com/asi-cambiamos-al-mundo/mundo/planeta/",
    "gente":         "https://www.tqconfiable.com/asi-cambiamos-al-mundo/mundo/gente/",
    "innovacion":    "https://www.tqconfiable.com/asi-cambiamos-al-mundo/innovacion/",
    "investigacion": "https://www.tqconfiable.com/asi-cambiamos-al-mundo/innovacion/investigaci%C3%B3n/",
    "ofertas":       "https://www.tqconfiable.com/trabaja/ofertas/",
    "beneficios":    "https://www.tqconfiable.com/trabaja/beneficios/",
    "testimonios":   "https://www.tqconfiable.com/trabaja/testimonios/",
    "encuentranos":  "https://www.tqconfiable.com/contacto/encuentranos/",
    "servicio":      "https://www.tqconfiable.com/contacto/servicio-al-cliente/",
    "faq":           "https://www.tqconfiable.com/contacto/preguntas-frecuentes/",
    "linea_etica":   "https://www.tqconfiable.com/contacto/linea-etica/",
    "gobierno":      "https://www.tqconfiable.com/gobierno-corporativo/",
    "noticias":                  "https://www.tqconfiable.com/noticias/",
    "noticia_alcohol_gel":       "https://www.tqconfiable.com/noticias/tq-lanza-su-alcohol-gel-mk-al-70/",
    "noticia_multilatinas":      "https://www.tqconfiable.com/noticias/tq-una-de-las-100-multilatinas/",
    "noticia_lactancia":         "https://www.tqconfiable.com/noticias/programa-de-lactancia-materna-y-plan-canguro/",
    "noticia_500empresas":       "https://www.tqconfiable.com/noticias/tq-una-de-las-500-empresas-mas-exitosas-del-valle/",
    "noticia_historia_medicina": "https://www.tqconfiable.com/noticias/tomo-iii-historia-de-la-medicina-en-colombia/",
    "noticia_winny_marca":       "https://www.tqconfiable.com/noticias/winny-una-de-las-20-marcas-colombianas-mas-valiosas/",
    "noticia_copidrogas":        "https://www.tqconfiable.com/noticias/copidrogas-exalto-a-tq/",
    "noticia_educacion":         "https://www.tqconfiable.com/noticias/en-tq-tambien-le-aportamos-al-bienestar-de-nuestra-gente-con-programas-de-educacion/",
    "noticia_canguro":           "https://www.tqconfiable.com/noticias/tq-comprometida-con-el-programa-contacto-canguro-de-la-fundacion-valle-del-lili/",
    "noticia_ecuador":           "https://www.tqconfiable.com/noticias/tq-se-solidariza-con-ecuador-y-sus-colaboradores-en-el-vecino-pais/",
    "noticia_asocoldro":         "https://www.tqconfiable.com/noticias/asocoldro-distinguio-al-doctor-francisco-jose-barberi-por-sus-aportes-a-los-droguistas-colombianos/",
    "noticia_asinfar":           "https://www.tqconfiable.com/noticias/asinfar-una-historia-de-importantes-logros-a-favor-de-la-salud-en-colombia/",
    "noticia_ced_graduacion":    "https://www.tqconfiable.com/noticias/rodeados-de-amor-12-ni%C3%B1os-del-ced-tq-recibieron-diplomas-y-medallas-de-graduacion/",
    "noticia_codigo_etica":      "https://www.tqconfiable.com/noticias/las-empresas-farmaceuticas-afiliadas-a-la-andi-suscribieron-su-codigo-de-etica-y-transparencia/",
    "noticia_andi_barberi":      "https://www.tqconfiable.com/noticias/la-andi-seccional-valle-exalto-la-trayectoria-de-francisco-jose-barberi-presidente-de-tq/",
    "noticia_auditorio":         "https://www.tqconfiable.com/noticias/auditorio-lucero-ospina-de-barberi-un-nuevo-espacio-para-el-crecimiento-integral-de-nuestra-familia-tq/",
    "noticia_winny_prematuros":  "https://www.tqconfiable.com/noticias/winny-dona-pa%C3%B1ales-para-los-bebes-prematuros-de-colombia/",
    "noticia_colbon":            "https://www.tqconfiable.com/noticias/colbon-incursiona-con-productos-innovadores-en-el-mercado-de-la-construccion/",
    "noticia_educando":          "https://www.tqconfiable.com/noticias/educando-para-la-vida/",
    "noticia_vive_tq":           "https://www.tqconfiable.com/noticias/vive-tq-un-programa-creado-para-fortalecer-la-relacion-con-los-universitarios/",
    "noticia_reputacion":        "https://www.tqconfiable.com/noticias/tq-la-compa%C3%B1ia-colombiana-con-mayor-reputacion-en-la-industria-farmaceutica-del-pais/",
    "noticia_cruz_roja":         "https://www.tqconfiable.com/noticias/reconocimiento-de-la-cruz-roja-a-tecnoquimicas-del-ecuador/",
    "noticia_proveedor_lider":   "https://www.tqconfiable.com/noticias/tq-es-el-proveedor-lider-en-colaboracion-y-logistica-para-los-comerciantes-del-sector-salud-en-colombia/",
    "noticia_estudio_salutia":   "https://www.tqconfiable.com/noticias/estudio-cientifico-realizado-por-tq-y-la-fundacion-salutia-fue-destacado-en-prestigiosa-publicacion-internacional/",
    "noticia_dermatologicos":    "https://www.tqconfiable.com/noticias/con-nuevos-estudios-cientificos-sobre-productos-dermatologicos-tq-sigue-contribuyendo-al-bienestar-de-los-colombianos/",
    "noticia_cultura":           "https://www.tqconfiable.com/noticias/en-tq-las-actividades-culturales-promueven-el-desarrollo-integral-de-nuestros-colaboradores/",
    "noticia_valle_lili":        "https://www.tqconfiable.com/noticias/con-el-apoyo-de-tq-se-inauguro-nueva-sala-para-el-bienestar-de-ni%C3%B1os-y-jovenes-en-la-fundacion-clinica-valle-del-lili/",
    "noticia_winny_innovador":   "https://www.tqconfiable.com/noticias/tq-y-su-marca-winny-ofrecen-un-producto-innovador-para-garantizar-la-proteccion-y-comodidad-para-nuestros-bebes/",
    "noticia_compromiso":        "https://www.tqconfiable.com/noticias/tecnoquimicas-reafirma-su-compromiso-con-el-desarrollo/",
    "noticia_tq_agro":           "https://www.tqconfiable.com/noticias/tq-agro-fortalece-su-novedosa-l%C3%ADnea-de-productos-amigables-con-el-medio-ambiente/",
    "noticia_vacunacion":        "https://www.tqconfiable.com/noticias/en-tq-celebramos-ser-parte-de-las-primeras-empresas-privadas-en-vacunar-a-sus-empleados-contra-el-covid-19/",
    "noticia_orden_merito":      "https://www.tqconfiable.com/noticias/nos-mueve-el-compromiso-con-colombia-y-su-gente-francisco-jos%C3%A9-barberi-al-recibir-la-orden-al-m%C3%A9rito-empresarial-de-la-andi/",
    "noticia_cancer_colon":      "https://www.tqconfiable.com/noticias/campana-cancer-colon/",
    "noticia_educacion_calidad": "https://www.tqconfiable.com/noticias/educacion-alta-calidad-transformacion-social/",
    "noticia_grupo_innovacion":  "https://www.tqconfiable.com/noticias/grupo-tq-innovacion-investigacion-salud-bienestar/",
    "noticia_comunidad":         "https://www.tqconfiable.com/noticias/grupo-tq-compromiso-comunidad-salud-bienestar-titanes-caracol/",
    "noticia_content":           "https://www.tqconfiable.com/noticias/content-un-compromiso-con-el-cuidado-y-el-bienestar-del-adulto/",
}

# ══════════════════════════════════════════════════════════════════════════════
# URLS TQ FARMA (Usarán Requests para ser más rápidos)
# ══════════════════════════════════════════════════════════════════════════════
URLS_REQUESTS = {
    "tqfarma_inicio":       "https://www.tqfarma.com/",
    "tqfarma_quienes":      "https://www.tqfarma.com/quienes-somos",
    "tqfarma_contacto":     "https://www.tqfarma.com/contactenos",
    "tqfarma_vademecum":    "https://www.tqfarma.com/vademecum-tq",
    "tqfarma_vademecum_mk": "https://www.tqfarma.com/vademecum-mk",
    "tqfarma_vademecum_otc":"https://www.tqfarma.com/vademecum-otc",
    "tqfarma_medicamentos": "https://www.tqfarma.com/medicamentos-a-z",
    "tqfarma_noticias":     "https://www.tqfarma.com/biblioteca-cientifica/noticias-actualidad",
    "tqfarma_guias":        "https://www.tqfarma.com/biblioteca-cientifica/actualizacion-en-guias-de-practica-clinica",
}

NAV_EXACT = {
    "Síguenos", "LinkedIn", "Instagram", "Facebook", "Youtube", "Twitter",
    "Colaborador TQ", "Portal Médicos", "Gobierno Corporativo", "Pagos Clientes",
    "Así Cambiamos El Mundo", "Trabaja con Nosotros", "Nuestras Marcas",
    "Términos y condiciones", "Políticas de privacidad", "Todos los derechos reservados", 
    "INICIAR SESIÓN", "REGISTRARSE", "Acceso a Journals", "VER TODAS", "ACCEDER", "Buscar", "Cerrar"
}

def extract_text(html: str, section: str) -> str:
    """Extrae el texto manteniendo la mayor cantidad de 'carne' posible"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    
    raw = soup.get_text(separator="\n\n")
    lines = []
    seen = set()
    for line in raw.splitlines():
        line = line.strip()
        # FILTRO RELAJADO: Si la línea tiene menos de 4 letras PERO tiene un número (como "MK" o "2024"), la guardamos
        if len(line) < 4 and not any(c.isdigit() for c in line) and line not in ["TQ", "MK"]:
            continue
        if line in NAV_EXACT:
            continue
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return f"=== SECCION: {section.upper()} ===\n" + "\n".join(lines) + "\n"

# ══════════════════════════════════════════════════════════════════════════════
# MOTOR 1: UNDETECTED CHROMEDRIVER (Modo Stealth)
# ══════════════════════════════════════════════════════════════════════════════
def get_stealth_driver():
    options = uc.ChromeOptions()
    options.headless = False 
    options.add_argument("--window-size=1920,1080")
    # Forzamos la versión 147 para que no crashee con tu Chrome local
    driver = uc.Chrome(options=options, version_main=147)
    return driver

def scrape_stealth(driver, url, section):
    try:
        driver.get(url)
        # Esperamos a que cargue algo de texto real
        WebDriverWait(driver, 20).until(
            lambda d: len(d.find_element(By.TAG_NAME, "body").text) > 100
        )
        # Scroll humano (fundamental para cargar contenido dinámico)
        for i in range(1, 4):
            driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * ({i}/4));")
            time.sleep(2)
            
        return extract_text(driver.page_source, section)
    except Exception as e:
        return "ERROR"

# ══════════════════════════════════════════════════════════════════════════════
# MOTOR 2: REQUESTS (Para páginas médicas)
# ══════════════════════════════════════════════════════════════════════════════
def scrape_requests(url, section):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "es-CO,es;q=0.9",
        "Referer": "https://www.google.com/"
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            return extract_text(r.text, section)
        return "ERROR"
    except:
        return "ERROR"

# ══════════════════════════════════════════════════════════════════════════════
# EJECUCIÓN PRINCIPAL (CON MEMORIA Y PACIENCIA NINJA)
# ══════════════════════════════════════════════════════════════════════════════
def run_scraping():
    print("\n" + "═" * 68)
    print("   INICIANDO SCRAPING MODO PACIENCIA (ANTI-BOT) - TQ CONFIABLE")
    print("   Advertencia: Esto tomará tiempo. ¡Déjalo correr tranquilo!")
    print("═" * 68 + "\n")

    results = {}
    
    # 1. CARGAMOS LA MEMORIA
    if os.path.exists("raw_data.json"):
        try:
            with open("raw_data.json", "r", encoding="utf-8") as f:
                results = json.load(f)
            print(f"📦 ¡Memoria cargada! Se encontraron {len(results)} secciones previas.")
        except Exception:
            print("⚠️ Archivo raw_data.json vacío o corrupto. Empezando de cero.")

    # --- FASE 1: SITIO PRINCIPAL (Undetected Chromedriver) ---
    print("\nLevantando navegador fantasma...")
    driver = get_stealth_driver()
    print("¡Navegador listo! No cierres la ventana.\n")

    current = 0
    total = len(URLS_SELENIUM) + len(URLS_REQUESTS)

    for section, url in URLS_SELENIUM.items():
        current += 1
        
        # Saltamos si ya lo tenemos bien descargado
        if section in results and results[section] != "ERROR" and len(results[section]) > 100:
            print(f"[{current:2}/{total}] ⏭️ Saltando: {section} (Ya en memoria)")
            continue

        print(f"[{current:2}/{total}] 🕵️ Extrayendo: {section}...")
        text = scrape_stealth(driver, url, section)
        
        if text != "ERROR" and len(text) > 100:
            results[section] = text
            print(f"      ✅ Éxito ({len(text)} chars)")
            
            # GUARDADO INCREMENTAL INMEDIATO
            with open("raw_data.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                
            # LA PAUSA NINJA: Entre 30 y 45 segundos
            pausa = random.uniform(20, 30)
            print(f"      ⏳ Esperando {int(pausa)} segs para evadir firewall...")
            time.sleep(pausa) 
            
        else:
            print(f"      ❌ Falló o bloqueado. Esperando 2 minutos de castigo...")
            time.sleep(120) # Castigo si sospechan de nosotros

    driver.quit()

    # --- FASE 2: SITIO MÉDICO (Requests) ---
    print("\nPasando a Fase 2: Portal Médico...")
    for section, url in URLS_REQUESTS.items():
        current += 1
        
        if section in results and results[section] != "ERROR" and len(results[section]) > 100:
            print(f"[{current:2}/{total}] ⏭️ Saltando: {section} (Ya en memoria)")
            continue

        print(f"[{current:2}/{total}] ⚡ Extrayendo: {section}...")
        text = scrape_requests(url, section)
        
        if text != "ERROR" and len(text) > 100:
            results[section] = text
            print(f"      ✅ Éxito ({len(text)} chars)")
            
            with open("raw_data.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                
            # Pausa Requests: Entre 30 y 120 segundos
            pausa_req = random.uniform(30, 120)
            print(f"      ⏳ Esperando {int(pausa_req)} segs...")
            time.sleep(pausa_req)
        else:
            print(f"      ❌ Falló. Esperando 60s...")
            time.sleep(60)

    print("\n✅ ¡SCRAPING 100% COMPLETADO! Revisa tu raw_data.json de oro.")

if __name__ == "__main__":
    run_scraping()
