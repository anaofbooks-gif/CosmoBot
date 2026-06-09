import discord
from discord.ext import commands
import logging
import re
from collections import Counter

import config
from storage import dados, guardar_dados
from utils import livro_completo, livro_ja_lido, enviar_mensagem_longa, este_ano
from images import analisar_titulo_alfabeto

logger = logging.getLogger('CosmoBot')


class ChallengesCog(commands.Cog):
    """Comandos de desafios (A-Z, estatísticas)"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="alfabeto", help="Mostra o progresso do desafio A-Z.")
    async def ver_desafio_alfabeto(self, ctx: commands.Context):
        preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        msg = f"🔤 **DESAFIO A A Z ({este_ano()})**\n📊 Progresso Geral: **{preenchidas}/26** letras completadas.\n\n"

        for letra, livro in dados["desafio_alfabeto"].items():
            icon = "🟢" if livro != config.VAZIO_ALFABETO else "⚫"
            msg += f"{icon} **{letra}**: {livro}\n"

        await ctx.send(msg)

    @commands.command(name="addletra", help="Adiciona uma letra ao desafio A-Z manualmente.")
    async def adicionar_letra_alfabeto(self, ctx: commands.Context, letra: str, *, livro: str):
        letra = letra.strip().upper()
        
        if len(letra) != 1 or letra not in dados["desafio_alfabeto"]:
            return await ctx.send("❌ Letra inválida. Usa apenas uma letra de A a Z.")
        
        try:
            titulo_completo = livro_completo(livro)
        except ValueError:
            titulo_completo = livro.strip()
        
        if dados["desafio_alfabeto"][letra] != config.VAZIO_ALFABETO:
            return await ctx.send(
                f"⚠️ A letra **{letra}** já está preenchida com:\n"
                f"📖 **{dados['desafio_alfabeto'][letra]}**\n\n"
                f"Usa `!remalfabeto {letra}` primeiro se quiseres substituir."
            )
        
        livro_existe = livro_ja_lido(titulo_completo, dados)
        
        dados["desafio_alfabeto"][letra] = titulo_completo
        guardar_dados()
        
        preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        
        msg = f"🔤 **Letra {letra}** adicionada ao desafio A-Z com:\n📖 {titulo_completo}\n"
        if not livro_existe:
            msg += f"\n⚠️ Este livro **não está no teu histórico de leituras**. Se foi lido, regista-o com `!lido \"{titulo_completo}\"`."
        else:
            msg += f"\n✅ Este livro já consta no teu histórico."
        
        msg += f"\n\n📊 Progresso atual: **{preenchidas}/26** letras."
        
        await ctx.send(msg)

    @commands.command(name="remalfabeto", help="Remove um livro de uma letra do desafio A-Z.")
    async def remover_do_alfabeto(self, ctx: commands.Context, letra: str):
        letra = letra.strip().upper()

        if len(letra) != 1 or letra not in dados["desafio_alfabeto"]:
            return await ctx.send("❌ Letra inválida. Usa apenas uma letra de A a Z. Exemplo: `!remalfabeto B`")

        livro_atual = dados["desafio_alfabeto"][letra]

        if livro_atual == config.VAZIO_ALFABETO:
            preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
            return await ctx.send(
                f"⚫ A letra **{letra}** já estava vazia.\n"
                f"Progresso atual do A-Z: **{preenchidas}/26**. Usa `!alfabeto` para ver a lista completa."
            )

        dados["desafio_alfabeto"][letra] = config.VAZIO_ALFABETO
        guardar_dados()

        preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)

        await ctx.send(
            f"🗑️ A letra **{letra}** foi limpa com sucesso.\n"
            f"Livro removido: **{livro_atual}**\n"
            f"Progresso atual do A-Z: **{preenchidas}/26**."
        )

    @commands.command(name="desafios", help="Mostra o progresso geral dos desafios de leitura.")
    async def ver_progresso_desafios(self, ctx: commands.Context):
        total_lidos = len(dados["livros_lidos"])
        percentagem_anual = min(100, round((total_lidos / config.META_ANUAL) * 100))

        letras_preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        percentagem_az = round((letras_preenchidas / 26) * 100)
        letras_em_falta = [letra for letra, livro in dados["desafio_alfabeto"].items() if livro == config.VAZIO_ALFABETO]

        from utils import livros_tbr_flat
        total_tbr = len(livros_tbr_flat())
        metas_ativas = sum(1 for lembrete in dados["lembretes_metas"] if not lembrete.get("avisado", False))
        livros_avaliados = sum(
            1
            for livro in dados["livros_lidos"]
            if livro.get("estrelas") and livro.get("estrelas") != "Sem avaliação"
        )

        embed = discord.Embed(
            title=f"🏆 PROGRESSO DOS DESAFIOS ({este_ano()})",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="📚 Meta anual",
            value=f"**{total_lidos}/{config.META_ANUAL}** livros lidos ({percentagem_anual}%)",
            inline=False
        )
        embed.add_field(
            name="🔤 Desafio A-Z",
            value=(
                f"**{letras_preenchidas}/26** letras completas ({percentagem_az}%).\n"
                f"Faltam: {', '.join(letras_em_falta) if letras_em_falta else 'nenhuma 🎉'}"
            ),
            inline=False
        )
        embed.add_field(
            name="⭐ Avaliações",
            value=f"**{livros_avaliados}/{total_lidos}** livros lidos avaliados.",
            inline=False
        )
        embed.add_field(
            name="📅 Leituras conjuntas",
            value=f"**{metas_ativas}** metas futuras/pendentes guardadas.",
            inline=False
        )
        embed.add_field(
            name="📌 TBR",
            value=f"**{total_tbr}** livros por ler no planeamento.",
            inline=False
        )
        embed.set_footer(text="Usa !alfabeto para ver o detalhe letra a letra.")

        await ctx.send(embed=embed)

    @commands.command(name="historico", help="Mostra o histórico de leituras (agrupado por ano).")
    async def mostrar_historico(self, ctx: commands.Context):
        if not dados["livros_lidos"]:
            return await ctx.send("📭 O teu histórico de leituras ainda está vazio.")
        
        historico_por_ano = {}
        for livro in dados["livros_lidos"]:
            data_str = livro.get("data_leitura", "Data desconhecida")
            ano = data_str.split("/")[-1] if "/" in data_str else "Desconhecido"
            if ano not in historico_por_ano:
                historico_por_ano[ano] = []
            historico_por_ano[ano].append(livro)
        
        for ano, livros in sorted(historico_por_ano.items(), reverse=True):
            embed = discord.Embed(
                title=f"📜 HISTÓRICO DE LEITURAS - {ano}",
                color=discord.Color.gold()
            )
            
            linhas = []
            for i, l in enumerate(livros, 1):
                genero = l.get("genero", "")
                paginas = l.get("paginas", 0)
                extra = ""
                if genero and genero != "N/D":
                    extra += f" | {genero}"
                if paginas:
                    extra += f" | {paginas} págs."
                linhas.append(f"{i}. {l.get('titulo', 'Sem título')} — {l.get('estrelas', 'Sem avaliação')}{extra}")
            
            if len("\n".join(linhas)) > 4000:
                partes = []
                parte_atual = []
                tamanho_atual = 0
                for linha in linhas:
                    if tamanho_atual + len(linha) + 1 > 3800:
                        partes.append("\n".join(parte_atual))
                        parte_atual = [linha]
                        tamanho_atual = len(linha)
                    else:
                        parte_atual.append(linha)
                        tamanho_atual += len(linha) + 1
                if parte_atual:
                    partes.append("\n".join(parte_atual))
                
                for idx, parte in enumerate(partes):
                    if idx == 0:
                        embed.description = parte
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send(parte)
            else:
                embed.description = "\n".join(linhas)
                await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ChallengesCog(bot))