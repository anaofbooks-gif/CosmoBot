import json
import re
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional

from google import genai
import config
from models import RespostaMetas, RespostaRecomendacoes, RespostaSerie

logger = logging.getLogger('CosmoBot')
ai_client = genai.Client(api_key=config.GEMINI_API_KEY)


async def ai_text_hibrido(prompt: str) -> str:
    try:
        response = ai_client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config={"system_instruction": "És o Cosmo, um assistente literário erudito, divertido e mágico. Responde em português de Portugal."}
        )
        if response.text:
            return response.text
    except Exception as e:
        logger.warning(f"Gemini falhou: {e}")

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
    try:
        response = ai_client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json", "system_instruction": "Responde estritamente com JSON."}
        )
        txt = response.text if response.text else "{}"
        txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
        return json.loads(txt)
    except Exception as e:
        logger.warning(f"Gemini JSON falhou: {e}")

    if config.DEEPSEEK_API_KEY:
        headers = {"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": f"{prompt}\n\nResponde APENAS com JSON."}], "temperature": 0.2, "response_format": {"type": "json_object"}}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        txt = res_json["choices"][0]["message"]["content"]
                        txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
                        return json.loads(txt)
        except Exception as ds_err:
            logger.warning(f"DeepSeek JSON falhou: {ds_err}")
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


def validar_resposta_ia(resposta: Dict, campos: List[str]) -> Dict:
    if not isinstance(resposta, dict):
        return {}
    for campo in campos:
        if campo not in resposta:
            return {}
    return resposta


async def extrair_texto_da_imagem(url_imagem: str) -> str:
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
                        }
    except Exception:
        pass
    return {"titulo": query, "autor": "Desconhecido", "genero": "N/D", "paginas": 0, "capa": ""}
