import asyncio
import logging
import discord
from discord.ext import commands
import signal
import sys

import config
from storage import carregar_dados, guardar_dados, dados, resumo_persistencia

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CosmoBot')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)

# Importar tasks depois do bot estar definido
import tasks


def signal_handler(sig, frame):
    """Guarda os dados quando o bot é interrompido (Ctrl+C ou SIGTERM)"""
    logger.info("🛑 A fechar... A guardar dados...")
    guardar_dados()
    logger.info("✅ Dados guardados. A encerrar...")
    sys.exit(0)

# Registar handlers para sinais de fecho
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


async def carregar_cogs():
    cogs = ["commands.tbr", "commands.reading", "commands.challenges", "commands.lc", 
            "commands.recommendations", "commands.bookstagram", "commands.stats_cog", 
            "commands.extras", "commands.admin"]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Cog {cog} carregado")
        except Exception as e:
            logger.error(f"❌ Falha ao carregar {cog}: {e}")
    logger.info(f"📋 Total de comandos registados: {len(bot.commands)}")


@bot.event
async def on_ready():
    logger.info(f"👑 {bot.user} está online!")
    logger.info(f"💾 {resumo_persistencia()}")
    await carregar_cogs()
    
    # Iniciar as tasks
    tasks.set_bot(bot)
    tasks.autosave_loop.start()
    tasks.verificar_lembretes_loop.start()
    tasks.resumos_automaticos_loop.start()
    tasks.verificar_lc_concluidas.start()
    
    logger.info("✅ Todas as tasks iniciadas!")


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
                    texto_extraido = await extrair_texto_da_imagem(anexo.url)
                    if texto_extraido:
                        review.setdefault("conversas", []).append(f"📸 Print: {texto_extraido}")
                        await message.add_reaction("👁️")
                    else:
                        review.setdefault("anexos", []).append(anexo.url)
                        review.setdefault("desabafos", []).append(f"[Print de mensagem: {anexo.url}]")
            guardar_dados()
            await message.add_reaction("📝")
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Comando não encontrado. Usa `{config.COMMAND_PREFIX}guia` para ver a lista de comandos.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Falta informação no comando. Usa `{config.COMMAND_PREFIX}guia` para ajuda.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Um dos valores não está no formato certo.")
    else:
        logger.error(f"Erro: {error}")
        await ctx.send(f"❌ Erro: {error}")


if __name__ == "__main__":
    carregar_dados()
    try:
        bot.run(config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        signal_handler(None, None)
