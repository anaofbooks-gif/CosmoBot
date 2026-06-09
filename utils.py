import re
import unicodedata
import hashlib
from datetime import datetime
from typing import List, Optional, Tuple, Any, Dict
import discord

import config

# ==============================================================================
# FUNÇÕES DE LIVROS
# ==============================================================================

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
    titulo, autor = titulo.strip(), autor.strip()
    if not titulo or not autor:
        raise ValueError("autor_obrigatorio")
    return titulo, autor


def livro_completo(texto: str) -> str:
    if config.SEPARADOR_LIVRO in texto:
        return texto.strip()
    raise ValueError("autor_obrigatorio")


def livro_ja_lido(titulo_completo: str, dados: Dict) -> bool:
    alvo = titulo_completo.lower().strip()
    return any(l.get("titulo", "").lower().strip() == alvo for l in dados.get("livros_lidos", []))


def buscar_livro_case_insensitive(lista: List[str], alvo: str) -> Optional[str]:
    alvo_lower = alvo.lower().strip()
    for item in lista:
        if item.lower().strip() == alvo_lower:
            return item
    return None


def normalizar_titulo(titulo: str) -> str:
    """Remove caracteres especiais no início"""
    return re.sub(r'^[~!@#$%^&*()_+{}\[\]:;<>?/\\|]+\s*', '', titulo)


def safe_custom_id(base: str, max_len: int = 100) -> str:
    """Garante que o custom_id não ultrapassa o limite do Discord (100 caracteres)"""
    if len(base) <= max_len:
        return base
    hash_sufixo = hashlib.md5(base.encode()).hexdigest()[:8]
    prefixo = base[:max_len - 9]
    return f"{prefixo}_{hash_sufixo}"

# ==============================================================================
# FUNÇÕES DE DATA
# ==============================================================================

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


def numero_mes(mes: str) -> int:
    return config.MESES_ORDEM.index(normalizar_categoria(mes)) + 1


def normalizar_categoria(categoria: str) -> str:
    return categoria.strip().capitalize()

# ==============================================================================
# FUNÇÕES DE AVALIAÇÃO
# ==============================================================================

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
    resto = round(nota * 4) % 4
    return resto == 0

# ==============================================================================
# FUNÇÕES DE TEXTO
# ==============================================================================

def canal_nome_seguro(base: str) -> str:
    texto = unicodedata.normalize("NFKD", base.lower().strip())
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"\s+", "-", texto)
    return "".join(ch for ch in texto if ch.isalnum() or ch == "-")


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