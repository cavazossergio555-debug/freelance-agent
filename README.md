# Agente de Freelance con IA

Busca proyectos en Workana, genera propuestas personalizadas con Claude y te notifica por Telegram para que apruebas antes de enviar.

## Cómo funciona

```
Railway (servidor gratis)
    └── agent.py corre cada 60 min
        ├── Busca proyectos nuevos en Workana
        ├── Filtra los relevantes con IA
        ├── Genera propuesta personalizada
        └── Te manda mensaje en Telegram
                └── Tú apruebas → copias y pegas en Workana
```

---

## Instalación local (para probar)

### 1. Clona el repo
```bash
git clone https://github.com/TU_USUARIO/freelance-agent.git
cd freelance-agent
```

### 2. Instala dependencias
```bash
pip install -r requirements.txt
```

### 3. Configura tus variables
```bash
cp .env.example .env
# Edita .env con tu editor y llena los valores
```

### 4. Prueba que funciona
```bash
python src/agent.py
```

---

## Deploy en Railway (servidor gratis)

### 1. Crea cuenta en Railway
Ve a [railway.app](https://railway.app) → Sign up with GitHub

### 2. Nuevo proyecto
- Click en **New Project**
- Selecciona **Deploy from GitHub repo**
- Elige este repositorio

### 3. Agrega las variables de entorno
En Railway → tu proyecto → **Variables**, agrega:

| Variable | Valor |
|----------|-------|
| `ANTHROPIC_API_KEY` | tu key de Anthropic |
| `FREELANCER_NAME` | Tu nombre |
| `TELEGRAM_BOT_TOKEN` | token de tu bot |
| `TELEGRAM_CHAT_ID` | tu chat ID |
| `CHECK_INTERVAL_MINUTES` | 60 |

### 4. Deploy
Railway detecta el `railway.toml` y despliega automáticamente.

---

## Cómo obtener tu Telegram Chat ID

1. Habla con [@userinfobot](https://t.me/userinfobot) en Telegram
2. Te responde con tu Chat ID

## Cómo crear tu bot de Telegram

1. Habla con [@BotFather](https://t.me/BotFather)
2. Escribe `/newbot`
3. Elige nombre y usuario
4. Copia el token

---

## Flujo de aprobación

Cuando el agente encuentra un proyecto relevante, recibirás en Telegram:

```
🔍 Nueva oportunidad de freelance

Redactor de contenido tech para blog SaaS
💰 $80 - $120 USD
🏆 Relevancia: 88/100
🔗 https://workana.com/job/...

Propuesta generada:
[texto de la propuesta]

¿Apruebas el envío?
✅ /aprobar_1
❌ /rechazar_1
```

Tú copias la propuesta y la pegas directamente en Workana.

---

## Personalizar el perfil

Edita `FREELANCER_PROFILE` en `src/agent.py`:

```python
FREELANCER_PROFILE = {
    "name": "Tu Nombre",
    "skills": ["redacción", "SEO", "traducción"],
    "experience": "Describe tu experiencia aquí...",
}
```
