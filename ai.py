import json
import re
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional
from google import genai

import config
from models import RespostaMetas, RespostaRecomendacoes, RespostaSerie
from utils import validar_resposta_ia_pydantic, validar_resposta_ia

logger = logging.getLogger('CosmoBot')

ai_client = genai.Client(api_key=config.GEMINI_API_KEY)

# ==============================================================================
# GEMINI (FALLBACK)
# ==============================================================================

def gemini_text(prompt: str) -> str:
    response = ai_client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt
    )
    return response.text.strip() if response.text else ""


def gemini_json(prompt: str) -> Dict[str, Any]:
    response = ai_client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )
    texto = response.text if response.text else "{}"
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.IGNORECASE)
    if "{" in texto and "}" in texto:
        texto = texto[texto.find("{"):texto.rfind("}") + 1]
    return json.loads(texto)

# ==============================================================================
# DEEPSEEK (PRINCIPAL PARA TEXTO)
# ==============================================================================

def deepseek_text(prompt: str) -> str:
    if not config.DEEPSEEK_API_KEY:
        return gemini_text(prompt)
    
    headers = {
        "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    try:
        import urllib.request
        req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions", data=json.dumps(data).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"DeepSeek falhou: {e}, usando Gemini")
        return gemini_text(prompt)


def deepseek_json(prompt: str) -> Dict[str, Any]:
    if not config.DEEPSEEK_API_KEY:
        return gemini_json(prompt)
    
    prompt_json = f"{prompt}\n\nResponda APENAS com JSON válido, sem texto adicional."
    
    headers = {
        "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt_json}],
        "temperature": 0.3,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"}
    }
    
    try:
        import urllib.request
        req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions", data=json.dumps(data).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
            texto = result["choices"][0]["message"]["content"].strip()
            texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.IGNORECASE)
            if "{" in texto and "}" in texto:
                texto = texto[texto.find("{"):texto.rfind("}") + 1]
            return json.loads(texto)
    except Exception as e:
        logger.warning(f"DeepSeek JSON falhou: {e}, usando Gemini")
        return gemini_json(prompt)

# ==============================================================================
# IA HÍBRIDA (PRINCIPAL)
# ==============================================================================

async def ai_text_hibrido(prompt: str) -> str:
    """Tenta DeepSeek primeiro, fallback para Gemini"""
    try:
        return await asyncio.to_thread(deepseek_text, prompt)
    except Exception as e:
        logger.warning(f"DeepSeek falhou: {e}, usando Gemini")
        return await asyncio.to_thread(gemini_text, prompt)


async def ai_json_hibrido(prompt: str) -> Dict[str, Any]:
    """Tenta DeepSeek primeiro, fallback para Gemini"""
    try:
        return await asyncio.to_thread(deepseek_json, prompt)
    except Exception as e:
        logger.warning(f"DeepSeek JSON falhou: {e}, usando Gemini")
        return await asyncio.to_thread(gemini_json, prompt)

# ==============================================================================
# FUNÇÕES COM RETRY
# ==============================================================================

async def ai_text_com_retry(prompt: str, tentativas: int = 3, espera: int = 5) -> str:
    for tentativa in range(tentativas):
        try:
            return await asyncio.wait_for(ai_text_hibrido(prompt), timeout=25)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout na tentativa {tentativa + 1}/{tentativas}")
            if tentativa < tentativas - 1:
                await asyncio.sleep(espera * (tentativa + 1))
                continue
            else:
                return "❌ A IA demorou demasiado a responder. Tenta novamente."
        except Exception as e:
            logger.warning(f"Erro na IA: {e}")
            if tentativa < tentativas - 1:
                await asyncio.sleep(espera * (tentativa + 1))
                continue
            else:
                return f"❌ Erro na IA: {e}"
    return ""


async def ai_json_com_retry(prompt: str, tentativas: int = 3, espera: int = 5) -> Dict[str, Any]:
    for tentativa in range(tentativas):
        try:
            return await asyncio.wait_for(ai_json_hibrido(prompt), timeout=25)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout JSON na tentativa {tentativa + 1}/{tentativas}")
            if tentativa < tentativas - 1:
                await asyncio.sleep(espera * (tentativa + 1))
                continue
            else:
                return {}
        except Exception as e:
            logger.warning(f"Erro na IA JSON: {e}")
            if tentativa < tentativas - 1:
                await asyncio.sleep(espera * (tentativa + 1))
                continue
            else:
                return {}
    return {}

# ==============================================================================
# FUNÇÕES ESPECÍFICAS COM VALIDAÇÃO PYDANTIC
# ==============================================================================

async def gerar_metas_lc(livro: str, mes: str, cronograma: str) -> tuple:
    """Gera metas para leitura conjunta, retorna (metas, nota)"""
    prompt = f"""
You are a joint reading assistant. Create a reading schedule for "{livro}" in {mes} {config.este_ano()}.

Reader instructions:
"{cronograma}"

Rules:
1. Extract the goals with their specific dates.
2. Each goal should have a date (DD/MM format) and a short description.
3. Write the descriptions in European Portuguese (pt-PT) or English — never Brazilian Portuguese.

Respond only with valid JSON in this structure:
{{
  "metas": [ {{"data": "DD/MM/{config.este_ano()}", "texto": "Short goal description"}} ],
  "nota": "Brief explanation of the schedule (optional)"
}}
"""
    resposta = await ai_json_com_retry(prompt)
    
    # Validar com Pydantic
    try:
        validada = RespostaMetas(**resposta)
        return [meta.dict() for meta in validada.metas], validada.nota
    except Exception as e:
        logger.warning(f"Validação Pydantic falhou: {e}, usando fallback")
        return resposta.get("metas", []), resposta.get("nota", "")


async def gerar_recomendacoes(favoritos_texto: str, tbr_texto: str, vistos_texto: str) -> List[Dict]:
    """Gera recomendações de livros"""
    prompt = f"""
You are a literary curator.
The reader loved these books (rated 4 stars or higher). Suggest NEW books with similar tone, genre, pacing and emotional impact:
{favoritos_texto}

Rules:
- Recommend books similar to the highly-rated titles above (authors, subgenres, themes, vibe).
- Do NOT suggest books already in this TBR list: [{tbr_texto}].
- Do NOT suggest books already shown and dismissed: [{vistos_texto}].

Write all descriptive text in European Portuguese (pt-PT) OR English — never Brazilian Portuguese.

Respond only with valid JSON in this structure:
{{
  "livros": [
    {{
      "titulo": "Book Title",
      "autor": "Author Name",
      "data_publicacao": "Month/Year or DD/MM/YYYY",
      "genero": "Main Genre",
      "subgenero": "Subgenre",
      "porque_ler": "Short convincing text in pt-PT or English",
      "link_capa": "https://..."
    }}
  ]
}}

Suggest exactly 3 real books. Always include author and title separately.
"""
    resposta = await ai_json_com_retry(prompt)
    
    try:
        validada = RespostaRecomendacoes(**resposta)
        return [livro.dict() for livro in validada.livros]
    except Exception as e:
        logger.warning(f"Validação Pydantic falhou: {e}, usando fallback")
        return resposta.get("livros", [])


async def detetar_serie(titulo_livro: str) -> List[str]:
    """Deteta se um livro faz parte de uma série e retorna os próximos"""
    prompt = f"""
O utilizador adicionou o livro "{titulo_livro}".
Se este livro fizer parte de uma série literária conhecida, identifica os próximos livros da série (máximo 3).
Responde apenas em JSON válido:
{{"sequencias": ["Nome do Livro 2 - Autor", "Nome do Livro 3 - Autor", "Nome do Livro 4 - Autor"]}}
Se não for uma série ou não houver sequências conhecidas, responde:
{{"sequencias": []}}
"""
    resposta = await ai_json_com_retry(prompt)
    
    try:
        validada = RespostaSerie(**resposta)
        return validada.sequencias
    except Exception as e:
        logger.warning(f"Validação Pydantic falhou: {e}, usando fallback")
        return resposta.get("sequencias", [])


async def gerar_legenda_review(titulo: str, desabafos: List[str], conversas: List[str], anexos: List[str]) -> str:
    """Gera legenda para review do Bookstagram"""
    conteudo = ""
    
    if desabafos:
        conteudo += "**SENTIMENTOS E EMOÇÕES:**\n- " + "\n- ".join(desabafos) + "\n\n"
    
    if conversas:
        conteudo += "**CONVERSAS E DEBATES:**\n- " + "\n- ".join(conversas) + "\n\n"
    
    if anexos:
        conteudo += "**ANEXOS/PRINTS:**\n- " + "\n- ".join(anexos) + "\n\n"

    prompt = f"""
Create a structured, aesthetic and emotional Bookstagram caption in European Portuguese (pt-PT) or English.
The reader is sharing their experience with the book '{titulo}'.

Here is everything they captured during their reading journey:

{conteudo}

Instructions:
- Capture the authentic emotions and reactions
- If there are conversations/debates, include interesting quotes or arguments
- Make it feel personal and engaging, like a real reader sharing their journey
- Keep the tone natural and passionate
- Include emojis and line breaks for Instagram aesthetic
- Maximum 2000 characters

Write only the caption, no extra text.
"""
    return await ai_text_com_retry(prompt)