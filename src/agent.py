"""
Agente de Freelance — Motor principal
Busca proyectos en múltiples plataformas, genera propuestas y notifica al usuario.
Plataformas: RemoteOK, PeoplePerHour, Workana
"""

import os
import time
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from anthropic import Anthropic

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/agent.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

FREELANCER_PROFILE = {
    "name": os.environ.get("FREELANCER_NAME", "Sergio"),
    "skills": ["redacción", "copywriting", "traducción", "asistente virtual", "prompts IA"],
    "languages": ["español", "inglés"],
    "experience": "Redactor bilingüe con experiencia en contenido tech, SEO y traducción técnica ES/EN.",
    "availability": "inmediata",
    "hourly_rate_usd": 8,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

seen_ids: set = set()

# ──────────────────────────────────────────────────────
#  SCRAPERS
# ──────────────────────────────────────────────────────

def fetch_remoteok() -> list[dict]:
    """RemoteOK — API pública sin tag para evitar 403, filtramos por keywords."""
    log.info("Buscando en RemoteOK...")
    try:
        resp = requests.get(
            "https://remoteok.com/api",
            headers={**HEADERS, "Accept": "application/json"},
            timeout=20
        )
        resp.raise_for_status()
        data = resp.json()

        keywords = ["writ", "translat", "content", "copy", "redact", "traducc", "editor", "seo", "blog"]
        projects = []
        for job in data[1:]:
            if not isinstance(job, dict):
                continue
            text = (job.get("position", "") + " " + " ".join(job.get("tags", []))).lower()
            if not any(kw in text for kw in keywords):
                continue
            sal_min = job.get("salary_min", "")
            sal_max = job.get("salary_max", "")
            budget = f"${sal_min} - ${sal_max}" if sal_min and sal_max else "Ver en plataforma"
            projects.append({
                "id": str(job.get("id", job.get("slug", ""))),
                "title": job.get("position", "Sin título"),
                "budget": budget,
                "description": BeautifulSoup(job.get("description", ""), "html.parser").get_text()[:300],
                "url": job.get("url", "https://remoteok.com"),
                "platform": "RemoteOK",
                "found_at": datetime.now().isoformat(),
            })
            if len(projects) >= 10:
                break

        log.info(f"RemoteOK: {len(projects)} proyectos relevantes encontrados")
        return projects
    except Exception as e:
        log.error(f"Error en RemoteOK: {e}")
        return []


def fetch_peopleperhour() -> list[dict]:
    """PeoplePerHour — SSR, los jobs vienen en el HTML inicial."""
    log.info("Buscando en PeoplePerHour...")
    try:
        search_terms = ["writing+translation", "content+writing", "copywriting"]
        projects = []
        seen_titles = set()

        for term in search_terms:
            url = f"https://www.peopleperhour.com/freelance-jobs?ref=nav&search={term}"
            resp = requests.get(url, headers=HEADERS, timeout=25)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            job_cards = (
                soup.select("li.jobs-list-item") or
                soup.select("div.job-item") or
                soup.select("[class*='JobCard']") or
                soup.select("[class*='job-listing']") or
                soup.select("article[class*='job']")
            )

            log.info(f"PPH ({term}): {len(job_cards)} cards en HTML")

            for card in job_cards[:8]:
                title_el = (
                    card.select_one("h2 a") or
                    card.select_one("h3 a") or
                    card.select_one("a[href*='/job/']") or
                    card.select_one("[class*='title'] a")
                )
                desc_el = card.select_one("p") or card.select_one("[class*='desc']")

                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                href = title_el.get("href", "")
                job_url = f"https://www.peopleperhour.com{href}" if href.startswith("/") else href or url
                desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

                projects.append({
                    "id": f"pph_{href}",
                    "title": title,
                    "budget": "Ver en plataforma",
                    "description": desc,
                    "url": job_url,
                    "platform": "PeoplePerHour",
                    "found_at": datetime.now().isoformat(),
                })

            time.sleep(1)

        log.info(f"PeoplePerHour: {len(projects)} proyectos encontrados")
        return projects
    except Exception as e:
        log.error(f"Error en PeoplePerHour: {e}")
        return []


def fetch_workana() -> list[dict]:
    """Workana — SSR con selectores verificados en DOM real."""
    if not os.environ.get("WORKANA_ENABLED", "false").lower() == "true":
        return []

    log.info("Buscando en Workana...")
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        session.get("https://www.workana.com", timeout=15)
        time.sleep(1)

        urls = [
            "https://www.workana.com/jobs?category=redaccion-traduccion&language=es",
            "https://www.workana.com/jobs?category=marketing-digital-ventas&language=es",
        ]
        projects = []

        for url in urls:
            resp = session.get(url, timeout=25)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            job_cards = soup.select("div.project-item")
            log.info(f"Workana ({url.split('category=')[-1].split('&')[0]}): {len(job_cards)} cards encontradas")

            for card in job_cards[:12]:
                title_a = card.select_one("h2.project-title a")
                title_h2 = card.select_one("h2.project-title")
                if not title_a and not title_h2:
                    continue

                title = (title_a or title_h2).get_text(strip=True)
                href = title_a.get("href", "") if title_a else ""
                job_url = f"https://www.workana.com{href}" if href.startswith("/") else href

                budget_el = card.select_one("span.values") or card.select_one("div.budget")
                budget = budget_el.get_text(strip=True) if budget_el else "Ver en plataforma"

                desc_el = card.select_one("div.html-desc") or card.select_one("p.text-expander-content")
                desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

                if title:
                    projects.append({
                        "id": f"wk_{href}",
                        "title": title,
                        "budget": budget,
                        "description": desc,
                        "url": job_url,
                        "platform": "Workana",
                        "found_at": datetime.now().isoformat(),
                    })

            time.sleep(2)

        log.info(f"Workana: {len(projects)} proyectos en total")
        return projects
    except Exception as e:
        log.error(f"Error en Workana: {e}")
        return []


def generate_proposal(project: dict) -> str:
    try:
        p = FREELANCER_PROFILE
        prompt = (
            "Eres experto en propuestas freelance para plataformas LATAM. "
            "Escribe una propuesta en español, máximo 130 palabras, directa y sin relleno. "
            "Termina con una pregunta concreta al cliente.\n\n"
            f"PROYECTO en {project['platform']}:\n"
            f"Título: {project['title']}\n"
            f"Presupuesto: {project['budget']}\n"
            f"Descripción: {project['description']}\n\n"
            f"FREELANCER: {p['name']}, skills: {', '.join(p['skills'])}, "
            f"idiomas: {', '.join(p['languages'])}, ${p['hourly_rate_usd']}/hr, disponible ahora.\n\n"
            "Devuelve solo el texto de la propuesta."
        )
        response = client.messages.create(model="claude-sonnet-4-6", max_tokens=350, messages=[{"role": "user", "content": prompt}])
        return response.content[0].text.strip()
    except Exception as e:
        log.error(f"Error generando propuesta: {e}")
        return f"Hola, me interesa este proyecto. Tengo experiencia en {', '.join(FREELANCER_PROFILE['skills'][:2])} y puedo empezar de inmediato. ¿Cuéntame más detalles?"


def send_telegram(message: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}, timeout=10)
        resp.raise_for_status()
        log.info("Telegram: OK")
        return True
    except Exception as e:
        log.error(f"Error Telegram: {e}")
        return False


def format_notification(project: dict, proposal: str) -> str:
    ts = project['found_at'][:16].replace('T', ' ')
    return (
        f"\U0001f195 <b>Nuevo proyecto — {project['platform']}</b>\n\n"
        f"\U0001f4cc <b>{project['title']}</b>\n"
        f"\U0001f4b0 {project['budget']}\n"
        f"\U0001f517 {project['url']}\n\n"
        f"\U0001f4dd <b>Propuesta:</b>\n{proposal}\n\n"
        f"\u23f0 {ts}"
    )


KEYWORDS = [
    "redacción", "redactor", "escritor", "copywriting", "copywriter",
    "traducción", "traductor", "translation", "translator",
    "contenido", "content", "writing", "writer", "writ",
    "artículo", "article", "blog", "seo",
    "asistente virtual", "virtual assistant",
    "español", "spanish", "inglés", "english", "bilingual", "bilingüe",
    "ia", "ai", "prompts", "chatgpt", "inteligencia artificial",
    "corrección", "proofreading", "edición", "editing",
    "transcript", "subtitl", "localiz",
]

def is_relevant(project: dict) -> bool:
    text = (project.get("title", "") + " " + project.get("description", "")).lower()
    return any(kw in text for kw in KEYWORDS)


def run_cycle():
    log.info("=" * 55)
    log.info("Iniciando ciclo de búsqueda...")
    all_projects = []
    all_projects.extend(fetch_remoteok())
    all_projects.extend(fetch_peopleperhour())
    all_projects.extend(fetch_workana())
    log.info(f"Total bruto: {len(all_projects)}")
    new_count = 0
    for project in all_projects:
        pid = project.get("id") or project.get("url", "")
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        if not is_relevant(project):
            log.info(f"Descartado: {project['title'][:55]}")
            continue
        log.info(f"✅ NUEVO [{project['platform']}]: {project['title'][:60]}")
        proposal = generate_proposal(project)
        message = format_notification(project, proposal)
        send_telegram(message)
        new_count += 1
        time.sleep(3)
    log.info(f"Ciclo completado. {new_count} nuevos proyectos notificados.")


def main():
    interval = int(os.environ.get("CHECK_INTERVAL_MINUTES", "5")) * 60
    workana_on = os.environ.get("WORKANA_ENABLED", "").lower() == "true"
    platforms = "RemoteOK + PeoplePerHour" + (" + Workana" if workana_on else "")
    log.info(f"🤖 Agente freelance iniciado. Intervalo: {interval // 60} min | {platforms}")
    send_telegram(f"🤖 <b>Agente iniciado</b>\nPlataformas: {platforms}\nIntervalo: cada {interval // 60} minutos.")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Error inesperado: {e}")
        log.info(f"Esperando {interval // 60} min...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
