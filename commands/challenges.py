import discord
from discord.ext import commands
from collections import Counter

import config
from storage import dados, guardar_dados
from utils import livro_completo, livro_ja_lido, enviar_mensagem_longa, este_ano, livros_tbr_flat


class ChallengesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="alfabeto")
    async def alfabeto(self, ctx):
        preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        msg = f"🔤 **DESAFIO A A Z ({este_ano()})**\n📊 Progresso Geral: **{preenchidas}/26** letras completadas.\n\n"
        for letra, livro in dados["desafio_alfabeto"].items():
            msg += f"{'🟢' if livro != config.VAZIO_ALFABETO else '⚫'} **{letra}**: {livro}\n"
        await ctx.send(msg)

    @commands.command(name="addletra")
    async def addletra(self, ctx, letra: str, *, livro: str):
        letra = letra.strip().upper()
        if len(letra) != 1 or letra not in dados["desafio_alfabeto"]:
            return await ctx.send("❌ Letra inválida. Usa apenas uma letra de A a Z.")
        try:
            titulo = livro_completo(livro)
        except ValueError:
            titulo = livro.strip()
        if dados["desafio_alfabeto"][letra] != config.VAZIO_ALFABETO:
            return await ctx.send(f"⚠️ A letra **{letra}** já está preenchida com:\n📖 **{dados['desafio_alfabeto'][letra]}**\n\nUsa `!remalfabeto {letra}` primeiro se quiseres substituir.")
        dados["desafio_alfabeto"][letra] = titulo
        guardar_dados()
        preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        msg = f"🔤 **Letra {letra}** adicionada ao desafio A-Z com:\n📖 {titulo}\n"
        if not livro_ja_lido(titulo, dados):
            msg += f"\n⚠️ Este livro **não está no teu histórico de leituras**. Se foi lido, regista-o com `!lido \"{titulo}\"`."
        else:
            msg += f"\n✅ Este livro já consta no teu histórico."
        msg += f"\n\n📊 Progresso atual: **{preenchidas}/26** letras."
        await ctx.send(msg)

    @commands.command(name="remalfabeto")
    async def remalfabeto(self, ctx, letra: str):
        letra = letra.strip().upper()
        if len(letra) != 1 or letra not in dados["desafio_alfabeto"]:
            return await ctx.send("❌ Letra inválida. Usa apenas uma letra de A a Z.")
        if dados["desafio_alfabeto"][letra] == config.VAZIO_ALFABETO:
            preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
            return await ctx.send(f"⚫ A letra **{letra}** já estava vazia.\nProgresso atual do A-Z: **{preenchidas}/26**. Usa `!alfabeto` para ver a lista completa.")
        dados["desafio_alfabeto"][letra] = config.VAZIO_ALFABETO
        guardar_dados()
        preenchidas = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        await ctx.send(f"🗑️ A letra **{letra}** foi limpa com sucesso.\nProgresso atual do A-Z: **{preenchidas}/26**.")

    @commands.command(name="desafios")
    async def desafios(self, ctx):
        total = len(dados["livros_lidos"])
        letras = sum(1 for v in dados["desafio_alfabeto"].values() if v != config.VAZIO_ALFABETO)
        tbr_total = len(livros_tbr_flat())
        metas = sum(1 for l in dados["lembretes_metas"] if not l.get("avisado", False))
        avaliados = sum(1 for l in dados["livros_lidos"] if l.get("estrelas") and l.get("estrelas") != "Sem avaliação")
        embed = discord.Embed(title=f"🏆 PROGRESSO DOS DESAFIOS ({este_ano()})", color=discord.Color.gold())
        embed.add_field(name="📚 Meta anual", value=f"**{total}/{config.META_ANUAL}** livros lidos ({min(100, round(total / config.META_ANUAL * 100))}%)", inline=False)
        embed.add_field(name="🔤 Desafio A-Z", value=f"**{letras}/26** letras completas ({round(letras / 26 * 100)}%).\nFaltam: {', '.join([l for l, v in dados['desafio_alfabeto'].items() if v == config.VAZIO_ALFABETO]) or 'nenhuma 🎉'}", inline=False)
        embed.add_field(name="⭐ Avaliações", value=f"**{avaliados}/{total}** livros lidos avaliados.", inline=False)
        embed.add_field(name="📅 Leituras conjuntas", value=f"**{metas}** metas futuras/pendentes guardadas.", inline=False)
        embed.add_field(name="📌 TBR", value=f"**{tbr_total}** livros por ler no planeamento.", inline=False)
        embed.set_footer(text="Usa !alfabeto para ver o detalhe letra a letra.")
        await ctx.send(embed=embed)

    @commands.command(name="historico")
    async def historico(self, ctx):
        if not dados["livros_lidos"]:
            return await ctx.send("📭 O teu histórico de leituras ainda está vazio.")
        por_ano = {}
        for livro in dados["livros_lidos"]:
            data = livro.get("data_leitura", "Data desconhecida")
            ano = data.split("/")[-1] if "/" in data else "Desconhecido"
            por_ano.setdefault(ano, []).append(livro)
        for ano, livros in sorted(por_ano.items(), reverse=True):
            embed = discord.Embed(title=f"📜 HISTÓRICO DE LEITURAS - {ano}", color=discord.Color.gold())
            linhas = []
            for i, l in enumerate(livros, 1):
                extra = ""
                if l.get("genero") and l.get("genero") != "N/D":
                    extra += f" | {l.get('genero')}"
                if l.get("paginas"):
                    extra += f" | {l.get('paginas')} págs."
                linhas.append(f"{i}. {l.get('titulo', 'Sem título')} — {l.get('estrelas', 'Sem avaliação')}{extra}")
            if len("\n".join(linhas)) > 4000:
                partes = []
                atual = []
                tam = 0
                for linha in linhas:
                    if tam + len(linha) + 1 > 3800:
                        partes.append("\n".join(atual))
                        atual = [linha]
                        tam = len(linha)
                    else:
                        atual.append(linha)
                        tam += len(linha) + 1
                if atual:
                    partes.append("\n".join(atual))
                embed.description = partes[0]
                await ctx.send(embed=embed)
                for parte in partes[1:]:
                    await ctx.send(parte)
            else:
                embed.description = "\n".join(linhas)
                await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ChallengesCog(bot))
