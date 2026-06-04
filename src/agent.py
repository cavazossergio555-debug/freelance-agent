"""
Agente de Freelance — Motor principal
Busca proyectos en múltiples plataformas, genera propuestas y notifica al usuario.
Plataformas: Freelancer.com, RemoteOK, PeoplePerHour, Workana (cuando esté disponible)
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
 
 
# ─────────────────────────────────────────────
#  SCRAPERS POR PLATAFORMA
# ─────────────────────────────────────────────
 
def fetch_remoteok() -> list[dict]:
    """RemoteOK — tiene API pública gratuita, muy confiable."""
    log.info("Buscando en RemoteOK...")
    try:
        resp = requests.get(
            "https://remoteok.com/api?tag=writing",
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        projects = []
        for job in data[1:11]:  # Primeros 10, skip el primer elemento (legal notice)
            if not isinstance(job, dict):
                continue
            projects.append({
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
 
 
def fetch_freelancer_rss() -> list[dict]:
    """Freelancer.com vía RSS — no requiere cuenta."""
    log.info("Buscando en Freelancer.com RSS...")
    try:
        urls = [
            "https://www.freelancer.com/rss/jobs/writing.xml",
            "https://www.freelancer.com/rss/jobs/translation.xml",
        ]
        projects = []
        for url in urls:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "xml")
            for item in soup.find_all("item")[:6]:
                title = item.find("title")
                link = item.find("link")
                desc = item.find("description")
                if not title:
                    continue
                projects.append({
                    "title": title.get_text(strip=True),
                    "budget": "Ver en plataforma",
                    "description": BeautifulSoup(desc.get_text(), "html.parser").get_text()[:300] if desc else "",
                    "url": link.get_text(strip=True) if link else "https://www.freelancer.com",
                    "platform": "Freelancer.com",
                    "found_at": datetime.now().isoformat(),
                })
        log.info(f"Freelancer.com: {len(projects)} proyectos encontrados")
        return projects
    except Exception as e:
        log.error(f"Error en Freelancer.com RSS: {e}")
        return []
 
 
def fetch_peopleperhour() -> list[dict]:
    """PeoplePerHour — scraping básico."""
    log.info("Buscando en PeoplePerHour...")
    try:
        resp = requests.get(
            "https://www.peopleperhour.com/freelance-jobs?service=writing-translation",
            headers=HEADERS,
            timeout=15
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        projects = []
        for card in soup.select(".job-list-item, .listing-item, article")[:8]:
            title_el = card.select_one("h2, h3, .title, .job-title")
            budget_el = card.select_one(".budget, .price, .fee")
            desc_el = card.select_one("p, .description, .snippet")
            link_el = card.select_one("a[href]")
            if not title_el:
                continue
            href = link_el["href"] if link_el else ""
            url = href if href.startswith("http") else "https://www.peopleperhour.com" + href
            projects.append({
                "title": title_el.get_text(strip=True),
                "budget": budget_el.get_text(strip=True) if budget_el else "Ver en plataforma",
                "description": desc_el.get_text(strip=True)[:300] if desc_el else "",
                "url": url,
                "platform": "PeoplePerHour",
                "found_at": datetime.now().isoformat(),
            })
        log.info(f"PeoplePerHour: {len(projects)} proyectos encontrados")
        return projects
    except Exception as e:
        log.error(f"Error en PeoplePerHour: {e}")
        return []
 
 
def fetch_workana() -> list[dict]:
    """Workana — activo solo si la cuenta está aprobada."""
    if os.environ.get("WORKANA_ENABLED", "false").lower() != "true":
        log.info("Workana desactivado — actívalo cuando aprueben tu cuenta")
        return []
    log.info("Buscando en Workana...")
    try:
        resp = requests.get(
            "https://www.workana.com/jobs?category=translation-writing&language=es",
            headers=HEADERS, timeout=15
        )
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
                "url": "https://www.workana.com" + link_el["href"] if link_el else "https://www.workana.com",
                "platform": "Workana",
                "found_at": datetime.now().isoformat(),
            })
        log.info(f"Workana: {len(projects)} proyectos encontrados")
        return projects
    except Exception as e:
        log.error(f"Error en Workana: {e}")
        return []
 
 
def fetch_all_platforms() -> list[dict]:
    """Busca en todas las plataformas activas y combina resultados."""
    all_projects = []
    fetchers = [
        fetch_remoteok,
        fetch_freelancer_rss,
        fetch_peopleperhour,
        fetch_workana,
    ]
    for fetcher in fetchers:
        try:
            projects = fetcher()
            all_projects.extend(projects)
            time.sleep(1)  # Pausa entre requests
        except Exception as e:
            log.error(f"Error en {fetcher.__name__}: {e}")
    log.info(f"Total proyectos encontrados en todas las plataformas: {len(all_projects)}")
    return all_projects
 
 
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
Tarifa: ${FREELANCER_PROFILE['hourly_rate_usd']} USD/hr
 
PROYECTO:
Título: {project['title']}
Presupuesto: {project['budget']}
Descripción: {project['description']}
Plataforma: {project['platform']}
 
Redacta una propuesta en español que:
1. Abra con algo específico del proyecto (no genérico)
2. Explique por qué este freelancer es ideal para ESTE proyecto
3. Detalle 3-4 entregables concretos con tiempos
4. Cierre con una pregunta que invite al cliente a responder
5. Tono: profesional pero humano, directo, sin exageraciones
 
Máximo 200 palabras. Solo devuelve el texto de la propuesta."""
 
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
#  NOTIFICACIONES TELEGRAM
# ─────────────────────────────────────────────
 
def send_telegram_notification(project: dict, proposal: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
 
    if not token or not chat_id:
        log.warning("Telegram no configurado — imprimiendo en consola")
        print("\n" + "="*60)
        print(f"[{project['platform']}] NUEVA OPORTUNIDAD")
        print(f"Proyecto: {project['title']}")
        print(f"Presupuesto: {project['budget']}")
        print(f"URL: {project['url']}")
        print(f"Propuesta:\n{proposal}")
        print("="*60 + "\n")
        return True
 
    message = (
        f"🔍 *Nueva oportunidad — {project['platform']}*\n\n"
        f"*{project['title']}*\n"
        f"💰 {project['budget']}\n"
        f"🏆 Relevancia: {project.get('relevance_score', '?')}/100\n"
        f"🔗 {project['url']}\n\n"
        f"*Propuesta generada:*\n\n"
        f"{proposal}\n\n"
        f"✅ Copia y pega en la plataforma cuando apruebes."
    )
 
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
        resp.raise_for_status()
        log.info(f"Telegram enviado: {project['platform']} — {project['title']}")
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
#  LOOP PRINCIPAL
# ─────────────────────────────────────────────
 
def run_agent_cycle():
    log.info("─── Iniciando ciclo del agente ───")
    seen = load_seen()
 
    all_projects = fetch_all_platforms()
    new_projects = [p for p in all_projects if p["url"] not in seen]
 
    if not new_projects:
        log.info("No hay proyectos nuevos en este ciclo.")
        return
 
    relevant = filter_relevant_projects(new_projects)
 
    for project in relevant:
        proposal = generate_proposal(project)
        send_telegram_notification(project, proposal)
        seen.add(project["url"])
        time.sleep(2)
 
    save_seen(seen)
    log.info(f"─── Ciclo completado: {len(relevant)} oportunidades enviadas ───")
 
 
def main():
    interval_minutes = int(os.environ.get("CHECK_INTERVAL_MINUTES", "15"))
    log.info(f"Agente iniciado. Revisando cada {interval_minutes} minutos.")
    log.info(f"Plataformas activas: RemoteOK, Freelancer.com, PeoplePerHour" +
             (" + Workana" if os.environ.get("WORKANA_ENABLED") == "true" else " (Workana pendiente)"))
 
    while True:
        try:
            run_agent_cycle()
        except Exception as e:
            log.error(f"Error en ciclo principal: {e}")
        log.info(f"Próxima revisión en {interval_minutes} minutos...")
        time.sleep(interval_minutes * 60)
 
 
if __name__ == "__main__":
    main()
 
