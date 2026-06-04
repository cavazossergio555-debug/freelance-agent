"""
Agente de Freelance — Motor principal
Busca proyectos, genera propuestas y notifica al usuario para aprobación.
"""

import os
import json
import time
import logging
import requests
from datetime import datetime
from typing import Optional
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
    "hourly_rate_usd": 15,
}


# ─────────────────────────────────────────────
#  SCRAPER DE WORKANA
# ─────────────────────────────────────────────

WORKANA_SEARCH_URL = "https://www.workana.com/jobs?category=translation-writing&language=es"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}


def fetch_workana_projects() -> list[dict]:
    """Scrapea proyectos recientes de Workana."""
    log.info("Buscando proyectos en Workana...")
    try:
        resp = requests.get(WORKANA_SEARCH_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        projects = []
        for card in soup.select(".project-item, .job-item, article.project")[:10]:
            title_el = card.select_one("h2 a, h3 a, .project-title a")
            budget_el = card.select_one(".budget, .price, .project-budget")
            desc_el = card.select_one(".project-description, .description, p")
            link_el = card.select_one("a[href*='/job/']")

            if not title_el:
                continue

            projects.append({
                "title": title_el.get_text(strip=True),
                "budget": budget_el.get_text(strip=True) if budget_el else "No especificado",
                "description": desc_el.get_text(strip=True)[:300] if desc_el else "",
                "url": "https://www.workana.com" + link_el["href"] if link_el else WORKANA_SEARCH_URL,
                "platform": "Workana",
                "found_at": datetime.now().isoformat(),
            })

        log.info(f"Encontrados {len(projects)} proyectos en Workana")
        return projects

    except Exception as e:
        log.error(f"Error scrapeando Workana: {e}")
        # Proyectos de ejemplo si el scraping falla (para pruebas)
        return [
            {
                "title": "Redactor de contenido tech para blog SaaS",
                "budget": "$80 - $120 USD",
                "description": "Necesito redactor para crear 4 artículos mensuales sobre software empresarial y tendencias digitales. Experiencia en SEO requerida.",
                "url": "https://www.workana.com/job/example-1",
                "platform": "Workana",
                "found_at": datetime.now().isoformat(),
            },
            {
                "title": "Traducción técnica ES→EN de documentación API",
                "budget": "$150 - $200 USD",
                "description": "Manual técnico de 15 páginas sobre integración de API REST. Requiere conocimiento técnico y dominio del inglés.",
                "url": "https://www.workana.com/job/example-2",
                "platform": "Workana",
                "found_at": datetime.now().isoformat(),
            },
        ]


# ─────────────────────────────────────────────
#  FILTRO DE RELEVANCIA CON IA
# ─────────────────────────────────────────────

def filter_relevant_projects(projects: list[dict]) -> list[dict]:
    """Usa Claude para filtrar solo los proyectos relevantes al perfil."""
    if not projects:
        return []

    log.info("Filtrando proyectos con IA...")

    prompt = f"""Eres un asistente que filtra proyectos de freelance.

PERFIL DEL FREELANCER:
{json.dumps(FREELANCER_PROFILE, ensure_ascii=False, indent=2)}

PROYECTOS ENCONTRADOS:
{json.dumps(projects, ensure_ascii=False, indent=2)}

Evalúa cada proyecto y devuelve SOLO un JSON con este formato exacto, sin texto adicional:
{{
  "relevant": [
    {{
      "index": 0,
      "score": 85,
      "reason": "Coincide con habilidades de redacción tech"
    }}
  ]
}}

Solo incluye proyectos con score >= 60. El índice corresponde a la posición en la lista original."""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        # Limpiar posibles backticks
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())

        relevant = []
        for item in data.get("relevant", []):
            idx = item["index"]
            if idx < len(projects):
                proj = projects[idx].copy()
                proj["relevance_score"] = item["score"]
                proj["relevance_reason"] = item["reason"]
                relevant.append(proj)

        log.info(f"{len(relevant)} proyectos relevantes tras filtrado")
        return relevant

    except Exception as e:
        log.error(f"Error filtrando proyectos: {e}")
        return projects[:3]


# ─────────────────────────────────────────────
#  GENERADOR DE PROPUESTAS
# ─────────────────────────────────────────────

def generate_proposal(project: dict) -> str:
    """Genera una propuesta personalizada para un proyecto."""
    log.info(f"Generando propuesta para: {project['title']}")

    prompt = f"""Eres un experto en redactar propuestas de freelance ganadoras.

PERFIL DEL FREELANCER:
Nombre: {FREELANCER_PROFILE['name']}
Experiencia: {FREELANCER_PROFILE['experience']}
Habilidades: {', '.join(FREELANCER_PROFILE['skills'])}
Disponibilidad: {FREELANCER_PROFILE['availability']}

PROYECTO:
Título: {project['title']}
Presupuesto: {project['budget']}
Descripción: {project['description']}
Plataforma: {project['platform']}

Redacta una propuesta en español que:
1. Abra con algo específico del proyecto (no genérico)
2. Explique por qué este freelancer es ideal para ESTE proyecto en particular
3. Detalle 3-4 entregables concretos con tiempos
4. Cierre con una pregunta que invite al cliente a responder
5. Tono: profesional pero humano, directo, sin exageraciones

Máximo 200 palabras. Solo devuelve el texto de la propuesta, sin títulos ni explicaciones."""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        proposal = resp.content[0].text.strip()
        log.info("Propuesta generada exitosamente")
        return proposal

    except Exception as e:
        log.error(f"Error generando propuesta: {e}")
        return f"Error generando propuesta: {e}"


# ─────────────────────────────────────────────
#  SISTEMA DE NOTIFICACIONES (Telegram)
# ─────────────────────────────────────────────

def send_telegram_notification(project: dict, proposal: str) -> bool:
    """Envía notificación al usuario vía Telegram para aprobación."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log.warning("Telegram no configurado — imprimiendo en consola")
        print("\n" + "="*60)
        print("NUEVA OPORTUNIDAD ENCONTRADA — REQUIERE TU APROBACIÓN")
        print("="*60)
        print(f"Proyecto: {project['title']}")
        print(f"Presupuesto: {project['budget']}")
        print(f"URL: {project['url']}")
        print(f"Score de relevancia: {project.get('relevance_score', 'N/A')}/100")
        print("\nPROPUESTA GENERADA:")
        print("-"*60)
        print(proposal)
        print("-"*60)
        print("Para aprobar: escribe 'APROBAR' en la consola")
        print("Para rechazar: escribe 'RECHAZAR'")
        print("="*60 + "\n")
        return True

    message = (
        f"🔍 *Nueva oportunidad de freelance*\n\n"
        f"*{project['title']}*\n"
        f"💰 {project['budget']}\n"
        f"🏆 Relevancia: {project.get('relevance_score', '?')}/100\n"
        f"🔗 {project['url']}\n\n"
        f"*Propuesta generada:*\n\n"
        f"{proposal}\n\n"
        f"¿Apruebas el envío? Responde:\n"
        f"✅ /aprobar\\_1\n"
        f"❌ /rechazar\\_1"
    )

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
        resp.raise_for_status()
        log.info(f"Notificación Telegram enviada para: {project['title']}")
        return True
    except Exception as e:
        log.error(f"Error enviando Telegram: {e}")
        return False


# ─────────────────────────────────────────────
#  GESTOR DE PROYECTOS VISTOS
# ─────────────────────────────────────────────

SEEN_FILE = "logs/seen_projects.json"

def load_seen() -> set:
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen: set):
    os.makedirs("logs", exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


# ─────────────────────────────────────────────
#  LOOP PRINCIPAL DEL AGENTE
# ─────────────────────────────────────────────

def run_agent_cycle():
    """Un ciclo completo: buscar → filtrar → generar → notificar."""
    log.info("─── Iniciando ciclo del agente ───")

    seen = load_seen()

    # 1. Buscar proyectos
    all_projects = fetch_workana_projects()

    # 2. Filtrar los ya vistos
    new_projects = [p for p in all_projects if p["url"] not in seen]
    if not new_projects:
        log.info("No hay proyectos nuevos en este ciclo.")
        return

    # 3. Filtrar por relevancia con IA
    relevant = filter_relevant_projects(new_projects)

    # 4. Para cada proyecto relevante: generar propuesta y notificar
    for project in relevant:
        proposal = generate_proposal(project)
        send_telegram_notification(project, proposal)
        seen.add(project["url"])
        time.sleep(2)  # Pausa entre notificaciones

    save_seen(seen)
    log.info(f"─── Ciclo completado: {len(relevant)} oportunidades enviadas ───")


def main():
    """Punto de entrada: corre el agente cada N minutos."""
    interval_minutes = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))
    log.info(f"Agente iniciado. Revisando cada {interval_minutes} minutos.")
    log.info(f"Perfil: {FREELANCER_PROFILE['name']} | Skills: {', '.join(FREELANCER_PROFILE['skills'])}")

    while True:
        try:
            run_agent_cycle()
        except Exception as e:
            log.error(f"Error en ciclo principal: {e}")
        log.info(f"Próxima revisión en {interval_minutes} minutos...")
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    main()
