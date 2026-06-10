import discord
from discord.ext import commands
import random
import calendar
import asyncio
import logging
from typing import Optional

import config
from storage import dados, guardar_dados, livros_tbr_flat, adicionar_livro_a_tbr_mes, sorteio_mes_ativo
from utils import livro_completo, normalizar_categoria, normalizar_titulo, buscar_livro_case_insensitive, hoje_str, este_ano, numero_mes, enviar_mensagem_longa
from ai import detetar_e_agendar_serie
from images import desenhar_calendario_leituras, Image
from views import ViewConfirmarDuplicado

logger = logging.getLogger('CosmoBot')


class TBRCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addtbr")
    async def addtbr(self, ctx, categoria: Optional[str] = None, *, livro: Optional[str] = None):
        if not categoria:
            return await ctx.send("❌ Diz-me o livro que queres adicionar. Exemplo: `!addtbr Nome do Livro`")
        cat_sugerida = normalizar_categoria(categoria)
        if cat_sugerida in dados["tbr_por_mes"]:
            if not livro:
                return await ctx.send(f"❌ Falta o nome do livro para adicionar a **{cat_sugerida}**.\nExemplo: `!addtbr {cat_sugerida} \"Título - Autor\"`")
            cat = cat_sugerida
            texto_livro = livro.strip()
        else:
            cat = "Geral"
            texto_livro = f"{categoria} {livro or ''}".strip()
        try:
            titulo_livro = livro_completo(texto_livro)
        except ValueError:
            return await ctx.send('❌ O formato tem de incluir autor: **"Título - Autor"**.\nExemplo: `!addtbr "Quarta Asa - Rebecca Yarros"`')
        if any(titulo_livro.lower().strip() == i.lower().strip() for i in livros_tbr_flat()):
            return await ctx.send("🤔 Esse livro já está na tua TBR.")
        dados["tbr_por_mes"][cat].append(titulo_livro)
        guardar_dados()
        await ctx.send(f"📅 **{titulo_livro}** adicionado com sucesso a **{cat}**.")
        await ctx.send("🔍 A verificar se pertence a uma série...")
        if cat == "Geral":
            msgs = await detetar_e_agendar_serie(titulo_livro, "Geral", ctx.channel)
            if msgs:
                await ctx.send("🧬 **Série detetada!** Sequências agendadas automaticamente na TBR Geral:\n" + "\n".join(msgs) + "\n\n💡 Dica: Se quiseres movê-las para meses específicos, usa `!addtbr Mês \"Livro - Autor\"`")
        else:
            msgs = await detetar_e_agendar_serie(titulo_livro, cat, ctx.channel)
            if msgs:
                await ctx.send("🧬 **Série detetada!** Sequências agendadas automaticamente:\n" + "\n".join(msgs))

    @commands.command(name="tbr")
    async def tbr(self, ctx, mes: str, extras: int = 2):
        mes_cap = normalizar_categoria(mes)
        if mes_cap not in config.MESES_ORDEM:
            return await ctx.send("❌ Mês inválido.")
        ativo = sorteio_mes_ativo(mes_cap)
        if ativo:
            pendentes = ativo.get("pendentes", ativo.get("livros", []))
            return await ctx.send(f"🔒 O sorteio de **{mes_cap}** está trancado até leres todos os livros.\nFaltam:\n" + "\n".join(f"• {l}" for l in pendentes) + "\n\nUsa `!lido \"Título - Autor\"` à medida que fores terminando.")
        obrigatorios = list(dados["tbr_por_mes"][mes_cap])
        obrig_norm = {l.lower().strip() for l in obrigatorios}
        geral_disponivel = [l for l in dados["tbr_por_mes"]["Geral"] if l.lower().strip() not in obrig_norm]
        extras_sorteados = random.sample(geral_disponivel, min(extras, len(geral_disponivel)))
        livros_sorteio = obrigatorios + extras_sorteados
        if not livros_sorteio:
            return await ctx.send(f"📭 Não tens livros planeados para {mes_cap} nem na lista Geral.")
        dados["sorteios_mes"][mes_cap] = {"livros": livros_sorteio, "lidos": [], "data_sorteio": hoje_str(), "ano": int(este_ano())}
        guardar_dados()
        ano, mes_num = int(este_ano()), numero_mes(mes_cap)
        _, dias_no_mes = calendar.monthrange(ano, mes_num)
        dias_uteis = [d for d in range(1, dias_no_mes + 1) if calendar.weekday(ano, mes_num, d) < 5] or list(range(1, dias_no_mes + 1))
        passo = max(1, len(dias_uteis) // max(len(livros_sorteio), 1))
        for idx, livro in enumerate(livros_sorteio):
            dia = dias_uteis[min(idx * passo, len(dias_uteis) - 1)]
            dados["lembretes_metas"].append({"data": f"{dia:02d}/{mes_num:02d}/{ano}", "livro": livro, "meta": f"Iniciar/concluir leitura de {livro}", "canal_id": ctx.channel.id, "avisado": False, "tipo": "sorteio_tbr"})
        guardar_dados()
        await enviar_mensagem_longa(ctx, f"🎲 **TBR de {mes_cap} sorteada e trancada**\n📌 **Livros deste mês:**\n" + "\n".join(f"• {l}" for l in livros_sorteio) + "\n\n🔒 Novo sorteio só depois de marcares todos como lidos com `!lido`.")
        if Image:
            try:
                img = desenhar_calendario_leituras(mes_cap, ano)
                await ctx.send(f"🗓️ Calendário de leituras de **{mes_cap}**:", file=discord.File(img, filename=f"tbr-{mes_cap.lower()}-{ano}.png"))
            except Exception as e:
                logger.warning(f"Erro ao gerar calendário TBR: {e}")

    @commands.command(name="verbar")
    async def verbar(self, ctx):
        embed = discord.Embed(title=f"📋 PLANEAMENTO DE TBR ({este_ano()})", description="A tua lista de leituras organizada por mês", color=discord.Color.purple())
        if dados["tbr_por_mes"]["Geral"]:
            lista = "\n".join(f"• {l}" for l in dados["tbr_por_mes"]["Geral"])
            embed.add_field(name="🌎 Geral", value=lista[:1000] + ("..." if len(lista) > 1000 else ""), inline=False)
        for mes in config.MESES_ORDEM:
            if dados["tbr_por_mes"][mes]:
                lista = "\n".join(f"• {l}" for l in dados["tbr_por_mes"][mes])
                embed.add_field(name=f"📅 {mes}", value=lista[:1000] + ("..." if len(lista) > 1000 else ""), inline=False)
        if not any(dados["tbr_por_mes"].values()):
            embed.description = "📭 A tua TBR está vazia. Adiciona livros com `!addtbr`!"
        await ctx.send(embed=embed)

    @commands.command(name="remtbr")
    async def remtbr(self, ctx, categoria: str, *, livro: str):
        cat = normalizar_categoria(categoria)
        if cat not in dados["tbr_por_mes"]:
            return await ctx.send("❌ Categoria inválida.")
        livro_norm = normalizar_titulo(livro)
        existente = buscar_livro_case_insensitive(dados["tbr_por_mes"][cat], livro_norm) or buscar_livro_case_insensitive(dados["tbr_por_mes"][cat], livro)
        if not existente:
            return await ctx.send(f"❌ *{livro}* não foi encontrado em **{cat}**.")
        dados["tbr_por_mes"][cat].remove(existente)
        guardar_dados()
        await ctx.send(f"🗑️ *{existente}* removido com sucesso de **{cat}**.")

    @commands.command(name="remtbrpos")
    async def remtbrpos(self, ctx, categoria: str, posicao: int):
        cat = normalizar_categoria(categoria)
        if cat not in dados["tbr_por_mes"]:
            return await ctx.send("❌ Categoria inválida.")
        if posicao < 1 or posicao > len(dados["tbr_por_mes"][cat]):
            return await ctx.send(f"❌ Posição inválida. A lista tem {len(dados['tbr_por_mes'][cat])} livros.")
        removido = dados["tbr_por_mes"][cat].pop(posicao - 1)
        guardar_dados()
        await ctx.send(f"🗑️ *{removido}* removido da posição **{posicao}** em **{cat}**.")

    @commands.command(name="limpartbr")
    async def limpartbr(self, ctx, categoria: str):
        cat = normalizar_categoria(categoria)
        if cat not in dados["tbr_por_mes"]:
            return await ctx.send("❌ Categoria inválida.")
        if not dados["tbr_por_mes"][cat]:
            return await ctx.send(f"📭 A categoria **{cat}** já está vazia.")
        await ctx.send(f"⚠️ Vou remover **{len(dados['tbr_por_mes'][cat])}** livros de **{cat}**.\nTens a certeza? Responde com `sim` em 30 segundos.")
        def check(m): return m.author == ctx.author and m.content.lower() in ["sim", "s", "yes", "y"]
        try:
            await self.bot.wait_for('message', timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("❌ Operação cancelada.")
        dados["tbr_por_mes"][cat] = []
        guardar_dados()
        await ctx.send(f"🗑️ Categoria **{cat}** foi limpa com sucesso!")


async def setup(bot):
    await bot.add_cog(TBRCog(bot))
