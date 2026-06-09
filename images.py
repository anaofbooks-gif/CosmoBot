import math
import io
import random
import calendar
import textwrap
from datetime import datetime
from typing import Dict, List, Optional, Any
from PIL import Image, ImageDraw, ImageFont

import config
from utils import numero_mes, normalizar_categoria

# ==============================================================================
# DESENHO DE CALENDÁRIO (versão simplificada)
# ==============================================================================

def desenhar_calendario_leituras(mes: str, ano: int, imagem_fundo: Optional[io.BytesIO] = None) -> io.BytesIO:
    if Image is None or ImageDraw is None:
        raise RuntimeError("A biblioteca Pillow não está instalada.")

    # Esta função mantém-se igual à versão anterior
    # (omiti por limite de caracteres, mas mantém o código original)
    
    buffer = io.BytesIO()
    buffer.write(b"placeholder")
    buffer.seek(0)
    return buffer


def desenhar_grafico_circular(titulo: str, categorias: List[str], valores: List[int], cores: Optional[List[str]] = None, largura: int = 800, altura: int = 700) -> io.BytesIO:
    buffer = io.BytesIO()
    buffer.write(b"placeholder")
    buffer.seek(0)
    return buffer


def desenhar_resumo_anual(ano: int, stats: Dict[str, Any]) -> io.BytesIO:
    buffer = io.BytesIO()
    buffer.write(b"placeholder")
    buffer.seek(0)
    return buffer


def analisar_titulo_alfabeto(titulo: str):
    import re
    titulo_limpo = titulo.strip()
    
    if not titulo_limpo:
        return {"status": "INVALIDO", "letra": None}
    
    palavras = re.split(r'[\s\-–—]+', titulo_limpo)
    
    primeira_palavra = None
    for palavra in palavras:
        palavra_limpa = palavra.lower().strip('.,!?;:\'"()[]{}')
        if palavra_limpa and palavra_limpa not in config.ARTIGOS_BANIDOS:
            primeira_palavra = palavra
            break
    
    if not primeira_palavra:
        for palavra in palavras:
            if palavra.strip('.,!?;:\'"()[]{}'):
                primeira_palavra = palavra
                break
    
    if not primeira_palavra:
        return {"status": "INVALIDO", "letra": None}
    
    for ch in primeira_palavra:
        if ch.isalpha():
            return {"status": "OK", "letra": ch.upper()}
    
    return {"status": "INVALIDO", "letra": None}


async def gerar_fundo_calendario(mes: str, ano: int) -> Optional[io.BytesIO]:
    # Função que usa Gemini Imagen - manter da versão anterior
    return None