import logging
import discord
from discord.ext import commands
from datetime import datetime

import config
from storage import dados, guardar_dados
from utils import enviar_mensagem_longa
from ai import ai_text_com_retry, extrair_texto_da_imagem

logger = logging.getLogger('CosmoBot')

class BookstagramCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="desabafar")
    async def desabafar(self, ctx, *, livro: str):
        user_id = str(ctx.author.id)
        if user_id in dados["review_em_andamento"]:
            return await ctx.send(f"⚠️ Já tens uma review em andamento para **{dados['review_em_andamento'][user_id]['titulo']}**.\nTermina com `!gerar` ou usa `!desabafar` para um livro diferente.")
        dados["review_em_andamento"][user_id] = {"titulo": livro, "desabafos": [], "conversas": [], "anexos": [], "tipo": "desabafo"}
        guardar_dados()
        await ctx.send(f"💭 **Modo Desabafo ativado para: *{livro}***\n\n**Podes fazer 3 coisas:**\n1️⃣ **Escrever emoções/sensações** - manda mensagens normais com o que sentes\n2️⃣ **Enviar prints de conversas** - anexa imagens de debates com amigos\n3️⃣ **Mencionar mensagens** - responde a uma mensagem com `!mencionar`\n\nQuando terminares, usa `!gerar` para criar a review com tudo capturado! 🎨")

    @commands.command(name="mencionar")
    async def mencionar(self, ctx):
        user_id = str(ctx.author.id)
        if user_id not in dados["review_em_andamento"]:
            return await ctx.send("❌ Não tens nenhuma review/desabafo em andamento. Usa `!desabafar \"Título - Autor\"` primeiro.")
        if not ctx.message.reference:
            return await ctx.send("❌ Responde a uma mensagem que queres capturar! Exemplo: clica em responder a uma mensagem e usa `!mencionar`")
        try:
            msg_ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except:
            return await ctx.send("❌ Não consegui encontrar a mensagem referenciada.")
        review = dados["review_em_andamento"][user_id]
        entrada = f"📝 **{msg_ref.author.display_name}** ({msg_ref.created_at.strftime('%d/%m/%Y %H:%M')}): {msg_ref.content if msg_ref.content else '[Sem texto]'}"
        for anexo in msg_ref.attachments:
            if anexo.content_type and anexo.content_type.startswith("image/"):
                texto = await extrair_texto_da_imagem(anexo.url)
                if texto:
                    entrada += f"\n   📸 Print: {texto}"
                else:
                    entrada += f"\n   📎 Anexo: {anexo.url}"
                review.setdefault("anexos", []).append(anexo.url)
        review.setdefault("conversas", []).append(entrada)
        guardar_dados()
        await ctx.send(f"✅ Mensagem de **{msg_ref.author.display_name}** adicionada à tua review! (+1 conversa capturada)")
        await ctx.message.add_reaction("📥")

    @commands.command(name="gerar")
    async def gerar(self, ctx):
        user_id = str(ctx.author.id)
        if user_id not in dados["review_em_andamento"]:
            return await ctx.send("❌ Não tens nenhuma review em andamento. Usa `!desabafar \"Título - Autor\"` ou `!review \"Título - Autor\"` primeiro.")
        review = dados["review_em_andamento"][user_id]
        titulo = review["titulo"]
        desabafos = review.get("desabafos", [])
        conversas = review.get("conversas", [])
        anexos = review.get("anexos", [])
        if not desabafos and not conversas and not anexos:
            return await ctx.send("❌ Ainda não tens nenhum apontamento, desabafo ou conversa guardada para esta review.")
        conteudo = ""
        if desabafos:
            conteudo += "**SENTIMENTOS E EMOÇÕES:**\n- " + "\n- ".join(desabafos) + "\n\n"
        if conversas:
            conteudo += "**CONVERSAS E DEBATES:**\n- " + "\n- ".join(conversas) + "\n\n"
        if anexos:
            conteudo += "**ANEXOS/PRINTS:**\n- " + "\n- ".join(anexos) + "\n\n"
        prompt = f"""
Create a structured, aesthetic and emotional Bookstagram caption in European Portuguese (pt-PT) or English.
The reader is sharing their experience with the book '{titulo}'.

Here is everything they captured during their reading journey:

{conteudo}

Instructions:
- Capture the authentic emotions and reactions
- If there are conversations/debates, include interesting quotes or arguments
- Make it feel personal and engaging, like a real reader sharing their journey
- Keep the tone natural and passionate
- Include emojis and line breaks for Instagram aesthetic
- Maximum 2000 characters

Write only the caption, no extra text.
"""
        try:
            legenda = await ai_text_com_retry(prompt)
            msg_final = f"✨ **LEGENDA PARA O INSTAGRAM PRONTA!** ✨\n\n{legenda}"
            if len(msg_final) > 1900:
                await enviar_mensagem_longa(ctx, msg_final)
            else:
                await ctx.send(msg_final)
            if anexos:
                await ctx.send("📎 **Prints e anexos incluídos na review:**\n" + "\n".join(anexos[:5]) + (f"\n(+ {len(anexos) - 5} anexos adicionais)" if len(anexos) > 5 else ""))
            del dados["review_em_andamento"][user_id]
            guardar_dados()
            await ctx.send("🎨 Review finalizada! Tudo o que capturaste foi usado. Podes começar uma nova review com `!desabafar` quando quiseres.")
        except Exception as e:
            await ctx.send(f"❌ Erro ao gerar legenda: {e}")

    @commands.command(name="review")
    async def review(self, ctx, *, livro: str):
        user_id = str(ctx.author.id)
        dados["review_em_andamento"][user_id] = {"titulo": livro, "desabafos": [], "anexos": []}
        guardar_dados()
        await ctx.send(f"📸 **Modo Bloco de Notas ativado para: *{livro}***\nEscreve rants, opiniões ou cola **prints de mensagens** (imagens) em mensagens normais.\nQuando terminares, usa `!gerar`.")

    @commands.command(name="trend")
    async def trend(self, ctx, *, livro_foco: str = None):
        ultimo = dados["livros_lidos"][-1].get("titulo", "um romance ou fantasia em voga") if dados["livros_lidos"] else "um romance ou fantasia em voga"
        livro = livro_foco if livro_foco else ultimo
        await ctx.send(f"📸 A analisar ideias para: **{livro}**...")
        prompt = f"Gera 3 ideias criativas de posts ou reels estéticos de Bookstagram com base em trends de {datetime.now().year} para o livro '{livro}' em português de Portugal. Adiciona sugestões de áudio e hashtags."
        try:
            res = await ai_text_com_retry(prompt)
            await enviar_mensagem_longa(ctx, f"✨ **TRENDS INSTAGRAM** ✨\n\n{res}")
        except Exception as e:
            await ctx.send(f"❌ Erro ao gerar trends: {e}")

    @commands.command(name="vibe")
    async def vibe(self, ctx, *, livro: str):
        prompt = f"Cria um guia compacto de estética literária para o livro '{livro}' (cenários, cores, objetos marcantes), ideal para fotos de Bookstagram."
        try:
            res = await ai_text_com_retry(prompt)
            await enviar_mensagem_longa(ctx, f"📸 **BOOKSTAGRAM MOODBOARD VIBE:**\n\n{res}")
        except Exception as e:
            await ctx.send(f"❌ Erro ao gerar vibe: {e}")


async def setup(bot):
    await bot.add_cog(BookstagramCog(bot))
