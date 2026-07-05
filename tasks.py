import asyncio
import logging
import discord
from datetime import datetime, timedelta
from discord.ext import tasks

import config
from storage import dados, guardar_dados
from utils import obter_canal_discord, set_bot_instance
from stats import estatisticas_mes, estatisticas_ano
from images import desenhar_grafico_circular, desenhar_resumo_anual, Image

logger = logging.getLogger('CosmoBot')

# Bot global
bot = None

def set_bot(bot_instance):
    global bot
    bot = bot_instance
    set_bot_instance(bot_instance)

# 🔥 Autosave a cada 30 segundos (mais frequente para evitar perdas)
@tasks.loop(seconds=30)
async def autosave_loop():
    guardar_dados()


@autosave_loop.before_loop
async def antes_autosave():
    await bot.wait_until_ready()


async def enviar_lembretes_pendentes_hoje():
    hoje = datetime.now().strftime("%d/%m/%Y")
    alterado = False
    for lembrete in dados["lembretes_metas"]:
        if lembrete.get("data") != hoje or lembrete.get("avisado"):
            continue
        canal = await obter_canal_discord(lembrete.get("thread_id") or lembrete.get("canal_id"))
        if canal:
            try:
                await canal.send(f"🔔 **METAS DE HOJE!**\nLivro: **{lembrete.get('livro', 'Livro')}**\n📖 **Meta:** {lembrete.get('meta', '')}\nBoas leituras!")
                lembrete["avisado"] = True
                alterado = True
            except Exception as e:
                logger.warning(f"Erro ao enviar lembrete: {e}")
    if alterado:
        guardar_dados()


@tasks.loop(hours=1)
async def verificar_lembretes_loop():
    await enviar_lembretes_pendentes_hoje()


@verificar_lembretes_loop.before_loop
async def antes_lembretes():
    await bot.wait_until_ready()


@tasks.loop(hours=6)
async def resumos_automaticos_loop():
    if bot is None:
        return
    agora = datetime.now()
    if agora.day == 1 and agora.hour == 10:
        mes_idx = agora.month - 2
        if mes_idx < 0:
            mes_idx = 11
            ano = agora.year - 1
        else:
            ano = agora.year
        mes_nome = config.MESES_ORDEM[mes_idx]
        for guild in bot.guilds:
            canal = discord.utils.get(guild.text_channels, name="sugestoes-leitura")
            if canal and Image:
                stats = estatisticas_mes(mes_nome, ano)
                if stats["total_livros"] > 0:
                    img = desenhar_grafico_circular(f"Resumo de {mes_nome} {ano}", ["Livros", "Páginas", "Autores", "Géneros"], [stats["total_livros"], stats["paginas"], stats["autores_unicos"], stats["generos_unicos"]])
                    await canal.send(f"📊 **Resumo de leituras - {mes_nome} {ano}**\nTotal de livros: {stats['total_livros']}\nPáginas lidas: {stats['paginas']}", file=discord.File(img, filename=f"resumo-{mes_nome.lower()}.png"))
    if agora.month == 1 and agora.day == 2 and agora.hour == 10:
        ano_anterior = agora.year - 1
        for guild in bot.guilds:
            canal = discord.utils.get(guild.text_channels, name="sugestoes-leitura")
            if canal and Image:
                stats = estatisticas_ano(ano_anterior)
                if stats["total_livros"] > 0:
                    img = desenhar_resumo_anual(ano_anterior, stats)
                    await canal.send(f"🏆 **Resumo Anual {ano_anterior}** 🏆\nLivros lidos: {stats['total_livros']}\nPáginas lidas: {stats['total_paginas']}", file=discord.File(img, filename=f"resumo-anual-{ano_anterior}.png"))


@resumos_automaticos_loop.before_loop
async def antes_resumos():
    await bot.wait_until_ready()


@tasks.loop(hours=1)
async def verificar_lc_concluidas():
    if bot is None:
        return
    from views import ViewConfirmarLido
    from utils import livro_ja_lido

    livros_lc = {}
    for lembrete in dados["lembretes_metas"]:
        if lembrete.get("tipo") != "lc":
            continue
        if lembrete.get("lc_concluida_notificada"):
            continue
        livro = lembrete.get("livro")
        if livro not in livros_lc:
            livros_lc[livro] = {"lembretes": [], "canal_id": lembrete.get("thread_id") or lembrete.get("canal_id"), "autor": lembrete.get("autor", "")}
        livros_lc[livro]["lembretes"].append(lembrete)

    alterado = False
    hoje = datetime.now().date()
    limite_antigo = hoje - timedelta(days=2)

    for livro, info in livros_lc.items():
        metas_cumpridas = 0
        datas_validas = []
        for lembrete in info["lembretes"]:
            try:
                data_meta = datetime.strptime(lembrete["data"], "%d/%m/%Y").date()
                datas_validas.append(data_meta)
                if data_meta <= hoje:
                    metas_cumpridas += 1
            except Exception:
                pass

        if metas_cumpridas < len(info["lembretes"]):
            continue

        ultima_meta = max(datas_validas) if datas_validas else hoje
        if ultima_meta < limite_antigo:
            for lembrete in info["lembretes"]:
                lembrete["lc_concluida_notificada"] = True
            alterado = True
            logger.info(f"LC antiga marcada como já tratada sem notificar: {livro}")
            continue

        canal = await obter_canal_discord(info["canal_id"])
        if not canal:
            continue

        if livro_ja_lido(livro, dados):
            await canal.send(f"📚 **LC CONCLUÍDA!**\nO livro **{livro}** já está registado como lido. 🎉")
        else:
            await canal.send(f"🎉 **PARABÉNS! A leitura conjunta de '{livro}' foi concluída!** 🎉\n\nTodas as metas foram cumpridas. Queres registar este livro como lido?", view=ViewConfirmarLido(livro, info["autor"], info["canal_id"]))

        for lembrete in info["lembretes"]:
            lembrete["lc_concluida_notificada"] = True
        alterado = True

    if alterado:
        guardar_dados()
@verificar_lc_concluidas.before_loop
async def antes_verificar_lc():
    await bot.wait_until_ready()


