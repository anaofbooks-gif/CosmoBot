import logging
import discord
from discord.ext import commands
import re
import asyncio

import config
from storage import dados, guardar_dados, resumo_persistencia, forcar_upload
from utils import livro_completo, parsear_livro, formatar_livro, enviar_mensagem_longa, normalizar_titulo

logger = logging.getLogger('CosmoBot')

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
            autor_novo = None
        livro = None
        titulo_norm = titulo_antigo_raw.lower().strip()
        for l in dados["livros_lidos"]:
            if l.get("titulo", "").lower().strip() == titulo_norm:
                livro = l
                break
        if not livro:
            for l in dados["livros_lidos"]:
                if titulo_norm in l.get("titulo", "").lower().strip() or l.get("titulo", "").lower().strip() in titulo_norm:
                    livro = l
                    break
        if not livro:
            sugestoes = [f"• {l.get('titulo', 'Desconhecido')}" for l in dados["livros_lidos"][-8:]]
            return await ctx.send(f"❌ Não encontrei **{titulo_antigo_raw}** no histórico.\n\n**Livros recentes:**\n" + "\n".join(sugestoes))
        titulo_antigo = livro["titulo"]
        autor_antigo = livro.get("autor", "")
        if autor_novo is None:
            novo_titulo = formatar_livro(titulo_novo, autor_antigo) if titulo_novo else titulo_antigo
            autor_novo = autor_antigo
        else:
            novo_titulo = formatar_livro(titulo_novo, autor_novo) if titulo_novo else formatar_livro(parsear_livro(titulo_antigo)[0], autor_novo)
        livro["titulo"] = novo_titulo
        livro["autor"] = autor_novo
        for letra, v in dados["desafio_alfabeto"].items():
            if v == titulo_antigo:
                dados["desafio_alfabeto"][letra] = novo_titulo
                break
        for lista in dados["tbr_por_mes"].values():
            for i, item in enumerate(lista):
                if item == titulo_antigo:
                    lista[i] = novo_titulo
        for lembrete in dados["lembretes_metas"]:
            if lembrete.get("livro") == titulo_antigo:
                lembrete["livro"] = novo_titulo
                if autor_novo:
                    lembrete["autor"] = autor_novo
        for info in dados["sorteios_mes"].values():
            for i, item in enumerate(info.get("livros", [])):
                if item == titulo_antigo:
                    info["livros"][i] = novo_titulo
            for i, item in enumerate(info.get("lidos", [])):
                if item == titulo_antigo:
                    info["lidos"][i] = novo_titulo
        guardar_dados()
        msg = f"✏️ **Livro atualizado com sucesso!**\n\n📖 **Título antigo:** {titulo_antigo}\n📖 **Título novo:** {novo_titulo}"
        if autor_novo != autor_antigo:
            msg += f"\n👤 **Autor antigo:** {autor_antigo}\n👤 **Autor novo:** {autor_novo}"
        await ctx.send(msg)

    @commands.command(name="remover")
    async def remover(self, ctx, *, livro: str):
        from utils import livros_tbr_flat
        try:
            livro_txt = livro_completo(livro)
        except ValueError:
            livro_txt = livro.strip()
        existe_hist = any(l.get("titulo", "").lower().strip() == livro_txt.lower().strip() for l in dados["livros_lidos"])
        existe_tbr = any(livro_txt.lower().strip() == i.lower().strip() for i in livros_tbr_flat())
        existe_lc = any(l.get("livro", "").lower().strip() == livro_txt.lower().strip() for l in dados["lembretes_metas"])
        if not (existe_hist or existe_tbr or existe_lc):
            return await ctx.send(f"❌ Não encontrei **{livro_txt}** em lado nenhum.")
        await ctx.send(f"⚠️ Vou remover **{livro_txt}** de:\n• Histórico de leituras\n• Desafio A-Z\n• TBR\n• Leituras conjuntas\n• Sorteios\n\nTens a certeza? Responde com `sim` em 30 segundos.")
        def check(m): return m.author == ctx.author and m.content.lower() in ["sim", "s", "yes", "y"]
        try:
            await self.bot.wait_for('message', timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("❌ Operação cancelada por timeout.")
        dados["livros_lidos"] = [l for l in dados["livros_lidos"] if l.get("titulo", "").lower().strip() != livro_txt.lower().strip()]
        for letra, v in dados["desafio_alfabeto"].items():
            if v.lower().strip() == livro_txt.lower().strip():
                dados["desafio_alfabeto"][letra] = config.VAZIO_ALFABETO
        for cat in dados["tbr_por_mes"]:
            dados["tbr_por_mes"][cat] = [i for i in dados["tbr_por_mes"][cat] if i.lower().strip() != livro_txt.lower().strip()]
        dados["lembretes_metas"] = [l for l in dados["lembretes_metas"] if l.get("livro", "").lower().strip() != livro_txt.lower().strip()]
        for info in dados["sorteios_mes"].values():
            info["livros"] = [i for i in info.get("livros", []) if i.lower().strip() != livro_txt.lower().strip()]
            info["lidos"] = [i for i in info.get("lidos", []) if i.lower().strip() != livro_txt.lower().strip()]
        guardar_dados()
        await ctx.send(f"🗑️ **{livro_txt}** foi removido com sucesso!\n\nPodes adicionar a versão correta com `!addtbr \"Título Correto - Autor Correto\"`")

    @commands.command(name="ligarlivros")
    async def ligarlivros(self, ctx, *, argumentos: str):
        livros = re.findall(r'"([^"]+)"', argumentos)
        if len(livros) != 2:
            return await ctx.send('❌ Uso correto: `!ligarlivros "Título PT - Autor" "Título EN - Autor"`')

        principal, alias = [livro.strip() for livro in livros]
        if config.SEPARADOR_LIVRO not in principal or config.SEPARADOR_LIVRO not in alias:
            return await ctx.send('❌ Ambos os títulos devem estar no formato `"Título - Autor"`.')

        aliases = dados.setdefault("aliases_livros", {})
        grupo = set(aliases.get(principal, []))
        grupo.add(alias)

        for chave, valores in list(aliases.items()):
            todos = {chave, *valores}
            if principal in todos or alias in todos:
                grupo.update(todos)
                aliases.pop(chave, None)

        grupo.discard(principal)
        aliases[principal] = sorted(grupo)
        guardar_dados()
        await ctx.send(f"🔗 Vou tratar estes títulos como o mesmo livro:\n• {principal}\n• " + "\n• ".join(sorted(grupo)))
    @commands.command(name="buscar")
    async def buscar(self, ctx, *, termo: str):
        termo_busca = termo.lower().strip()
        resultados = []
        for livro in dados["livros_lidos"]:
            if termo_busca in livro.get("titulo", "").lower() or termo_busca in livro.get("autor", "").lower():
                resultados.append(livro)
        if not resultados:
            return await ctx.send(f"❌ Não encontrei nenhum livro com **{termo}**.")
        linhas = [f"{i}. {l.get('titulo', 'Sem título')} — {l.get('estrelas', 'Sem avaliação')}" for i, l in enumerate(resultados[:10], 1)]
        if len(resultados) > 10:
            linhas.append(f"\n... e mais {len(resultados) - 10} resultado(s).")
        await enviar_mensagem_longa(ctx, f"🔍 **Resultados para '{termo}':**\n\n" + "\n".join(linhas))

    @commands.command(name="autores")
    async def autores(self, ctx):
        autores = set()
        for livro in dados["livros_lidos"]:
            autor = livro.get("autor", "")
            if autor:
                autores.add(autor)
            else:
                try:
                    _, autor = parsear_livro(livro.get("titulo", ""))
                    autores.add(autor)
                except:
                    pass
        if not autores:
            return await ctx.send("📭 Ainda não tens autores registados.")
        await enviar_mensagem_longa(ctx, f"📚 **Autores registados ({len(autores)}):**\n" + "\n".join(f"• {a}" for a in sorted(autores)))

    @commands.command(name="dadosficheiro")
    async def dadosficheiro(self, ctx):
        await ctx.send(f"💾 **Persistência do bot**\n{resumo_persistencia()}")

    @commands.command(name="armazenamento")
    async def armazenamento(self, ctx):
        embed = discord.Embed(title="☁️ Armazenamento na nuvem", description="Se o bot corre em **Render, Railway, Fly.io**, etc., o disco é **temporário** — a TBR apaga-se a cada reinício. Usa armazenamento remoto:", color=discord.Color.blue())
        embed.add_field(name="Opção 1 — GitHub", value="1. Criar token com permissão **Contents**\n2. Variáveis: `GITHUB_TOKEN` e `GITHUB_REPO`", inline=False)
        embed.add_field(name="Opção 2 — Supabase", value="Tabela `bot_state` + variáveis `SUPABASE_URL` e `SUPABASE_KEY`", inline=False)
        embed.add_field(name="Opção 3 — JSONBin", value="Variáveis: `JSONBIN_BIN_ID` e `JSONBIN_API_KEY`", inline=False)
        embed.add_field(name="Estado atual", value=resumo_persistencia(), inline=False)
        await ctx.send(embed=embed)

    # 🔥 NOVO COMANDO: Forçar upload dos dados
    @commands.command(name="subir")
    async def subir(self, ctx):
        """Força o upload dos dados para a nuvem (GitHub/Supabase/JSONBin)"""
        await ctx.send("📤 A forçar upload dos dados para a nuvem...")
        
        modo = modo_armazenamento()
        if modo == "local":
            await ctx.send("⚠️ Estás em modo **local**. Os dados só estão guardados no disco do servidor.\nConfigura GitHub, Supabase ou JSONBin para persistência na nuvem.")
            return
        
        try:
            sucesso = forcar_upload(f"Upload forçado por {ctx.author.name}")
            if sucesso:
                await ctx.send(f"✅ **Dados guardados com sucesso em {modo}!**\n📊 TBR: {sum(len(v) for v in dados['tbr_por_mes'].values())} livros | Lidos: {len(dados['livros_lidos'])}")
            else:
                await ctx.send(f"❌ Falha ao guardar dados em **{modo}**. Verifica os logs.")
        except Exception as e:
            await ctx.send(f"❌ Erro ao fazer upload: {e}")

    @commands.command(name="guia")
    async def guia(self, ctx):
        p = config.COMMAND_PREFIX
        embed = discord.Embed(title="📖 GUIA DO COSMO", description=f"Bot de leituras com TBR, leituras conjuntas, desafios e Bookstagram.\n**Formato obrigatório dos livros:** `\"Título - Autor\"`\n\n🤖 **IA Híbrida:** Gemini + fallback entre modelos", color=discord.Color.purple())
        embed.add_field(name="📚 TBR", value=f"`{p}addtbr` `{p}remtbr` `{p}remtbrpos` `{p}limpartbr` `{p}verbar` `{p}tbr`", inline=False)
        embed.add_field(name="📅 Leituras Conjuntas", value=f"`{p}meta` `{p}editmeta` `{p}calendariolc` `{p}removerlc`", inline=False)
        embed.add_field(name="🏆 Desafios", value=f"`{p}lido` `{p}avaliar` `{p}reavaliar` `{p}alfabeto` `{p}addletra` `{p}remalfabeto` `{p}desafios` `{p}historico`", inline=False)
        embed.add_field(name="✏️ Edição", value=f"`{p}editar` `{p}remover` `{p}ligarlivros` `{p}removerlc` `{p}buscar` `{p}autores`", inline=False)
        embed.add_field(name="✨ Recomendações", value=f"`{p}recomendar` `{p}marcarsugestoes`", inline=False)
        embed.add_field(name="📸 Bookstagram", value=f"`{p}desabafar` `{p}review` `{p}mencionar` `{p}gerar` `{p}trend` `{p}vibe`", inline=False)
        embed.add_field(name="📊 Estatísticas", value=f"`{p}resumomes` `{p}resumoano`", inline=False)
        embed.add_field(name="🎲 Extras", value=f"`{p}entrevista` `{p}ressaca` `{p}teoria` `{p}sprint` `{p}livroinfo`", inline=False)
        embed.add_field(name="☁️ Sistema", value=f"`{p}dadosficheiro` `{p}armazenamento` `{p}subir` `{p}guia`", inline=False)
        embed.set_footer(text=f"Prefixo atual: {config.COMMAND_PREFIX} · Usa {config.COMMAND_PREFIX}guia para rever este painel")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))


