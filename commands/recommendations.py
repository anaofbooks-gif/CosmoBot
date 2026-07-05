import logging
import re
import unicodedata
import aiohttp
import discord
from discord.ext import commands

import config
from storage import dados, guardar_dados, livros_tbr_flat
from utils import formatar_livro, livros_bem_avaliados, garantir_canal
from ai import ai_json_hibrido, validar_livro_existe
from views import ViewSugestoes

logger = logging.getLogger('CosmoBot')


def _normalizar_chave(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "").lower().strip())
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _titulo_sem_autor(texto: str) -> str:
    texto = str(texto or "").strip()
    if config.SEPARADOR_LIVRO in texto:
        return texto.rsplit(config.SEPARADOR_LIVRO, 1)[0].strip()
    return texto


def _chaves_livro(titulo: str, autor: str = "") -> set[str]:
    completo = formatar_livro(titulo, autor) if autor else str(titulo or "").strip()
    titulo_curto = _titulo_sem_autor(completo)
    chaves = {_normalizar_chave(completo), _normalizar_chave(titulo_curto)}
    if autor:
        chaves.add(_normalizar_chave(f"{titulo_curto} {autor}"))
    return {chave for chave in chaves if chave}


def _chaves_bloqueadas() -> set[str]:
    bloqueadas = set()
    for livro in dados.get("livros_lidos", []):
        bloqueadas.update(_chaves_livro(livro.get("titulo", ""), livro.get("autor", "")))
    for livro in livros_tbr_flat():
        bloqueadas.update(_chaves_livro(livro))
    for livro in dados.get("sugestoes_vistas", []):
        bloqueadas.update(_chaves_livro(livro))
    return bloqueadas


def _esta_bloqueado(titulo: str, autor: str, bloqueadas: set[str]) -> bool:
    return bool(_chaves_livro(titulo, autor) & bloqueadas)


def _resumir_bloqueados(max_items: int = 80) -> str:
    itens = []
    for livro in dados.get("livros_lidos", []):
        if livro.get("titulo"):
            itens.append(livro["titulo"])
    itens.extend(livros_tbr_flat())
    itens.extend(dados.get("sugestoes_vistas", []))
    vistos = set()
    unicos = []
    for item in itens:
        chave = _normalizar_chave(item)
        if chave and chave not in vistos:
            vistos.add(chave)
            unicos.append(item)
    return "; ".join(unicos[:max_items]) or "Nenhum"


async def _novidades_openlibrary(favoritos: list[dict], bloqueadas: set[str], limite: int = 3) -> list[dict]:
    candidatos = []
    temas = []
    for livro in favoritos[:8]:
        genero = str(livro.get("genero", "")).split(",")[0].strip()
        if genero and genero.upper() != "N/D":
            temas.append(genero)
    temas.extend(["fantasy", "romance", "fiction"])

    async with aiohttp.ClientSession() as session:
        for tema in temas:
            try:
                async with session.get(
                    "https://openlibrary.org/search.json",
                    params={"subject": tema, "sort": "new", "limit": 12, "language": "eng"},
                    timeout=12,
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
            except Exception as e:
                logger.warning(f"Falha ao procurar novidades na Open Library: {e}")
                continue

            for doc in data.get("docs", []):
                titulo = doc.get("title", "").strip()
                autores = doc.get("author_name") or []
                autor = autores[0].strip() if autores else ""
                if not titulo or not autor or _esta_bloqueado(titulo, autor, bloqueadas):
