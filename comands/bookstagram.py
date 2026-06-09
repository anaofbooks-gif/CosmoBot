import discord
from discord.ext import commands
import logging

import config
from storage import dados, guardar_dados
from utils import enviar_mensagem_longa
from ai import ai_text_com_retry, extrair_texto_da_imagem
from views import ViewAvaliacao

logger = logging.getLogger('CosmoBot')


class BookstagramCog(commands.Cog):
    """Comandos de Bookstagram e Desabafos"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="desabafar", help="Regista emoções, reações e conversas sobre um livro para a review.")
    async def iniciar_desabafo(self, ctx: commands.Context, *, titulo_livro: str):
        user_id = str(ctx.author.id)
        
        if user_id in dados["review_em_andamento"]:
            return await ctx.send(
                f"⚠️ Já tens uma review em andamento para **{dados['review_em_andamento'][user_id]['titulo']}**.\n"
                f"Termina com `!gerar` ou usa `!desabafar` para um livro diferente."
            )
        
        dados["review_em_andamento"][user_id] = {
            "titulo": titulo_livro,
            "desabafos": [],
            "conversas": [],
            "anexos": [],
            "tipo": "desabafo"
        }
        guardar_dados()
        
        await ctx.send(
            f"💭 **Modo Desabafo ativado para: *{titulo_livro}***\n\n"
            f"**Podes fazer 3 coisas:**\n"
            f"1️⃣ **Escrever emoções/sensações** - manda mensagens normais com o que sentes\n"
            f"2️⃣ **Enviar prints de conversas** - anexa imagens de debates com amigos\n"
            f"3️⃣ **Mencionar mensagens** - responde a uma mensagem com `!mencionar`\n\n"
            f"Quando terminares, usa `!gerar` para criar a review com tudo capturado! 🎨"
        )

    @commands.command(name="mencionar", help="Adiciona uma mensagem específica à tua review. Responde à mensagem que queres capturar.")
    async def adicionar_mensagem_review(self, ctx: commands.Context):
        user_id = str(ctx.author.id)
        
        if user_id not in dados["review_em_andamento"]:
            return await ctx.send("❌ Não tens nenhuma review/desabafo em andamento. Usa `!desabafar \"Título - Autor\"` primeiro.")
        
        if not ctx.message.reference:
            return await ctx.send("❌ Responde a uma mensagem que queres capturar! Exemplo: clica em responder a uma mensagem e usa `!mencionar`")
        
        try:
            msg_referencia = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except (discord.NotFound, discord.HTTPException):
            return await ctx.send("❌ Não consegui encontrar a mensagem referenciada.")
        
        review = dados["review_em_andamento"][user_id]
        
        autor = msg_referencia.author.display_name
        conteudo = msg_referencia.content if msg_referencia.content else "[Sem texto - apenas anexos]"
        data = msg_referencia.created_at.strftime("%d/%m/%Y %H:%M")
        
        entrada = f"📝 **{autor}** ({data}): {conteudo}"
        
        if msg_referencia.attachments:
            for anexo in msg_referencia.attachments:
                if anexo.content_type and anexo.content_type.startswith("image/"):
                    texto_extraido = await extrair_texto_da_imagem(anexo.url)
                    if texto_extraido:
                        entrada += f"\n   📸 Print: {texto_extraido}"
                    else:
                        entrada += f"\n   📎 Anexo: {anexo.url}"
                    review.setdefault("anexos", []).append(anexo.url)
        
        review.setdefault("conversas", []).append(entrada)
        guardar_dados()
        
        await ctx.send(f"✅ Mensagem de **{autor}** adicionada à tua review! (+1 conversa capturada)")
        await ctx.message.add_reaction("📥")

    @commands.command(name="gerar", help="Gera a legenda final da review de Bookstagram a partir dos teus desabafos e conversas.")
    async def gerar_review(self, ctx: commands.Context):
        user_id = str(ctx.author.id)

        if user_id not in dados["review_em_andamento"]:
            return await ctx.send("❌ Não tens nenhuma review em andamento. Usa `!desabafar \"Título - Autor\"` ou `!review \"Título - Autor\"` primeiro.")

        review = dados["review_em_andamento"][user_id]
        titulo = review["titulo"]
        desabafos = review.get("desabafos", [])
        conversas = review.get("conversas", [])
        anexos = review.get("anexos", [])
        tipo = review.get("tipo", "review")

        if not desabafos and not conversas and not anexos:
            return await ctx.send("❌ Ainda não tens nenhum apontamento, desabafo ou conversa guardada para esta review.")

        from ai import gerar_legenda_review
        
        try:
            legenda = await gerar_legenda_review(titulo, desabafos, conversas, anexos)
            
            mensagem_final = f"✨ **LEGENDA PARA O INSTAGRAM PRONTA!** ✨\n\n{legenda}"
            
            if len(mensagem_final) > 1900:
                await enviar_mensagem_longa(ctx, mensagem_final)
            else:
                await ctx.send(mensagem_final)
            
            if anexos:
                await ctx.send("📎 **Prints e anexos incluídos na review:**\n" + "\n".join(anexos[:5]))
                if len(anexos) > 5:
                    await ctx.send(f"(+ {len(anexos) - 5} anexos adicionais)")
            
            del dados["review_em_andamento"][user_id]
            guardar_dados()
            
            await ctx.send("🎨 Review finalizada! Tudo o que capturaste foi usado. Podes começar uma nova review com `!desabafar` quando quiseres.")
            
        except Exception as e:
            logger.exception(f"Erro ao gerar review: {e}")
            await ctx.send(f"❌ Erro ao gerar legenda: {e}")

    @commands.command(name="review", help="Inicia notas para gerar uma legenda de review (modo tradicional).")
    async def iniciar_review(self, ctx: commands.Context, *, titulo_livro: str):
        user_id = str(ctx.author.id)
        dados["review_em_andamento"][user_id] = {
            "titulo": titulo_livro,
            "desabafos": [],
            "anexos": [],
        }
        guardar_dados()

        await ctx.send(
            f"📸 **Modo Bloco de Notas ativado para: *{titulo_livro}***\n"
            f"Escreve rants, opiniões ou cola **prints de mensagens** (imagens) em mensagens normais.\n"
            f"Quando terminares, usa `!gerar`."
        )

    @commands.command(name="trend", help="Gera ideias de posts ou reels de Bookstagram.")
    async def sugerir_trends_bookstagram(self, ctx: commands.Context, *, livro_foco: str = None):
        from utils import este_ano
        
        ultimo = (
            dados["livros_lidos"][-1].get("titulo", "um romance ou fantasia em voga")
            if dados["livros_lidos"]
            else "um romance ou fantasia em voga"
        )
        livro_alvo = livro_foco if livro_foco else ultimo

        await ctx.send(f"📸 A analisar ideias para: **{livro_alvo}**...")
        prompt = (
            f"Gera 3 ideias criativas de posts ou reels estéticos de Bookstagram com base em trends de {este_ano()} "
            f"para o livro '{livro_alvo}' em português de Portugal. Adiciona sugestões de áudio e hashtags."
        )

        try:
            res = await ai_text_com_retry(prompt)
            await enviar_mensagem_longa(ctx, f"✨ **TRENDS INSTAGRAM** ✨\n\n{res}")
        except Exception as e:
            logger.exception(f"Erro ao gerar trends: {e}")
            await ctx.send(f"❌ Erro ao gerar trends: {e}")

    @commands.command(name="vibe", help="Gera uma estética visual e temática para um livro.")
    async def gerar_estetica(self, ctx: commands.Context, *, nome_livro: str):
        prompt = (
            f"Cria um guia compacto de estética literária para o livro '{nome_livro}' "
            f"(cenários, cores, objetos marcantes), ideal para fotos de Bookstagram."
        )

        try:
            res = await ai_text_com_retry(prompt)
            await enviar_mensagem_longa(ctx, f"📸 **BOOKSTAGRAM MOODBOARD VIBE:**\n\n{res}")
        except Exception as e:
            logger.exception(f"Erro ao gerar vibe: {e}")
            await ctx.send(f"❌ Erro ao gerar vibe: {e}")


async def setup(bot):
    await bot.add_cog(BookstagramCog(bot))