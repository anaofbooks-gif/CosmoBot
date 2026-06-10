import json
import re
import asyncio
import aiohttp
import logging

import config

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CosmoBot')

# ========== GEMINI (google.genai) ==========
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

# ========== GROQ (gratuito, fallback) ==========
GROQ_DISPONIVEL = False
GROQ_CLIENT = None

try:
    import groq
    if config.GROQ_API_KEY:
        GROQ_CLIENT = groq.AsyncGroq(api_key=config.GROQ_API_KEY)
        GROQ_DISPONIVEL = True
        logger.info("✅ Groq configurado com sucesso (gratuito)")
    else:
        logger.warning("⚠️ GROQ_API_KEY não configurada")
except ImportError:
    logger.warning("⚠️ Biblioteca groq não instalada. Tente: pip install groq")
except Exception as e:
    logger.warning(f"⚠️ Erro ao configurar Groq: {e}")

# ========== CONFIGURAÇÕES ==========
TIMEOUT_IA = 25  # segundos
TIMEOUT_GROQ = 20

# Modelos para fallback (Groq tem vários gratuitos)
GROQ_MODELOS = [
    "mixtral-8x7b-32768",  # Mais inteligente, mais lento
    "llama3-70b-8192",      # Muito bom, rápido
    "llama3-8b-8192",       # Mais rápido, menos preciso
    "gemma2-9b-it",         # Google Gemma, bom equilíbrio
]


async def ai_json_hibrido(prompt: str) -> dict:
    """
    Tenta Gemini primeiro, se falhar usa Groq como fallback.
    Ambos são gratuitos.
    """
    
    # 1. Tenta Gemini
    if GEMINI_DISPONIVEL:
        try:
            if GEMINI_USE_LEGACY:
                import google.generativeai as genai_legacy
                model = genai_legacy.GenerativeModel(config.GEMINI_MODEL)
                response = await asyncio.wait_for(
                    model.generate_content_async(
                        prompt, 
                        generation_config={"response_mime_type": "application/json"}
                    ),
                    timeout=TIMEOUT_IA
                )
                txt = response.text if response.text else "{}"
            else:
                client = genai.Client(api_key=config.GEMINI_API_KEY)
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=config.GEMINI_MODEL,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2
                        )
                    ),
                    timeout=TIMEOUT_IA
                )
                txt = response.text if response.text else "{}"
            
            txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
            logger.info("✅ Gemini respondeu (JSON)")
            return json.loads(txt)
            
        except asyncio.TimeoutError:
            logger.warning("⚠️ Gemini timeout, a tentar Groq...")
        except Exception as e:
            logger.warning(f"⚠️ Gemini falhou: {e}, a tentar Groq...")

    # 2. Fallback: Groq (gratuito)
    if GROQ_DISPONIVEL and GROQ_CLIENT:
        for modelo in GROQ_MODELOS:
            try:
                completion = await asyncio.wait_for(
                    GROQ_CLIENT.chat.completions.create(
                        model=modelo,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant. Respond only with valid JSON. No explanations, no markdown, just pure JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.2,
                        response_format={"type": "json_object"}
                    ),
                    timeout=TIMEOUT_GROQ
                )
                txt = completion.choices[0].message.content
                txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
                logger.info(f"✅ Groq respondeu (JSON) usando {modelo}")
                return json.loads(txt)
                
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Groq timeout com {modelo}")
                continue
            except Exception as e:
                logger.warning(f"⚠️ Groq falhou com {modelo}: {e}")
                continue
    
    return {}


async def ai_text_hibrido(prompt: str) -> str:
    """
    Tenta Gemini primeiro, se falhar usa Groq como fallback.
    """
    
    # 1. Tenta Gemini
    if GEMINI_DISPONIVEL:
        try:
            if GEMINI_USE_LEGACY:
                import google.generativeai as genai_legacy
                model = genai_legacy.GenerativeModel(config.GEMINI_MODEL)
                response = await asyncio.wait_for(
                    model.generate_content_async(prompt),
                    timeout=TIMEOUT_IA
                )
                return response.text if response.text else "❌ Sem resposta do Gemini."
            else:
                client = genai.Client(api_key=config.GEMINI_API_KEY)
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=config.GEMINI_MODEL,
                        contents=prompt,
                        config=types.GenerateContentConfig(temperature=0.7)
                    ),
                    timeout=TIMEOUT_IA
                )
                return response.text if response.text else "❌ Sem resposta do Gemini."
                
        except asyncio.TimeoutError:
            logger.warning("⚠️ Gemini timeout, a tentar Groq...")
        except Exception as e:
            logger.warning(f"⚠️ Gemini falhou: {e}, a tentar Groq...")

    # 2. Fallback: Groq (gratuito)
    if GROQ_DISPONIVEL and GROQ_CLIENT:
        for modelo in GROQ_MODELOS[:2]:  # Só tenta os 2 melhores para texto
            try:
                completion = await asyncio.wait_for(
                    GROQ_CLIENT.chat.completions.create(
                        model=modelo,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7
                    ),
                    timeout=TIMEOUT_GROQ
                )
                txt = completion.choices[0].message.content
                logger.info(f"✅ Groq respondeu (texto) usando {modelo}")
                return txt
                
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Groq timeout com {modelo}")
                continue
            except Exception as e:
                logger.warning(f"⚠️ Groq falhou com {modelo}: {e}")
                continue
    
    return "❌ Nenhuma IA disponível. Tenta novamente mais tarde."


async def ai_json_com_retry(prompt: str, tentativas: int = 2, espera_base: int = 1) -> dict:
    """Tenta até {tentativas} vezes com exponential backoff"""
    for i in range(tentativas):
        resultado = await ai_json_hibrido(prompt)
        if resultado:
            return resultado
        
        if i < tentativas - 1:
            tempo_pausa = espera_base * (2 ** i)
            logger.warning(f"⏳ Tentativa {i+1}/{tentativas} falhou. Re-tentativa em {tempo_pausa}s...")
            await asyncio.sleep(tempo_pausa)
    
    logger.error(f"❌ JSON falhou após {tentativas} tentativas")
    return {}


async def ai_text_com_retry(prompt: str, tentativas: int = 2, espera_base: int = 1) -> str:
    """Tenta até {tentativas} vezes com exponential backoff"""
    for i in range(tentativas):
        resultado = await ai_text_hibrido(prompt)
        if resultado and not resultado.startswith("❌"):
            return resultado
        
        if i < tentativas - 1:
            tempo_pausa = espera_base * (2 ** i)
            logger.warning(f"⏳ Tentativa {i+1}/{tentativas} falhou. Re-tentativa em {tempo_pausa}s...")
            await asyncio.sleep(tempo_pausa)
    
    logger.error(f"❌ Texto falhou após {tentativas} tentativas")
    return "❌ A IA está indisponível no momento. Tenta novamente mais tarde."


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
    """Extrai texto de imagem usando IA (implementar com Gemini Vision se necessário)"""
    # TODO: Implementar com Gemini Vision
    return ""


async def obter_info_livro(query: str) -> dict:
    """Busca informação do livro na Open Library, fallback para IA"""
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
        logger.error(f"Erro ao pesquisar livro na Open Library: {e}")
    
    return {
        "titulo": query, 
        "autor": "Desconhecido", 
        "genero": "N/D", 
        "paginas": 0, 
        "ano": "N/D", 
        "capa": "", 
        "fonte": "IA"
    }


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
