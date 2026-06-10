import discord
from discord.ext import commands
import logging
import asyncio
import unicodedata
from datetime import datetime
from typing import Optional

import config
from storage import dados, guardar_dados, adicionar_livro_a_tbr_mes
from utils import (
    livro_completo, parsear_livro, normalizar_categoria, canal_nome_seguro,
    enviar_mensagem_longa, data_valida, este_ano, obter_canal_discord, garantir_canal
)
from ai import ai_json_hibrido, validar_resposta_ia_pydantic, validar_resposta_ia
from models import RespostaMetas
from images import desenhar_calendario_leituras, gerar_fundo_calendario, Image

logger = logging.getLogger('CosmoBot')


class LCCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="meta")
    async def meta(self, ctx, mes: str, livro: str, *, cronograma: str):
        mes_cap = normalizar_categoria(mes)
        if mes_cap not in config.MESES_ORDEM:
            return await ctx.send("❌ Mês inválido.")

        try:
            livro_txt = livro_completo(livro)
            titulo_curto, autor = parsear_livro(livro_txt)
        except ValueError:
            return await ctx.send('❌ Usa o formato **"Título - Autor"**.\nExemplo: `!meta Junho "Quarta Asa - Rebecca Yarros" dia 7 até cap. 10`')

        guild = ctx.guild
        if not guild:
            return await ctx.send("❌ Este comando só funciona dentro de um servidor.")

        msg_tbr = adicionar_livro_a_tbr_mes(livro_txt, mes_cap)
        guardar_dados()

        canal_mes = await garantir_canal(guild, canal_nome_seguro(mes_cap))
        ancora = await canal_mes.send(f"📚 **LEITURA CONJUNTA: {titulo_curto.upper()}** 📚\n👤 **Autor:** {autor}")
        topico = await canal_mes.create_thread(name=f"livro-{canal_nome_seguro(livro_txt)[:70]}", message=ancora)

        await ctx.send(f"{msg_tbr}\n🔮 A organizar cronograma em {topico.mention}...")

        prompt = f"""
You are a joint reading assistant. Create a reading schedule for "{livro_txt}" in {mes_cap} {este_ano()}.

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
            resposta = await ai_json_hibrido(prompt)
            validada = validar_resposta_ia_pydantic(resposta, RespostaMetas) or validar_resposta_ia(resposta, ["metas"])
            metas = validada.get("metas", []) if isinstance(validada, dict) else [m.dict() for m in validada.metas]
            nota = validada.get("nota", "") if isinstance(validada, dict) else getattr(validada, "nota", "")

            if not metas:
                return await ctx.send("❌ A IA não conseguiu gerar um cronograma válido. Tenta novamente.")

            if nota:
                await enviar_mensagem_longa(topico, f"ℹ️ {nota}")

            criados = 0
            for m in metas:
                data_meta = str(m.get("data", "")).strip()
                texto_meta = str(m.get("texto", "")).strip()
                if not data_valida(data_meta) or not texto_meta:
                    continue
                dados["lembretes_metas"].append({
                    "data": data_meta,
                    "livro": livro_txt,
                    "autor": autor,
                    "meta": texto_meta,
                    "canal_id": topico.id,
                    "thread_id": topico.id,
                    "avisado": False,
                    "tipo": "lc"
                })
                criados += 1

            guardar_dados()

            if Image:
                try:
                    img = desenhar_calendario_leituras(mes_cap, int(este_ano()))
                    await topico.send("🗓️ **Calendário visual do mês:**", file=discord.File(img, filename=f"lc-{mes_cap.lower()}-{este_ano()}.png"))
                except Exception as e:
                    logger.warning(f"Erro ao gerar calendário LC: {e}")

            await ctx.send(f"✅ Metas guardadas com sucesso para {topico.mention}. Lembretes criados: **{criados}**.\nUsa `!calendariolc {mes_cap}` para gerar o calendário visual novamente.")

        except Exception as e:
            logger.exception(f"Erro ao processar metas: {e}")
            await ctx.send(f"❌ Erro ao processar metas: {e}")

    @commands.command(name="editmeta")
    async def editmeta(self, ctx, livro: str, *, cronograma: str):
        try:
            livro_txt = livro_completo(livro)
            _, autor = parsear_livro(livro_txt)
        except ValueError:
            return await ctx.send('❌ Usa o formato **"Título - Autor"**.')

        lembretes = [l for l in dados["lembretes_metas"] if l.get("livro", "").lower().strip() == livro_txt.lower().strip() and l.get("tipo") == "lc"]
        if not lembretes:
            return await ctx.send("❌ Não encontrei metas de leitura conjunta para esse livro.")

        meses = set()
        for l in lembretes:
            try:
                data = datetime.strptime(l["data"], "%d/%m/%Y")
                meses.add(config.MESES_ORDEM[data.month - 1])
            except:
                pass
        mes_cap = next(iter(meses), config.MESES_ORDEM[datetime.now().month - 1])

        dados["lembretes_metas"] = [l for l in dados["lembretes_metas"] if not (l.get("livro", "").lower().strip() == livro_txt.lower().strip() and l.get("tipo") == "lc")]

        canal_id = lembretes[0].get("thread_id") or lembretes[0].get("canal_id")
        prompt = f"""
Create an updated reading schedule for "{livro_txt}" in {mes_cap} {este_ano()}.

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
            resposta = await ai_json_hibrido(prompt)
            validada = validar_resposta_ia_pydantic(resposta, RespostaMetas) or validar_resposta_ia(resposta, ["metas"])
            metas = validada.get("metas", []) if isinstance(validada, dict) else [m.dict() for m in validada.metas]
            nota = validada.get("nota", "") if isinstance(validada, dict) else getattr(validada, "nota", "")

            if not metas:
                return await ctx.send("❌ A IA não conseguiu gerar um cronograma válido. Tenta novamente.")

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
                    "livro": livro_txt,
                    "autor": autor,
                    "meta": texto_meta,
                    "canal_id": canal_id,
                    "thread_id": canal_id,
                    "avisado": False,
                    "tipo": "lc"
                })
                criados += 1

            guardar_dados()

            if Image:
                try:
                    img = desenhar_calendario_leituras(mes_cap, int(este_ano()))
                    await ctx.send("🗓️ **Calendário visual atualizado:**", file=discord.File(img, filename=f"lc-edit-{mes_cap.lower()}.png"))
                except Exception as e:
                    logger.warning(f"Erro ao gerar calendário editado: {e}")

            await ctx.send(f"✅ Metas atualizadas para **{livro_txt}**. Novos lembretes: **{criados}**.")

        except Exception as e:
            logger.exception(f"Erro ao editar metas: {e}")
            await ctx.send(f"❌ Erro ao editar metas: {e}")

    @commands.command(name="calendariolc")
    async def calendariolc(self, ctx, mes: Optional[str] = None, modo: str = "comia"):
        if Image is None:
            return await ctx.send("❌ Falta instalar a biblioteca de imagem. Usa: `pip install Pillow`")

        mes_alvo = normalizar_categoria(mes) if mes else config.MESES_ORDEM[datetime.now().month - 1]
        if mes_alvo not in config.MESES_ORDEM:
            return await ctx.send("❌ Mês inválido. Exemplo: `!calendariolc Junho`")

        ano = int(este_ano())
        usar_ia = modo.lower() not in ["sem", "sem-ia", "semia", "sem ia", "normal", "basico"]
        img_fundo = None

        if usar_ia:
            await ctx.send("🎨 A gerar fundo temático com IA... (pode demorar alguns segundos)")
            img_fundo = await gerar_fundo_calendario(mes_alvo, ano)
            if not img_fundo:
                await ctx.send("⚠️ Não consegui gerar fundo IA, usando fundo padrão.")
        else:
            await ctx.send("📅 A gerar calendário com fundo padrão...")

        try:
            img = desenhar_calendario_leituras(mes_alvo, ano, img_fundo)
            arquivo = discord.File(img, filename=f"leituras-conjuntas-{mes_alvo.lower()}-{ano}.png")
            if usar_ia and img_fundo:
                await ctx.send(f"✨ **Calendário de {mes_alvo} {ano} com fundo gerado por IA!** ✨", file=arquivo)
            else:
                await ctx.send(f"🗓️ **Calendário de leituras conjuntas - {mes_alvo} {ano}**", file=arquivo)
        except Exception as e:
            logger.exception(f"Erro ao criar calendário: {e}")
            await ctx.send(f"❌ Erro ao criar calendário: {e}")

    @commands.command(name="removerlc")
    async def removerlc(self, ctx, *, livro: str):
        try:
            livro_txt = livro_completo(livro)
        except ValueError:
            livro_txt = livro.strip()

        encontrados = []
        for lembrete in dados["lembretes_metas"]:
            livro_lembrete = lembrete.get("livro", "")
            if (livro_lembrete.lower().strip() == livro_txt.lower().strip() or
                unicodedata.normalize('NFKD', livro_lembrete.lower()).encode('ASCII', 'ignore').decode() ==
                unicodedata.normalize('NFKD', livro_txt.lower()).encode('ASCII', 'ignore').decode()):
                encontrados.append(lembrete)

        if not encontrados:
            return await ctx.send(f"❌ Não encontrei metas/lembretes para o livro **{livro_txt}**.")

        await ctx.send(f"⚠️ Vou remover **{len(encontrados)}** lembrete(s) da LC de **{livro_txt}**.\nTens a certeza? Responde com `sim` em 30 segundos.")

        def check(m):
            return m.author == ctx.author and m.content.lower() in ["sim", "s", "yes", "y"]

        try:
            await self.bot.wait_for('message', timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("❌ Operação cancelada por timeout.")

        dados["lembretes_metas"] = [l for l in dados["lembretes_metas"] if l.get("livro", "").lower().strip() != livro_txt.lower().strip()]

        for mes, info in dados["sorteios_mes"].items():
            if livro_txt in info.get("livros", []):
                info["livros"].remove(livro_txt)
            if livro_txt in info.get("lidos", []):
                info["lidos"].remove(livro_txt)

        guardar_dados()
        await ctx.send(f"🗑️ **{livro_txt}** foi removido de todas as leituras conjuntas.\nLembretes removidos: **{len(encontrados)}**\n\nSe ainda estiver na TBR, usa `!remtbr Geral \"{livro_txt}\"` para remover.")


async def setup(bot):
    await bot.add_cog(LCCog(bot))
