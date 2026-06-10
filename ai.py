import json
import re
import asyncio
import aiohttp
import logging

import config

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CosmoBot')

# Gemini - tentar novo pacote primeiro, depois o antigo como fallback
GEMINI_DISPONIVEL = False
GEMINI_USE_LEGACY = False

try:
    from google import genai
    from google.genai import types
    GEMINI_USE_LEGACY = False
    GEMINI_DISPONIVEL = True
    logger.info("✅ Gemini configurado com sucesso (google.genai)")
except ImportError:
    try:
        import google.generativeai as genai_legacy
        genai_legacy.configure(api_key=config.GEMINI_API_KEY)
        GEMINI_USE_LEGACY = True
        GEMINI_DISPONIVEL = True
        logger.info("✅ Gemini configurado com sucesso (modo legado)")
    except ImportError:
        logger.warning("⚠️ Biblioteca google-genai não instalada. Tente: pip install google-genai")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao configurar Gemini: {e}")

# DeepSeek
DEEPSEEK_DISPONIVEL = bool(config.DEEPSEEK_API_KEY)
if DEEPSEEK_DISPONIVEL:
    logger.info("✅ DeepSeek API key configurada")


async def ai_json_hibrido(prompt: str) -> dict:
    # 1. DeepSeek
    if DEEPSEEK_DISPONIVEL:
        headers = {"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
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
                        logger.info("✅ DeepSeek respondeu (JSON)")
                        return json.loads(txt)
                    else:
                        logger.warning(f"⚠️ DeepSeek erro HTTP {resp.status}")
        except asyncio.TimeoutError:
            logger.warning("⚠️ DeepSeek timeout (30s)")
        except Exception as e:
            logger.warning(f"⚠️ DeepSeek falhou: {e}")

    # 2. Gemini (novo pacote ou legado)
    if GEMINI_DISPONIVEL:
        try:
            if GEMINI_USE_LEGACY:
                import google.generativeai as genai_legacy
                model = genai_legacy.GenerativeModel(config.GEMINI_MODEL)
                response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                txt = response.text if response.text else "{}"
            else:
                client = genai.Client(api_key=config.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2
                    )
                )
                txt = response.text if response.text else "{}"
            
            txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
            logger.info("✅ Gemini respondeu (JSON)")
            return json.loads(txt)
        except Exception as e:
            logger.warning(f"⚠️ Gemini falhou: {e}")

    return {}


async def ai_text_hibrido(prompt: str) -> str:
    # 1. DeepSeek
    if DEEPSEEK_DISPONIVEL:
        headers = {"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        txt = res_json["choices"][0]["message"]["content"]
                        logger.info("✅ DeepSeek respondeu (texto)")
                        return txt
                    else:
                        logger.warning(f"⚠️ DeepSeek erro HTTP {resp.status}")
        except asyncio.TimeoutError:
            logger.warning("⚠️ DeepSeek timeout (30s)")
        except Exception as e:
            logger.warning(f"⚠️ DeepSeek falhou: {e}")

    # 2. Gemini
    if GEMINI_DISPONIVEL:
        try:
            if GEMINI_USE_LEGACY:
                import google.generativeai as genai_legacy
                model = genai_legacy.GenerativeModel(config.GEMINI_MODEL)
                response = model.generate_content(prompt)
                return response.text if response.text else "❌ Sem resposta do Gemini."
            else:
                client = genai.Client(api_key=config.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.7)
                )
                return response.text if response.text else "❌ Sem resposta do Gemini."
        except Exception as e:
            logger.warning(f"⚠️ Gemini falhou: {e}")

    return "❌ Nenhuma IA disponível."


async def ai_json_com_retry(prompt: str, tentativas: int = 3, espera_base: int = 2) -> dict:
    """
    Exponential backoff: espera = 2s, 4s, 8s...
    """
    for i in range(tentativas):
        try:
            return await asyncio.wait_for(ai_json_hibrido(prompt), timeout=45)
        except asyncio.TimeoutError:
            if i < tentativas - 1:
                tempo_pausa = espera_base * (2 ** i)
                logger.warning(f"⏳ Timeout na tentativa {i+1}/{tentativas}. Re-tentativa em {tempo_pausa}s...")
                await asyncio.sleep(tempo_pausa)
                continue
            logger.error(f"❌ JSON falhou após {tentativas} tentativas (timeout)")
            return {}
        except Exception as e:
            if i < tentativas - 1:
                tempo_pausa = espera_base * (2 ** i)
                logger.warning(f"⚠️ Erro na tentativa {i+1}/{tentativas}: {e}. Re-tentativa em {tempo_pausa}s...")
                await asyncio.sleep(tempo_pausa)
                continue
            logger.error(f"❌ JSON falhou após {tentativas} tentativas: {e}")
            return {}
    return {}


async def ai_text_com_retry(prompt: str, tentativas: int = 3, espera_base: int = 2) -> str:
    """
    Exponential backoff: espera = 2s, 4s, 8s...
    """
    for i in range(tentativas):
        try:
            return await asyncio.wait_for(ai_text_hibrido(prompt), timeout=45)
        except asyncio.TimeoutError:
            if i < tentativas - 1:
                tempo_pausa = espera_base * (2 ** i)
                logger.warning(f"⏳ Timeout na tentativa {i+1}/{tentativas}. Re-tentativa em {tempo_pausa}s...")
                await asyncio.sleep(tempo_pausa)
                continue
            logger.error(f"❌ Texto falhou após {tentativas} tentativas (timeout)")
            return "❌ A IA demorou demasiado a responder. Tenta novamente."
        except Exception as e:
            if i < tentativas - 1:
                tempo_pausa = espera_base * (2 ** i)
                logger.warning(f"⚠️ Erro na tentativa {i+1}/{tentativas}: {e}. Re-tentativa em {tempo_pausa}s...")
                await asyncio.sleep(tempo_pausa)
                continue
            logger.error(f"❌ Texto falhou após {tentativas} tentativas: {e}")
            return "❌ Erro na IA. Tenta novamente mais tarde."
    return "❌ Erro na IA."


def validar_resposta_ia_pydantic(resposta: dict, schema_class):
    try:
        return schema_class(**resposta)
    except Exception as e:
        logger.warning(f"Validação Pydantic falhou: {e}")
        return None


def validar_resposta_ia(resposta: dict, campos: list) -> dict:
    if not isinstance(resposta, dict):
        return {}
    for campo in campos:
        if campo not in resposta:
            return {}
    return resposta


async def extrair_texto_da_imagem(url_imagem: str) -> str:
    """Extrai texto de imagem usando IA (placeholder - pode ser implementado com Gemini Vision)"""
    # TODO: Implementar com Gemini Vision
    return ""


async def obter_info_livro(query: str) -> dict:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://openlibrary.org/search.json?q={query}&limit=1") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    docs = data.get("docs", [])
                    if docs:
                        doc = docs[0]
                        autores = doc.get("author_name", [])
                        ano = doc.get("first_publish_year", doc.get("publish_year", ["N/D"]))
                        if isinstance(ano, list):
                            ano = ano[0] if ano else "N/D"
                        return {
                            "titulo": doc.get("title", query),
                            "autor": autores[0] if autores else "Desconhecido",
                            "genero": ", ".join(doc.get("subject", [])[:3]) or "N/D",
                            "paginas": doc.get("number_of_pages_median", 0),
                            "ano": str(ano),
                            "capa": f"https://covers.openlibrary.org/b/id/{doc.get('cover_i')}-L.jpg" if doc.get("cover_i") else "",
                            "fonte": "Open Library",
                        }
    except Exception as e:
        logger.error(f"Erro ao pesquisar livro: {e}")
    return {"titulo": query, "autor": "Desconhecido", "genero": "N/D", "paginas": 0, "ano": "N/D", "capa": "", "fonte": "IA"}


async def detetar_e_agendar_serie(titulo_livro: str, mes_origem: str, canal) -> list:
    from storage import dados, guardar_dados, livros_tbr_flat
    from datetime import datetime

    prompt = f"""
O utilizador adicionou o livro "{titulo_livro}" para leitura em "{mes_origem}".
Se este livro fizer parte de uma série literária conhecida, identifica os próximos livros da série (máximo 3).
Responde apenas em JSON: {{"sequencias": ["Nome do Livro 2 - Autor", ...]}}
"""
    resposta = await ai_json_com_retry(prompt)
    sequencias = resposta.get("sequencias", [])
    if not sequencias:
        return []

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
