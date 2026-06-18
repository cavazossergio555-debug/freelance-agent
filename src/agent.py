"""
Agente de Freelance — Motor principal
Busca proyectos en múltiples plataformas vía APIs públicas (sin scraping HTML).
Fuentes: RemoteOK, Remotive, Jobicy — todas con API JSON oficial, sin bloqueo de datacenter.
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
    "Accept": "application/json",
}

seen_ids: set = set()

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


def fetch_remoteok() -> list[dict]:
    """RemoteOK API pública. Reintenta ante timeout (común en su servidor)."""
    log.info("Buscando en RemoteOK...")
    for attempt in range(2):
        try:
            resp = requests.get(
                "https://remoteok.com/api",
                headers=HEADERS,
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            kws = ["writ", "translat", "content", "copy", "redact", "editor", "seo", "blog"]
            projects = []
            for job in data[1:]:
                if not isinstance(job, dict):
                    continue
                text = (job.get("position", "") + " " + " ".join(job.get("tags", []))).lower()
                if not any(kw in text for kw in kws):
                    continue
                sal_min = job.get("salary_min", "")
                sal_max = job.get("salary_max", "")
                budget = f"${sal_min} - ${sal_max}" if sal_min and sal_max else "Ver en plataforma"
                projects.append({
                    "id": "rok_" + str(job.get("id", job.get("slug", ""))),
                    "title": job.get("position", "Sin título"),
                    "budget": budget,
                    "description": BeautifulSoup(job.get("description", ""), "html.parser").get_text()[:300],
                    "url": job.get("url", "https://remoteok.com"),
                    "platform": "RemoteOK",
                    "found_at": datetime.now().isoformat(),
                })
                if len(projects) >= 10:
                    break

            log.info(f"RemoteOK: {len(projects)} proyectos relevantes")
            return projects
        except requests.exceptions.Timeout:
            log.warning(f"RemoteOK timeout (intento {attempt + 1}/2)")
            time.sleep(3)
        except Exception as e:
            log.error(f"Error en RemoteOK: {e}")
            return []
    log.error("RemoteOK: falló tras reintentos")
    return []


def fetch_remotive() -> list[dict]:
    """Remotive — API pública oficial, sin auth, categoría 'writing' incluida."""
    log.info("Buscando en Remotive...")
    try:
        projects = []
        seen_local = set()

        # Categoría writing + búsqueda por keyword como respaldo
        urls = [
            "https://remotive.com/api/remote-jobs?category=writing",
            "https://remotive.com/api/remote-jobs?search=translation",
            "https://remotive.com/api/remote-jobs?search=copywriting",
        ]

        for url in urls:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs", [])
            log.info(f"Remotive ({url.split('?')[-1]}): {len(jobs)} resultados")

            for job in jobs[:8]:
                jid = "rmt_" + str(job.get("id", ""))
                if jid in seen_local:
                    continue
                seen_local.add(jid)

                desc_raw = job.get("description", "")
                desc = BeautifulSoup(desc_raw, "html.parser").get_text()[:300] if desc_raw else ""

                sal = job.get("salary", "") or "Ver en plataforma"

                projects.append({
                    "id": jid,
                    "title": job.get("title", "Sin título"),
                    "budget": sal,
                    "description": desc,
                    "url": job.get("url", "https://remotive.com"),
                    "platform": "Remotive",
                    "found_at": datetime.now().isoformat(),
                })

            time.sleep(1)

        log.info(f"Remotive: {len(projects)} proyectos en total")
        return projects
    except Exception as e:
        log.error(f"Error en Remotive: {e}")
        return []


def fetch_jobicy() -> list[dict]:
    """Jobicy — API pública oficial, sin auth, soporta tag de búsqueda libre."""
    log.info("Buscando en Jobicy...")
    try:
        projects = []
        seen_local = set()

        tags = ["copywriting", "writing", "translation", "content"]

        for tag in tags:
            url = f"https://jobicy.com/api/v2/remote-jobs?count=10&tag={tag}"
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs", [])
            log.info(f"Jobicy (tag={tag}): {len(jobs)} resultados")

            for job in jobs:
                jid = "job_" + str(job.get("id", ""))
                if jid in seen_local:
                    continue
                seen_local.add(jid)

                desc_raw = job.get("jobExcerpt", "") or job.get("jobDescription", "")
                desc = BeautifulSoup(desc_raw, "html.parser").get_text()[:300] if desc_raw else ""

                sal_min = job.get("salaryMin", "")
                sal_max = job.get("salaryMax", "")
                budget = f"${sal_min} - ${sal_max}" if sal_min and sal_max else "Ver en plataforma"

                projects.append({
                    "id": jid,
                    "title": job.get("jobTitle", "Sin título"),
                    "budget": budget,
                    "description": desc,
                    "url": job.get("url", "https://jobicy.com"),
                    "platform": "Jobicy",
                    "found_at": datetime.now().isoformat(),
                })

            time.sleep(1)

        log.info(f"Jobicy: {len(projects)} proyectos en total")
        return projects
    except Exception as e:
        log.error(f"Error en Jobicy: {e}")
        return []


def generate_proposal(project: dict) -> str:
    try:
        p = FREELANCER_PROFILE
        prompt = (
            "Eres experto en propuestas freelance. "
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
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        log.error(f"Error generando propuesta: {e}")
        return f"Hola, me interesa este proyecto. Tengo experiencia en {', '.join(FREELANCER_PROFILE['skills'][:2])} y puedo empezar de inmediato. ¿Cuéntame más detalles?"


def send_telegram(message: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("Telegram no configurado")
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }, timeout=10)
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


def is_relevant(project: dict) -> bool:
    text = (project.get("title", "") + " " + project.get("description", "")).lower()
    return any(kw in text for kw in KEYWORDS)


def run_cycle():
    log.info("=" * 55)
    log.info("Iniciando ciclo de búsqueda...")

    all_projects = []
    all_projects.extend(fetch_remoteok())
    all_projects.extend(fetch_remotive())
    all_projects.extend(fetch_jobicy())

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
    platforms = "RemoteOK + Remotive + Jobicy"

    log.info(f"🤖 Agente freelance iniciado. Intervalo: {interval // 60} min | {platforms}")
    send_telegram(
        f"🤖 <b>Agente actualizado</b>\n"
        f"Fuentes: {platforms} (APIs oficiales, sin bloqueo)\n"
        f"Intervalo: cada {interval // 60} minutos."
    )

    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Error inesperado: {e}")
        log.info(f"Esperando {interval // 60} min...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
