import re
import unicodedata
import hashlib
import asyncio
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import discord

import config

# ========== FUNÇÕES DE LIVROS ==========

def formatar_livro(titulo: str, autor: str) -> str:
    titulo = titulo.strip()
    autor = autor.strip()
    if config.SEPARADOR_LIVRO in titulo:
        return titulo
    if not autor:
        raise ValueError("autor_obrigatorio")
    return f"{titulo}{config.SEPARADOR_LIVRO}{autor}"

def parsear_livro(texto: str) -> Tuple[str, str]:
    texto = texto.strip()
    if config.SEPARADOR_LIVRO not in texto:
        raise ValueError("autor_obrigatorio")
    titulo, autor = texto.rsplit(config.SEPARADOR_LIVRO, 1)
    return titulo.strip(), autor.strip()

def livro_completo(texto: str) -> str:
    if config.SEPARADOR_LIVRO in texto:
        return texto.strip()
    raise ValueError("autor_obrigatorio")

def normalizar_titulo(titulo: str) -> str:
    return re.sub(r'^[~!@#$%^&*()_+{}\[\]:;<>?/\\|]+\s*', '', titulo)

def safe_custom_id(base: str, max_len: int = 100) -> str:
    if len(base) <= max_len:
        return base
    hash_sufixo = hashlib.md5(base.encode()).hexdigest()[:8]
    return f"{base[:max_len-9]}_{hash_sufixo}"

def livros_tbr_flat() -> List[str]:
    from storage import dados
    return [livro for lista in dados.get("tbr_por_mes", {}).values() for livro in lista]

def buscar_livro_case_insensitive(lista: List[str], alvo: str) -> Optional[str]:
    alvo_lower = alvo.lower().strip()
    for item in lista:
        if item.lower().strip() == alvo_lower:
            return item
    return None

def livro_ja_lido(titulo_completo: str, dados: Dict) -> bool:
    alvo = titulo_completo.lower().strip()
    return any(l.get("titulo", "").lower().strip() == alvo for l in dados.get("livros_lidos", []))

def adicionar_livro_a_tbr_mes(livro: str, mes: str) -> str:
    from storage import dados, guardar_dados
    existente_no_mes = buscar_livro_case_insensitive(dados["tbr_por_mes"][mes], livro)
    if existente_no_mes:
        return f"📌 **{existente_no_mes}** já estava na TBR de **{mes}**."

    removido_de = []
    titulo_a_guardar = livro

    for categoria, lista in dados["tbr_por_mes"].items():
        if categoria == mes:
            continue
        existente = buscar_livro_case_insensitive(lista, livro)
        if existente:
            lista.remove(existente)
            removido_de.append(categoria)
            titulo_a_guardar = existente

    dados["tbr_por_mes"][mes].append(titulo_a_guardar)
    guardar_dados()

    if removido_de:
        return f"📚 **{titulo_a_guardar}** foi movido da TBR de **{', '.join(removido_de)}** para **{mes}**."
    return f"📚 **{titulo_a_guardar}** foi adicionado à TBR de **{mes}**."

def marcar_livro_sorteio_lido(titulo_completo: str) -> List[str]:
    from storage import dados, guardar_dados
    meses_desbloqueados = []
    alvo = titulo_completo.lower().strip()
    for mes, info in dados.get("sorteios_mes", {}).items():
        livros = [l.lower().strip() for l in info.get("livros", [])]
        if alvo in livros:
            lidos = info.setdefault("lidos", [])
            if titulo_completo not in lidos and alvo not in {x.lower().strip() for x in lidos}:
                for livro in info.get("livros", []):
                    if livro.lower().strip() == alvo:
                        lidos.append(livro)
                        break
            pendentes = [l for l in info.get("livros", []) if l.lower().strip() not in {x.lower().strip() for x in lidos}]
            if not pendentes:
                meses_desbloqueados.append(mes)
    guardar_dados()
    return meses_desbloqueados

def sorteio_mes_ativo(mes: str) -> Optional[Dict[str, Any]]:
    from storage import dados
    info = dados.get("sorteios_mes", {}).get(mes)
    if not info:
        return None
    livros = info.get("livros", [])
    lidos = {l.lower().strip() for l in info.get("lidos", [])}
    pendentes = [l for l in livros if l.lower().strip() not in lidos]
    if pendentes:
        info["pendentes"] = pendentes
        return info
    return None

# ========== FUNÇÕES DE DISCORD ==========

async def obter_canal_discord(canal_id: int) -> Optional[discord.abc.Messageable]:
    from main import bot
    canal = bot.get_channel(canal_id)
    if canal:
        return canal
    try:
        return await bot.fetch_channel(canal_id)
    except (discord.NotFound, discord.HTTPException):
        return None

async def garantir_canal(guild: discord.Guild, nome: str) -> discord.TextChannel:
    canal = discord.utils.get(guild.text_channels, name=nome)
    if canal:
        return canal
    return await guild.create_text_channel(nome)

async def enviar_mensagem_longa(canal: discord.abc.Messageable, texto: str, limite: int = 1900) -> None:
    partes = []
    bloco_atual = ""

    for linha in texto.splitlines():
        if len(bloco_atual) + len(linha) + 1 > limite:
            partes.append(bloco_atual)
            bloco_atual = linha
        else:
            bloco_atual = f"{bloco_atual}\n{linha}" if bloco_atual else linha

    if bloco_atual:
        partes.append(bloco_atual)

    for parte in partes:
        await canal.send(parte)

# ========== FUNÇÕES DE DATA ==========

def hoje_str() -> str:
    return datetime.now().strftime("%d/%m/%Y")

def este_ano() -> str:
    return datetime.now().strftime("%Y")

def data_valida(data_texto: str) -> bool:
    try:
        datetime.strptime(data_texto, "%d/%m/%Y")
        return True
    except (TypeError, ValueError):
        return False

def normalizar_categoria(categoria: str) -> str:
    return categoria.strip().capitalize()

def numero_mes(mes: str) -> int:
    return config.MESES_ORDEM.index(normalizar_categoria(mes)) + 1

def canal_nome_seguro(base: str) -> str:
    texto = unicodedata.normalize("NFKD", base.lower().strip())
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"\s+", "-", texto)
    return "".join(ch for ch in texto if ch.isalnum() or ch == "-")

# ========== FUNÇÕES DE AVALIAÇÃO ==========

def estrelas_para_texto(nota: float) -> str:
    if nota <= 0:
        return "Sem avaliação"
    cheias = int(nota)
    resto = round(nota - cheias, 2)
    texto = "⭐" * cheias
    if resto == 0.25:
        texto += "¼"
    elif resto == 0.5:
        texto += "½"
    elif resto == 0.75:
        texto += "¾"
    elif resto > 0:
        texto += f" ({nota})"
    return texto or f"{nota}⭐"

def estrelas_para_nota(estrelas: str) -> float:
    if not estrelas or estrelas == "Sem avaliação":
        return 0.0
    nota = estrelas.count("⭐")
    if "¼" in estrelas:
        nota += 0.25
    elif "½" in estrelas:
        nota += 0.5
    elif "¾" in estrelas:
        nota += 0.75
    match = re.search(r'\((\d+\.?\d*)\)', estrelas)
    if match:
        nota = float(match.group(1))
    return float(nota)

def nota_valida(nota: float) -> bool:
    if nota < 0.25 or nota > 5:
        return False
    return round(nota * 4) % 4 == 0

def livros_bem_avaliados(minimo: float = 4.0) -> List[Dict[str, Any]]:
    from storage import dados
    resultado = []
    for livro in dados.get("livros_lidos", []):
        titulo = str(livro.get("titulo", "")).strip()
        if not titulo:
            continue
        nota = livro.get("nota")
        if isinstance(nota, (int, float)) and nota > 0:
            nota_valor = float(nota)
        else:
            estrelas = livro.get("estrelas", "")
            nota_valor = estrelas_para_nota(estrelas)
        if nota_valor >= minimo:
            resultado.append({**livro, "nota": nota_valor})
    return resultado
