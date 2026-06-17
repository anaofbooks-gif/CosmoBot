import logging
import discord
from discord.ext import commands

import config
from storage import dados, guardar_dados, livros_tbr_flat
from utils import livro_completo, livro_ja_lido, enviar_mensagem_longa, este_ano, tem_artigo_no_inicio, obter_primeira_letra_sem_artigo, parsear_livro

logger = logging.getLogger('CosmoBot')

class ChallengesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="alfabeto")
    async def alfabeto(self, ctx):
        preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        msg = f"🔤 **DESAFIO A A Z ({este_ano()})**\n📊 Progresso Geral: **{preenchidas}/26** letras completadas.\n\n"
        for letra, livro in dados["desafio_alfabeto"].items():
            icon = "🟢" if livro != config.VAZIO_ALFABETO else "⚫"
            msg += f"{icon} **{letra}**: {livro}\n"
        await ctx.send(msg)

    @commands.command(name="addletra")
    async def addletra(self, ctx, letra: str, *, livro: str):
        letra = letra.strip().upper()
        if len(letra) != 1 or letra not in dados["desafio_alfabeto"]:
            return await ctx.send("❌ Letra inválida. Usa apenas uma letra de A a Z.")

        try:
            titulo_completo = livro_completo(livro)
        except ValueError:
            titulo_completo = livro.strip()

        # 🔥 REGRA DE OURO: Se começar por artigo, rejeita na hora (validação LOCAL)
        if tem_artigo_no_inicio(titulo_completo):
            return await ctx.send(f"❌ O livro **\"{titulo_completo}\"** começa com um artigo definido/indefinido. Pelas regras do desafio, livros com artigos iniciais **NÃO ENTRAM** no Desafio A-Z!")

        # Verifica se a letra está correta
        try:
            titulo_curto, _ = parsear_livro(titulo_completo)
        except ValueError:
            titulo_curto = titulo_completo

        # Se não tiver artigo, obtém a primeira letra
        letra_real = obter_primeira_letra_sem_artigo(titulo_curto)

        if not letra_real:
            return await ctx.send(f"❌ Não foi possível determinar a letra inicial de **{titulo_curto}**.")

        if letra != letra_real:
            return await ctx.send(f"❌ Esse livro começa pela letra **{letra_real}**. Não o podes colocar na letra **{letra}**.")

        if dados["desafio_alfabeto"][letra] != config.VAZIO_ALFABETO:
            return await ctx.send(f"⚠️ A letra **{letra}** já está preenchida com:\n📖 **{dados['desafio_alfabeto'][letra]}**\n\nUsa `!remalfabeto {letra}` primeiro se quiseres substituir.")

        dados["desafio_alfabeto"][letra] = titulo_completo
        guardar_dados()

        preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        msg = f"🔤 **Letra {letra}** adicionada ao desafio A-Z com:\n📖 {titulo_completo}\n"
        msg += f"\n📊 Progresso atual: **{preenchidas}/26** letras."
        await ctx.send(msg)

    @commands.command(name="remalfabeto")
    async def remalfabeto(self, ctx, letra: str):
        letra = letra.strip().upper()
        if len(letra) != 1 or letra not in dados["desafio_alfabeto"]:
            return await ctx.send("❌ Letra inválida. Usa apenas uma letra de A a Z.")

        livro_atual = dados["desafio_alfabeto"][letra]
        if livro_atual == config.VAZIO_ALFABETO:
            preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
            return await ctx.send(f"⚫ A letra **{letra}** já estava vazia.\nProgresso atual do A-Z: **{preenchidas}/26**. Usa `!alfabeto` para ver a lista completa.")

        dados["desafio_alfabeto"][letra] = config.VAZIO_ALFABETO
        guardar_dados()
        preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        await ctx.send(f"🗑️ A letra **{letra}** foi limpa com sucesso.\nProgresso atual do A-Z: **{preenchidas}/26**.")

    @commands.command(name="desafios")
    async def desafios(self, ctx):
        total_lidos = len(dados["livros_lidos"])
        letras_preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        letras_em_falta = [letra for letra, livro in dados["desafio_alfabeto"].items() if livro == config.VAZIO_ALFABETO]
        total_tbr = len(livros_tbr_flat())
        metas_ativas = sum(1 for lembrete in dados["lembretes_metas"] if not lembrete.get("avisado", False))
        livros_avaliados = sum(1 for livro in dados["livros_lidos"] if livro.get("estrelas") and livro.get("estrelas") != "Sem avaliação")

        embed = discord.Embed(title=f"🏆 PROGRESSO DOS DESAFIOS ({este_ano()})", color=discord.Color.gold())
        embed.add_field(name="📚 Meta anual", value=f"**{total_lidos}/{config.META_ANUAL}** livros lidos ({min(100, round(total_lidos / config.META_ANUAL * 100))}%)", inline=False)
        embed.add_field(name="🔤 Desafio A-Z", value=f"**{letras_preenchidas}/26** letras completas ({round(letras_preenchidas / 26 * 100)}%).\nFaltam: {', '.join(letras_em_falta) if letras_em_falta else 'nenhuma 🎉'}", inline=False)
        embed.add_field(name="⭐ Avaliações", value=f"**{livros_avaliados}/{total_lidos}** livros lidos avaliados.", inline=False)
        embed.add_field(name="📅 Leituras conjuntas", value=f"**{metas_ativas}** metas futuras/pendentes guardadas.", inline=False)
        embed.add_field(name="📌 TBR", value=f"**{total_tbr}** livros por ler no planeamento.", inline=False)
        embed.set_footer(text="Usa !alfabeto para ver o detalhe letra a letra.")
        await ctx.send(embed=embed)

    @commands.command(name="historico")
    async def historico(self, ctx):
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
            embed = discord.Embed(title=f"📜 HISTÓRICO DE LEITURAS - {ano}", color=discord.Color.gold())
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
