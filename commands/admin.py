import discord
from discord.ext import commands
import re
import asyncio

import config
from storage import dados, guardar_dados, resumo_persistencia
from utils import livro_completo, parsear_livro, formatar_livro, enviar_mensagem_longa, normalizar_titulo


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="editar")
    async def editar(self, ctx, *, argumentos: str):
        match = re.match(r'"([^"]+)"\s+(.+)', argumentos.strip())
        if not match:
            return await ctx.send("❌ Uso correto:\n`!editar \"Título Antigo - Autor Antigo\" Novo Título - Novo Autor`\n`!editar \"Título Antigo\" Novo Título - Autor`\n\nO título antigo deve estar entre aspas.")
        titulo_antigo_raw = match.group(1).strip()
        resto = match.group(2).strip()
        if config.SEPARADOR_LIVRO in resto:
            partes = resto.rsplit(config.SEPARADOR_LIVRO, 1)
            titulo_novo = partes[0].strip()
            autor_novo = partes[1].strip()
        else:
            titulo_novo = resto
            autor_novo =
