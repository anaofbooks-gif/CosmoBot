import re
import unicodedata
import hashlib
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import discord
import config

_bot_instance = None


def set_bot_instance(bot):
    global _bot_instance
    _bot_instance = bot

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
    titulo, autor = titulo.strip(), autor.strip()
    if not titulo or not autor:
        raise ValueError("autor_obrigatorio")
    return titulo, autor

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

def livro_ja_lido(titulo_completo: str, dados: Dict) -> bool:
    alvo = titulo_completo.lower().strip()
    return any(l.get("titulo", "").lower().strip() == alvo for l in dados.get("livros_lidos", []))

def buscar_livro_case_insensitive(lista: List[str], alvo: str) -> Optional[str]:
    alvo_lower = alvo.lower().strip()
    for item in lista:
        if item.lower().strip() == alvo_lower:
            return item
    return None

def livros_bem_avaliados(dados: Dict, minimo: float = 4.0) -> List[Dict]:
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
    quartos = nota * 4
    return abs(quartos - round(quartos)) < 1e-9

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

# ========== FUNÇÕES DO DESAFIO A-Z ==========

def tem_artigo_no_inicio(titulo: str) -> bool:
    """
    Verifica se o título começa estritamente com um artigo (PT/EN).
    RETORNA True se tiver artigo -> NÃO ELEGÍVEL para o desafio.
    """
    if not titulo:
        return False
    
    t = titulo.strip().lower()
    
    artigos_proibidos = [
        "o ", "a ", "os ", "as ",
        "um ", "uma ", "uns ", "umas ",
        "the ", "a ", "an "
    ]
    
    return any(t.startswith(artigo) for artigo in artigos_proibidos)


def obter_primeira_letra_sem_artigo(titulo: str) -> Optional[str]:
    """
    Obtém a primeira letra do título APÓS remover artigos.
    Se o título começar com artigo, retorna None (não é elegível).
    """
    if not titulo:
        return None
    
    titulo_limpo = titulo.strip()
    
    # 🔥 REGRA DE OURO: Se começa com artigo, NÃO é elegível
    if tem_artigo_no_inicio(titulo_limpo):
        return None
    
    # Caso contrário, devolve a primeira letra
    for char in titulo_limpo:
        if char.isalpha():
            return char.upper()
    
    return None

# ========== FUNÇÕES DE DISCORD ==========

async def obter_canal_discord(canal_id: int) -> Optional[discord.abc.Messageable]:
    if not canal_id or _bot_instance is None:
        return None
    canal = _bot_instance.get_channel(int(canal_id))
    if canal:
        return canal
    if not _bot_instance.is_ready():
        return None
    try:
        return await _bot_instance.fetch_channel(int(canal_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError, TypeError, ValueError):
        return None

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

async def garantir_canal(guild: discord.Guild, nome: str) -> discord.TextChannel:
    canal = discord.utils.get(guild.text_channels, name=nome)
    if canal:
        return canal
    return await guild.create_text_channel(nome)


