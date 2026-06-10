from collections import Counter
from datetime import datetime
from typing import Dict, Any, List

import config
from storage import dados
from utils import parsear_livro, numero_mes


def estatisticas_mes(mes: str, ano: int) -> Dict[str, Any]:
    mes_num = numero_mes(mes)
    livros_mes = []
    for livro in dados["livros_lidos"]:
        data_txt = livro.get("data_leitura", "")
        try:
            data = datetime.strptime(data_txt, "%d/%m/%Y")
            if data.month == mes_num and data.year == ano:
                livros_mes.append(livro)
        except (TypeError, ValueError):
            continue
    paginas = sum(int(l.get("paginas", 0) or 0) for l in livros_mes)
    autores = [parsear_livro(l["titulo"])[1] for l in livros_mes if config.SEPARADOR_LIVRO in l.get("titulo", "")]
    generos = [l.get("genero", "N/D") for l in livros_mes if l.get("genero")]
    return {
        "livros": livros_mes,
        "total_livros": len(livros_mes),
        "paginas": paginas,
        "autores_unicos": len(set(autores)),
        "generos_unicos": len(set(generos)),
        "contagem_autores": Counter(autores).most_common(5),
        "contagem_generos": Counter(generos).most_common(5),
    }


def estatisticas_ano(ano: int) -> Dict[str, Any]:
    livros_ano = []
    for livro in dados["livros_lidos"]:
        data_txt = livro.get("data_leitura", "")
        try:
            data = datetime.strptime(data_txt, "%d/%m/%Y")
            if data.year == ano:
                livros_ano.append(livro)
        except (TypeError, ValueError):
            if str(ano) in data_txt:
                livros_ano.append(livro)
    autores = []
    generos = []
    paginas = 0
    for livro in livros_ano:
        paginas += int(livro.get("paginas", 0) or 0)
        if config.SEPARADOR_LIVRO in livro.get("titulo", ""):
            autores.append(parsear_livro(livro["titulo"])[1])
        if livro.get("genero"):
            generos.append(livro["genero"])
    contagem_autores = Counter(autores)
    contagem_generos = Counter(generos)
    autor_top = contagem_autores.most_common(1)[0] if contagem_autores else ("N/D", 0)
    genero_top = contagem_generos.most_common(1)[0] if contagem_generos else ("N/D", 0)
    return {
        "total_livros": len(livros_ano),
        "total_paginas": paginas,
        "autor_top": autor_top,
        "genero_top": genero_top,
        "top_autores": contagem_autores.most_common(5),
        "top_generos": contagem_generos.most_common(5),
    }
