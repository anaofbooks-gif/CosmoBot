import io
import logging 
import math
import random
import calendar
import textwrap
import aiohttp
from datetime import datetime
from typing import Dict, List, Optional, Any
from PIL import Image, ImageDraw, ImageFont

import config
from utils import numero_mes, normalizar_categoria
from storage import dados

logger = logging.getLogger('CosmoBot')

# ========== CORES TEMÁTICAS POR MÊS ==========

ESTACOES = {
    "Janeiro": {"bg": "#e8f0f8", "header": "#4a6fa5", "texto": "#2c3e50", "destaque": "#7fb3d5", "titulo": "#2c3e50", "emoji": "❄️"},
    "Fevereiro": {"bg": "#f5e6f0", "header": "#c44d8c", "texto": "#5a2d4a", "destaque": "#e8a0c0", "titulo": "#8b3a62", "emoji": "💕"},
    "Março": {"bg": "#e8f5e8", "header": "#5a9e4e", "texto": "#2d4a2d", "destaque": "#a8d5a0", "titulo": "#2d6a2d", "emoji": "🌸"},
    "Abril": {"bg": "#fff0e0", "header": "#e8a040", "texto": "#5a3a1a", "destaque": "#f5d0a0", "titulo": "#c47a2a", "emoji": "🌧️"},
    "Maio": {"bg": "#f0f5e8", "header": "#7fb07f", "texto": "#3a5a2a", "destaque": "#c5e0b4", "titulo": "#5a8a3a", "emoji": "🌺"},
    "Junho": {"bg": "#fff8e0", "header": "#f4c542", "texto": "#7a5a1a", "destaque": "#ffdf99", "titulo": "#daa520", "emoji": "☀️", "sol": True},
    "Julho": {"bg": "#ffe0e0", "header": "#e86a5a", "texto": "#7a2a1a", "destaque": "#ffb3a3", "titulo": "#cc4422", "emoji": "🏖️", "sol": True, "palmeira": True},
    "Agosto": {"bg": "#f5e6d3", "header": "#d4a55a", "texto": "#6b4c2a", "destaque": "#f5d5a0", "titulo": "#b8860b", "emoji": "🌊", "sol": True, "palmeira": True},
    "Setembro": {"bg": "#f0ebe0", "header": "#b8860b", "texto": "#5a4a2a", "destaque": "#e8d5a0", "titulo": "#8b6508", "emoji": "🍂"},
    "Outubro": {"bg": "#f5e0d0", "header": "#e87a30", "texto": "#5a3a1a", "destaque": "#ffcc99", "titulo": "#cc5500", "emoji": "🎃", "abobora": True},
    "Novembro": {"bg": "#e8e0e8", "header": "#8b6b8b", "texto": "#4a3a4a", "destaque": "#c5aec5", "titulo": "#6b4a6b", "emoji": "🍁"},
    "Dezembro": {"bg": "#e0f0f5", "header": "#2d8f8f", "texto": "#1a4a5a", "destaque": "#a0d0d5", "titulo": "#1a6a7a", "emoji": "🎄", "neve": True},
}


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
    
    # Usar cores temáticas do mês
    tema = ESTACOES.get(mes, ESTACOES["Janeiro"])
    cor_fundo = tema["bg"]
    cor_header = tema["header"]
    cor_texto = tema["texto"]
    cor_destaque = tema["destaque"]
    cor_titulo = tema["titulo"]
    emoji = tema.get("emoji", "📚")
    
    # Se tiver imagem de fundo IA, usa-a; senão usa cor sólida
    if imagem_fundo:
        try:
            imagem = Image.open(imagem_fundo).resize((largura, altura)).convert("RGBA")
            overlay = Image.new("RGBA", (largura, altura), (255, 255, 255, 180))
            imagem = Image.alpha_composite(imagem, overlay).convert("RGB")
        except Exception:
            imagem_fundo = None
    
    if not imagem_fundo:
        imagem = Image.new("RGB", (largura, altura), cor_fundo)
    
    draw = ImageDraw.Draw(imagem)
    
    fonte_titulo = carregar_fonte(46, negrito=True)
    fonte_dia_semana = carregar_fonte(24, negrito=True)
    fonte_numero = carregar_fonte(24, negrito=True)
    fonte_meta = carregar_fonte(17)
    fonte_rodape = carregar_fonte(18)
    
    titulo = f"{emoji} Leituras conjuntas - {mes} {ano} {emoji}"
    draw.text((margem + 2, 47), titulo, fill="#000000", font=fonte_titulo)
    draw.text((margem, 45), titulo, fill=cor_titulo, font=fonte_titulo)
    
    draw.text((margem + 2, 107), "Metas guardadas pelo comando !meta", fill="#000000", font=fonte_rodape)
    draw.text((margem, 105), "Metas guardadas pelo comando !meta", fill=cor_destaque, font=fonte_rodape)
    
    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    for idx, dia in enumerate(dias_semana):
        x = margem + idx * largura_celula
        draw.rounded_rectangle((x, topo, x + largura_celula - 8, topo + 42), radius=8, fill=cor_header)
        draw.text((x + 18, topo + 9), dia, fill="#ffffff", font=fonte_dia_semana)
    
    # Desenhar elementos decorativos sazonais
    if tema.get("sol"):
        draw.ellipse((largura - 100, 30, largura - 60, 70), fill="#FFD700", outline="#FFA500", width=3)
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            x1 = largura - 80 + 25 * math.cos(rad)
            y1 = 50 + 25 * math.sin(rad)
            x2 = largura - 80 + 45 * math.cos(rad)
            y2 = 50 + 45 * math.sin(rad)
            draw.line((x1, y1, x2, y2), fill="#FFA500", width=3)
    
    if tema.get("palmeira"):
        draw.line((50, altura - 100, 50, altura - 40), fill="#8B4513", width=5)
        draw.arc((30, altura - 130, 70, altura - 90), 0, 180, fill="#228B22", width=6)
        draw.arc((20, altura - 120, 60, altura - 80), 20, 160, fill="#228B22", width=6)
        draw.arc((40, altura - 120, 80, altura - 80), 20, 160, fill="#228B22", width=6)
    
    if tema.get("abobora"):
        draw.ellipse((30, 30, 80, 80), fill="#FF8C00", outline="#CC5500", width=2)
        draw.rectangle((50, 20, 60, 30), fill="#228B22")
    
    if tema.get("neve"):
        for _ in range(30):
            x = random.randint(50, largura - 50)
            y = random.randint(50, altura - 50)
            draw.line((x - 5, y, x + 5, y), fill="#FFFFFF", width=2)
            draw.line((x, y - 5, x, y + 5), fill="#FFFFFF", width=2)
            draw.line((x - 4, y - 4, x + 4, y + 4), fill="#FFFFFF", width=1)
            draw.line((x + 4, y - 4, x - 4, y + 4), fill="#FFFFFF", width=1)
    
    semanas = calendar.monthcalendar(ano, mes_num)
    y_inicio = topo + 55
    
    for linha, semana in enumerate(semanas):
        for coluna, dia in enumerate(semana):
            x1 = margem + coluna * largura_celula
            y1 = y_inicio + linha * altura_celula
            x2 = x1 + largura_celula - 8
            y2 = y1 + altura_celula - 8
            draw.rounded_rectangle((x1, y1, x2, y2), radius=10, fill=(255, 255, 255, 230), outline=cor_destaque, width=2)
            if not dia:
                continue
            draw.text((x1 + 12, y1 + 10), str(dia), fill=cor_texto, font=fonte_numero)
            metas = metas_por_dia.get(dia, [])
            texto_y = y1 + 42
            for meta in metas[:2]:
                for linha_meta in textwrap.wrap(meta, width=24)[:3]:
                    draw.text((x1 + 12, texto_y), linha_meta, fill=cor_header, font=fonte_meta)
                    texto_y += 20
            if len(metas) > 2:
                draw.text((x1 + 12, y2 - 24), f"+{len(metas) - 2} meta(s)", fill=cor_titulo, font=fonte_meta)
    
    if not metas_por_dia:
        draw.text((margem, altura - 85), "Ainda não há metas de leitura conjunta guardadas para este mês.", fill=cor_titulo, font=fonte_rodape)
    
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
    """Gera fundo temático usando Stable Diffusion (via Replicate)"""
    import aiohttp
    import logging
    logger = logging.getLogger('CosmoBot')
    
    # Prompts para Stable Diffusion
    prompts = {
        "Janeiro": "winter landscape with soft snowflakes, light blue and white watercolor style, minimalist, no text, no letters",
        "Fevereiro": "romantic background with hearts and cherry blossoms, soft pink and red watercolor style, no text",
        "Março": "spring flowers and green leaves, pastel colors, watercolor style, no text",
        "Abril": "Easter eggs and bunnies, lilac and yellow watercolor, cute style, no text",
        "Maio": "flower field with blue sky, vibrant but soft watercolor, no text",
        "Junho": "tropical beach with palm trees, turquoise water, bright sun, watercolor summer style, no text",
        "Julho": "summer vacation beach with palm trees, hot sun, warm colors, tropical watercolor, no text",
        "Agosto": "sunset beach with orange and pink sky, calm ocean, palm trees silhouette, watercolor, no text",
        "Setembro": "autumn leaves falling, orange and golden watercolor, soft style, no text",
        "Outubro": "Halloween pumpkins and dry leaves, orange and purple watercolor, mysterious, no text",
        "Novembro": "deep autumn with brown and wine colors, dry leaves, melancholic watercolor, no text",
        "Dezembro": "Christmas trees with snow falling, red and green watercolor, festive, no text"
    }
    
    prompt = prompts.get(mes, f"soft abstract watercolor background for {mes}, pastel colors, no text, no letters")
    negative_prompt = "text, letters, words, writing, signature, watermark, human, people, faces"
    
    replicate_key = os.getenv("REPLICATE_API_KEY")
    if not replicate_key:
        logger.warning("⚠️ REPLICATE_API_KEY não configurada. Usando fundo padrão.")
        return None
    
    try:
        headers = {
            "Authorization": f"Token {replicate_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "version": "stability-ai/stable-diffusion-3.5-large",
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": 1408,
                "height": 896,
                "num_outputs": 1,
                "scheduler": "DPMSolverMultistep",
                "num_inference_steps": 28,
                "guidance_scale": 7.5
            }
        }
        
        async with aiohttp.ClientSession() as session:
            # Criar a previsão
            async with session.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload) as resp:
                if resp.status != 201:
                    logger.warning(f"Erro ao criar previsão: {resp.status}")
                    return None
                prediction = await resp.json()
                prediction_url = prediction.get("urls", {}).get("get")
                
                if not prediction_url:
                    return None
                
                # Aguardar a conclusão
                for _ in range(30):  # máximo 30 tentativas (30 segundos)
                    await asyncio.sleep(1)
                    async with session.get(prediction_url, headers=headers) as status_resp:
                        if status_resp.status != 200:
                            continue
                        status_data = await status_resp.json()
                        if status_data.get("status") == "succeeded":
                            output = status_data.get("output", [])
                            if output and len(output) > 0:
                                image_url = output[0]
                                # Descarregar a imagem
                                async with session.get(image_url) as img_resp:
                                    if img_resp.status == 200:
                                        image_bytes = await img_resp.read()
                                        logger.info(f"🎨 Fundo IA gerado para {mes}")
                                        return io.BytesIO(image_bytes)
                            break
                        elif status_data.get("status") == "failed":
                            logger.warning(f"Falha na geração: {status_data.get('error')}")
                            break
        
        return None
        
    except Exception as e:
        logger.warning(f"⚠️ Erro ao gerar fundo IA: {e}")
        return None
