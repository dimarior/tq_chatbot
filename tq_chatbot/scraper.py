"""
scraper.py
Web scraping COMPLETO de Tecnoquimicas - Solo fuentes oficiales
Fuentes oficiales:
  1. www.tqconfiable.com  (sitio principal - sitemap completo)
  2. www.tqfarma.com      (portal medico oficial de TQ)
Motor: Selenium + Chrome headless + requests + BeautifulSoup
Ejecutar: python scraper.py
"""

import json
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ══════════════════════════════════════════════════════════════════════════════
# FUENTE 1: tqconfiable.com — sitio oficial principal (requiere Selenium)
# ══════════════════════════════════════════════════════════════════════════════
URLS_SELENIUM = {
    # QUIENES SOMOS
    "quien_es_tq":   "http://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/quien-es-tq/",
    "mision":        "http://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/mision/",
    "vision":        "http://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/vision/",
    "credo":         "http://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/credo/",
    "historia":      "http://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/historia/",
    "proposito":     "http://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/nuestro-prop%C3%B3sito/",
    # MUNDO
    "planeta":       "http://www.tqconfiable.com/asi-cambiamos-al-mundo/mundo/planeta/",
    "gente":         "http://www.tqconfiable.com/asi-cambiamos-al-mundo/mundo/gente/",
    # INNOVACION
    "innovacion":    "http://www.tqconfiable.com/asi-cambiamos-al-mundo/innovacion/",
    "investigacion": "http://www.tqconfiable.com/asi-cambiamos-al-mundo/innovacion/investigaci%C3%B3n/",
    # TRABAJA
    "ofertas":       "http://www.tqconfiable.com/trabaja/ofertas/",
    "beneficios":    "http://www.tqconfiable.com/trabaja/beneficios/",
    "testimonios":   "http://www.tqconfiable.com/trabaja/testimonios/",
    # CONTACTO
    "encuentranos":  "http://www.tqconfiable.com/contacto/encuentranos/",
    "servicio":      "http://www.tqconfiable.com/contacto/servicio-al-cliente/",
    "faq":           "http://www.tqconfiable.com/contacto/preguntas-frecuentes/",
    "linea_etica":   "http://www.tqconfiable.com/contacto/linea-etica/",
    # GOBIERNO
    "gobierno":      "http://www.tqconfiable.com/gobierno-corporativo/",
    # NOTICIAS
    "noticias":                  "http://www.tqconfiable.com/noticias/",
    "noticia_alcohol_gel":       "http://www.tqconfiable.com/noticias/tq-lanza-su-alcohol-gel-mk-al-70/",
    "noticia_multilatinas":      "http://www.tqconfiable.com/noticias/tq-una-de-las-100-multilatinas/",
    "noticia_lactancia":         "http://www.tqconfiable.com/noticias/programa-de-lactancia-materna-y-plan-canguro/",
    "noticia_500empresas":       "http://www.tqconfiable.com/noticias/tq-una-de-las-500-empresas-mas-exitosas-del-valle/",
    "noticia_historia_medicina": "http://www.tqconfiable.com/noticias/tomo-iii-historia-de-la-medicina-en-colombia/",
    "noticia_winny_marca":       "http://www.tqconfiable.com/noticias/winny-una-de-las-20-marcas-colombianas-mas-valiosas/",
    "noticia_copidrogas":        "http://www.tqconfiable.com/noticias/copidrogas-exalto-a-tq/",
    "noticia_educacion":         "http://www.tqconfiable.com/noticias/en-tq-tambien-le-aportamos-al-bienestar-de-nuestra-gente-con-programas-de-educacion/",
    "noticia_canguro":           "http://www.tqconfiable.com/noticias/tq-comprometida-con-el-programa-contacto-canguro-de-la-fundacion-valle-del-lili/",
    "noticia_ecuador":           "http://www.tqconfiable.com/noticias/tq-se-solidariza-con-ecuador-y-sus-colaboradores-en-el-vecino-pais/",
    "noticia_asocoldro":         "http://www.tqconfiable.com/noticias/asocoldro-distinguio-al-doctor-francisco-jose-barberi-por-sus-aportes-a-los-droguistas-colombianos/",
    "noticia_asinfar":           "http://www.tqconfiable.com/noticias/asinfar-una-historia-de-importantes-logros-a-favor-de-la-salud-en-colombia/",
    "noticia_ced_graduacion":    "http://www.tqconfiable.com/noticias/rodeados-de-amor-12-ni%C3%B1os-del-ced-tq-recibieron-diplomas-y-medallas-de-graduacion/",
    "noticia_codigo_etica":      "http://www.tqconfiable.com/noticias/las-empresas-farmaceuticas-afiliadas-a-la-andi-suscribieron-su-codigo-de-etica-y-transparencia/",
    "noticia_andi_barberi":      "http://www.tqconfiable.com/noticias/la-andi-seccional-valle-exalto-la-trayectoria-de-francisco-jose-barberi-presidente-de-tq/",
    "noticia_auditorio":         "http://www.tqconfiable.com/noticias/auditorio-lucero-ospina-de-barberi-un-nuevo-espacio-para-el-crecimiento-integral-de-nuestra-familia-tq/",
    "noticia_winny_prematuros":  "http://www.tqconfiable.com/noticias/winny-dona-pa%C3%B1ales-para-los-bebes-prematuros-de-colombia/",
    "noticia_colbon":            "http://www.tqconfiable.com/noticias/colbon-incursiona-con-productos-innovadores-en-el-mercado-de-la-construccion/",
    "noticia_educando":          "http://www.tqconfiable.com/noticias/educando-para-la-vida/",
    "noticia_vive_tq":           "http://www.tqconfiable.com/noticias/vive-tq-un-programa-creado-para-fortalecer-la-relacion-con-los-universitarios/",
    "noticia_reputacion":        "http://www.tqconfiable.com/noticias/tq-la-compa%C3%B1ia-colombiana-con-mayor-reputacion-en-la-industria-farmaceutica-del-pais/",
    "noticia_cruz_roja":         "http://www.tqconfiable.com/noticias/reconocimiento-de-la-cruz-roja-a-tecnoquimicas-del-ecuador/",
    "noticia_proveedor_lider":   "http://www.tqconfiable.com/noticias/tq-es-el-proveedor-lider-en-colaboracion-y-logistica-para-los-comerciantes-del-sector-salud-en-colombia/",
    "noticia_estudio_salutia":   "http://www.tqconfiable.com/noticias/estudio-cientifico-realizado-por-tq-y-la-fundacion-salutia-fue-destacado-en-prestigiosa-publicacion-internacional/",
    "noticia_dermatologicos":    "http://www.tqconfiable.com/noticias/con-nuevos-estudios-cientificos-sobre-productos-dermatologicos-tq-sigue-contribuyendo-al-bienestar-de-los-colombianos/",
    "noticia_cultura":           "http://www.tqconfiable.com/noticias/en-tq-las-actividades-culturales-promueven-el-desarrollo-integral-de-nuestros-colaboradores/",
    "noticia_valle_lili":        "http://www.tqconfiable.com/noticias/con-el-apoyo-de-tq-se-inauguro-nueva-sala-para-el-bienestar-de-ni%C3%B1os-y-jovenes-en-la-fundacion-clinica-valle-del-lili/",
    "noticia_winny_innovador":   "http://www.tqconfiable.com/noticias/tq-y-su-marca-winny-ofrecen-un-producto-innovador-para-garantizar-la-proteccion-y-comodidad-para-nuestros-bebes/",
    "noticia_compromiso":        "http://www.tqconfiable.com/noticias/tecnoquimicas-reafirma-su-compromiso-con-el-desarrollo/",
    "noticia_tq_agro":           "http://www.tqconfiable.com/noticias/tq-agro-fortalece-su-novedosa-l%C3%ADnea-de-productos-amigables-con-el-medio-ambiente/",
    "noticia_vacunacion":        "http://www.tqconfiable.com/noticias/en-tq-celebramos-ser-parte-de-las-primeras-empresas-privadas-en-vacunar-a-sus-empleados-contra-el-covid-19/",
    "noticia_orden_merito":      "http://www.tqconfiable.com/noticias/nos-mueve-el-compromiso-con-colombia-y-su-gente-francisco-jos%C3%A9-barberi-al-recibir-la-orden-al-m%C3%A9rito-empresarial-de-la-andi/",
    "noticia_cancer_colon":      "http://www.tqconfiable.com/noticias/campana-cancer-colon/",
    "noticia_educacion_calidad": "http://www.tqconfiable.com/noticias/educacion-alta-calidad-transformacion-social/",
    "noticia_grupo_innovacion":  "http://www.tqconfiable.com/noticias/grupo-tq-innovacion-investigacion-salud-bienestar/",
    "noticia_comunidad":         "http://www.tqconfiable.com/noticias/grupo-tq-compromiso-comunidad-salud-bienestar-titanes-caracol/",
    "noticia_content":           "http://www.tqconfiable.com/noticias/content-un-compromiso-con-el-cuidado-y-el-bienestar-del-adulto/",
}

# ══════════════════════════════════════════════════════════════════════════════
# FUENTE 2: tqfarma.com — portal medico oficial (accesible con requests)
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

# ══════════════════════════════════════════════════════════════════════════════
# TERMINOS DE NAVEGACION A ELIMINAR
# ══════════════════════════════════════════════════════════════════════════════
NAV_EXACT = {
    "Síguenos", "LinkedIn", "Instagram", "Facebook", "Youtube", "Twitter",
    "Colaborador TQ", "Portal Médicos", "Gobierno Corporativo", "Pagos Clientes",
    "Así Cambiamos El Mundo", "Trabaja con Nosotros", "Nuestras Marcas",
    "Términos y condiciones", "Políticas de privacidad",
    "Todos los derechos reservados", "MK", "Winny", "Gastrofast",
    "Duraflex", "Ibuflash", "Yodora", "Portales de nuestras marcas",
    "Sal de Frutas Lua", "Quiénes somos", "Por un mundo mejor",
    "Investigación e Innovación", "Nuestro propósito", "Misión",
    "Visión", "Credo", "Historia", "Nuestro planeta", "Nuestra gente",
    "Ofertas de trabajo", "Beneficios TQ", "Testimonios",
    "Servicio al cliente", "Preguntas frecuentes", "Línea ética",
    "Encuéntranos", "Noticias", "Contacto", "Inicio",
    "Trabaja con nosotros", "Investigación", "INICIAR SESIÓN",
    "REGISTRARSE", "Vademécum", "Biblioteca científica",
    "Medicamentos A-Z", "Inicio Biblioteca", "Acceso a Journals",
    "VER TODAS", "ACCEDER",
}


# ══════════════════════════════════════════════════════════════════════════════
# MOTOR 1: SELENIUM
# ══════════════════════════════════════════════════════════════════════════════
def get_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def extract_text(html: str, section: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "img", "svg",
                     "button", "input", "select", "iframe", "form",
                     "header", "footer", "nav"]):
        tag.decompose()
    body = soup.find("body") or soup
    raw = body.get_text(separator="\n")
    lines = []
    seen = set()
    for line in raw.splitlines():
        line = line.strip()
        if len(line) < 5:
            continue
        if line in NAV_EXACT:
            continue
        if re.match(r"^©", line):
            continue
        if re.match(r"^https?://", line):
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return f"=== SECCION: {section.upper()} ===\n" + "\n".join(lines) + "\n"


def scrape_selenium(driver: webdriver.Chrome, url: str, section: str) -> str:
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            lambda d: len(d.find_element(By.TAG_NAME, "body").text) > 200
        )
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(0.8)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.8)
        return extract_text(driver.page_source, section)
    except Exception as e:
        return f"=== SECCION: {section.upper()} ===\nNo disponible: {e}\n"


# ══════════════════════════════════════════════════════════════════════════════
# MOTOR 2: REQUESTS
# ══════════════════════════════════════════════════════════════════════════════
def scrape_requests(url: str, section: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "es-CO,es;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return extract_text(r.text, section)
        return f"=== SECCION: {section.upper()} ===\nHTTP {r.status_code}\n"
    except Exception as e:
        return f"=== SECCION: {section.upper()} ===\nError: {e}\n"


# ══════════════════════════════════════════════════════════════════════════════
# REPORTE
# ══════════════════════════════════════════════════════════════════════════════
def print_banner(total: int):
    print("\n" + "═" * 68)
    print("   WEB SCRAPING COMPLETO - TQ CONFIABLE (Tecnoquimicas)")
    print("   ─────────────────────────────────────────────────────")
    print("   Fuente 1: www.tqconfiable.com  (sitio principal oficial)")
    print("   Fuente 2: www.tqfarma.com      (portal medico oficial TQ)")
    print("   Motor:    Selenium + Chrome + requests + BeautifulSoup")
    print(f"   URLs:     {total} paginas a procesar")
    print(f"   Inicio:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 68 + "\n")


def print_progress(current: int, total: int, section: str, chars: int, status: str):
    pct = (current / total) * 100
    filled = int(30 * current / total)
    bar = "█" * filled + "░" * (30 - filled)
    icon = "✅" if status == "EXITOSO" else "⚠️" if status == "PARCIAL" else "❌"
    print(f"  [{bar}] {pct:5.1f}%  ({current:2}/{total})")
    print(f"  {icon} {section:<40} {chars:>8,} chars  [{status}]")
    print()


def print_final_report(results: dict, exitosas: int, parciales: int,
                       fallidas: int, total: int, start_time: datetime):
    total_chars = sum(len(v) for v in results.values())
    elapsed = (datetime.now() - start_time).seconds

    print("═" * 68)
    print("  SCRAPING COMPLETADO - REPORTE FINAL")
    print("═" * 68)
    print(f"  Fin:           {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Tiempo total:  {elapsed // 60}m {elapsed % 60}s")
    print(f"  URLs totales:  {total}")
    print(f"  ✅ Exitosas:   {exitosas}")
    print(f"  ⚠️  Parciales:  {parciales}")
    print(f"  ❌ Fallidas:   {fallidas}")
    print(f"  Total chars:   {total_chars:,}")
    print(f"  Archivo:       raw_data.json")
    print()

    cats = {
        "tqconfiable.com - Quienes Somos": ["quien_es_tq","mision","vision","credo","historia","proposito"],
        "tqconfiable.com - Mundo":         ["planeta","gente"],
        "tqconfiable.com - Innovacion":    ["innovacion","investigacion"],
        "tqconfiable.com - Trabaja":       ["ofertas","beneficios","testimonios"],
        "tqconfiable.com - Contacto":      ["encuentranos","servicio","faq","linea_etica"],
        "tqconfiable.com - Gobierno":      ["gobierno"],
        "tqconfiable.com - Noticias":      [k for k in results if k.startswith("noticia")],
        "tqfarma.com - Portal Medico":     [k for k in results if k.startswith("tqfarma")],
    }
    print("  Distribucion por seccion y fuente:")
    for cat, keys in cats.items():
        cc = sum(len(results.get(k, "")) for k in keys)
        ok = sum(1 for k in keys if len(results.get(k, "")) > 500)
        print(f"    {cat:<42} {ok:2}/{len(keys):2} | {cc:>10,} chars")
    print("═" * 68 + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# EJECUCION PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
def run_scraping() -> dict:
    total = len(URLS_SELENIUM) + len(URLS_REQUESTS)
    print_banner(total)

    results = {}
    exitosas = parciales = fallidas = 0
    current = 0
    start_time = datetime.now()

    # ── FASE 1: Selenium — tqconfiable.com ────────────────────────────────────
    print("  FASE 1/2 — tqconfiable.com (Selenium + Chrome headless)")
    print("  " + "─" * 55)
    driver = get_driver()
    print("  Chrome headless listo\n")

    for section, url in URLS_SELENIUM.items():
        current += 1
        print(f"  [{current:2}/{total}] {url}")
        text = scrape_selenium(driver, url, section)
        chars = len(text)
        results[section] = text
        if chars > 500:
            status = "EXITOSO"; exitosas += 1
        elif chars > 150:
            status = "PARCIAL"; parciales += 1
        else:
            status = "SIN CONTENIDO"; fallidas += 1
        print_progress(current, total, section, chars, status)
        time.sleep(1)

    driver.quit()
    print("  Chrome cerrado\n")

    # ── FASE 2: Requests — tqfarma.com ────────────────────────────────────────
    print("  FASE 2/2 — tqfarma.com (requests + BeautifulSoup)")
    print("  " + "─" * 55)

    for section, url in URLS_REQUESTS.items():
        current += 1
        print(f"  [{current:2}/{total}] {url}")
        text = scrape_requests(url, section)
        chars = len(text)
        results[section] = text
        if chars > 500:
            status = "EXITOSO"; exitosas += 1
        elif chars > 150:
            status = "PARCIAL"; parciales += 1
        else:
            status = "SIN CONTENIDO"; fallidas += 1
        print_progress(current, total, section, chars, status)
        time.sleep(1)

    # ── Guardar ───────────────────────────────────────────────────────────────
    with open("raw_data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print_final_report(results, exitosas, parciales, fallidas, total, start_time)
    return results


if __name__ == "__main__":
    run_scraping()
