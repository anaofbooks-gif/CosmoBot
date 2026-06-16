import logging
import discord
from discord.ext import commands

import config
from storage import dados, guardar_dados, livros_tbr_flat
from utils import formatar_livro, livros_bem_avaliados, garantir_canal
from ai import ai_json_hibrido, validar_livro_existe
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

        prompt = f"""És um curador literário especializado em recomendações detalhadas.

O leitor adorou estes livros (4+ estrelas):
{favs_texto_str}

Sugere 3 livros NOVOS e SEMELHANTES.

REGRAS OBRIGATÓRIAS:
- **NÃO INVENTES LIVROS.** Se não tens a certeza que um livro existe, NÃO o recomendas.
- **APENAS PORTUGUÊS EUROPEU (PT-PT) OU INGLÊS (EN).** NUNCA uses Português do Brasil (PT-BR).
- **Mistura os idiomas**: tenta recomendar 1 ou 2 livros em Português Europeu (PT-PT) e 1 ou 2 em Inglês (EN)
- Se houver boas opções em PT-PT, dá prioridade ao Português
- Não sugerir livros já na TBR: {tbr_str}
- Não sugerir livros já vistos: {vistos_str}
- Livros devem ser REAIS e existentes
- A língua da descrição ("porque_ler") deve ser a mesma do livro (PT-PT para livros portugueses, EN para livros ingleses)

RESPONDE APENAS COM JSON neste formato EXATO:
{{"livros": [
  {{
    "titulo": "Nome exato do livro",
    "autor": "Nome do autor",
    "idioma": "PT" ou "EN",
    "data_publicacao": "Ano de lançamento (ex: 2021)",
    "genero": "Género principal",
    "subgenero": "Subgénero",
    "porque_ler": "Motivo curto e convincente (no idioma do livro)",
    "link_capa": "URL da capa do livro (se conhecer, senão deixar vazio)"
  }}
]}}

IMPORTANTE: 
- Se o idioma for PT, usa Português Europeu (pt-PT) com "género", "porquê", etc. NUNCA PT-BR.
- Se o idioma for EN, usa Inglês
- Preenche TODOS os campos
- Se não souber a data, usa "Desconhecido" / "Unknown"
- Se não souber o link da capa, usa ""
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

            livros_validados = []
            titulos_vistos = set()
            
            for livro in livros_sugeridos:
                titulo = livro.get("titulo", "")
                autor = livro.get("autor", "")
                idioma = livro.get("idioma", "").upper()
                
                if idioma not in ["PT", "EN"]:
                    logger.warning(f"⚠️ Idioma não suportado: {idioma} para {titulo}. A ignorar...")
                    continue
                
                chave_livro = f"{titulo.lower().strip()}|{autor.lower().strip()}"
                if chave_livro in titulos_vistos:
                    logger.warning(f"⚠️ Livro duplicado detectado: {titulo} - {autor}. A ignorar...")
                    continue
                
                if not await validar_livro_existe(titulo, autor):
                    logger.warning(f"⚠️ Livro não existe: {titulo} - {autor}. A ignorar...")
                    continue
                
                titulos_vistos.add(chave_livro)
                livros_validados.append(livro)

            if not livros_validados:
                return await ctx.send("❌ Nenhuma das sugestões geradas parece ser um livro real ou está duplicada. Tenta novamente mais tarde.")

            pt_count = sum(1 for l in livros_validados if l.get("idioma", "").upper() == "PT")
            en_count = sum(1 for l in livros_validados if l.get("idioma", "").upper() == "EN")
            
            intro = f"✨ **A TUA REVISTA LITERÁRIA PERSONALIZADA** ✨\n*Sugestões baseadas nos teus livros com 4⭐ ou mais:*\n" + "\n".join(f"• {l['titulo']} ({l.get('nota', 0):.1f}⭐)" for l in favoritos[:5])
            intro += f"\n\n📚 **{pt_count}** sugestão(ões) em Português | **{en_count}** em Inglês"
            
            await canal.send(intro)

            titulos_botoes = []
            for livro in livros_validados[:3]:
                titulo = livro.get("titulo", "")
                autor = livro.get("autor", "")
                idioma = livro.get("idioma", "").upper()
                data = livro.get("data_publicacao", "Desconhecido" if idioma == "PT" else "Unknown")
                genero = livro.get("genero", "N/D" if idioma == "PT" else "N/A")
                subgenero = livro.get("subgenero", "N/D" if idioma == "PT" else "N/A")
                porque_ler = livro.get("porque_ler", "Uma sugestão alinhada com o teu gosto." if idioma == "PT" else "A suggestion aligned with your taste.")
                link_capa = livro.get("link_capa", "")

                if not titulo or not autor:
                    continue
                    
                titulo_completo = formatar_livro(titulo, autor)

                if titulo_completo.lower().strip() in {v.lower().strip() for v in vistos}:
                    continue
                if any(titulo_completo.lower().strip() == x.lower().strip() for x in tbr_atual):
                    continue

                titulos_botoes.append(titulo_completo)

                if idioma == "PT":
                    cor = discord.Color.from_rgb(0, 150, 0)
                    bandeira = "🇵🇹"
                    label_data = "📅 Publicação"
                    label_genero = "🎭 Género"
                    label_sub = "🧬 Subgénero"
                else:
                    cor = discord.Color.blue()
                    bandeira = "🇬🇧"
                    label_data = "📅 Publication"
                    label_genero = "🎭 Genre"
                    label_sub = "🧬 Subgenre"

                embed = discord.Embed(
                    title=f"📖 {titulo_completo} {bandeira}",
                    description=f"**{'Autor' if idioma == 'EN' else 'Autor'}:** {autor}\n\n{porque_ler}",
                    color=cor
                )
                embed.add_field(name=label_data, value=data, inline=True)
                embed.add_field(name=label_genero, value=genero, inline=True)
                embed.add_field(name=label_sub, value=subgenero, inline=True)

                if link_capa and link_capa.startswith("http"):
                    embed.set_thumbnail(url=link_capa)

                await canal.send(embed=embed)

            if not titulos_botoes:
                return await ctx.send("❌ Todas as sugestões geradas já tinham sido vistas ou estão na TBR.")

            await canal.send("✨ **Adiciona as tuas escolhas instantaneamente:**", view=ViewSugestoes(titulos_botoes, titulos_botoes))
            
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
