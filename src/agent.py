"""
Agente de Freelance — Motor principal
Busca proyectos en múltiples plataformas, genera propuestas y notifica al usuario.
Plataformas: RemoteOK, PeoplePerHour, Workana
"""

import os
import json
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

# ─────────────────────────────────────────────
#  PERFIL DEL FREELANCER
# ─────────────────────────────────────────────

FREELANCER_PROFILE = {
    "name": os.environ.get("FREELANCER_NAME", "Tu Nombre"),
    "skills": ["redacción", "copywriting", "traducción", "asistente virtual", "diseño de prompts IA"],
    "languages": ["español", "inglés"],
    "experience": "Redactor con experiencia en contenido tech, SEO y traducción técnica ES/EN.",
    "availability": "inmediata",
    "hourly_rate_usd": 8,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

seen_ids: set = set()

# ─────────────────────────────────────────────
#  SCRAPERS
# ─────────────────────────────────────────────

def fetch_remoteok() -> list[dict]:
    log.info("Buscando en RemoteOK...")
    try:
        resp = requests.get("https://remoteok.com/api?tag=writing", headers={**HEADERS, "Accept": "application/json"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        projects = []
        for job in data[1:11]:
            if not isinstance(job, dict):
                continue
            projects.append({
                "id": str(job.get("id", "")),
                "title": job.get("position", "Sin título"),
                "budget": job.get("salary", "No especificado"),
                "description": job.get("description", "")[:300],
                "url": job.get("url", "https://remoteok.com"),
                "platform": "RemoteOK",
                "found_at": datetime.now().isoformat(),
            })
        log.info(f"RemoteOK: {len(projects)} proyectos encontrados")
        return projects
    except Exception as e:
        log.error(f"Error en RemoteOK: {e}")
        return []


def fetch_peopleperhour() -> list[dict]:
    log.info("Buscando en PeoplePerHour...")
    try:
        urls = [
            "https://www.peopleperhour.com/freelance-jobs?ref=nav&search=writing",
            "https://www.peopleperhour.com/freelance-jobs?ref=nav&search=translation",
        ]
        projects = []
        for url in urls:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            job_cards = (
                soup.select("li.jobs-list-item") or
                soup.select("div[class*='jobCard']") or
                soup.select("article[class*='job']") or
                soup.select(".jobitem") or
                soup.select("[data-job-id]")
            )
            for card in job_cards[:8]:
                title_el = card.select_one("h2") or card.select_one("h3") or card.select_one("[class*='title']") or card.select_one("a[href*='/job/']")
                link_el = card.select_one("a[href*='/job/']") or card.select_one("a")
                desc_el = card.select_one("p") or card.select_one("[class*='desc']")
                title = title_el.get_text(strip=True) if title_el else "Sin título"
                href = link_el.get("href", "") if link_el else ""
                job_url = f"https://www.peopleperhour.com{href}" if href.startswith("/") else href or url
                desc = desc_el.get_text(strip=True)[:300] if desc_el else ""
                if title and title != "Sin título":
                    projects.append({"id": f"pph_{job_url}", "title": title, "budget": "Ver en plataforma", "description": desc, "url": job_url, "platform": "PeoplePerHour", "found_at": datetime.now().isoformat()})
        log.info(f"PeoplePerHour: {len(projects)} proyectos encontrados")
        return projects
    except Exception as e:
        log.error(f"Error en PeoplePerHour: {e}")
        return []


def fetch_workana() -> list[dict]:
    if not os.environ.get("WORKANA_ENABLED", "false").lower() == "true":
        return []
    log.info("Buscando en Workana...")
    try:
        urls = [
            "https://www.workana.com/jobs?category=redaccion-traduccion&language=es",
            "https://www.workana.com/jobs?category=redaccion-traduccion&language=es&page=2",
        ]
        projects = []
        session = requests.Session()
        session.headers.update(HEADERS)
        for url in urls:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            job_cards = (
                soup.select("div.project-item") or
                soup.select("article.project") or
                soup.select("[class*='project-item']") or
                soup.select("div.job-list-item") or
                soup.select("li[class*='project']")
            )
            log.info(f"Workana ({url}): {len(job_cards)} cards en HTML")
            for card in job_cards[:10]:
                title_el = card.select_one("h2 a") or card.select_one("h3 a") or card.select_one(".project-title a") or card.select_one("a[class*='title']") or card.select_one("a[href*='/job/']")
                budget_el = card.select_one(".project-price") or card.select_one("[class*='budget']") or card.select_one("[class*='price']")
                desc_el = card.select_one(".project-description") or card.select_one("[class*='description']") or card.select_one("p")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                job_url = f"https://www.workana.com{href}" if href.startswith("/") else href
                budget = budget_el.get_text(strip=True) if budget_el else "Ver en plataforma"
                desc = desc_el.get_text(strip=True)[:300] if desc_el else ""
                if title:
                    projects.append({"id": f"wk_{job_url}", "title": title, "budget": budget, "description": desc, "url": job_url, "platform": "Workana", "found_at": datetime.now().isoformat()})
            time.sleep(2)
        log.info(f"Workana: {len(projects)} proyectos en total")
        return projects
    except Exception as e:
        log.error(f"Error en Workana: {e}")
        return []


# ─────────────────────────────────────────────
#  PROPUESTAS + NOTIFICACIONES
# ─────────────────────────────────────────────

def generate_proposal(project: dict) -> str:
    try:
        p = FREELANCER_PROFILE
        prompt = (
            f"Eres experto en propuestas freelance. Escribe una propuesta en español, "
            f"máximo 150 palabras, directa y sin relleno genérico, para este proyecto en {project['platform']}:\n\n"
            f"Título: {project['title']}\nPresupuesto: {project['budget']}\nDescripción: {project['description']}\n\n"
            f"El freelancer es {p['name']}, con skills en {', '.join(p['skills'])}, "
            f"habla {', '.join(p['languages'])}, tarifa undefined/hr, disponibilidad inmediata.\n\n"
            f"Solo devuelve el texto de la propuesta."
        )
        response = client.messages.create(model="claude-sonnet-4-6", max_tokens=400, messages=[{"role": "user", "content": prompt}])
        return response.content[0].text.strip()
    except Exception as e:
        log.error(f"Error generando propuesta: {e}")
        return f"Hola, me interesa este proyecto. Tengo experiencia en {', '.join(FREELANCER_PROFILE['skills'][:2])} y puedo empezar de inmediato. ¿Podemos hablar?"


def send_telegram(message: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("Telegram no configurado")
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
    return (
        f"U0001f195 <b>Nuevo proyecto en {project['platform']}</b>\n\n"
        f"U0001f4cc <b>{project['title']}</b>\n"
        f"U0001f4b0 {project['budget']}\n"
        f"U0001f517 {project['url']}\n\n"
        f"U0001f4dd <b>Propuesta sugerida:</b>\n"
        f"{proposal}\n\n"
        f"⏰ {project['found_at'][:16].replace('T', ' ')}"
    )


KEYWORDS_RELEVANTES = [
    "redacción", "redactor", "escritor", "copywriting", "copywriter",
    "traducción", "traductor", "translation", "translator",
    "contenido", "content", "writing", "writer",
    "artículo", "article", "blog", "seo",
    "asistente virtual", "virtual assistant", "español", "spanish",
    "inglés", "english", "bilingual", "bilingüe",
    "ia", "ai", "prompts", "chatgpt",
    "corrección", "proofreading", "edición", "editing",
]

def is_relevant(project: dict) -> bool:
    text = (project.get("title", "") + " " + project.get("description", "")).lower()
    return any(kw in text for kw in KEYWORDS_RELEVANTES)


# ─────────────────────────────────────────────
#  LOOP PRINCIPAL
# ─────────────────────────────────────────────

def run_cycle():
    log.info("=" * 50)
    log.info("Iniciando ciclo...")
    all_projects = []
    all_projects.extend(fetch_remoteok())
    all_projects.extend(fetch_peopleperhour())
    all_projects.extend(fetch_workana())
    log.info(f"Total encontrados: {len(all_projects)}")
    new_count = 0
    for project in all_projects:
        pid = project.get("id") or project.get("url", "")
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        if not is_relevant(project):
            log.info(f"Descartado: {project['title'][:50]}")
            continue
        log.info(f"✅ Nuevo [{project['platform']}]: {project['title'][:60]}")
        proposal = generate_proposal(project)
        message = format_notification(project, proposal)
        send_telegram(message)
        new_count += 1
        time.sleep(2)
    log.info(f"Ciclo completado. {new_count} nuevos notificados.")


def main():
    interval = int(os.environ.get("CHECK_INTERVAL_MINUTES", "5")) * 60
    workana_on = os.environ.get("WORKANA_ENABLED", "").lower() == "true"
    platforms = "RemoteOK, PeoplePerHour" + (", Workana" if workana_on else "")
    log.info(f"U0001f916 Agente iniciado. Intervalo: {interval // 60} min. Plataformas: {platforms}")
    send_telegram(f"U0001f916 <b>Agente freelance iniciado</b>\nBuscando cada {interval // 60} min en {platforms}.")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Error en ciclo: {e}")
        log.info(f"Esperando {interval // 60} min...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
