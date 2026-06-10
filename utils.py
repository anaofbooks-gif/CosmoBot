import re
import unicodedata
import hashlib
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import discord
import config


def formatar_livro(titulo: str, autor: str) -> str:
    if config.SEPARADOR_LIVRO in titulo:
        return titulo
    return f"{titulo}{config.SEPARADOR_LIVRO}{autor}"


def parsear_livro(texto: str) -> Tuple[str, str]:
    if config.SEPARADOR_LIVRO not in texto:
        raise ValueError("autor_obrigatorio")
    titulo, autor = texto.rsplit(config.SEPARADOR_LIVRO, 1)
    return titulo.strip(), autor.strip()


def livro_completo(texto: str) -> str:
    if config.SEPARADOR_LIVRO in texto:
        return texto.strip()
    raise ValueError("autor_obrigatorio")


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


def normalizar_titulo(titulo: str) -> str:
    return re.sub(r'^[~!@#$%^&*()_+{}\[\]:;<>?/\\|]+\s*', '', titulo)


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
    return texto


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
    return nota


def nota_valida(nota: float) -> bool:
    if nota < 0.25 or nota > 5:
        return False
    return round(nota * 4) % 4 == 0


def safe_custom_id(base: str, max_len: int = 100) -> str:
    if len(base) <= max_len:
        return base
    hash_sufixo = hashlib.md5(base.encode()).hexdigest()[:8]
    return f"{base[:max_len-9]}_{hash_sufixo}"


async def enviar_mensagem_longa(canal, texto, limite=1900):
    for i in range(0, len(texto), limite):
        await canal.send(texto[i:i+limite])


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
    existente = buscar_livro_case_insensitive(dados["tbr_por_mes"][mes], livro)
    if existente:
        return f"📌 **{existente}** já estava na TBR de **{mes}**."
    dados["tbr_por_mes"][mes].append(livro)
    guardar_dados()
    return f"📚 **{livro}** foi adicionado à TBR de **{mes}**."


def marcar_livro_sorteio_lido(titulo_completo: str) -> List[str]:
    from storage import dados, guardar_dados
    meses = []
    alvo = titulo_completo.lower().strip()
    for mes, info in dados.get("sorteios_mes", {}).items():
        livros = [l.lower().strip() for l in info.get("livros", [])]
        if alvo in livros:
            lidos = info.setdefault("lidos", [])
            if titulo_completo not in lidos:
                for livro in info.get("livros", []):
                    if livro.lower().strip() == alvo:
                        lidos.append(livro)
                        break
            pendentes = [l for l in info.get("livros", []) if l.lower().strip() not in {x.lower().strip() for x in lidos}]
            if not pendentes:
                meses.append(mes)
    guardar_dados()
    return meses


def livros_bem_avaliados(minimo: float = 4.0) -> List[Dict]:
    from storage import dados
    resultado = []
    for livro in dados.get("livros_lidos", []):
        nota = livro.get("nota", 0)
        if nota >= minimo:
            resultado.append(livro)
    return resultado
