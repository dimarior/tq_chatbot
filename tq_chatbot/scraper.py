"""
scraper.py
Web scraping REAL de tqconfiable.com usando Selenium + Chrome.
El sitio carga contenido con JavaScript, por eso se requiere Selenium.
Ejecutar: python scraper.py
"""

import json
import re
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ── URLs reales verificadas de tqconfiable.com ────────────────────────────────
URLS = {
    "quienes_somos": "https://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/quien-es-tq/",
    "historia":      "https://www.tqconfiable.com/asi-cambiamos-al-mundo/quienes-somos/historia/",
    "innovacion":    "https://www.tqconfiable.com/asi-cambiamos-al-mundo/innovacion/",
    "planeta":       "https://www.tqconfiable.com/asi-cambiamos-al-mundo/mundo/planeta/",
    "beneficios":    "https://www.tqconfiable.com/trabaja/beneficios/",
    "noticias":      "https://www.tqconfiable.com/noticias/",
    "marcas":        "https://www.tqconfiable.com/productos-tq/",
    "contacto":      "https://www.tqconfiable.com/contacto/encuentranos/",
    "servicio":      "https://www.tqconfiable.com/contacto/servicio-al-cliente/",
    "faq":           "https://www.tqconfiable.com/contacto/preguntas-frecuentes/",
    "trabaja":       "https://www.tqconfiable.com/trabaja/ofertas/",
    "linea_etica":   "https://www.tqconfiable.com/contacto/linea-etica/",
}

# Texto de navegación que aparece igual en TODAS las páginas (header/footer)
NAV_EXACT = {
    "Síguenos", "LinkedIn", "Instagram", "Facebook", "Youtube", "Twitter",
    "Colaborador TQ", "Portal Médicos", "Gobierno Corporativo", "Pagos Clientes",
    "Así Cambiamos El Mundo", "Trabaja con Nosotros", "Nuestras Marcas",
    "Términos y condiciones", "Políticas de privacidad",
    "Todos los derechos reservados",
    "MK", "Winny", "Gastrofast", "Duraflex", "Ibuflash", "Yodora",
    "Portales de nuestras marcas", "Sal de Frutas Lua",
    "¿Quiénes somos?", "Por un mundo mejor", "Investigación e Innovación",
    "Nuestro propósito", "Misión", "Visión", "Credo", "Historia",
    "Nuestro planeta", "Nuestra gente",
    "Ofertas de trabajo", "Beneficios TQ", "Testimonios",
    "Servicio al cliente", "Preguntas frecuentes", "Línea ética",
    "Encuéntranos", "Noticias", "Contacto", "Inicio",
    "Trabaja con nosotros",
}


def get_driver() -> webdriver.Chrome:
    """Inicializa Chrome en modo headless (sin ventana visible)."""
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
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def extract_text(html: str, section: str) -> str:
    """Extrae y limpia el texto de contenido real, eliminando navegación."""
    soup = BeautifulSoup(html, "html.parser")

    # Eliminar etiquetas sin contenido útil
    for tag in soup(["script", "style", "noscript", "img", "svg",
                     "button", "input", "select", "iframe", "form",
                     "header", "footer", "nav"]):
        tag.decompose()

    # Extraer todo el texto del body
    body = soup.find("body") or soup
    raw = body.get_text(separator="\n")

    lines = []
    seen = set()
    for line in raw.splitlines():
        line = line.strip()

        if len(line) < 4:
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

    content = "\n".join(lines)
    return f"=== SECCIÓN: {section.upper()} ===\n{content}\n"


def scrape_page(driver: webdriver.Chrome, url: str, section: str) -> str:
    """Abre una página con Selenium, espera que cargue y extrae el texto."""
    try:
        driver.get(url)
        # Esperar hasta que el body tenga contenido real (más de 500 chars)
        WebDriverWait(driver, 15).until(
            lambda d: len(d.find_element(By.TAG_NAME, "body").text) > 500
        )
        # Esperar adicional para contenido JS dinámico
        time.sleep(3)

        # Scroll para activar lazy-loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)

        html = driver.page_source
        return extract_text(html, section)

    except Exception as e:
        print(f"      Error en {url}: {e}")
        return f"=== SECCIÓN: {section.upper()} ===\nContenido no disponible.\n"


def run_scraping() -> dict:
    print("=" * 60)
    print("  WEB SCRAPING - TQ CONFIABLE (Tecnoquímicas)")
    print("  Motor: Selenium + Chrome (JavaScript renderizado)")
    print("  Fuente: www.tqconfiable.com")
    print("=" * 60)

    print("\n Iniciando navegador Chrome...")
    driver = get_driver()
    print(" Chrome listo\n")

    results = {}
    exitosas = 0

    for section, url in URLS.items():
        print(f" [{section}]")
        print(f"   {url}")
        text = scrape_page(driver, url, section)
        char_count = len(text)
        results[section] = text

        if char_count > 500:
            print(f"    {char_count:,} caracteres extraídos")
            exitosas += 1
        elif char_count > 100:
            print(f"     {char_count:,} caracteres (contenido parcial)")
            exitosas += 1
        else:
            print(f"    {char_count} caracteres (sin contenido útil)")

        print()
        time.sleep(1.5)

    driver.quit()
    print(" Navegador cerrado")

    with open("raw_data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f" Scraping completado: {exitosas}/{len(URLS)} páginas con contenido")
    print(f" Guardado en: raw_data.json")
    print(f"{'='*60}")
    return results


if __name__ == "__main__":
    run_scraping()