import logging
import re
import unicodedata
import aiohttp
import discord
from discord.ext import commands

import config
from storage import dados, guardar_dados, livros_tbr_flat
from utils import formatar_livro, livros_bem_avaliados, garantir_canal
from ai import ai_json_hibrido, validar_livro_existe
from views import ViewSugestoes

logger = logging.getLogger('CosmoBot')


def _normalizar_chave(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "").lower().strip())
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _titulo_sem_autor(texto: str) -> str:
    texto = str(texto or "").strip()
    if config.SEPARADOR_LIVRO in texto:
        return texto.rsplit(config.SEPARADOR_LIVRO, 1)[0].strip()
    return texto


def _chaves_livro(titulo: str, autor: str = "") -> set[str]:
    completo = formatar_livro(titulo, autor) if autor else str(titulo or "").strip()
    titulo_curto = _titulo_sem_autor(completo)
    chaves = {_normalizar_chave(completo), _normalizar_chave(titulo_curto)}
    if autor:
        chaves.add(_normalizar_chave(f"{titulo_curto} {autor}"))
    return {chave for chave in chaves if chave}


def _chaves_bloqueadas() -> set[str]:
    bloqueadas = set()
    for livro in dados.get("livros_lidos", []):
        bloqueadas.update(_chaves_livro(livro.get("titulo", ""), livro.get("autor", "")))
    for livro in livros_tbr_flat():
        bloqueadas.update(_chaves_livro(livro))
    for livro in dados.get("sugestoes_vistas", []):
        bloqueadas.update(_chaves_livro(livro))
    for principal, aliases in dados.get("aliases_livros", {}).items():
        bloqueadas.update(_chaves_livro(principal))
        for alias in aliases:
            bloqueadas.update(_chaves_livro(alias))
    return bloqueadas


def _esta_bloqueado(titulo: str, autor: str, bloqueadas: set[str]) -> bool:
    return bool(_chaves_livro(titulo, autor) & bloqueadas)


def _parece_ptbr(livro: dict) -> bool:
    campos = [
        livro.get("idioma", ""),
        livro.get("variante", ""),
        livro.get("mercado", ""),
        livro.get("editora", ""),
        livro.get("observacoes", ""),
        livro.get("porque_ler", ""),
    ]
    texto = _normalizar_chave(" ".join(str(campo) for campo in campos))
    termos_ptbr = {"pt br", "ptbr", "br", "brasil", "brasileiro", "brasileira"}
    return any(termo in texto.split() or termo in texto for termo in termos_ptbr)


def _resumir_bloqueados(max_items: int = 80) -> str:
    itens = []
    for livro in dados.get("livros_lidos", []):
        if livro.get("titulo"):
            itens.append(livro["titulo"])
    itens.extend(livros_tbr_flat())
    itens.extend(dados.get("sugestoes_vistas", []))
    vistos = set()
    unicos = []
    for item in itens:
        chave = _normalizar_chave(item)
        if chave and chave not in vistos:
            vistos.add(chave)
            unicos.append(item)
    return "; ".join(unicos[:max_items]) or "Nenhum"


async def _novidades_openlibrary(favoritos: list[dict], bloqueadas: set[str], limite: int = 3) -> list[dict]:
    candidatos = []
    temas = []
    for livro in favoritos[:10]:
        genero = str(livro.get("genero", "")).split(",")[0].strip()
        if genero and genero.upper() != "N/D":
            temas.append(genero)
    temas.extend(["fantasy", "romance", "fiction"])

    async with aiohttp.ClientSession() as session:
        for tema in temas:
            try:
                async with session.get(
                    "https://openlibrary.org/search.json",
                    params={"subject": tema, "sort": "new", "limit": 12, "language": "eng"},
                    timeout=12,
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
            except Exception as e:
                logger.warning(f"Falha ao procurar novidades na Open Library: {e}")
                continue

            for doc in data.get("docs", []):
                titulo = doc.get("title", "").strip()
                autores = doc.get("author_name") or []
                autor = autores[0].strip() if autores else ""
                if not titulo or not autor or _esta_bloqueado(titulo, autor, bloqueadas):
                    continue
                ano = doc.get("first_publish_year") or "Desconhecido"
                capa_id = doc.get("cover_i")
                candidatos.append({
                    "titulo": titulo,
                    "autor": autor,
                    "idioma": "EN",
                    "data_publicacao": str(ano),
                    "genero": tema.title(),
                    "subgenero": "Novidade",
                    "porque_ler": "Uma opção recente alinhada com os teus favoritos e validada na Open Library.",
                    "link_capa": f"https://covers.openlibrary.org/b/id/{capa_id}-L.jpg" if capa_id else "",
                })
                bloqueadas.update(_chaves_livro(titulo, autor))
                if len(candidatos) >= limite:
                    return candidatos
    return candidatos


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

        bloqueadas = _chaves_bloqueadas()
        favs_texto = []
        for livro in favoritos[:10]:
            genero = livro.get("genero", "N/D")
            favs_texto.append(f"- {livro['titulo']} (⭐{livro['nota']:.1f}, género: {genero})")
        favs_texto_str = "\n".join(favs_texto)
        bloqueados_str = _resumir_bloqueados()

        prompt = f"""És um curador literário cuidadoso. Responde em Português Europeu (pt-PT).

O leitor adorou estes livros, todos avaliados com 4 estrelas ou mais:
{favs_texto_str}

Sugere 6 livros REAIS para eu filtrar e mostrar 3. Quero sobretudo livros em inglês e, quando existir uma edição portuguesa de Portugal, também podes incluir português europeu.

REGRAS OBRIGATÓRIAS:
1. Não inventes livros, autores, datas ou capas.
2. Não sugiras livros já lidos, na TBR, favoritos acima, ou arquivados nesta lista: {bloqueados_str}
3. Não sugiras livros em PT-BR, edições brasileiras, títulos brasileiros ou mercado brasileiro.
4. Se um livro só existir em português do Brasil, escolhe antes a edição em inglês ou outro livro.
5. Inclui pelo menos 2 livros em inglês. Só inclui português se for PT-PT/edição portuguesa.
6. Inclui pelo menos 2 livros publicados nos últimos 5 anos, se existirem opções reais compatíveis.
7. Usa apenas JSON válido, sem markdown.

IDIOMAS ACEITES:
- "EN" para inglês.
- "PT-PT" apenas para português europeu/edição portuguesa.
- Nunca uses "PT", "PT-BR", "BR" ou "Português do Brasil".

PORTUGUÊS:
- Todo o texto explicativo deve estar em português europeu.
- Escreve "género", "publicação", "sugestão", "tu".
- Evita palavras/formas brasileiras como "você", "gênero", "lançamento" quando significar publicação.

Formato exato:
{{"livros": [{{"titulo": "Nome exato", "autor": "Nome do autor", "idioma": "PT-PT" ou "EN", "data_publicacao": "Ano", "genero": "Género", "subgenero": "Subgénero", "porque_ler": "Motivo curto em pt-PT", "link_capa": "URL ou vazio"}}]}}
"""

        try:
            resposta = await ai_json_hibrido(prompt)
            livros_sugeridos = []
            if isinstance(resposta, dict):
                livros_sugeridos = resposta.get("livros") or resposta.get("recomendacoes") or []

            livros_validados = []
            titulos_vistos = set()
            for livro in livros_sugeridos:
                titulo = str(livro.get("titulo", "")).strip()
                autor = str(livro.get("autor", "")).strip()
                idioma = str(livro.get("idioma", "")).upper().strip()
                if idioma == "PT_PT":
                    idioma = "PT-PT"
                if not titulo or not autor or idioma not in {"PT-PT", "EN"}:
                    logger.info(f"Sugestão ignorada por idioma não aceite: {titulo} - {autor} ({idioma})")
                    continue
                if _parece_ptbr(livro):
                    logger.info(f"Sugestão PT-BR bloqueada: {titulo} - {autor}")
                    continue
                if _esta_bloqueado(titulo, autor, bloqueadas):
                    logger.info(f"Sugestão bloqueada por já existir/estar arquivada: {titulo} - {autor}")
                    continue
                chave_livro = _normalizar_chave(f"{titulo} {autor}")
                if chave_livro in titulos_vistos:
                    continue
                if not await validar_livro_existe(titulo, autor):
                    logger.warning(f"Livro não validado: {titulo} - {autor}")
                    continue
                titulos_vistos.add(chave_livro)
                bloqueadas.update(_chaves_livro(titulo, autor))
                livro["idioma"] = idioma
                livros_validados.append(livro)
                if len(livros_validados) >= 3:
                    break

            if len(livros_validados) < 3:
                livros_validados.extend(await _novidades_openlibrary(favoritos, bloqueadas, 3 - len(livros_validados)))

            if not livros_validados:
                return await ctx.send("❌ Não consegui encontrar sugestões reais que não estivessem lidas, na TBR ou arquivadas. Tenta novamente mais tarde.")

            pt_count = sum(1 for l in livros_validados if str(l.get("idioma", "")).upper() == "PT-PT")
            en_count = sum(1 for l in livros_validados if str(l.get("idioma", "")).upper() == "EN")
            intro = "✨ **A TUA REVISTA LITERÁRIA PERSONALIZADA** ✨\n*Sugestões baseadas nos teus livros com 4⭐ ou mais:*\n"
            intro += "\n".join(f"• {l['titulo']} ({l.get('nota', 0):.1f}⭐)" for l in favoritos[:10])
            intro += f"\n\n📚 **{pt_count}** sugestão(ões) em PT-PT | **{en_count}** em Inglês"
            await canal.send(intro)

            titulos_botoes = []
            for livro in livros_validados[:3]:
                titulo = str(livro.get("titulo", "")).strip()
                autor = str(livro.get("autor", "")).strip()
                idioma = str(livro.get("idioma", "")).upper().strip()
                if idioma == "PT_PT":
                    idioma = "PT-PT"
                data = livro.get("data_publicacao", "Desconhecido")
                genero = livro.get("genero", "N/D")
                subgenero = livro.get("subgenero", "N/D")
                porque_ler = livro.get("porque_ler", "Uma sugestão alinhada com o teu gosto.")
                link_capa = livro.get("link_capa", "")
                titulo_completo = formatar_livro(titulo, autor)
                titulos_botoes.append(titulo_completo)

                if idioma == "PT-PT":
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
                    description=f"**Autor:** {autor}\n\n{porque_ler}",
                    color=cor,
                )
                embed.add_field(name=label_data, value=data, inline=True)
                embed.add_field(name=label_genero, value=genero, inline=True)
                embed.add_field(name=label_sub, value=subgenero, inline=True)
                if link_capa and str(link_capa).startswith("http"):
                    embed.set_thumbnail(url=link_capa)
                await canal.send(embed=embed)

            await canal.send("✨ **Adiciona ou arquiva as tuas escolhas:**", view=ViewSugestoes(titulos_botoes, titulos_botoes))
            await ctx.send(f"✅ Painel visual gerado com sucesso em {canal.mention}!")

        except Exception as e:
            logger.exception("Erro ao processar recomendações")
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
        vistos = {_normalizar_chave(v) for v in dados.setdefault("sugestoes_vistas", [])}
        novos = 0
        for titulo in [t.strip() for t in titulos.split("|") if t.strip()]:
            chave = _normalizar_chave(titulo)
            if chave and chave not in vistos:
                dados["sugestoes_vistas"].append(titulo)
                vistos.add(chave)
                novos += 1
        guardar_dados()
        await ctx.send(f"✅ **{novos}** sugestão(ões) arquivada(s).")


async def setup(bot):
    await bot.add_cog(RecommendationsCog(bot))



