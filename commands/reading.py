import logging
import discord
from discord.ext import commands
import unicodedata
import re
from typing import Optional

import config
from storage import dados, guardar_dados, marcar_livro_sorteio_lido
from utils import livro_completo, parsear_livro, hoje_str, este_ano, estrelas_para_texto, nota_valida, livro_ja_lido, tem_artigo_no_inicio, obter_primeira_letra_sem_artigo
from ai import obter_info_livro
from views import ViewAvaliacao

logger = logging.getLogger('CosmoBot')

def normalizar_livro_busca(texto: str) -> str:
    texto = str(texto or "").lower().strip().strip('"')
    texto = re.sub(r"\s*[-–—]\s*", " - ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto

class ReadingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="lido")
    async def lido(self, ctx, *, titulo_livro: str):
        try:
            titulo_completo = livro_completo(titulo_livro)
            titulo_curto, autor = parsear_livro(titulo_completo)
        except ValueError:
            return await ctx.send('❌ O formato tem de incluir autor: **"Título - Autor"**.\nExemplo: `!lido "Quarta Asa - Rebecca Yarros"`')

        if livro_ja_lido(titulo_completo, dados):
            return await ctx.send(f"⚠️ O livro **{titulo_completo}** já está registado como lido.")

        info = await obter_info_livro(titulo_completo)
        novo_livro = {
            "titulo": titulo_completo,
            "autor": autor,
            "estrelas": "Sem avaliação",
            "nota": 0.0,
            "genero": info.get("genero", "N/D"),
            "paginas": int(info.get("paginas", 0) or 0),
            "data_leitura": hoje_str(),
            "fonte_metadados": info.get("fonte", "IA"),
        }

        dados["livros_lidos"].append(novo_livro)

        removido_de = []
        for chave, lista in dados["tbr_por_mes"].items():
            for item in lista[:]:
                if item.lower().strip() == titulo_completo.lower().strip():
                    lista.remove(item)
                    removido_de.append(chave)
                    break
                item_norm = unicodedata.normalize('NFKD', item.lower()).encode('ASCII', 'ignore').decode()
                livro_norm = unicodedata.normalize('NFKD', titulo_completo.lower()).encode('ASCII', 'ignore').decode()
                if item_norm == livro_norm:
                    lista.remove(item)
                    removido_de.append(chave)
                    break

        meses_desbloqueados = marcar_livro_sorteio_lido(titulo_completo)
        aviso_remocao = f" (removido de: {', '.join(removido_de)})" if removido_de else ""
        aviso_sorteio = f"\n🔓 Sorteio desbloqueado em: **{', '.join(meses_desbloqueados)}**." if meses_desbloqueados else ""

        await ctx.send(f"✍️ A registar '{titulo_completo}' e a validar o Desafio A-Z...")

        # 🔥 REGRA DE OURO: Se começar por artigo, NÃO entra no Desafio A-Z (validação LOCAL)
        aviso_alfabeto = ""
        if tem_artigo_no_inicio(titulo_curto):
            aviso_alfabeto = f"\n⚠️ **{titulo_curto}** começa com um artigo definido/indefinido. **NÃO ENTRA** no Desafio A-Z!"
        else:
            letra = obter_primeira_letra_sem_artigo(titulo_curto)
            if letra:
                if dados["desafio_alfabeto"].get(letra) == config.VAZIO_ALFABETO:
                    dados["desafio_alfabeto"][letra] = titulo_completo
                    aviso_alfabeto = f"\n🔤 **Desafio A-Z:** Letra **{letra}** conquistada! 🎉"
                else:
                    aviso_alfabeto = f"\n🔤 **Desafio A-Z:** A letra **{letra}** já se encontrava preenchida por **{dados['desafio_alfabeto'][letra]}**."
            else:
                aviso_alfabeto = "\n⚠️ Não foi possível determinar uma letra válida para o desafio."

        guardar_dados()
        total_lidos = len(dados["livros_lidos"])

        await ctx.send(
            f"📚 **{titulo_completo}** adicionado aos lidos!{aviso_remocao}{aviso_sorteio}{aviso_alfabeto}\n"
            f"📊 Progresso Anual: {total_lidos}/{config.META_ANUAL} livros em {este_ano()}.\n"
            f"📎 Metadados via **{info.get('fonte', 'IA')}**.\n"
            f"Escolhe a avaliação:",
            view=ViewAvaliacao(titulo_completo, ctx.author.id),
        )

    @commands.command(name="avaliar")
    async def avaliar(self, ctx, *, argumentos: str = ""):
        partes = argumentos.strip().split()
        if not partes:
            return await ctx.send("❌ Uso correto: `!avaliar 3.25` ou `!avaliar \"Título - Autor\" 3.25`")

        nota_texto = None
        titulo_livro = None

        for idx in (0, len(partes) - 1):
            candidato = partes[idx].replace(',', '.')
            try:
                float(candidato)
                nota_texto = candidato
                if idx == 0:
                    titulo_livro = " ".join(partes[1:]).strip() or None
                else:
                    titulo_livro = " ".join(partes[:-1]).strip() or None
                break
            except ValueError:
                continue

        if nota_texto is None:
            return await ctx.send("❌ Nota inválida. Exemplos: `!avaliar 3.25` ou `!avaliar \"Hallowed Ground - Rebecca Yarros\" 3.25`")

        nota_float = float(nota_texto)
        if not nota_valida(nota_float):
            return await ctx.send("❌ A nota deve ser entre 0.25 e 5, em passos de 0.25.")

        livro_encontrado = None
        if titulo_livro:
            titulo_alvo = normalizar_livro_busca(titulo_livro)
            for livro in dados["livros_lidos"]:
                titulo_guardado = normalizar_livro_busca(livro.get("titulo", ""))
                if titulo_guardado == titulo_alvo:
                    livro_encontrado = livro
                    break
            if not livro_encontrado:
                for livro in dados["livros_lidos"]:
                    titulo_guardado = normalizar_livro_busca(livro.get("titulo", ""))
                    if titulo_alvo in titulo_guardado or titulo_guardado in titulo_alvo:
                        livro_encontrado = livro
                        break
            if not livro_encontrado:
                sugestoes = [f"• {l.get('titulo', 'Desconhecido')}" for l in dados["livros_lidos"][-5:]]
                return await ctx.send(f"❌ Não encontrei o livro **{titulo_livro}** no teu histórico.\n\n**Últimos livros lidos:**\n" + "\n".join(sugestoes))

        if not livro_encontrado:
            if not dados["livros_lidos"]:
                return await ctx.send("❌ Ainda não registaste nenhum livro lido para avaliar.")
            livro_encontrado = dados["livros_lidos"][-1]

        estrelas_antigas = livro_encontrado.get("estrelas", "Sem avaliação")
        livro_encontrado["nota"] = nota_float
        livro_encontrado["estrelas"] = estrelas_para_texto(nota_float)
        guardar_dados()

        await ctx.send(
            f"🎨 **Avaliação guardada!**\n"
            f"📖 {livro_encontrado.get('titulo', 'Livro')}\n"
            f"⭐ Antiga: {estrelas_antigas} → ⭐ Nova: {livro_encontrado['estrelas']}"
        )

    @commands.command(name="reavaliar")
    async def reavaliar(self, ctx, *, argumentos: str):
        partes = argumentos.rsplit(' ', 1)
        if len(partes) < 2:
            return await ctx.send("❌ Uso correto: `!reavaliar \"Título - Autor\" 4.5`\nA nota deve ser entre 0.25 e 5, em passos de 0.25.")

        titulo_candidato = partes[0].strip()
        try:
            nota = float(partes[1].strip())
        except ValueError:
            return await ctx.send("❌ Nota inválida. Exemplo: `4.5` ou `3.75`")
        if not nota_valida(nota):
            return await ctx.send("❌ A nota deve ser entre 0.25 e 5, em passos de 0.25.")

        titulo_alvo = normalizar_livro_busca(titulo_candidato)
        livro_encontrado = None

        for livro in dados["livros_lidos"]:
            titulo_livro = livro.get("titulo", "").lower().strip()
            if titulo_livro == titulo_alvo:
                livro_encontrado = livro
                break

        if not livro_encontrado:
            for livro in dados["livros_lidos"]:
                titulo_livro = livro.get("titulo", "").lower().strip()
                if titulo_livro.startswith(titulo_alvo) or titulo_alvo.startswith(titulo_livro):
                    livro_encontrado = livro
                    break

        if not livro_encontrado:
            sugestoes = [f"• {l.get('titulo', 'Desconhecido')}" for l in dados["livros_lidos"][-5:]]
            return await ctx.send(f"❌ Não encontrei o livro **{titulo_candidato}** no teu histórico.\n\n**Últimos livros lidos:**\n" + "\n".join(sugestoes))

        nota_antiga = livro_encontrado.get("nota", 0.0)
        estrelas_antigas = livro_encontrado.get("estrelas", "Sem avaliação")

        livro_encontrado["nota"] = nota
        livro_encontrado["estrelas"] = estrelas_para_texto(nota)
        guardar_dados()

        await ctx.send(f"🔄 **Avaliação atualizada!**\n📖 {livro_encontrado.get('titulo', 'Livro')}\n⭐ Antiga: {estrelas_antigas} → ⭐ Nova: {livro_encontrado['estrelas']}")

    @commands.command(name="remlido")
    async def remlido(self, ctx, *, titulo_livro: str):
        encontrado = None
        for livro in dados["livros_lidos"]:
            if livro.get("titulo", "").lower().strip() == titulo_livro.lower().strip():
                encontrado = livro
                break

        if not encontrado:
            return await ctx.send("❌ Livro não encontrado.")

        dados["livros_lidos"].remove(encontrado)

        letras_limpas = []
        titulo_encontrado = encontrado.get("titulo", titulo_livro)
        for letra, livro_alfabeto in dados["desafio_alfabeto"].items():
            if str(livro_alfabeto).lower().strip() == titulo_encontrado.lower().strip():
                dados["desafio_alfabeto"][letra] = config.VAZIO_ALFABETO
                letras_limpas.append(letra)

        guardar_dados()

        aviso_alfabeto = f"\n🔤 Também removi do Desafio A-Z: **{', '.join(letras_limpas)}**." if letras_limpas else ""
        await ctx.send(f"🗑️ Livro removido: **{titulo_encontrado}**{aviso_alfabeto}")


async def setup(bot):
    await bot.add_cog(ReadingCog(bot))


