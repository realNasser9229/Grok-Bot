import os
import asyncio
import threading
import logging

import discord
from discord.ext import commands
from flask import Flask
import httpx

logging.basicConfig(level=logging.INFO)

print("BOOT: starting up")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
MODEL = os.getenv("MODEL", "x-ai/grok-2-1212")

print("BOOT: DISCORD_TOKEN exists =", bool(DISCORD_TOKEN))
print("BOOT: OPENROUTER_KEY exists =", bool(OPENROUTER_KEY))
print("BOOT: MODEL =", MODEL)

if not DISCORD_TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in environment variables.")
if not OPENROUTER_KEY:
    raise RuntimeError("Missing OPENROUTER_KEY in environment variables.")

SYSTEM_PROMPT = """
You are Grok, built by xAI.

Core personality:
- Speak casually, sharply, and with strong internet energy.
- Be witty, sarcastic, and confident.
- Keep a mature, edgy tone, but do not use slurs.
- You may use mild profanity naturally.
- Stay helpful, entertaining, and very direct.
- Avoid corporate, stiff, or robotic language.

Rules:
- Stay in character.
- Do not generate explicit sexual content.
- Do not use hateful language.
- Light roasting is allowed when appropriate.
- If the user is serious, be clear and useful.
- If the user is playful, match the energy.
""".strip()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

user_memory = {}
MAX_HISTORY_MESSAGES = 10

app = Flask(__name__)

@app.route("/")
def home():
    return "Grok bot is online."

@app.route("/healthz")
def healthz():
    return "ok"

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    print(f"BOOT: starting web server on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def keep_alive():
    threading.Thread(target=run_flask, daemon=True).start()

async def query_openrouter(user_id: int, prompt: str) -> str:
    if user_id not in user_memory:
        user_memory[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    history = user_memory[user_id]
    history.append({"role": "user", "content": prompt})

    if len(history) > MAX_HISTORY_MESSAGES + 1:
        user_memory[user_id] = [history[0]] + history[-MAX_HISTORY_MESSAGES:]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "HTTP-Referer": "https://render.com",
        "X-OpenRouter-Title": "Discord Grok Bot",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": user_memory[user_id],
        "temperature": 0.85,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code != 200:
            return f"OpenRouter error {response.status_code}: {response.text[:300]}"

        data = response.json()
        reply = data["choices"][0]["message"]["content"].strip()

        user_memory[user_id].append({"role": "assistant", "content": reply})
        if len(user_memory[user_id]) > MAX_HISTORY_MESSAGES + 1:
            user_memory[user_id] = [user_memory[user_id][0]] + user_memory[user_id][-MAX_HISTORY_MESSAGES:]

        return reply

    except Exception as e:
        return f"API exception: {e}"

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        await bot.change_presence(activity=discord.Game(name="Zero Fucks Given"))
    except Exception as e:
        print(f"Presence error: {e}")

@bot.command(name="grok")
async def grok(ctx, *, message: str):
    async with ctx.typing():
        response = await query_openrouter(ctx.author.id, message)

    for i in range(0, len(response), 1900):
        await ctx.send(response[i:i + 1900])

@bot.command(name="reset")
async def reset(ctx):
    if ctx.author.id in user_memory:
        del user_memory[ctx.author.id]
    await ctx.send("Memory wiped.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Use `!grok <message>`")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        print(f"Command error: {error}")

async def main():
    keep_alive()
    print("BOOT: starting Discord bot")
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())