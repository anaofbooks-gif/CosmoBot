import logging
import discord
from discord.ext import commands
import asyncio
from datetime import datetime

import config
from storage import dados
from ai import ai_text_com_retry, obter_info_livro
from utils import enviar_mensagem_longa

logger = logging.getLogger('CosmoBot')

class ExtrasCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="entrevista")
    async def entrevista(self, ctx, personagem: str, *, pergunta: str):
        await ctx.send(f"🔮 A invocar o espírito de {personagem}...")
        prompt = f"Assume integralmente a personalidade da personagem fictícia '{personagem}'. Responde estritamente na primeira pessoa, em português de Portugal. Pergunta: '{pergunta}'"
        try:
            res = await ai_text_com_retry(prompt)
            await enviar_mensagem_longa(ctx, f"**[{personagem}]:** {res}")
        except Exception as e:
            await ctx.send(f"❌ Erro na entrevista: {e}")

    @commands.command(name="ressaca")
    async def ressaca(self, ctx, *, livro: str):
        prompt = f"O leitor está em ressaca literária após ler '{livro}'. Sugere duas opções de livros reais, leves e cativantes, justificando em português de Portugal."
        try:
            res = await ai_text_com_retry(prompt)
            await enviar_mensagem_longa(ctx, f"🩺 **DIAGNÓSTICO PARA RESSACA LITERÁRIA**\n\n{res}")
        except Exception as e:
            await ctx.send(f"❌ Erro ao gerar sugestões: {e}")

    @commands.command(name="teoria")
    async def teoria(self, ctx, *, teoria: str):
        prompt = f"Uma leitora partilhou esta teoria sobre os rumos de uma história: '{teoria}'. Reage como uma fã empolgada, sem spoilers confirmados, em português de Portugal."
        try:
            res = await ai_text_com_retry(prompt)
            await enviar_mensagem_longa(ctx, f"💭 **AVALIAÇÃO DA TUA TEORIA:**\n\n{res}")
        except Exception as e:
            await ctx.send(f"❌ Erro ao avaliar teoria: {e}")

    @commands.command(name="sprint")
    async def sprint(self, ctx, minutes: int):
        if minutes <= 0:
            return await ctx.send("❌ O tempo deve ser superior a 0 minutos.")
        await ctx.send(f"⏱️ **Sprint de Leitura começado!**\nFoco total durante **{minutes}** minutos. Boas páginas! 📖")
        await asyncio.sleep(minutes * 60)
        await ctx.send(f"🔔 **FIM DO SPRINT!** {ctx.author.mention}, o tempo acabou! Quantas páginas conseguiste ler?")

    @commands.command(name="livroinfo")
    async def livroinfo(self, ctx, *, consulta: str):
        await ctx.send(f"🔍 A pesquisar **{consulta}**...")
        info = await obter_info_livro(consulta)
        embed = discord.Embed(title=f"📖 {info.get('titulo', consulta)}", description=f"**Autor:** {info.get('autor', 'Desconhecido')}", color=discord.Color.teal())
        embed.add_field(name="Género", value=info.get("genero", "N/D"), inline=True)
        embed.add_field(name="Páginas", value=str(info.get("paginas", 0) or "N/D"), inline=True)
        embed.add_field(name="Ano", value=str(info.get("ano", "N/D")), inline=True)
        embed.add_field(name="Fonte", value=info.get("fonte", "IA"), inline=True)
        if info.get("capa"):
            embed.set_thumbnail(url=info["capa"])
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ExtrasCog(bot))
