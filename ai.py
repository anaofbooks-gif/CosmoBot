import json
import re
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional

import config

logger = logging.getLogger('CosmoBot')

# ==============================================================================
# GEMINI (via google.generativeai)
# ==============================================================================

GEMINI_DISPONIVEL = False
try:
    import google.generativeai as genai
    genai.configure(api_key=config.GEMINI_API_KEY)
    GEMINI_DISPONIVEL = True
    logger.info("✅ Gemini configurado com sucesso")
except ImportError:
    logger.warning("⚠️ Biblioteca google.generativeai não instalada")
except Exception as e:
    logger.warning(f"⚠️ Erro ao configurar Gemini: {e}")

# ==============================================================================
# DEEPSEEK
# ==============================================================================

DEEPSEEK_DISPONIVEL = bool(config.DEEPSEEK_API_KEY)
if DEEPSEEK_DISPONIVEL:
    logger.info("✅ DeepSeek API key configurada")
else:
    logger.warning("⚠️ DeepSeek API key não configurada")

# ==============================================================================
# FUNÇÕES PRINCIPAIS
# ==============================================================================

async def ai_json_hibrido(prompt: str) -> Dict[str, Any]:
    """Tenta DeepSeek primeiro, depois Gemini como fallback"""
    
    # 1. DeepSeek
    if DEEPSEEK_DISPONIVEL:
        headers = {
            "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": f"{prompt}\n\nRESPONDE APENAS COM JSON VÁLIDO. NADA MAIS."}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        txt = res_json["choices"][0]["message"]["content"]
                        txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
                        logger.info(f"✅ DeepSeek respondeu")
                        return json.loads(txt)
                    else:
                        logger.warning(f"⚠️ DeepSeek erro {resp.status}")
        except asyncio.TimeoutError:
            logger.warning("⚠️ DeepSeek timeout")
        except Exception as e:
            logger.warning(f"⚠️ DeepSeek exceção: {e}")

    # 2. Fallback: Gemini
    if GEMINI_DISPONIVEL:
        try:
            model = genai.GenerativeModel(config.GEMINI_MODEL)
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            txt = response.text if response.text else "{}"
            txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
            logger.info(f"✅ Gemini respondeu")
            return json.loads(txt)
        except Exception as e:
            logger.error(f"❌ Gemini falhou: {e}")
    
    logger.error("❌ Todas as tentativas de IA falharam")
    return {}


async def ai_text_hibrido(prompt: str) -> str:
    """Tenta DeepSeek primeiro, depois Gemini como fallback"""
    
    # 1. DeepSeek
    if DEEPSEEK_DISPONIVEL:
        headers = {
            "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        return res_json["choices"][0]["message"]["content"]
                    else:
                        logger.warning(f"⚠️ DeepSeek erro {resp.status}")
        except asyncio.TimeoutError:
            logger.warning("⚠️ DeepSeek timeout")
        except Exception as e:
            logger.warning(f"⚠️ DeepSeek exceção: {e}")

    # 2. Fallback: Gemini
    if GEMINI_DISPONIVEL:
        try:
            model = genai.GenerativeModel(config.GEMINI_MODEL)
            response = model.generate_content(prompt)
            return response.text if response.text else "❌ Sem resposta do Gemini."
        except Exception as e:
            logger.error(f"❌ Gemini falhou: {e}")
            return "❌ Ambas as IAs falharam."
    
    return "❌ Nenhuma IA disponível. Verifica as chaves no Railway."


async def ai_json_com_retry(prompt: str, tentativas: int = 2, espera: int = 3) -> Dict:
    for i in range(tentativas):
        try:
            return await asyncio.wait_for(ai_json_hibrido(prompt), timeout=35)
        except asyncio.TimeoutError:
            if i < tentativas - 1:
                await asyncio.sleep(espera)
                continue
            return {}
        except Exception:
            if i < tentativas - 1:
                await asyncio.sleep(espera)
                continue
            return {}
    return {}


async def ai_text_com_retry(prompt: str, tentativas: int = 2, espera: int = 3) -> str:
    for i in range(tentativas):
        try:
            return await asyncio.wait_for(ai_text_hibrido(prompt), timeout=35)
        except asyncio.TimeoutError:
            if i < tentativas - 1:
                await asyncio.sleep(espera)
                continue
            return "❌ A IA demorou demasiado."
        except Exception:
            if i < tentativas - 1:
                await asyncio.sleep(espera)
                continue
            return "❌ Erro na IA."
    return "❌ Erro na IA."


# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

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
    """OCR com Gemini"""
    if not GEMINI_DISPONIVEL:
        return ""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_imagem) as resp:
                if resp.status != 200:
                    return ""
                imagem_bytes = await resp.read()
        
        from PIL import Image
        import io
        imagem = Image.open(io.BytesIO(imagem_bytes))
        
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        response = model.generate_content(["Extrai TODO o texto visível nesta imagem. Retorna APENAS o texto.", imagem])
        return response.text if response.text else ""
    except Exception as e:
        logger.error(f"Erro OCR: {e}")
        return ""


async def obter_info_livro(query: str) -> Dict:
    """Pesquisa info do livro usando Open Library"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://openlibrary.org/search.json?q={query}&limit=1") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    docs = data.get("docs", [])
                    if docs:
                        doc = docs[0]
                        autores = doc.get("author_name", [])
                        return {
                            "titulo": doc.get("title", query),
                            "autor": autores[0] if autores else "Desconhecido",
                            "genero": ", ".join(doc.get("subject", [])[:3]) or "N/D",
                            "paginas": doc.get("number_of_pages_median", 0),
                            "capa": f"https://covers.openlibrary.org/b/id/{doc.get('cover_i')}-L.jpg" if doc.get("cover_i") else "",
                            "fonte": "Open Library",
                        }
    except Exception as e:
        logger.warning(f"Erro ao pesquisar livro: {e}")
    return {"titulo": query, "autor": "Desconhecido", "genero": "N/D", "paginas": 0, "capa": "", "fonte": "IA"}


async def detetar_e_agendar_serie(titulo_livro: str, mes_origem: str, canal) -> list:
    """Deteta série e agenda próximos livros"""
    prompt = f"""
O utilizador adicionou o livro "{titulo_livro}" para leitura em "{mes_origem}".
Se este livro fizer parte de uma série literária conhecida, identifica os próximos livros da série (máximo 3).
Responde apenas em JSON: {{"sequencias": ["Nome do Livro 2 - Autor", ...]}}
"""
    resposta = await ai_json_com_retry(prompt)
    sequencias = resposta.get("sequencias", [])
    if not sequencias:
        return []
    
    from storage import dados, guardar_dados, livros_tbr_flat
    from datetime import datetime
    
    idx_mes_atual = config.MESES_ORDEM.index(mes_origem) if mes_origem in config.MESES_ORDEM else datetime.now().month - 1
    if mes_origem == "Geral":
        idx_mes_atual = datetime.now().month - 1
    
    mensagens = []
    for i, prox in enumerate(sequencias[:3]):
        idx_destino = (idx_mes_atual + 1 + i) % 12
        mes_destino = config.MESES_ORDEM[idx_destino]
        if not any(prox.lower().strip() == x.lower().strip() for x in livros_tbr_flat()):
            dados["tbr_por_mes"][mes_destino].append(prox)
            mensagens.append(f"• **{prox}** agendado para **{mes_destino}**")
    if mensagens:
        guardar_dados()
    return mensagens
