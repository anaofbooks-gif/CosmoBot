import discord
from discord.ext import commands
import logging
from typing import Optional

import config
from storage import dados
from utils import normalizar_categoria, este_ano
from stats import estatisticas_mes, estatisticas_ano
from images import desenhar_grafico_circular, desenhar_resumo_anual, Image

logger = logging.getLogger('CosmoBot')


class StatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="resumomes")
    async def resumomes(self, ctx, mes: Optional[str] = None):
        if Image is None:
            return await ctx.send("❌ Falta instalar Pillow: `pip install Pillow`")
        mes_alvo = normalizar_categoria(mes) if mes else config.MESES_ORDEM[datetime.now().month - 1]
        if mes_alvo not in config.MESES_ORDEM:
            return await ctx.send("❌ Mês inválido. Exemplo: `!resumomes Junho`")
        ano = int(este_ano())
        stats = estatisticas_mes(mes_alvo, ano)
        if stats["total_livros"] == 0:
            return await ctx.send(f"📭 Sem leituras registadas em **{mes_alvo} {ano}**.")
        img = desenhar_grafico_circular(f"Resumo de {mes_alvo} {ano}", ["Livros", "Páginas", "Autores", "Géneros"], [stats["total_livros"], stats["paginas"], stats["autores_unicos"], stats["generos_unicos"]])
        await ctx.send(f"📊 **{mes_alvo} {ano}**\nLivros: **{stats['total_livros']}** | Páginas: **{stats['paginas']}**\nAutores distintos: **{stats['autores_unicos']}** | Géneros: **{stats['generos_unicos']}**", file=discord.File(img, filename=f"resumo-{mes_alvo.lower()}.png"))

    @commands.command(name="resumoano")
    async def resumoano(self, ctx, ano: Optional[int] = None):
        if Image is None:
            return await ctx.send("❌ Falta instalar Pillow: `pip install Pillow`")
        ano_alvo = ano or int(este_ano())
        stats = estatisticas_ano(ano_alvo)
        if stats["total_livros"] == 0:
            return await ctx.send(f"📭 Sem leituras registadas em **{ano_alvo}**.")
        img = desenhar_resumo_anual(ano_alvo, stats)
        await ctx.send(f"🏆 **Resumo anual {ano_alvo}** — {stats['total_livros']} livros, {stats['total_paginas']} páginas.", file=discord.File(img, filename=f"resumo-anual-{ano_alvo}.png"))


async def setup(bot):
    await bot.add_cog(StatsCog(bot))
