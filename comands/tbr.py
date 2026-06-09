import discord
from discord.ext import commands
import random
import calendar
import logging
from typing import Optional

import config
from storage import dados, guardar_dados
from utils import (
    livro_completo, normalizar_categoria, livros_tbr_flat, numero_mes,
    hoje_str, este_ano, adicionar_livro_a_tbr_mes, enviar_mensagem_longa,
    buscar_livro_case_insensitive, normalizar_titulo
)
from ai import detetar_serie
from images import desenhar_calendario_leituras, Image
from views import ViewConfirmarDuplicado

logger = logging.getLogger('CosmoBot')


class TBRCog(commands.Cog):
    """Comandos de TBR e Planeamento"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addtbr", help="Adiciona um livro à TBR geral ou mensal.")
    async def adicionar_tbr_mes(self, ctx: commands.Context, categoria: Optional[str] = None, *, livro: Optional[str] = None):
        if not categoria:
            return await ctx.send("❌ Diz-me o livro que queres adicionar. Exemplo: `!addtbr Nome do Livro`")

        cat_sugerida = normalizar_categoria(categoria)

        if cat_sugerida in dados["tbr_por_mes"]:
            if not livro:
                return await ctx.send(
                    f"❌ Falta o nome do livro para adicionar a **{cat_sugerida}**.\n"
                    f'Exemplo: `!addtbr {cat_sugerida} "Título - Autor"`'
                )
            cat = cat_sugerida
            texto_livro = livro.strip()
        else:
            cat = "Geral"
            texto_livro = f"{categoria} {livro or ''}".strip()

        try:
            titulo_livro = livro_completo(texto_livro)
        except ValueError:
            return await ctx.send(
                '❌ O formato tem de incluir autor: **"Título - Autor"**.\n'
                'Exemplo: `!addtbr "Quarta Asa - Rebecca Yarros"`'
            )

        ja_existe = any(
            titulo_livro.lower().strip() == item.lower().strip()
            for item in livros_tbr_flat()
        )
        
        livro_similar = None
        if not ja_existe:
            import unicodedata
            for item in livros_tbr_flat():
                item_norm = unicodedata.normalize('NFKD', item.lower()).encode('ASCII', 'ignore').decode()
                livro_norm = unicodedata.normalize('NFKD', titulo_livro.lower()).encode('ASCII', 'ignore').decode()
                if item_norm == livro_norm:
                    ja_existe = True
                    livro_similar = item
                    break
        
        if ja_existe:
            livro_similar = livro_similar if livro_similar else next((item for item in livros_tbr_flat() if item.lower().strip() == titulo_livro.lower().strip()), titulo_livro)
            view = ViewConfirmarDuplicado(titulo_livro, livro_similar, cat, ctx.author.id)
            await ctx.send(
                f"⚠️ **Atenção!** O livro **{titulo_livro}** é muito semelhante a:\n"
                f"📖 **{livro_similar}**\n\n"
                f"Queres mesmo adicionar na mesma?",
                view=view
            )
            return

        dados["tbr_por_mes"][cat].append(titulo_livro)
        guardar_dados()

        await ctx.send(f"📅 **{titulo_livro}** adicionado com sucesso a **{cat}**.")

        await ctx.send("🔍 A verificar se pertence a uma série...")
        
        sequencias = await detetar_serie(titulo_livro)
        
        if sequencias:
            idx_mes_atual = config.MESES_ORDEM.index(cat) if cat in config.MESES_ORDEM else datetime.now().month - 1
            if cat == "Geral":
                idx_mes_atual = datetime.now().month - 1
            
            mensagens = []
            for i, proximo_livro in enumerate(sequencias):
                idx_destino = (idx_mes_atual + 1 + i) % 12
                mes_destino = config.MESES_ORDEM[idx_destino]
                
                ja_existe = any(proximo_livro.lower().strip() == x.lower().strip() for x in livros_tbr_flat())
                
                if not ja_existe:
                    dados["tbr_por_mes"][mes_destino].append(proximo_livro)
                    mensagens.append(f"• **{proximo_livro}** agendado para **{mes_destino}**")
            
            if mensagens:
                guardar_dados()
                await ctx.send(
                    "🧬 **Série detetada!** Sequências agendadas automaticamente:\n" +
                    "\n".join(mensagens)
                )
            else:
                await ctx.send("📚 Não foram detetadas sequências novas para esta série.")
        else:
            await ctx.send("📚 Não foi detetada uma série associada a este livro.")

    @commands.command(name="tbr", help="Sorteia a TBR do mês, tranca até ler tudo e coloca no calendário.")
    async def sortear_tbr_mes(self, ctx: commands.Context, mes: str, extras: int = 2):
        from utils import sorteio_mes_ativo
        
        mes_cap = normalizar_categoria(mes)
        if mes_cap not in config.MESES_ORDEM:
            return await ctx.send("❌ Mês inválido.")

        if extras < 0:
            return await ctx.send("❌ O número de extras não pode ser negativo.")

        sorteio_ativo = sorteio_mes_ativo(mes_cap)
        if sorteio_ativo:
            pendentes = sorteio_ativo.get("pendentes", sorteio_ativo.get("livros", []))
            lista = "\n".join(f"• {livro}" for livro in pendentes)
            return await ctx.send(
                f"🔒 O sorteio de **{mes_cap}** está trancado até leres todos os livros.\n"
                f"Faltam:\n{lista}\n\nUsa `!lido \"Título - Autor\"` à medida que fores terminando."
            )

        obrigatorios = list(dados["tbr_por_mes"][mes_cap])
        obrigatorios_norm = {livro.lower().strip() for livro in obrigatorios}
        geral_disponivel = [
            livro
            for livro in dados["tbr_por_mes"]["Geral"]
            if livro.lower().strip() not in obrigatorios_norm
        ]
        extras_sorteados = random.sample(geral_disponivel, min(extras, len(geral_disponivel)))
        livros_sorteio = obrigatorios + extras_sorteados

        if not livros_sorteio:
            return await ctx.send(f"📭 Não tens livros planeados para {mes_cap} nem na lista Geral.")

        dados["sorteios_mes"][mes_cap] = {
            "livros": livros_sorteio,
            "lidos": [],
            "data_sorteio": hoje_str(),
            "ano": int(este_ano()),
        }
        guardar_dados()

        ano = int(este_ano())
        mes_num = numero_mes(mes_cap)
        _, dias_no_mes = calendar.monthrange(ano, mes_num)
        dias_uteis = [d for d in range(1, dias_no_mes + 1) if calendar.weekday(ano, mes_num, d) < 5]
        if not dias_uteis:
            dias_uteis = list(range(1, dias_no_mes + 1))

        passo = max(1, len(dias_uteis) // max(len(livros_sorteio), 1))
        for idx, livro in enumerate(livros_sorteio):
            dia = dias_uteis[min(idx * passo, len(dias_uteis) - 1)]
            data_meta = f"{dia:02d}/{mes_num:02d}/{ano}"
            dados["lembretes_metas"].append({
                "data": data_meta,
                "livro": livro,
                "meta": f"Iniciar/concluir leitura de {livro}",
                "canal_id": ctx.channel.id,
                "avisado": False,
                "tipo": "sorteio_tbr",
            })

        guardar_dados()

        mensagem = f"🎲 **TBR de {mes_cap} sorteada e trancada**\n"
        mensagem += "\n📌 **Livros deste mês:**\n"
        mensagem += "\n".join(f"• {livro}" for livro in livros_sorteio)
        mensagem += "\n\n🔒 Novo sorteio só depois de marcares todos como lidos com `!lido`."

        await enviar_mensagem_longa(ctx, mensagem)

        if Image is not None:
            try:
                imagem = desenhar_calendario_leituras(mes_cap, ano)
                ficheiro = discord.File(imagem, filename=f"tbr-{mes_cap.lower()}-{ano}.png")
                await ctx.send(f"🗓️ Calendário de leituras de **{mes_cap}**:", file=ficheiro)
            except Exception as e:
                logger.warning(f"Erro ao gerar calendário TBR: {e}")

    @commands.command(name="verbar", help="Mostra toda a TBR organizada por mês (com bullet points).")
    async def ver_tbr_completa(self, ctx: commands.Context):
        embed = discord.Embed(
            title=f"📋 PLANEAMENTO DE TBR ({este_ano()})",
            description="A tua lista de leituras organizada por mês",
            color=discord.Color.purple()
        )
        
        if dados["tbr_por_mes"]["Geral"]:
            lista_geral = "\n".join(f"• {livro}" for livro in dados["tbr_por_mes"]["Geral"])
            if len(lista_geral) > 1000:
                lista_geral = lista_geral[:1000] + "..."
            embed.add_field(name="🌎 Geral", value=lista_geral, inline=False)
        
        for mes in config.MESES_ORDEM:
            if dados["tbr_por_mes"][mes]:
                lista_mes = "\n".join(f"• {livro}" for livro in dados["tbr_por_mes"][mes])
                if len(lista_mes) > 1000:
                    lista_mes = lista_mes[:1000] + "..."
                embed.add_field(name=f"📅 {mes}", value=lista_mes, inline=False)
        
        if not any(dados["tbr_por_mes"].values()):
            embed.description = "📭 A tua TBR está vazia. Adiciona livros com `!addtbr`!"
        
        await ctx.send(embed=embed)

    @commands.command(name="remtbr", help="Remove um livro da TBR.")
    async def remover_tbr_mes(self, ctx: commands.Context, categoria: str, *, livro: str):
        cat = normalizar_categoria(categoria)

        if cat not in dados["tbr_por_mes"]:
            return await ctx.send("❌ Categoria inválida.")
        
        livro_normalizado = normalizar_titulo(livro)
        
        existente = buscar_livro_case_insensitive(dados["tbr_por_mes"][cat], livro_normalizado)
        
        if not existente:
            existente = buscar_livro_case_insensitive(dados["tbr_por_mes"][cat], livro)
        
        if not existente:
            lista = "\n".join(f"• {l}" for l in dados["tbr_por_mes"][cat][:10])
            return await ctx.send(
                f"❌ *{livro}* não foi encontrado em **{cat}**.\n\n"
                f"**Livros em {cat}:**\n{lista}"
            )

        dados["tbr_por_mes"][cat].remove(existente)
        guardar_dados()
        await ctx.send(f"🗑️ *{existente}* removido com sucesso de **{cat}**.")

    @commands.command(name="remtbrpos", help="Remove um livro da TBR por posição. Ex: !remtbrpos Junho 2")
    async def remover_tbr_por_posicao(self, ctx: commands.Context, categoria: str, posicao: int):
        cat = normalizar_categoria(categoria)
        
        if cat not in dados["tbr_por_mes"]:
            return await ctx.send("❌ Categoria inválida.")
        
        if posicao < 1 or posicao > len(dados["tbr_por_mes"][cat]):
            return await ctx.send(f"❌ Posição inválida. A lista tem {len(dados['tbr_por_mes'][cat])} livros.")
        
        livro_removido = dados["tbr_por_mes"][cat].pop(posicao - 1)
        guardar_dados()
        
        await ctx.send(f"🗑️ *{livro_removido}* removido da posição **{posicao}** em **{cat}**.")

    @commands.command(name="limpartbr", help="Remove TODOS os livros de uma categoria. Ex: !limpartbr Junho")
    async def limpar_tbr_categoria(self, ctx: commands.Context, categoria: str):
        cat = normalizar_categoria(categoria)
        
        if cat not in dados["tbr_por_mes"]:
            return await ctx.send("❌ Categoria inválida.")
        
        if not dados["tbr_por_mes"][cat]:
            return await ctx.send(f"📭 A categoria **{cat}** já está vazia.")
        
        await ctx.send(
            f"⚠️ Vou remover **{len(dados['tbr_por_mes'][cat])}** livros de **{cat}**.\n"
            f"Tens a certeza? Responde com `sim` em 30 segundos."
        )
        
        def check(m):
            return m.author == ctx.author and m.content.lower() in ["sim", "s", "yes", "y"]
        
        try:
            await self.bot.wait_for('message', timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("❌ Operação cancelada.")
        
        dados["tbr_por_mes"][cat] = []
        guardar_dados()
        
        await ctx.send(f"🗑️ Categoria **{cat}** foi limpa com sucesso!")


async def setup(bot):
    await bot.add_cog(TBRCog(bot))