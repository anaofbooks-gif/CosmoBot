import discord
from discord.ext import commands
import logging

import config
from storage import dados, guardar_dados, livros_tbr_flat
from utils import formatar_livro, livros_bem_avaliados, garantir_canal
from ai import ai_json_com_retry, validar_resposta_ia_pydantic, validar_resposta_ia
from models import RespostaRecomendacoes
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
        favs_texto = "\n".join(f"- {l['titulo']} ({l['nota']:g}⭐, género: {l.get('genero', 'N/D')})" for l in favoritos)
        prompt = f"""
You are a literary curator. The reader loved these books (rated 4 stars or higher). Suggest NEW books with similar tone, genre, pacing and emotional impact:
{favs_texto}

Rules:
- Recommend books similar to the highly-rated titles above.
- Do NOT suggest books already in this TBR list: [{', '.join(tbr_atual) or 'Nenhum'}].
- Do NOT suggest books already shown and dismissed: [{', '.join(vistos) or 'Nenhum'}].

Write all descriptive text in European Portuguese (pt-PT) or English — never Brazilian Portuguese.

Respond only with valid JSON in this structure:
{{
  "livros": [
    {{
      "titulo": "Book Title",
      "autor": "Author Name",
      "data_publicacao": "Month/Year or DD/MM/YYYY",
      "genero": "Main Genre",
      "subgenero": "Subgenre",
      "porque_ler": "Short convincing text in pt-PT or English",
      "link_capa": "https://..."
    }}
  ]
}}

Suggest exactly 3 real books. Always include author and title separately.
"""
        try:
            resposta = await ai_json_com_retry(prompt)
            validada = validar_resposta_ia_pydantic(resposta, RespostaRecomendacoes) or validar_resposta_ia(resposta, ["livros"])
            livros_sugeridos = validada.get("livros", []) if isinstance(validada, dict) else [l.dict() for l in validada.livros]
            if not livros_sugeridos:
                return await ctx.send("❌ Não consegui gerar sugestões válidas.")
            await canal.send("✨ **A TUA REVISTA LITERÁRIA PERSONALIZADA** ✨\n*Sugestões baseadas nos teus livros com 4⭐ ou mais:*\n" + "\n".join(f"• {l['titulo']} ({l['nota']:g}⭐)" for l in favoritos))
            titulos_botoes = []
            for livro in livros_sugeridos:
                titulo = livro.get("titulo", "Sem título")
                autor = livro.get("autor", "Desconhecido")
                titulo_completo = formatar_livro(titulo, autor)
                if titulo_completo.lower().strip() in {v.lower().strip() for v in vistos}:
                    continue
                titulos_botoes.append(titulo_completo)
                embed = discord.Embed(title=f"📖 {titulo_completo}", description=f"**Autor:** {autor}\n\n{livro.get('porque_ler', '')}", color=discord.Color.from_rgb(255, 182, 193))
                embed.add_field(name="📅 Publicação", value=livro.get("data_publicacao", "Desconhecida"), inline=True)
                embed.add_field(name="🎭 Género", value=livro.get("genero", "N/D"), inline=True)
                embed.add_field(name="🧬 Subgénero", value=livro.get("subgenero", "N/D"), inline=True)
                if livro.get("link_capa", "").startswith("http"):
                    embed.set_image(url=livro["link_capa"])
                await canal.send(embed=embed)
            if not titulos_botoes:
                return await ctx.send("❌ Todas as sugestões geradas já tinham sido vistas antes.")
            await canal.send("✨ **Adiciona as tuas escolhas instantaneamente:**", view=ViewSugestoes(titulos_botoes, titulos_botoes))
            await ctx.send(f"✅ Painel visual gerado com sucesso em {canal.mention}.")
        except Exception as e:
            logger.exception(f"Erro ao processar recomendações: {e}")
            await ctx.send(f"❌ Erro ao processar recomendações: {e}")

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
