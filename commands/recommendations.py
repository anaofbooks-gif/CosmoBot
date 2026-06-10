import discord
from discord.ext import commands
import logging

import config
from storage import dados, guardar_dados, livros_tbr_flat
from utils import formatar_livro, livros_bem_avaliados, garantir_canal
from ai import ai_json_hibrido
from views import ViewSugestoes

logger = logging.getLogger('CosmoBot')


class RecommendationsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="recomendar")
    async def recomendar(self, ctx):
        guild = ctx.guild
        if not guild:
            return await ctx.send("❌ Este comando só pode ser usado dentro de um servidor.")

        favoritos = livros_bem_avaliados(dados, 4.0)
        if not favoritos:
            return await ctx.send("📭 Ainda não tens livros avaliados com **4 estrelas ou mais**.\nRegista leituras com `!lido \"Título - Autor\"` e avalia com o menu de estrelas ou `!avaliar 4.5`.")

        canal = await garantir_canal(guild, "sugestoes-leitura")
        await ctx.send(f"🔍 A preparar sugestões com base em **{len(favoritos)}** livro(s) bem avaliado(s) em {canal.mention}...")

        tbr_atual = livros_tbr_flat()
        vistos = dados.get("sugestoes_vistas", [])

        favs_texto = []
        for l in favoritos[:10]:
            genero = l.get('genero', 'N/D')
            favs_texto.append(f"- {l['titulo']} (⭐{l['nota']:.1f}, género: {genero})")
        favs_texto_str = "\n".join(favs_texto)

        tbr_str = ', '.join(tbr_atual[:15]) if tbr_atual else 'Nenhum'
        vistos_str = ', '.join(vistos[:15]) if vistos else 'Nenhum'

        prompt = f"""És um curador literário.

O leitor adorou estes livros (4+ estrelas):
{favs_texto_str}

Sugere 3 livros novos e SEMELHANTES.

REGRAS:
- Não sugerir livros já na TBR: {tbr_str}
- Não sugerir livros já vistos: {vistos_str}
- Livros devem ser reais

RESPONDE APENAS COM JSON:
{{"livros": [
  {{"titulo": "Nome", "autor": "Autor", "porque_ler": "Motivo curto"}}
]}}"""

        try:
            logger.info("📤 Enviando prompt para IA...")
            resposta = await ai_json_hibrido(prompt)
            logger.info(f"📥 Resposta da IA: {resposta}")

            livros_sugeridos = []
            if isinstance(resposta, dict):
                if "livros" in resposta:
                    livros_sugeridos = resposta["livros"]
                elif "recomendacoes" in resposta:
                    livros_sugeridos = resposta["recomendacoes"]

            if not livros_sugeridos:
                logger.warning(f"Nenhum livro encontrado na resposta: {resposta}")
                return await ctx.send("❌ Não consegui gerar sugestões válidas. Tenta novamente daqui a pouco.")

            await canal.send("✨ **A TUA REVISTA LITERÁRIA PERSONALIZADA** ✨\n*Sugestões baseadas nos teus livros com 4⭐ ou mais:*\n" + "\n".join(f"• {l['titulo']} ({l.get('nota', 0):.1f}⭐)" for l in favoritos[:5]))

            titulos_botoes = []
            for livro in livros_sugeridos[:3]:
                titulo = livro.get("titulo", "")
                autor = livro.get("autor", "")
                if not titulo or not autor:
                    continue
                titulo_completo = formatar_livro(titulo, autor)

                if titulo_completo.lower().strip() in {v.lower().strip() for v in vistos}:
                    continue
                if any(titulo_completo.lower().strip() == x.lower().strip() for x in tbr_atual):
                    continue

                titulos_botoes.append(titulo_completo)

                embed = discord.Embed(
                    title=f"📖 {titulo_completo}",
                    description=f"**Autor:** {autor}\n\n{livro.get('porque_ler', 'Uma sugestão alinhada com o teu gosto.')}",
                    color=discord.Color.from_rgb(255, 182, 193)
                )
                embed.add_field(name="📅 Publicação", value=livro.get("data_publicacao", "Desconhecida"), inline=True)
                embed.add_field(name="🎭 Género", value=livro.get("genero", "N/D"), inline=True)
                embed.add_field(name="🧬 Subgénero", value=livro.get("subgenero", "N/D"), inline=True)

                if livro.get("link_capa", "").startswith("http"):
                    embed.set_image(url=livro["link_capa"])

                await canal.send(embed=embed)

            if not titulos_botoes:
                return await ctx.send("❌ Todas as sugestões geradas já tinham sido vistas ou estão na TBR.")

            await canal.send("✨ **Adiciona as tuas escolhas instantaneamente:**", view=ViewSugestoes(titulos_botoes, titulos_botoes))
            await ctx.send(f"✅ Painel visual gerado com sucesso em {canal.mention}!")

        except Exception as e:
            logger.exception(f"Erro ao processar recomendações: {e}")
            await ctx.send(f"❌ Erro ao processar recomendações: {e}")

    @commands.command(name="testeia")
    async def teste_ia(self, ctx):
        """Comando de teste para verificar se a IA está a responder"""
        await ctx.send("🔍 A testar ligação à IA...")

        prompt = 'Responde APENAS com JSON: {"teste": "funcionou"}'

        try:
            resposta = await ai_json_hibrido(prompt)
            await ctx.send(f"✅ IA respondeu: {resposta}")
        except Exception as e:
            await ctx.send(f"❌ Erro na IA: {e}")

    @commands.command(name="marcarsugestoes")
    async def marcar_sugestoes_vistas(self, ctx, *, titulos: str):
        vistos = {v.lower().strip() for v in dados.setdefault("sugestoes_vistas", [])}
        novos = 0
        for titulo in [t.strip() for t in titulos.split("|") if t.strip()]:
            if titulo.lower() not in vistos:
                dados["sugestoes_vistas"].append(titulo)
                vistos.add(titulo.lower())
                novos += 1
        guardar_dados()
        await ctx.send(f"✅ **{novos}** sugestão(ões) arquivada(s).")


async def setup(bot):
    await bot.add_cog(RecommendationsCog(bot))
