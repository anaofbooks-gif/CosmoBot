import asyncio
import logging
import discord
from discord.ext import commands

import config
from storage import carregar_dados, guardar_dados, dados
from tasks import autosave_loop, verificar_lembretes_loop, resumos_automaticos_loop, verificar_lc_concluidas_loop

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
    await carregar_cogs()
    if not autosave_loop.is_running():
        autosave_loop.start()
    if not verificar_lembretes_loop.is_running():
        verificar_lembretes_loop.start()
    if not resumos_automaticos_loop.is_running():
        resumos_automaticos_loop.start(bot)
    if not verificar_lc_concluidas_loop.is_running():
        verificar_lc_concluidas_loop.start(bot)


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Falta informação. Usa `{config.COMMAND_PREFIX}guia` para ajuda.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Formato inválido.")
    else:
        logger.error(f"Erro: {error}")
        await ctx.send(f"❌ Erro: {error}")


if __name__ == "__main__":
    carregar_dados()
    bot.run(config.DISCORD_TOKEN)

# ==============================================================================
# EVENTOS
# ==============================================================================

@bot.event
async def on_ready():
    logger.info(f"👑 {bot.user} está online.")
    logger.info(f"💾 {resumo_persistencia().replace('**', '')}")
    logger.info(f"🤖 IA: Gemini + DeepSeek (fallback automático)")
    
    # Iniciar tasks
    if not autosave_loop.is_running():
        autosave_loop.start()
    if not verificar_lembretes_loop.is_running():
        verificar_lembretes_loop.start()
    if not resumos_automaticos_loop.is_running():
        resumos_automaticos_loop.start(bot)
    if not verificar_lc_concluidas_loop.is_running():
        verificar_lc_concluidas_loop.start(bot)
    
    # Carregar cogs
    await carregar_cogs()


async def carregar_cogs():
    """Carrega todos os cogs"""
    from commands import (
        tbr, reading, challenges, lc, recommendations,
        bookstagram, stats, extras, admin
    )
    
    await bot.add_cog(tbr.TBRCog(bot))
    await bot.add_cog(reading.ReadingCog(bot))
    await bot.add_cog(challenges.ChallengesCog(bot))
    await bot.add_cog(lc.LCCog(bot))
    await bot.add_cog(recommendations.RecommendationsCog(bot))
    await bot.add_cog(bookstagram.BookstagramCog(bot))
    await bot.add_cog(stats.StatsCog(bot))
    await bot.add_cog(extras.ExtrasCog(bot))
    await bot.add_cog(admin.AdminCog(bot))
    
    logger.info("✅ Todos os cogs carregados")


@bot.event
async def on_message(message: discord.Message):
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
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Falta informação no comando. Usa `{config.COMMAND_PREFIX}guia` para ajuda.")
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ Um dos valores não está no formato certo. Usa `!guia` para ver exemplos.")
        return

    if isinstance(error, (discord.Forbidden, discord.NotFound, discord.HTTPException)):
        logger.warning(f"Erro Discord tratado: {error}")
        await ctx.send("❌ Ocorreu um erro de comunicação com o Discord. Tenta novamente.")
        return

    logger.exception(f"Erro não tratado no comando {ctx.command}: {error}")
    await ctx.send(f"❌ Erro inesperado: {error}")


# ==============================================================================
# RUN
# ==============================================================================

if __name__ == "__main__":
    # Carregar dados
    global dados
    dados = carregar_dados()
    
    # Correr bot
    bot.run(config.DISCORD_TOKEN)
