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
    garantir_canal, adicionar_livro_a_tbr_mes, enviar_mensagem_longa, data_valida,
    este_ano, hoje_str
)
from ai import gerar_metas_lc, ai_json_com_retry
from images import desenhar_calendario_leituras, Image, gerar_fundo_calendario
from views import ViewConfirmarLido

logger = logging.getLogger('CosmoBot')


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

        try:
            metas, nota = await gerar_metas_lc(livro_completo_txt, mes_cap, cronograma)

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

            if Image is not None:
                try:
                    imagem = desenhar_calendario_leituras(mes_cap, int(este_ano()))
                    ficheiro = discord.File(imagem, filename=f"lc-{mes_cap.lower()}-{este_ano()}.png")
                    await topico_livro.send("🗓️ **Calendário visual do mês:**", file=ficheiro)
                except Exception as e:
                    logger.warning(f"Erro ao gerar calendário LC: {e}")

            await ctx.send(
                f"✅ Metas guardadas com sucesso para {topico_livro.mention}. "
                f"Lembretes criados: **{lembretes_criados}**.\n"
                f"Usa `!calendariolc {mes_cap}` para gerar o calendário visual novamente."
            )

        except Exception as e:
            logger.exception(f"Erro ao processar metas: {e}")
            await ctx.send(f"❌ Erro ao processar metas: {e}")

    @commands.command(name="editmeta", help='Edita metas de uma LC existente. Ex.: !editmeta "Título - Autor" dia 7 até cap. 10')
    async def editar_meta_lc(self, ctx: commands.Context, livro: str, *, cronograma: str):
        from utils import obter_canal_discord
        
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

        try:
            metas, nota = await gerar_metas_lc(livro_completo_txt, mes_cap, cronograma)

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

            if Image is not None:
                try:
                    imagem = desenhar_calendario_leituras(mes_cap, int(este_ano()))
                    ficheiro = discord.File(imagem, filename=f"lc-edit-{mes_cap.lower()}.png")
                    await ctx.send("🗓️ **Calendário visual atualizado:**", file=ficheiro)
                except Exception as e:
                    logger.warning(f"Erro ao gerar calendário editado: {e}")

            await ctx.send(f"✅ Metas atualizadas para **{livro_completo_txt}**. Novos lembretes: **{criados}**.")
        except Exception as e:
            logger.exception(f"Erro ao editar metas: {e}")
            await ctx.send(f"❌ Erro ao editar metas: {e}")

    @commands.command(name="calendariolc", help="Cria uma imagem do calendário mensal das leituras conjuntas (com fundo IA opcional).")
    async def calendario_leituras_conjuntas(self, ctx: commands.Context, mes: Optional[str] = None, modo: str = "comia"):
        if Image is None:
            return await ctx.send("❌ Falta instalar a biblioteca de imagem. Usa: `pip install Pillow`")

        mes_alvo = normalizar_categoria(mes) if mes else config.MESES_ORDEM[datetime.now().month - 1]
        if mes_alvo not in config.MESES_ORDEM:
            return await ctx.send("❌ Mês inválido. Exemplo: `!calendariolc Junho`")

        ano = int(este_ano())
        
        usar_ia = modo.lower() not in ["sem", "sem-ia", "semia", "sem ia", "normal", "basico", "basico"]
        
        imagem_fundo = None
        if usar_ia:
            await ctx.send("🎨 A gerar fundo temático com IA... (pode demorar alguns segundos)")
            imagem_fundo = await gerar_fundo_calendario(mes_alvo, ano)
            if not imagem_fundo:
                await ctx.send("⚠️ Não consegui gerar fundo IA, usando fundo padrão.")
        else:
            await ctx.send("📅 A gerar calendário com fundo padrão...")

        try:
            imagem = desenhar_calendario_leituras(mes_alvo, ano, imagem_fundo)
        except Exception as e:
            logger.exception(f"Erro ao criar calendário: {e}")
            return await ctx.send(f"❌ Erro ao criar calendário: {e}")

        ficheiro = discord.File(imagem, filename=f"leituras-conjuntas-{mes_alvo.lower()}-{ano}.png")
        
        if usar_ia and imagem_fundo:
            await ctx.send(f"✨ **Calendário de {mes_alvo} {ano} com fundo gerado por IA!** ✨", file=ficheiro)
        else:
            await ctx.send(f"🗓️ **Calendário de leituras conjuntas - {mes_alvo} {ano}**", file=ficheiro)

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
        
        for mes, info in dados["sorteios_mes"].items():
            if livro_completo_txt in info.get("livros", []):
                info["livros"].remove(livro_completo_txt)
            if livro_completo_txt in info.get("lidos", []):
                info["lidos"].remove(livro_completo_txt)
        
        guardar_dados()
        
        await ctx.send(
            f"🗑️ **{livro_completo_txt}** foi removido de todas as leituras conjuntas.\n"
            f"Lembretes removidos: **{len(lembretes_encontrados)}**\n\n"
            f"Se ainda estiver na TBR, usa `!remtbr Geral \"{livro_completo_txt}\"` para remover."
        )


async def setup(bot):
    await bot.add_cog(LCCog(bot))