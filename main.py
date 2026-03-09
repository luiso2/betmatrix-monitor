import asyncio
import os
import logging
from datetime import datetime
from aiohttp import web
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Config
API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION_STRING = os.environ["TELEGRAM_SESSION_STRING"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
JOSE_CHAT_ID = int(os.environ.get("JOSE_CHAT_ID", "6287853524"))
MONITOR_GROUP = os.environ.get("MONITOR_GROUP", "Andrew Bot testing")
PORT = int(os.environ.get("PORT", 8080))

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Bot state
bot_state = {
    "status": "starting",
    "connected_as": None,
    "monitoring": MONITOR_GROUP,
    "messages_analyzed": 0,
    "started_at": datetime.utcnow().isoformat(),
    "last_message_at": None,
}

SYSTEM_PROMPT = """Eres un asistente inteligente que monitorea el grupo de Telegram "Andrew Bot testing" del proyecto BetMatrix (Win Works Gaming).

CONTEXTO DEL PROYECTO BETMATRIX:
- Plataforma multi-tenant de comparación y automatización de apuestas deportivas
- Scrapea odds en tiempo real de 10 sportsbooks
- Stack: Node.js 24, Express 5, SQLite, Next.js 16, Railway
- Staging: betmatrixproject-stagin.up.railway.app / dashboard-stagin.up.railway.app

SPORTSBOOKS INTEGRADOS:
1. ace23/action23/play23 → backend.play23.ag | Cuentas: WWPLAYER1, WWPLAYER2, WWPLAYER3
2. 1BV (Godds) → godds.ag | Cuentas: wp5023, wp5024, wp5025
3. Buckeye (StrikeRich) → strikerich.ag | Cuentas: RD341, TP56
4. Fesster (Blue987) → blue987.com | Cuenta: jay
5. LVA (HighRoller) → thehighroller.net | Cuentas: WWG15, WWG25
6. ABCWager → abcwagering | Cuenta: Qr3834
7. BetWindyCity → betwindycity.com | Cuenta: Doc205
8. Jazz → play1010.com | Cuenta: tplay1010 (necesita IP extranjera)
9. PHX (BetPhoenix) → betphoenix.ag | Cuenta: BP48685
10. TossAndGo → tossandgo.live | Cuenta: BP48685

PARTICIPANTES DEL GRUPO:
- WW (@WinWorksgaming) = Dueño del proyecto, da instrucciones
- Andrew (@agfl0308) = Nuevo tester, probando el sistema
- Jacob (@PiaJ0307) = Developer
- Jose (@vargas9310) = Developer principal (TÚ le reportas a ÉL)

CONTEXTO RECIENTE:
- Andrew acaba de unirse hoy para testear
- Login de Andrew: andrew@wwg.com / andrew@123 en el staging copy
- WW le pidió a Andrew enviar info de cuentas para "ace", "LVA" y "eagle"
- "ace" = ace23/action23 (play23.ag)
- "LVA" = HighRoller (thehighroller.net)
- "eagle" = posiblemente BetPhoenix (PHX) o cuenta nueva

TU TAREA:
Cuando recibas un mensaje nuevo del grupo, analiza:
1. ¿Quién lo dijo?
2. ¿Qué está pidiendo, reportando o enviando?
3. ¿Requiere acción inmediata de Jose?
4. ¿Qué parte del sistema BetMatrix afecta? (sportsbook específico, dashboard, API, cuentas, etc.)
5. Si envían credenciales de cuentas, identifícalas claramente.

Responde SIEMPRE en español. Sé conciso pero completo. Máximo 200 palabras.
Formato de respuesta:
👤 [Nombre]: [mensaje original corto]
📊 Análisis: [qué significa en el contexto BetMatrix]
⚡ Acción: [lo que Jose debe hacer, o "Ninguna - solo informativo"]"""


async def analyze_message(sender_name: str, message_text: str) -> str:
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{sender_name}: {message_text}"}
            ],
            max_tokens=300,
            temperature=0.3,
        )
        return response.choices[0].message.content or "Sin análisis"
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return f"⚠️ Error al analizar: {e}"


# --- HTTP Health Server ---
async def handle_health(request):
    return web.json_response({
        "status": bot_state["status"],
        "connected_as": bot_state["connected_as"],
        "monitoring": bot_state["monitoring"],
        "messages_analyzed": bot_state["messages_analyzed"],
        "started_at": bot_state["started_at"],
        "last_message_at": bot_state["last_message_at"],
    })

async def handle_root(request):
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>BetMatrix Monitor</title>
    <style>body{{font-family:monospace;background:#0a0a0a;color:#D4A84B;padding:40px}}
    h1{{color:#fff}} .ok{{color:#4ade80}} .tag{{background:#1a1a1a;padding:4px 10px;border-radius:4px;margin:4px 0;display:block}}</style>
    </head>
    <body>
    <h1>🤖 BetMatrix Monitor</h1>
    <p>Estado: <span class="ok">● {bot_state['status'].upper()}</span></p>
    <span class="tag">👤 Conectado como: {bot_state['connected_as'] or 'conectando...'}</span>
    <span class="tag">👁 Monitoreando: {bot_state['monitoring']}</span>
    <span class="tag">📊 Mensajes analizados: {bot_state['messages_analyzed']}</span>
    <span class="tag">🕐 Iniciado: {bot_state['started_at']}</span>
    <span class="tag">💬 Último mensaje: {bot_state['last_message_at'] or 'ninguno aún'}</span>
    <br><p><a href="/health" style="color:#D4A84B">GET /health → JSON</a></p>
    </body></html>
    """
    return web.Response(text=html, content_type="text/html")

async def start_http_server():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"HTTP server running on port {PORT}")


# --- Telegram Bot ---
async def main():
    logger.info("Starting BetMatrix Monitor...")

    # Start HTTP server first so Railway doesn't timeout
    await start_http_server()
    bot_state["status"] = "connecting"

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    bot_state["status"] = "running"
    bot_state["connected_as"] = f"{me.first_name} (@{me.username})"
    logger.info(f"Connected as: {me.first_name} (@{me.username})")

    @client.on(events.NewMessage(chats=MONITOR_GROUP))
    async def handler(event):
        sender = await event.get_sender()
        sender_name = getattr(sender, "first_name", "Unknown")
        username = getattr(sender, "username", "")
        message_text = event.message.text or ""

        if not message_text.strip():
            return
        if sender.id == JOSE_CHAT_ID:
            return

        logger.info(f"New message from {sender_name}: {message_text[:50]}")
        bot_state["messages_analyzed"] += 1
        bot_state["last_message_at"] = datetime.utcnow().isoformat()

        analysis = await analyze_message(sender_name, message_text)

        notification = (
            f"🔔 *Andrew Bot Testing*\n\n"
            f"*De:* {sender_name} (@{username})\n"
            f"*Mensaje:* {message_text}\n\n"
            f"─────────────────\n"
            f"{analysis}"
        )

        await client.send_message(JOSE_CHAT_ID, notification, parse_mode="markdown")
        logger.info("Analysis sent to Jose")

    logger.info(f"Monitoring group: '{MONITOR_GROUP}'")
    logger.info("Waiting for messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
