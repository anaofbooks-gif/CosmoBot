import io
import math
import random
import calendar
import textwrap
from datetime import datetime
from typing import Dict, List, Optional, Any
from PIL import Image, ImageDraw, ImageFont

import config
from utils import numero_mes, normalizar_categoria
from storage import dados


def carregar_fonte(tamanho: int, negrito: bool = False):
    if ImageFont is None:
        return None
    nomes = ["arialbd.ttf", "segoeuib.ttf"] if negrito else ["arial.ttf", "segoeui.ttf"]
    for nome in nomes:
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def _desenhar_fatia(draw, cx, cy, raio, angulo_inicio, angulo_fim, cor):
    inicio_rad = math.radians(angulo_inicio - 90)
    fim_rad = math.radians(angulo_fim - 90)
    pontos = [(cx, cy)]
    x = cx + raio * math.cos(inicio_rad)
    y = cy + raio * math.sin(inicio_rad)
    pontos.append((x, y))
    num_pontos = max(10, int(abs(angulo_fim - angulo_inicio) / 5))
    for i in range(1, num_pontos + 1):
        ang = inicio_rad + (fim_rad - inicio_rad) * (i / num_pontos)
        x = cx + raio * math.cos(ang)
        y = cy + raio * math.sin(ang)
        pontos.append((x, y))
    draw.polygon(pontos, fill=cor, outline="#fff8f1", width=2)


def desenhar_grafico_circular(titulo: str, categorias: List[str], valores: List[int], cores: Optional[List[str]] = None, largura: int = 800, altura: int = 700) -> io.BytesIO:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow não instalada.")
    cores_padrao = ["#583d72", "#e86a5a", "#f4c542", "#5a9e4e", "#4a6fa5", "#c44d8c", "#e8a040", "#7fb07f", "#d4a55a", "#8b6b8b"]
    cores = cores or cores_padrao[:len(categorias)]
    imagem = Image.new("RGB", (largura, altura), "#fff8f1")
    draw = ImageDraw.Draw(imagem)
    fonte_titulo = carregar_fonte(28, negrito=True)
    fonte_legenda = carregar_fonte(18)
    fonte_valor = carregar_fonte(22, negrito=True)
    draw.text((largura // 2, 40), titulo, fill="#3b2f2f", font=fonte_titulo, anchor="mt")
    if not valores or sum(valores) == 0:
        draw.text((largura // 2, altura // 2), "Sem dados suficientes.", fill="#8a4f2d", font=fonte_legenda, anchor="mm")
        buffer = io.BytesIO()
        imagem.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    total = sum(valores)
    angulos = []
    angulo_atual = 0
    for valor in valores:
        angulo = (valor / total) * 360
        angulos.append((angulo_atual, angulo_atual + angulo))
        angulo_atual += angulo
    centro_x, centro_y = largura // 2 - 50, altura // 2 + 20
    raio = 180
    for i, (inicio, fim) in enumerate(angulos):
        _desenhar_fatia(draw, centro_x, centro_y, raio, inicio, fim, cores[i % len(cores)])
    draw.ellipse((centro_x - 60, centro_y - 60, centro_x + 60, centro_y + 60), fill="#fff8f1", outline="#d7c4b5", width=2)
    draw.text((centro_x, centro_y), str(total), fill="#583d72", font=fonte_valor, anchor="mm")
    legenda_x, legenda_y = centro_x + raio + 40, centro_y - 120
    for i, (cat, val) in enumerate(zip(categorias, valores)):
        draw.rectangle((legenda_x, legenda_y + i * 30, legenda_x + 20, legenda_y + i * 30 + 15), fill=cores[i % len(cores)])
        percentual = (val / total) * 100
        draw.text((legenda_x + 30, legenda_y + i * 30), f"{cat}: {val} ({percentual:.1f}%)", fill="#3b2f2f", font=fonte_legenda)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def desenhar_calendario_leituras(mes: str, ano: int, imagem_fundo: Optional[io.BytesIO] = None) -> io.BytesIO:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow não instalada.")
    mes_num = numero_mes(mes)
    metas_por_dia = {}
    for lembrete in dados["lembretes_metas"]:
        try:
            data = datetime.strptime(lembrete.get("data", ""), "%d/%m/%Y")
            if data.month == mes_num and data.year == ano:
                metas_por_dia.setdefault(data.day, []).append(f"{lembrete.get('livro', 'Livro')}: {lembrete.get('meta', '')}")
        except (TypeError, ValueError):
            continue
    largura, altura = 1400, 1000
    margem, topo = 60, 150
    largura_celula = (largura - margem * 2) // 7
    altura_celula = 115
    if imagem_fundo:
        try:
            imagem = Image.open(imagem_fundo).resize((largura, altura)).convert("RGBA")
            overlay = Image.new("RGBA", (largura, altura), (255, 255, 255, 180))
            imagem = Image.alpha_composite(imagem, overlay).convert("RGB")
        except Exception:
            imagem_fundo = None
    if not imagem_fundo:
        estacoes = {"Janeiro": "#e8f0f8", "Fevereiro": "#f5e6f0", "Março": "#e8f5e8", "Abril": "#fff0e0", "Maio": "#f0f5e8", "Junho": "#fff8e0", "Julho": "#ffe0e0", "Agosto": "#f5e6d3", "Setembro": "#f0ebe0", "Outubro": "#f5e0d0", "Novembro": "#e8e0e8", "Dezembro": "#e0f0f5"}
        imagem = Image.new("RGB", (largura, altura), estacoes.get(mes, "#fff8f1"))
    draw = ImageDraw.Draw(imagem)
    fonte_titulo = carregar_fonte(46, negrito=True)
    fonte_dia_semana = carregar_fonte(24, negrito=True)
    fonte_numero = carregar_fonte(24, negrito=True)
    fonte_meta = carregar_fonte(17)
    fonte_rodape = carregar_fonte(18)
    titulo = f"📚 Leituras conjuntas - {mes} {ano} 📚"
    draw.text((margem + 2, 47), titulo, fill="#000000", font=fonte_titulo)
    draw.text((margem, 45), titulo, fill="#3b2f2f", font=fonte_titulo)
    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    for idx, dia in enumerate(dias_semana):
        x = margem + idx * largura_celula
        draw.rounded_rectangle((x, topo, x + largura_celula - 8, topo + 42), radius=8, fill="#583d72")
        draw.text((x + 18, topo + 9), dia, fill="#ffffff", font=fonte_dia_semana)
    semanas = calendar.monthcalendar(ano, mes_num)
    y_inicio = topo + 55
    for linha, semana in enumerate(semanas):
        for coluna, dia in enumerate(semana):
            x1 = margem + coluna * largura_celula
            y1 = y_inicio + linha * altura_celula
            x2 = x1 + largura_celula - 8
            y2 = y1 + altura_celula - 8
            draw.rounded_rectangle((x1, y1, x2, y2), radius=10, fill=(255, 255, 255, 230), outline="#d7c4b5", width=2)
            if not dia:
                continue
            draw.text((x1 + 12, y1 + 10), str(dia), fill="#3b2f2f", font=fonte_numero)
            metas = metas_por_dia.get(dia, [])
            texto_y = y1 + 42
            for meta in metas[:2]:
                for linha_meta in textwrap.wrap(meta, width=24)[:3]:
                    draw.text((x1 + 12, texto_y), linha_meta, fill="#315f58", font=fonte_meta)
                    texto_y += 20
            if len(metas) > 2:
                draw.text((x1 + 12, y2 - 24), f"+{len(metas) - 2} meta(s)", fill="#8a4f2d", font=fonte_meta)
    if not metas_por_dia:
        draw.text((margem, altura - 85), "Ainda não há metas de leitura conjunta guardadas para este mês.", fill="#8a4f2d", font=fonte_rodape)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def desenhar_resumo_anual(ano: int, stats: Dict) -> io.BytesIO:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow não instalada.")
    largura, altura = 1400, 1000
    imagem = Image.new("RGB", (largura, altura), "#fff8f1")
    draw = ImageDraw.Draw(imagem)
    fonte_titulo = carregar_fonte(44, negrito=True)
    fonte_sec = carregar_fonte(28, negrito=True)
    fonte_txt = carregar_fonte(22)
    draw.text((60, 40), f"Resumo de Leituras {ano}", fill="#3b2f2f", font=fonte_titulo)
    draw.text((60, 110), f"Total de livros: {stats.get('total_livros', 0)}", fill="#583d72", font=fonte_sec)
    draw.text((60, 160), f"Páginas lidas: {stats.get('total_paginas', 0)}", fill="#315f58", font=fonte_sec)
    autor_top = stats.get("autor_top", ("N/D", 0))
    genero_top = stats.get("genero_top", ("N/D", 0))
    draw.text((60, 240), "Autor mais lido", fill="#8a4f2d", font=fonte_sec)
    draw.text((60, 285), f"{autor_top[0]} ({autor_top[1]} livros)", fill="#3b2f2f", font=fonte_txt)
    draw.text((60, 360), "Género dominante", fill="#8a4f2d", font=fonte_sec)
    draw.text((60, 405), f"{genero_top[0]} ({genero_top[1]} livros)", fill="#3b2f2f", font=fonte_txt)
    y = 500
    draw.text((60, y), "Top autores", fill="#8a4f2d", font=fonte_sec)
    y += 45
    for autor, qtd in stats.get("top_autores", [])[:5]:
        draw.text((80, y), f"• {autor}: {qtd}", fill="#3b2f2f", font=fonte_txt)
        y += 34
    y = 500
    draw.text((720, y), "Top géneros", fill="#8a4f2d", font=fonte_sec)
    y += 45
    for genero, qtd in stats.get("top_generos", [])[:5]:
        draw.text((740, y), f"• {genero}: {qtd}", fill="#3b2f2f", font=fonte_txt)
        y += 34
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def analisar_titulo_alfabeto(titulo: str):
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
    """Gera uma imagem de fundo temática para o calendário usando Gemini Imagen."""
    prompts = {
        "Janeiro": "fundo azul inverno com flocos de neve suaves, estilo aquarela, tons pastel",
        "Fevereiro": "fundo romântico coração e flores, tons rosa e vermelho, estilo aquarela",
        "Março": "fundo primavera com flores silvestres e folhas verdes, tons pastel, estilo aquarela",
        "Abril": "fundo de Páscoa com ovos decorados e flores, tons lilás e amarelo, estilo aquarela",
        "Maio": "fundo de campo de flores coloridas, céu azul claro, estilo aquarela",
        "Junho": "fundo de praia, areia clara e mar azul, sol brilhante, estilo aquarela de verão",
        "Julho": "fundo de férias de verão, palmeiras e sol, cores quentes, estilo tropical aquarela",
        "Agosto": "fundo de pôr do sol na praia, tons laranja e rosa, estilo aquarela",
        "Setembro": "fundo de folhas de outono caindo, tons laranja e dourado, estilo aquarela",
        "Outubro": "fundo de Halloween com abóboras e folhas secas, tons laranja e roxo, estilo aquarela",
        "Novembro": "fundo de outono profundo, tons castanho e vinho, estilo aquarela",
        "Dezembro": "fundo de Natal com árvores e neve, tons vermelho e verde, estilo aquarela",
    }
    
    from ai import ai_client
    if not ai_client:
        return None
    
    prompt = prompts.get(mes, f"fundo abstrato suave para calendário de {mes}, estilo aquarela, tons pastel")
    
    try:
        response = ai_client.models.generate_content(
            model="imagen-3.0-generate-001",
            contents=prompt,
            config={
                "response_modalities": ["IMAGE"],
                "image_config": {
                    "aspect_ratio": "16:9",
                    "output_format": "png"
                }
            }
        )
        
        for part in response.parts:
            if part.inline_data:
                logger.info(f"🎨 Fundo IA gerado para {mes}")
                return io.BytesIO(part.inline_data.data)
        return None
    except Exception as e:
        logger.warning(f"Erro ao gerar fundo com IA: {e}")
        return None
