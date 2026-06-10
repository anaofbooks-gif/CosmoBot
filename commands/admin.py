import discord
from discord.ext import commands
import logging
import re
import unicodedata

import config
from storage import dados, guardar_dados, resumo_persistencia
from utils import (
    formatar_livro, parsear_livro, livro_completo, enviar_mensagem_longa,
    normalizar_categoria
)

logger = logging.getLogger('CosmoBot')


class AdminCog(commands.Cog):
    """Comandos administrativos e de edição"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="editar", help="Edita título ou autor de um livro.")
    async def editar_livro(self, ctx: commands.Context, *, argumentos: str):
        argumentos = argumentos.strip()
        
        match_aspas = re.match(r'"([^"]+)"\s+(.+)', argumentos)
        
        if not match_aspas:
            return await ctx.send(
                "❌ Uso correto:\n"
                "`!editar \"Título Antigo - Autor Antigo\" Novo Título - Novo Autor`\n"
                "`!editar \"Título Antigo\" Novo Título - Autor`\n\n"
                "O título antigo deve estar entre aspas."
            )
        
        titulo_antigo_raw = match_aspas.group(1).strip()
        resto = match_aspas.group(2).strip()
        
        if config.SEPARADOR_LIVRO in resto:
            partes = resto.rsplit(config.SEPARADOR_LIVRO, 1)
            titulo_novo = partes[0].strip()
            autor_novo = partes[1].strip()
        else:
            titulo_novo = resto
            autor_novo = None
        
        livro_encontrado = None
        titulo_antigo_normalizado = titulo_antigo_raw.lower().strip()
        
        for livro in dados["livros_lidos"]:
            titulo_livro = livro.get("titulo", "").lower().strip()
            if (titulo_livro == titulo_antigo_normalizado or
                titulo_antigo_normalizado in titulo_livro or
                titulo_livro in titulo_antigo_normalizado):
                livro_encontrado = livro
                break
        
        if not livro_encontrado:
            sugestoes = []
            for livro in dados["livros_lidos"][-8:]:
                sugestoes.append(f"• {livro.get('titulo', 'Desconhecido')}")
            
            await ctx.send(
                f"❌ Não encontrei **{titulo_antigo_raw}** no histórico.\n\n"
                f"**Livros recentes:**\n" + "\n".join(sugestoes) + "\n\n"
                f"Usa `!buscar \"palavra\"` para encontrar o nome exato."
            )
            return
        
        titulo_antigo_completo = livro_encontrado.get("titulo", "")
        autor_antigo = livro_encontrado.get("autor", "")
        
        if autor_novo is None:
            if titulo_novo:
                novo_titulo_completo = formatar_livro(titulo_novo, autor_antigo)
            else:
                novo_titulo_completo = titulo_antigo_completo
                autor_novo = autor_antigo
        else:
            if titulo_novo:
                novo_titulo_completo = formatar_livro(titulo_novo, autor_novo)
            else:
                try:
                    titulo_antigo_curto, _ = parsear_livro(titulo_antigo_completo)
                    novo_titulo_completo = formatar_livro(titulo_antigo_curto, autor_novo)
                except ValueError:
                    novo_titulo_completo = f"{titulo_antigo_completo.split(config.SEPARADOR_LIVRO)[0]}{config.SEPARADOR_LIVRO}{autor_novo}"
        
        livro_encontrado["titulo"] = novo_titulo_completo
        livro_encontrado["autor"] = autor_novo if autor_novo else autor_antigo
        
        for letra, livro_alfabeto in dados["desafio_alfabeto"].items():
            if livro_alfabeto == titulo_antigo_completo:
                dados["desafio_alfabeto"][letra] = novo_titulo_completo
                break
        
        for categoria, lista in dados["tbr_por_mes"].items():
            for i, item in enumerate(lista):
                if item == titulo_antigo_completo:
                    lista[i] = novo_titulo_completo
        
        for lembrete in dados["lembretes_metas"]:
            if lembrete.get("livro") == titulo_antigo_completo:
                lembrete["livro"] = novo_titulo_completo
                if autor_novo:
                    lembrete["autor"] = autor_novo
        
        for mes, info in dados["sorteios_mes"].items():
            livros = info.get("livros", [])
            for i, livro in enumerate(livros):
                if livro == titulo_antigo_completo:
                    livros[i] = novo_titulo_completo
            lidos = info.get("lidos", [])
            for i, livro in enumerate(lidos):
                if livro == titulo_antigo_completo:
                    lidos[i] = novo_titulo_completo
        
        guardar_dados()
        
        mensagem = f"✏️ **Livro atualizado com sucesso!**\n\n"
        mensagem += f"📖 **Título antigo:** {titulo_antigo_completo}\n"
        mensagem += f"📖 **Título novo:** {novo_titulo_completo}\n"
        
        if autor_novo and autor_novo != autor_antigo:
            mensagem += f"👤 **Autor antigo:** {autor_antigo}\n"
            mensagem += f"👤 **Autor novo:** {autor_novo}\n"
        
        mensagem += f"\n✅ Atualizado em: histórico, TBR, desafios, sorteios e lembretes."
        
        await ctx.send(mensagem)

    @commands.command(name="remover", help="Remove um livro do histórico (lidos), TBR e LCs.")
    async def remover_livro_completo(self, ctx: commands.Context, *, livro: str):
        try:
            livro_completo_txt = livro_completo(livro)
        except ValueError:
            livro_completo_txt = livro.strip()
        
        from utils import livros_tbr_flat
        
        existe_historico = any(l.get("titulo", "").lower().strip() == livro_completo_txt.lower().strip() 
                              for l in dados["livros_lidos"])
        
        existe_tbr = any(livro_completo_txt.lower().strip() == item.lower().strip() 
                        for item in livros_tbr_flat())
        
        existe_lc = any(l.get("livro", "").lower().strip() == livro_completo_txt.lower().strip() 
                       for l in dados["lembretes_metas"])
        
        if not (existe_historico or existe_tbr or existe_lc):
            return await ctx.send(f"❌ Não encontrei **{livro_completo_txt}** em lado nenhum.")
        
        await ctx.send(
            f"⚠️ Vou remover **{livro_completo_txt}** de:\n"
            f"• Histórico de leituras\n"
            f"• Desafio A-Z\n"
            f"• TBR\n"
            f"• Leituras conjuntas\n"
            f"• Sorteios\n\n"
            f"Tens a certeza? Responde com `sim` em 30 segundos."
        )
        
        def check(m):
            return m.author == ctx.author and m.content.lower() in ["sim", "s", "yes", "y"]
        
        try:
            await self.bot.wait_for('message', timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("❌ Operação cancelada por timeout.")
        
        dados["livros_lidos"] = [
            l for l in dados["livros_lidos"]
            if l.get("titulo", "").lower().strip() != livro_completo_txt.lower().strip()
        ]
        
        for letra, livro_alfabeto in dados["desafio_alfabeto"].items():
            if livro_alfabeto.lower().strip() == livro_completo_txt.lower().strip():
                dados["desafio_alfabeto"][letra] = config.VAZIO_ALFABETO
        
        for categoria in dados["tbr_por_mes"]:
            dados["tbr_por_mes"][categoria] = [
                item for item in dados["tbr_por_mes"][categoria]
                if item.lower().strip() != livro_completo_txt.lower().strip()
            ]
        
        dados["lembretes_metas"] = [
            l for l in dados["lembretes_metas"]
            if l.get("livro", "").lower().strip() != livro_completo_txt.lower().strip()
        ]
        
        for mes, info in dados["sorteios_mes"].items():
            info["livros"] = [
                l for l in info.get("livros", [])
                if l.lower().strip() != livro_completo_txt.lower().strip()
            ]
            info["lidos"] = [
                l for l in info.get("lidos", [])
                if l.lower().strip() != livro_completo_txt.lower().strip()
            ]
        
        guardar_dados()
        
        await ctx.send(
            f"🗑️ **{livro_completo_txt}** foi removido com sucesso!\n\n"
            f"Podes adicionar a versão correta com `!addtbr \"Título Correto - Autor Correto\"`"
        )

    @commands.command(name="buscar", help="Busca livros no histórico por título ou autor.")
    async def buscar_livro(self, ctx: commands.Context, *, termo: str):
        termo_busca = termo.lower().strip()
        resultados = []
        
        for livro in dados["livros_lidos"]:
            titulo = livro.get("titulo", "").lower()
            autor = livro.get("autor", "").lower()
            
            if termo_busca in titulo or termo_busca in autor:
                resultados.append(livro)
        
        if not resultados:
            return await ctx.send(f"❌ Não encontrei nenhum livro com **{termo}**.")
        
        linhas = []
        for i, livro in enumerate(resultados[:10], 1):
            estrelas = livro.get("estrelas", "Sem avaliação")
            linhas.append(f"{i}. {livro.get('titulo', 'Sem título')} — {estrelas}")
        
        if len(resultados) > 10:
            linhas.append(f"\n... e mais {len(resultados) - 10} resultado(s).")
        
        await enviar_mensagem_longa(ctx, f"🔍 **Resultados para '{termo}':**\n\n" + "\n".join(linhas))

    @commands.command(name="autores", help="Lista todos os autores dos livros lidos.")
    async def listar_autores(self, ctx: commands.Context):
        autores = set()
        for livro in dados["livros_lidos"]:
            autor = livro.get("autor", "")
            if autor:
                autores.add(autor)
            else:
                try:
                    _, autor = parsear_livro(livro.get("titulo", ""))
                    autores.add(autor)
                except ValueError:
                    pass
        
        if not autores:
            return await ctx.send("📭 Ainda não tens autores registados.")
        
        autores_ordenados = sorted(autores)
        msg = f"📚 **Autores registados ({len(autores_ordenados)}):**\n"
        msg += "\n".join(f"• {autor}" for autor in autores_ordenados)
        
        await enviar_mensagem_longa(ctx, msg)

    @commands.command(name="dadosficheiro", help="Mostra onde os dados do bot são guardados.")
    async def mostrar_dados_ficheiro(self, ctx: commands.Context):
        await ctx.send(f"💾 **Persistência do bot**\n{resumo_persistencia()}")

    @commands.command(name="armazenamento", help="Explica como persistir dados na nuvem.")
    async def ajuda_armazenamento(self, ctx: commands.Context):
        embed = discord.Embed(
            title="☁️ Armazenamento na nuvem",
            description=(
                "Se o bot corre em **Render, Railway, Fly.io**, etc., o disco é **temporário** — "
                "a TBR apaga-se a cada reinício. Usa armazenamento remoto:"
            ),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Opção 1 — GitHub",
            value=(
                "1. GitHub → Settings → Developer settings → Personal access tokens\n"
                "2. Cria token com permissão **Contents**\n"
                "3. Adiciona `dados_bot.json` ao repo\n"
                "4. Variáveis: `GITHUB_TOKEN` e `GITHUB_REPO`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Opção 2 — Supabase",
            value=(
                "1. Projeto em [supabase.com](https://supabase.com) + tabela `bot_state`\n"
                "2. Variáveis: `SUPABASE_URL` e `SUPABASE_KEY`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Opção 3 — JSONBin",
            value="Variáveis: `JSONBIN_BIN_ID` e `JSONBIN_API_KEY`",
            inline=False,
        )
        embed.add_field(
            name="Estado atual",
            value=resumo_persistencia(),
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command(name="guia", help="Mostra o guia completo de comandos do bot.")
    async def enviar_guia(self, ctx: commands.Context):
        p = config.COMMAND_PREFIX
        
        embed = discord.Embed(
            title="📖 GUIA DO COSMO",
            description=(
                "Bot de leituras com TBR, leituras conjuntas, desafios e Bookstagram.\n"
                f"**Formato obrigatório dos livros:** `\"Título - Autor\"`\n\n"
                f"🤖 **IA Híbrida:** Gemini + DeepSeek (fallback automático)"
            ),
            color=discord.Color.purple(),
        )
        
        embed.add_field(
            name="📚 TBR",
            value=f"`{p}addtbr` `{p}remtbr` `{p}remtbrpos` `{p}limpartbr` `{p}verbar` `{p}tbr`",
            inline=False
        )
        embed.add_field(
            name="📅 Leituras Conjuntas",
            value=f"`{p}meta` `{p}editmeta` `{p}calendariolc` `{p}removerlc`",
            inline=False
        )
        embed.add_field(
            name="🏆 Desafios",
            value=f"`{p}lido` `{p}avaliar` `{p}reavaliar` `{p}alfabeto` `{p}addletra` `{p}remalfabeto` `{p}desafios` `{p}historico`",
            inline=False
        )
        embed.add_field(
            name="✏️ Edição",
            value=f"`{p}editar` `{p}remover` `{p}removerlc` `{p}buscar` `{p}autores`",
            inline=False
        )
        embed.add_field(
            name="✨ Recomendações",
            value=f"`{p}recomendar` `{p}marcarsugestoes`",
            inline=False
        )
        embed.add_field(
            name="📸 Bookstagram",
            value=f"`{p}desabafar` `{p}review` `{p}mencionar` `{p}gerar` `{p}trend` `{p}vibe`",
            inline=False
        )
        embed.add_field(
            name="📊 Estatísticas",
            value=f"`{p}resumomes` `{p}resumoano`",
            inline=False
        )
        embed.add_field(
            name="🎲 Extras",
            value=f"`{p}entrevista` `{p}ressaca` `{p}teoria` `{p}sprint` `{p}livroinfo`",
            inline=False
        )
        embed.add_field(
            name="☁️ Sistema",
            value=f"`{p}dadosficheiro` `{p}armazenamento` `{p}guia`",
            inline=False
        )
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))