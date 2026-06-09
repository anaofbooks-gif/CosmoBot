import discord
from discord.ext import commands
import logging

import config
from storage import dados, guardar_dados
from utils import formatar_livro, livros_tbr_flat, livros_bem_avaliados, garantir_canal
from ai import gerar_recomendacoes
from views import ViewSugestoes

logger = logging.getLogger('CosmoBot')


class RecommendationsCog(commands.Cog):
    """Comandos de recomendações"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="recomendar", help="Sugere livros com base nos teus lidos avaliados com 4⭐ ou mais.")
    async def curadoria_inteligente(self, ctx: commands.Context):
        guild = ctx.guild
        if not guild:
            return await ctx.send("❌ Este comando só pode ser usado dentro de um servidor.")

        favoritos = livros_bem_avaliados(minimo=4.0)
        if not favoritos:
            return await ctx.send(
                "📭 Ainda não tens livros avaliados com **4 estrelas ou mais**.\n"
                "Regista leituras com `!lido \"Título - Autor\"` e avalia com o menu de estrelas ou `!avaliar 4.5`."
            )

        nome_canal_sugestoes = "sugestoes-leitura"
        canal_sugestoes = await garantir_canal(guild, nome_canal_sugestoes)

        await ctx.send(
            f"🔍 A preparar sugestões com base em **{len(favoritos)}** livro(s) bem avaliado(s) "
            f"em {canal_sugestoes.mention}..."
        )

        tbr_atual = livros_tbr_flat()
        vistos = dados.get("sugestoes_vistas", [])

        linhas_favoritos = []
        for livro in favoritos:
            genero = livro.get("genero", "N/D")
            linhas_favoritos.append(
                f"- {livro['titulo']} ({livro['nota']:g}⭐, género: {genero})"
            )
        favs_texto = "\n".join(linhas_favoritos)
        tbr_texto = ", ".join(tbr_atual) if tbr_atual else "Nenhum"
        vistos_texto = ", ".join(vistos) if vistos else "Nenhum"

        try:
            livros_sugeridos = await gerar_recomendacoes(favs_texto, tbr_texto, vistos_texto)

            if not livros_sugeridos:
                return await ctx.send("❌ Não consegui gerar sugestões válidas.")

            base_favoritos = "\n".join(f"• {l['titulo']} ({l['nota']:g}⭐)" for l in favoritos)
            await canal_sugestoes.send(
                "✨ **A TUA REVISTA LITERÁRIA PERSONALIZADA** ✨\n"
                "*Sugestões baseadas nos teus livros com 4⭐ ou mais:*\n"
                f"{base_favoritos}"
            )

            titulos_botoes = []

            for livro in livros_sugeridos:
                titulo = livro.get("titulo", "Sem título")
                autor = livro.get("autor", "Desconhecido")
                titulo_completo = formatar_livro(titulo, autor)
                data_publicacao = livro.get("data_publicacao", "Desconhecida")
                genero = livro.get("genero", "N/D")
                subgenero = livro.get("subgenero", "N/D")
                porque_ler = livro.get("porque_ler", "Uma sugestão alinhada com o teu gosto.")
                link_capa = livro.get("link_capa", "")

                if titulo_completo.lower().strip() in {v.lower().strip() for v in vistos}:
                    continue

                titulos_botoes.append(titulo_completo)

                embed = discord.Embed(
                    title=f"📖 {titulo_completo}",
                    description=f"**Autor:** {autor}\n\n{porque_ler}",
                    color=discord.Color.from_rgb(255, 182, 193)
                )
                embed.add_field(name="📅 Publicação", value=data_publicacao, inline=True)
                embed.add_field(name="🎭 Género", value=genero, inline=True)
                embed.add_field(name="🧬 Subgénero", value=subgenero, inline=True)

                if isinstance(link_capa, str) and link_capa.startswith("http"):
                    embed.set_image(url=link_capa)

                embed.set_footer(text="Gostaste? Guarda na tua lista clicando no painel abaixo.")
                await canal_sugestoes.send(embed=embed)

            if not titulos_botoes:
                return await ctx.send("❌ Todas as sugestões geradas já tinham sido vistas antes.")

            await canal_sugestoes.send(
                "✨ **Adiciona as tuas escolhas instantaneamente:**",
                view=ViewSugestoes(titulos_botoes, titulos_botoes),
            )
            await ctx.send(f"✅ Painel visual gerado com sucesso em {canal_sugestoes.mention}.")

        except Exception as e:
            logger.exception(f"Erro ao processar recomendações: {e}")
            await ctx.send(f"❌ Erro ao processar recomendações: {e}")

    @commands.command(name="marcarsugestoes", help="Marca sugestões como já vistas para não voltarem a aparecer.")
    async def marcar_sugestoes_vistas(self, ctx: commands.Context, *, titulos: str):
        novos = 0
        vistos = {v.lower().strip() for v in dados.setdefault("sugestoes_vistas", [])}
        for titulo in [t.strip() for t in titulos.split("|") if t.strip()]:
            if titulo.lower() not in vistos:
                dados["sugestoes_vistas"].append(titulo)
                vistos.add(titulo.lower())
                novos += 1
        guardar_dados()
        await ctx.send(f"✅ **{novos}** sugestão(ões) arquivada(s).")


async def setup(bot):
    await bot.add_cog(RecommendationsCog(bot))