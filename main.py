import asyncio
import logging
import discord
from discord.ext import commands

import config
from storage import carregar_dados, guardar_dados, dados
from tasks import autosave_loop, verificar_lembretes_loop, resumos_automaticos_loop, verificar_lc_concluidas

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CosmoBot')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)


async def carregar_cogs():
    await bot.load_extension("commands.tbr")
    await bot.load_extension("commands.reading")
    await bot.load_extension("commands.challenges")
    await bot.load_extension("commands.lc")
    await bot.load_extension("commands.recommendations")
    await bot.load_extension("commands.bookstagram")
    await bot.load_extension("commands.stats_cog")
    await bot.load_extension("commands.extras")
    await bot.load_extension("commands.admin")
    logger.info("✅ Todos os cogs carregados!")


@bot.event
async def on_ready():
    logger.info(f"👑 {bot.user} está online!")
    logger.info(f"💾 {resumo_persistencia()}")
    await carregar_cogs()
    if not autosave_loop.is_running():
        autosave_loop.start()
    if not verificar_lembretes_loop.is_running():
        verificar_lembretes_loop.start()
    if not resumos_automaticos_loop.is_running():
        resumos_automaticos_loop.start()
    if not verificar_lc_concluidas.is_running():
        verificar_lc_concluidas.start()
    await enviar_lembretes_pendentes_hoje()


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    user_id = str(message.author.id)
    if user_id in dados.get("review_em_andamento", {}):
        if not message.content.startswith(config.COMMAND_PREFIX):
            review = dados["review_em_andamento"][user_id]
            texto = message.content.strip()
            if texto:
                review.setdefault("desabafos", []).append(texto)
            for anexo in message.attachments:
                if anexo.content_type and anexo.content_type.startswith("image/"):
                    from ai import extrair_texto_da_imagem
                    texto_extraido = await extrair_texto_d
