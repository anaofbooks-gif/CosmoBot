import discord
from discord.ext import commands
import logging
import asyncio
from datetime import datetime
from typing import Optional

import config
from storage import dados, guardar_dados
from utils import (
    livro_completo, parsear_livro, normalizar_categoria, canal_nome_seguro,
    adicionar_livro_a_tbr_mes, enviar_mensagem_longa, data_valida,
    este_ano, hoje_str, obter_canal_discord, garantir_canal
)
from ai import ai_json_retry, ai_text_retry

logger = logging.getLogger('CosmoBot')

# Tentar importar imagens (se disponível)
try:
    from images import desenhar_calendario_leituras, gerar_fundo_calendario, Image
except ImportError:
    Image = None
    def desenhar_calendario_leituras(*args, **kwargs):
        return None
    def gerar_fundo_calendario(*args, **kwargs):
        return None


class LCCog(commands.Cog):
    """Comandos de Leituras Conjuntas"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="meta", help='Cria metas de leitura conjunta. Ex.: !meta Junho "Quarta Asa - Rebecca Yarros" dia 7 até cap. 10')
    async def definir_meta_lc(self, ctx: commands.Context, mes: str, livro: str, *, cronograma: str):
        mes_cap = normalizar_categoria(mes)
        if mes_cap not in config.MESES_ORDEM:
            return await ctx.send("❌ Mês inválido.")

        try:
            livro_completo_txt = livro_completo(livro)
            titulo_curto, autor = parsear_livro(livro_completo_txt)
        except ValueError:
            return await ctx.send(
                '❌ Usa o formato **"Título - Autor"**.\n'
                'Exemplo: `!meta Junho "Quarta Asa - Rebecca Yarros" dia 7 até cap. 10`'
            )

        guild = ctx.guild
        if not guild:
            return await ctx.send("❌ Este comando só funciona dentro de um servidor.")

        mensagem_tbr = adicionar_livro_a_tbr_mes(livro_completo_txt, mes_cap)
        guardar_dados()

        nome_canal_mes = canal_nome_seguro(mes_cap)
        canal_mes = await garantir_canal(guild, nome_canal_mes)

        mensagem_ancora = await canal_mes.send(
            f"📚 **LEITURA CONJUNTA: {titulo_curto.upper()}** 📚\n👤 **Autor:** {autor}"
        )
        topico_livro = await canal_mes.create_thread(
            name=f"livro-{canal_nome_seguro(livro_completo_txt)[:70]}",
            message=mensagem_ancora,
        )

        await ctx.send(f"{mensagem_tbr}\n🔮 A organizar cronograma em {topico_livro.mention}...")

        prompt = f"""
You are a joint reading assistant. Create a reading schedule for "{livro_completo_txt}" in {mes_cap} {este_ano()}.

Reader instructions:
"{cronograma}"

Rules:
1. Extract the goals with their specific dates.
2. Each goal should have a date (DD/MM format) and a short description.
3. Write the descriptions in European Portuguese (pt-PT) or English — never Brazilian Portuguese.

Respond only with valid JSON in this structure:
{{
  "metas": [ {{"data": "DD/MM/{este_ano()}", "texto": "Short goal description"}} ],
  "nota": "Brief explanation of the schedule (optional)"
}}
"""

        try:
            resposta = await ai_json_retry(prompt)
            metas = resposta.get("metas", [])
            nota = resposta.get("nota", "")

            if nota:
                await enviar_mensagem_longa(topico_livro, f"ℹ️ {nota}")

            lembretes_criados = 0

            for m in metas:
                data_meta = str(m.get("data", "")).strip()
                texto_meta = str(m.get("texto", "")).strip()
                if not data_valida(data_meta) or not texto_meta:
                    continue

                dados["lembretes_metas"].append({
                    "data": data_meta,
                    "livro": livro_completo_txt,
                    "autor": autor,
                    "meta": texto_meta,
                    "canal_id": topico_livro.id,
                    "thread_id": topico_livro.id,
                    "avisado": False,
                    "tipo": "lc",
                })
                lembretes_criados += 1

            guardar_dados()

            await ctx.send(
                f"✅ Metas guardadas com sucesso para {topico_livro.mention}. "
                f"Lembretes criados: **{lembretes_criados}**.\n"
                f"Usa `!calendariolc {mes_cap}` para gerar o calendário visual."
            )

        except Exception as e:
            logger.exception(f"Erro ao processar metas: {e}")
            await ctx.send(f"❌ Erro ao processar metas: {e}")

    @commands.command(name="calendariolc", help="Cria uma imagem do calendário mensal das leituras conjuntas.")
    async def calendario_leituras_conjuntas(self, ctx: commands.Context, mes: Optional[str] = None):
        if Image is None:
            return await ctx.send("❌ Falta instalar a biblioteca de imagem. Usa: `pip install Pillow`")

        mes_alvo = normalizar_categoria(mes) if mes else config.MESES_ORDEM[datetime.now().month - 1]
        if mes_alvo not in config.MESES_ORDEM:
            return await ctx.send("❌ Mês inválido. Exemplo: `!calendariolc Junho`")

        ano = int(este_ano())

        try:
            imagem = desenhar_calendario_leituras(mes_alvo, ano)
            if imagem is None:
                return await ctx.send("❌ Erro ao gerar calendário. Tenta novamente.")
            ficheiro = discord.File(imagem, filename=f"leituras-conjuntas-{mes_alvo.lower()}-{ano}.png")
            await ctx.send(f"🗓️ **Calendário de leituras conjuntas - {mes_alvo} {ano}**", file=ficheiro)
        except Exception as e:
            logger.exception(f"Erro ao criar calendário: {e}")
            await ctx.send(f"❌ Erro ao criar calendário: {e}")

    @commands.command(name="editmeta", help='Edita metas de uma LC existente. Ex.: !editmeta "Título - Autor" dia 7 até cap. 10')
    async def editar_meta_lc(self, ctx: commands.Context, livro: str, *, cronograma: str):
        try:
            livro_completo_txt = livro_completo(livro)
            _, autor = parsear_livro(livro_completo_txt)
        except ValueError:
            return await ctx.send('❌ Usa o formato **"Título - Autor"**.')

        lembretes_livro = [
            l for l in dados["lembretes_metas"]
            if l.get("livro", "").lower().strip() == livro_completo_txt.lower().strip() and l.get("tipo") == "lc"
        ]
        if not lembretes_livro:
            return await ctx.send("❌ Não encontrei metas de leitura conjunta para esse livro.")

        meses_encontrados = set()
        for l in lembretes_livro:
            try:
                data = datetime.strptime(l["data"], "%d/%m/%Y")
                meses_encontrados.add(config.MESES_ORDEM[data.month - 1])
            except (TypeError, ValueError, IndexError):
                pass
        mes_cap = next(iter(meses_encontrados), config.MESES_ORDEM[datetime.now().month - 1])

        dados["lembretes_metas"] = [
            l for l in dados["lembretes_metas"]
            if not (l.get("livro", "").lower().strip() == livro_completo_txt.lower().strip() and l.get("tipo") == "lc")
        ]

        canal_id = lembretes_livro[0].get("thread_id") or lembretes_livro[0].get("canal_id")
        prompt = f"""
Create an updated reading schedule for "{livro_completo_txt}" in {mes_cap} {este_ano()}.

New instructions:
"{cronograma}"

Rules:
1. Extract the goals with their specific dates.
2. Each goal should have a date (DD/MM format) and a short description.
3. Write the descriptions in European Portuguese (pt-PT) or English.

JSON only:
{{
  "metas": [ {{"data": "DD/MM/{este_ano()}", "texto": "Short goal description"}} ],
  "nota": "Brief explanation (optional)"
}}
"""

        try:
            resposta = await ai_json_retry(prompt)
            metas = resposta.get("metas", [])
            nota = resposta.get("nota", "")

            canal = await obter_canal_discord(int(canal_id)) if canal_id else ctx.channel
            if canal and nota:
                await enviar_mensagem_longa(canal, f"ℹ️ {nota}")

            criados = 0
            for m in metas:
                data_meta = str(m.get("data", "")).strip()
                texto_meta = str(m.get("texto", "")).strip()
                if not data_valida(data_meta) or not texto_meta:
                    continue
                dados["lembretes_metas"].append({
                    "data": data_meta,
                    "livro": livro_completo_txt,
                    "autor": autor,
                    "meta": texto_meta,
                    "canal_id": canal_id,
                    "thread_id": canal_id,
                    "avisado": False,
                    "tipo": "lc",
                })
                criados += 1

            guardar_dados()

            await ctx.send(f"✅ Metas atualizadas para **{livro_completo_txt}**. Novos lembretes: **{criados}**.")
        except Exception as e:
            logger.exception(f"Erro ao editar metas: {e}")
            await ctx.send(f"❌ Erro ao editar metas: {e}")

    @commands.command(name="removerlc", help="Remove um livro de todas as leituras conjuntas (metas/lembretes).")
    async def remover_livro_das_lc(self, ctx: commands.Context, *, livro: str):
        import unicodedata
        
        try:
            livro_completo_txt = livro_completo(livro)
        except ValueError:
            livro_completo_txt = livro.strip()
        
        lembretes_encontrados = []
        for lembrete in dados["lembretes_metas"]:
            livro_lembrete = lembrete.get("livro", "")
            if (livro_lembrete.lower().strip() == livro_completo_txt.lower().strip() or
                unicodedata.normalize('NFKD', livro_lembrete.lower()).encode('ASCII', 'ignore').decode() ==
                unicodedata.normalize('NFKD', livro_completo_txt.lower()).encode('ASCII', 'ignore').decode()):
                lembretes_encontrados.append(lembrete)
        
        if not lembretes_encontrados:
            return await ctx.send(f"❌ Não encontrei metas/lembretes para o livro **{livro_completo_txt}**.")
        
        await ctx.send(
            f"⚠️ Vou remover **{len(lembretes_encontrados)}** lembrete(s) da LC de **{livro_completo_txt}**.\n"
            f"Tens a certeza? Responde com `sim` em 30 segundos."
        )
        
        def check(m):
            return m.author == ctx.author and m.content.lower() in ["sim", "s", "yes", "y"]
        
        try:
            await self.bot.wait_for('message', timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("❌ Operação cancelada por timeout.")
        
        dados["lembretes_metas"] = [
            l for l in dados["lembretes_metas"]
            if l.get("livro", "").lower().strip() != livro_completo_txt.lower().strip()
        ]
        
        for mes, info in dados.get("sorteios_mes", {}).items():
            if livro_completo_txt in info.get("livros", []):
                info["livros"].remove(livro_completo_txt)
            if livro_completo_txt in info.get("lidos", []):
                info["lidos"].remove(livro_completo_txt)
        
        guardar_dados()
        
        await ctx.send(
            f"🗑️ **{livro_completo_txt}** foi removido de todas as leituras conjuntas.\n"
            f"Lembretes removidos: **{len(lembretes_encontrados)}**"
        )


async def setup(bot):
    await bot.add_cog(LCCog(bot))
