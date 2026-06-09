import asyncio
import logging
from datetime import datetime
from discord.ext import tasks

import config
from storage import dados, guardar_dados
from utils import obter_canal_discord
from stats import estatisticas_mes, estatisticas_ano
from images import desenhar_grafico_circular, desenhar_resumo_anual

logger = logging.getLogger('CosmoBot')


# ==============================================================================
# TASK: AUTOSAVE
# ==============================================================================

@tasks.loop(minutes=2)
async def autosave_loop():
    guardar_dados()


@autosave_loop.before_loop
async def antes_autosave(bot):
    await bot.wait_until_ready()


# ==============================================================================
# TASK: LEMBRETES
# ==============================================================================

async def enviar_lembretes_pendentes_hoje() -> None:
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    alterado = False

    for lembrete in dados["lembretes_metas"]:
        if lembrete.get("data") != data_hoje or lembrete.get("avisado"):
            continue

        canal_id = lembrete.get("thread_id") or lembrete.get("canal_id")
        if not canal_id:
            continue

        canal = await obter_canal_discord(int(canal_id))
        if not canal:
            continue

        try:
            await canal.send(
                f"🔔 **METAS DE HOJE!**\n"
                f"Livro: **{lembrete.get('livro', 'Livro')}**\n"
                f"📖 **Meta:** {lembrete.get('meta', '')}\n"
                f"Boas leituras!"
            )
            lembrete["avisado"] = True
            alterado = True
        except discord.HTTPException as e:
            logger.warning(f"Erro ao enviar lembrete: {e}")

    if alterado:
        guardar_dados()


@tasks.loop(hours=1)
async def verificar_lembretes_loop():
    await enviar_lembretes_pendentes_hoje()


@verificar_lembretes_loop.before_loop
async def antes_lembretes(bot):
    await bot.wait_until_ready()


# ==============================================================================
# TASK: RESUMOS AUTOMÁTICOS
# ==============================================================================

@tasks.loop(hours=6)
async def resumos_automaticos_loop(bot):
    agora = datetime.now()
    
    if agora.day == 1 and agora.hour == 10:
        mes_anterior_idx = agora.month - 2
        if mes_anterior_idx < 0:
            mes_anterior_idx = 11
            ano = agora.year - 1
        else:
            ano = agora.year
        mes_nome = config.MESES_ORDEM[mes_anterior_idx]
        from images import Image
        for guild in bot.guilds:
            canal = discord.utils.get(guild.text_channels, name="sugestoes-leitura")
            if canal and Image is not None:
                stats = estatisticas_mes(mes_nome, ano)
                if stats["total_livros"] > 0:
                    img = desenhar_grafico_circular(
                        f"Resumo de {mes_nome} {ano}",
                        ["Livros", "Páginas", "Autores", "Géneros"],
                        [stats["total_livros"], stats["paginas"], stats["autores_unicos"], stats["generos_unicos"]],
                    )
                    await canal.send(
                        f"📊 **Resumo de leituras - {mes_nome} {ano}**\n"
                        f"Total de livros: {stats['total_livros']}\n"
                        f"Páginas lidas: {stats['paginas']}\n"
                        f"Autores distintos: {stats['autores_unicos']}\n"
                        f"Géneros diferentes: {stats['generos_unicos']}",
                        file=discord.File(img, filename=f"resumo-{mes_nome.lower()}.png")
                    )

    if agora.month == 1 and agora.day == 2 and agora.hour == 10:
        ano_anterior = agora.year - 1
        from images import Image
        for guild in bot.guilds:
            canal = discord.utils.get(guild.text_channels, name="sugestoes-leitura")
            if canal and Image is not None:
                stats = estatisticas_ano(ano_anterior)
                if stats["total_livros"] > 0:
                    img = desenhar_resumo_anual(ano_anterior, stats)
                    await canal.send(
                        f"🏆 **Resumo Anual {ano_anterior}** 🏆\n"
                        f"Livros lidos: {stats['total_livros']}\n"
                        f"Páginas lidas: {stats['total_paginas']}\n"
                        f"Autor mais lido: {stats['autor_top'][0]} ({stats['autor_top'][1]} livros)\n"
                        f"Género dominante: {stats['genero_top'][0]} ({stats['genero_top'][1]} livros)",
                        file=discord.File(img, filename=f"resumo-anual-{ano_anterior}.png")
                    )


@resumos_automaticos_loop.before_loop
async def antes_resumos(bot):
    await bot.wait_until_ready()


# ==============================================================================
# TASK: VERIFICAR LC CONCLUÍDAS
# ==============================================================================

@tasks.loop(hours=1)
async def verificar_lc_concluidas_loop(bot):
    from views import ViewConfirmarLido
    from utils import livro_ja_lido, obter_canal_discord
    
    livros_lc = {}
    for lembrete in dados["lembretes_metas"]:
        if lembrete.get("tipo") != "lc":
            continue
        livro = lembrete.get("livro")
        if livro not in livros_lc:
            livros_lc[livro] = {
                "lembretes": [],
                "canal_id": lembrete.get("thread_id") or lembrete.get("canal_id"),
                "autor": lembrete.get("autor", ""),
                "total_metas": 0,
                "metas_cumpridas": 0
            }
        livros_lc[livro]["lembretes"].append(lembrete)
    
    for livro, info in livros_lc.items():
        info["total_metas"] = len(info["lembretes"])
        
        metas_cumpridas = 0
        for lembrete in info["lembretes"]:
            try:
                data_meta = datetime.strptime(lembrete["data"], "%d/%m/%Y")
                data_hoje_dt = datetime.now()
                if data_meta.date() <= data_hoje_dt.date():
                    metas_cumpridas += 1
            except (TypeError, ValueError):
                pass
        
        if info.get("notificado") or metas_cumpridas < info["total_metas"]:
            continue
        
        info["notificado"] = True
        
        canal = await obter_canal_discord(int(info["canal_id"]))
        if not canal:
            continue
        
        if livro_ja_lido(livro, dados):
            await canal.send(
                f"📚 **LC CONCLUÍDA!**\n"
                f"O livro **{livro}** já está registado como lido. 🎉"
            )
            continue
        
        view = ViewConfirmarLido(livro, info["autor"], info["canal_id"])
        await canal.send(
            f"🎉 **PARABÉNS! A leitura conjunta de '{livro}' foi concluída!** 🎉\n\n"
            f"Todas as metas foram cumpridas. Queres registar este livro como lido?",
            view=view
        )


@verificar_lc_concluidas_loop.before_loop
async def antes_verificar_lc(bot):
    await bot.wait_until_ready()