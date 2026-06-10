import json
import re
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional

# Tentar importar o genai, mas com fallback
try:
    from google import genai
    AI_DISPONIVEL = True
except ImportError:
    import google.generativeai as genai
    AI_DISPONIVEL = True
except ImportError as e:
    print(f"⚠️ Google AI não disponível: {e}")
    AI_DISPONIVEL = False
    genai = None

import config

logger = logging.getLogger('CosmoBot')

# Só inicializa o cliente se a biblioteca estiver disponível
if AI_DISPONIVEL and genai:
    try:
        ai_client = genai.Client(api_key=config.GEMINI_API_KEY)
    except Exception as e:
        logger.warning(f"Erro ao inicializar Gemini: {e}")
        ai_client = None
else:
    ai_client = None


async def ai_text_hibrido(prompt: str) -> str:
    """Tenta gerar texto usando o Gemini; se falhar, recorre ao DeepSeek."""
    # 1. Tentativa com Gemini
    if ai_client:
        try:
            response = ai_client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config={"system_instruction": "És o Cosmo, um assistente literário. Responde em português de Portugal."}
            )
            if response.text:
                return response.text
        except Exception as e:
            logger.warning(f"Gemini falhou: {e}")
    else:
        logger.warning("Gemini não disponível")

    # 2. Fallback para DeepSeek (se configurado)
    if config.DEEPSEEK_API_KEY:
        headers = {"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        return res_json["choices"][0]["message"]["content"]
                    else:
                        logger.error(f"DeepSeek respondeu com status {resp.status}")
        except Exception as ds_err:
            logger.warning(f"DeepSeek falhou: {ds_err}")
    
    return "❌ Não foi possível obter resposta da IA."


async def ai_json_hibrido(prompt: str) -> Dict[str, Any]:
    """Tenta obter JSON usando o Gemini; se falhar, recorre ao DeepSeek."""
    logger.info(f"📤 Enviando prompt para IA (tamanho: {len(prompt)} caracteres)")
    
    # 1. Tentativa com Gemini
    if ai_client:
        try:
            response = ai_client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            txt = response.text if response.text else "{}"
            txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
            logger.info(f"✅ Gemini respondeu com {len(txt)} caracteres")
            return json.loads(txt)
        except Exception as e:
            logger.warning(f"Gemini JSON falhou: {e}")

    # 2. Fallback para DeepSeek
    if config.DEEPSEEK_API_KEY:
        headers = {"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": f"{prompt}\n\nResponde APENAS com JSON válido, sem texto adicional."}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        txt = res_json["choices"][0]["message"]["content"]
                        txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
                        logger.info(f"✅ DeepSeek respondeu com {len(txt)} caracteres")
                        return json.loads(txt)
                    else:
                        logger.error(f"DeepSeek respondeu com status {resp.status}")
        except Exception as ds_err:
            logger.warning(f"DeepSeek JSON falhou: {ds_err}")
    
    logger.error("❌ Todas as tentativas de IA falharam")
    return {}


async def ai_text_com_retry(prompt: str, tentativas: int = 3, espera: int = 5) -> str:
    for i in range(tentativas):
        try:
            return await asyncio.wait_for(ai_text_hibrido(prompt), timeout=25)
        except asyncio.TimeoutError:
            if i < tentativas - 1:
                await asyncio.sleep(espera * (i + 1))
                continue
            return "❌ A IA demorou demasiado. Tenta novamente."
        except Exception as e:
            if i < tentativas - 1:
                await asyncio.sleep(espera * (i + 1))
                continue
            logger.error(f"Erro na IA: {e}")
            return f"❌ Erro na IA: {e}"
    return ""


async def ai_json_com_retry(prompt: str, tentativas: int = 3, espera: int = 5) -> Dict:
    for i in range(tentativas):
        try:
            return await asyncio.wait_for(ai_json_hibrido(prompt), timeout=25)
        except (asyncio.TimeoutError, Exception):
            if i < tentativas - 1:
                await asyncio.sleep(espera * (i + 1))
                continue
            return {}
    return {}


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
    """Usa Gemini Vision para extrair texto de um print (requer a biblioteca)"""
    if not ai_client:
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
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=["Extrai TODO o texto visível nesta imagem. É um print de conversa. Retorna APENAS o texto.", imagem]
        )
        return response.text.strip() if response.text else ""
    except Exception as e:
        logger.error(f"Erro ao extrair texto da imagem: {e}")
        return ""


async def obter_info_livro(query: str) -> Dict:
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
    import config
    
    idx_mes_atual = config.MESES_ORDEM.index(mes_origem) if mes_origem in config.MESES_ORDEM else datetime.now().month - 1
    if mes_origem == "Geral":
        idx_mes_atual = datetime.now().month - 1
    
    mensagens = []
    for i, prox in enumerate(sequencias):
        idx_destino = (idx_mes_atual + 1 + i) % 12
        mes_destino = config.MESES_ORDEM[idx_destino]
        if not any(prox.lower().strip() == x.lower().strip() for x in livros_tbr_flat()):
            dados["tbr_por_mes"][mes_destino].append(prox)
            mensagens.append(f"• **{prox}** agendado para **{mes_destino}**")
    if mensagens:
        guardar_dados()
    return mensagens
