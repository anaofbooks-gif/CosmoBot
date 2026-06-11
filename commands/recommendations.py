import logging
import discord
from discord.ext import commands

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
        """
        Recomenda livros baseados nos teus favoritos.
        As recomendações aparecem em Português Europeu e Inglês.
        """
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

        # Prompt bilíngue - pede à IA que devolva os campos em ambos os idiomas
        prompt = f"""És um curador literário especializado em recomendações detalhadas.

O leitor adorou estes livros (4+ estrelas):
{favs_texto_str}

Sugere 3 livros NOVOS e SEMELHANTES.

REGRAS OBRIGATÓRIAS:
- Não sugerir livros já na TBR: {tbr_str}
- Não sugerir livros já vistos: {vistos_str}
- Livros devem ser REAIS e existentes
- Para CADA livro, fornece TODOS os campos abaixo em AMBOS os idiomas (Português Europeu e Inglês)

RESPONDE APENAS COM JSON neste formato EXATO:
{{"livros": [
  {{
    "titulo": "Nome exato do livro",
    "autor": "Nome do autor",
    "data_publicacao": "Ano de lançamento (ex: 2021)",
    "pt": {{
      "genero": "Género em Português Europeu",
      "subgenero": "Subgénero em Português Europeu",
      "porque_ler": "Motivo curto e convincente em Português Europeu (máx 200 caracteres)"
    }},
    "en": {{
      "genre": "Genre in English",
      "subgenre": "Subgenre in English",
      "why_read": "Short convincing reason in English (max 200 chars)"
    }},
    "link_capa": "URL da capa do livro (se conhecer, senão deixar vazio)"
  }}
]}}

IMPORTANTE: 
- Preenche TODOS os campos.
- Se não souber a data, usa "Desconhecido" / "Unknown"
- Se não souber o link da capa, usa ""
- Usa Português Europeu (pt-PT) no campo "pt" - com "género", "porquê", etc.
"""

        try:
            resposta = await ai_json_hibrido(prompt)

            livros_sugeridos = []
            if isinstance(resposta, dict):
                if "livros" in resposta:
                    livros_sugeridos = resposta["livros"]
                elif "recomendacoes" in resposta:
                    livros_sugeridos = resposta["recomendacoes"]

            if not livros_sugeridos:
                return await ctx.send("❌ Não consegui gerar sugestões válidas. Tenta novamente daqui a pouco.")

            # Mensagem de introdução bilíngue
            intro_pt = f"✨ **A TUA REVISTA LITERÁRIA PERSONALIZADA** ✨\n*Sugestões baseadas nos teus livros com 4⭐ ou mais:*\n" + "\n".join(f"• {l['titulo']} ({l.get('nota', 0):.1f}⭐)" for l in favoritos[:5])
            intro_en = f"✨ **YOUR PERSONALIZED LITERARY MAGAZINE** ✨\n*Suggestions based on your 4⭐+ books:*\n" + "\n".join(f"• {l['titulo']} ({l.get('nota', 0):.1f}⭐)" for l in favoritos[:5])
            
            await canal.send(f"{intro_pt}\n\n{intro_en}")

            titulos_botoes = []
            for livro in livros_sugeridos[:3]:
                titulo = livro.get("titulo", "")
                autor = livro.get("autor", "")
                data = livro.get("data_publicacao", "Desconhecida / Unknown")
                link_capa = livro.get("link_capa", "")
                
                # Campos em Português
                pt_data = livro.get("pt", {})
                pt_genero = pt_data.get("genero", "N/D")
                pt_subgenero = pt_data.get("subgenero", "N/D")
                pt_porque = pt_data.get("porque_ler", "Uma sugestão alinhada com o teu gosto.")
                
                # Campos em Inglês
                en_data = livro.get("en", {})
                en_genero = en_data.get("genre", "N/A")
                en_subgenero = en_data.get("subgenre", "N/A")
                en_porque = en_data.get("why_read", "A suggestion aligned with your taste.")

                if not titulo or not autor:
                    continue
                    
                titulo_completo = formatar_livro(titulo, autor)

                if titulo_completo.lower().strip() in {v.lower().strip() for v in vistos}:
                    continue
                if any(titulo_completo.lower().strip() == x.lower().strip() for x in tbr_atual):
                    continue

                titulos_botoes.append(titulo_completo)

                # Embed em Português
                embed_pt = discord.Embed(
                    title=f"📖 {titulo_completo}",
                    description=f"**Autor:** {autor}\n\n📅 **Publicação:** {data}\n\n{pt_porque}",
                    color=discord.Color.from_rgb(255, 182, 193)  # rosa suave
                )
                embed_pt.add_field(name="🎭 Género", value=pt_genero, inline=True)
                embed_pt.add_field(name="🧬 Subgénero", value=pt_subgenero, inline=True)
                embed_pt.set_footer(text="🇵🇹 Português (Europeu)")
                
                if link_capa and link_capa.startswith("http"):
                    embed_pt.set_thumbnail(url=link_capa)

                # Embed em Inglês
                embed_en = discord.Embed(
                    title=f"📖 {titulo_completo}",
                    description=f"**Author:** {autor}\n\n📅 **Publication:** {data}\n\n{en_porque}",
                    color=discord.Color.blue()
                )
                embed_en.add_field(name="🎭 Genre", value=en_genero, inline=True)
                embed_en.add_field(name="🧬 Subgenre", value=en_subgenero, inline=True)
                embed_en.set_footer(text="🇬🇧 English")
                
                if link_capa and link_capa.startswith("http"):
                    embed_en.set_thumbnail(url=link_capa)

                # Envia ambos os embeds
                await canal.send(embed=embed_pt)
                await canal.send(embed=embed_en)

            if not titulos_botoes:
                return await ctx.send("❌ Todas as sugestões geradas já tinham sido vistas ou estão na TBR.")

            # Botões bilíngues
            await canal.send(
                "✨ **Adiciona as tuas escolhas instantaneamente / Add your choices instantly:**",
                view=ViewSugestoes(titulos_botoes, titulos_botoes)
            )
            
            await ctx.send(f"✅ Painel visual gerado com sucesso em {canal.mention}!")

        except Exception as e:
            await ctx.send(f"❌ Erro ao processar recomendações: {e}")

    @commands.command(name="testeia")
    async def teste_ia(self, ctx):
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
