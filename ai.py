import json
import re
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional

import config

logger = logging.getLogger('CosmoBot')

# Tentativa de importar a biblioteca correta do Gemini
try:
    import google.generativeai as genai
    GENAI_DISPONIVEL = True
    logger.info("✅ Biblioteca google.generativeai carregada")
except ImportError:
    try:
        from google import genai as genai_new
        GENAI_DISPONIVEL = True
        logger.info("✅ Biblioteca google.genai carregada")
    except ImportError:
        GENAI_DISPONIVEL = False
        logger.warning("⚠️ Nenhuma biblioteca do Gemini encontrada")

# Inicializar cliente Gemini
ai_client = None
if GENAI_DISPONIVEL:
    try:
        # Tentar com a sintaxe antiga
        genai.configure(api_key=config.GEMINI_API_KEY)
        ai_client = genai
        logger.info("✅ Gemini configurado com google.generativeai")
    except:
        try:
            # Tentar com a sintaxe nova
            from google import genai as genai_new
            ai_client = genai_new.Client(api_key=config.GEMINI_API_KEY)
            logger.info("✅ Gemini configurado com google.genai")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao configurar Gemini: {e}")


async def ai_text_hibrido(prompt: str) -> str:
    """Tenta gerar texto usando o Gemini; se falhar, recorre ao DeepSeek."""
    # 1. Tentativa com Gemini
    if ai_client:
        try:
            if hasattr(ai_client, 'generate_content'):
                # Sintaxe antiga
                response = ai_client.generate_content(model=config.GEMINI_MODEL, contents=prompt)
                if response and response.text:
                    return response.text
            elif hasattr(ai_client, 'models'):
                # Sintaxe nova
                response = ai_client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
                if response and response.text:
                    return response.text
        except Exception as e:
            logger.warning(f"Gemini falhou: {e}")

    # 2. Fallback para DeepSeek
    if config.DEEPSEEK_API_KEY:
        headers = {"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        return res_json["choices"][0]["message"]["content"]
        except Exception as ds_err:
            logger.warning(f"DeepSeek falhou: {ds_err}")
    
    return "❌ Sem resposta da IA."


async def ai_json_hibrido(prompt: str) -> Dict[str, Any]:
    """Usa OpenRouter para gerar JSON"""
    
    modelos_gratuitos = [
        "google/gemini-2.0-flash-exp:free",
        "microsoft/phi-3-mini-128k-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free",
        "deepseek/deepseek-chat:free"
    ]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    for modelo in modelos_gratuitos:
        payload = {
            "model": modelo,
            "messages": [{"role": "user", "content": f"{prompt}\n\nRESPONDE APENAS COM JSON VÁLIDO. NADA MAIS."}],
            "temperature": 0.2,
            "max_tokens": 500
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        txt = res_json["choices"][0]["message"]["content"]
                        txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
                        logger.info(f"✅ {modelo} respondeu: {txt[:200]}...")
                        return json.loads(txt)
                    elif resp.status == 429:
                        logger.warning(f"⚠️ {modelo} - Rate Limit atingido! A aguardar...")
                        await asyncio.sleep(5)  # Esperar 5 segundos antes de tentar outro modelo
                        continue
                    else:
                        logger.warning(f"{modelo} falhou com status {resp.status}")
        except asyncio.TimeoutError:
            logger.warning(f"{modelo} timeout")
        except Exception as e:
            logger.warning(f"{modelo} erro: {e}")
    
    logger.error("❌ Todos os modelos falharam")
    return {}


async def ai_json_com_retry(prompt: str, tentativas: int = 3, espera: int = 5) -> Dict:
    for i in range(tentativas):
        try:
            return await asyncio.wait_for(ai_json_hibrido(prompt), timeout=25)
        except asyncio.TimeoutError:
            if i < tentativas - 1:
                await asyncio.sleep(espera * (i + 1))
                continue
            return {}
        except Exception:
            if i < tentativas - 1:
                await asyncio.sleep(espera * (i + 1))
                continue
            return {}
    return {}


async def ai_text_com_retry(prompt: str, tentativas: int = 3, espera: int = 5) -> str:
    for i in range(tentativas):
        try:
            return await asyncio.wait_for(ai_text_hibrido(prompt), timeout=25)
        except asyncio.TimeoutError:
            if i < tentativas - 1:
                await asyncio.sleep(espera * (i + 1))
                continue
            return "❌ A IA demorou demasiado."
        except Exception:
            if i < tentativas - 1:
                await asyncio.sleep(espera * (i + 1))
                continue
            return "❌ Erro na IA."
    return "❌ Erro na IA."


# Funções auxiliares
def validar_resposta_ia_pydantic(resposta: Dict, schema_class) -> Optional[Any]:
    try:
        return schema_class(**resposta)
    except Exception as e:
        logger.warning(f"Validação Pydantic falhou: {e}")
        return None


def validar_resposta_ia(resposta: Dict, campos: list) -> Dict:
    if not isinstance(resposta, dict):
        return {}
    for campo in campos:
        if campo not in resposta:
            return {}
    return resposta


async def extrair_texto_da_imagem(url_imagem: str) -> str:
    return ""


async def obter_info_livro(query: str) -> Dict:
    return {"titulo": query, "autor": "Desconhecido", "genero": "N/D", "paginas": 0, "capa": "", "fonte": "IA"}


async def detetar_e_agendar_serie(titulo_livro: str, mes_origem: str, canal) -> list:
    return []
