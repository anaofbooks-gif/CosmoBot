import json
import re
import asyncio
import aiohttp
import logging
import unicodedata
import os

import config

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CosmoBot')

# ========== GEMINI ==========
GEMINI_DISPONIVEL = False
GEMINI_USE_LEGACY = False

try:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada")
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
        logger.warning("⚠️ Biblioteca google-genai não instalada")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao configurar Gemini: {e}")
except Exception as e:
    logger.warning(f"⚠️ Gemini indisponível: {e}")

# ========== CONFIGURAÇÕES ==========
TIMEOUT_IA = 25

# Modelos Gemini disponíveis
MODELOS_GEMINI = []
for modelo in os.getenv("GEMINI_MODELS", config.GEMINI_MODEL).split(","):
    modelo = modelo.strip()
    if modelo and modelo not in MODELOS_GEMINI:
        MODELOS_GEMINI.append(modelo)
for modelo in ["gemini-2.0-flash"]:
    if modelo not in MODELOS_GEMINI:
        MODELOS_GEMINI.append(modelo)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", getattr(config, "GROQ_API_KEY", ""))
GROQ_MODELS = [m.strip() for m in os.getenv("GROQ_MODELS", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")).split(",") if m.strip()]
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODELS = [m.strip() for m in os.getenv("OPENROUTER_MODELS", os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")).split(",") if m.strip()]


def _extrair_json(txt: str) -> dict:
    txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        inicio = txt.find("{")
        fim = txt.rfind("}")
        if inicio < 0 or fim <= inicio:
            raise
        return json.loads(txt[inicio:fim + 1])


async def _chat_completion(
    *,
    provider: str,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    json_mode: bool,
    temperature: float,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "OpenRouter":
        headers["HTTP-Referer"] = os.getenv("OPENROUTER_SITE_URL", "https://railway.app")
        headers["X-Title"] = os.getenv("OPENROUTER_APP_NAME", "CosmoBot")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=TIMEOUT_IA) as resp:
            texto = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"{provider} {model} HTTP {resp.status}: {texto[:500]}")
            data = json.loads(texto)
            return data["choices"][0]["message"]["content"] or ""


async def _groq_json(prompt: str) -> dict:
    if not GROQ_API_KEY:
        return {}
    for modelo in GROQ_MODELS:
        try:
            txt = await _chat_completion(
                provider="Groq",
                url="https://api.groq.com/openai/v1/chat/completions",
                api_key=GROQ_API_KEY,
                model=modelo,
                prompt=prompt,
                json_mode=True,
                temperature=0.2,
            )
            logger.info(f"✅ Groq respondeu (JSON) com modelo {modelo}")
            return _extrair_json(txt)
        except Exception as e:
            logger.warning(f"⚠️ Groq falhou com {modelo}: {e}")
    return {}


async def _groq_text(prompt: str) -> str:
    if not GROQ_API_KEY:
        return ""
    for modelo in GROQ_MODELS:
        try:
            txt = await _chat_completion(
                provider="Groq",
                url="https://api.groq.com/openai/v1/chat/completions",
                api_key=GROQ_API_KEY,
                model=modelo,
                prompt=prompt,
                json_mode=False,
                temperature=0.7,
            )
            logger.info(f"✅ Groq respondeu (texto) com modelo {modelo}")
            return txt
        except Exception as e:
            logger.warning(f"⚠️ Groq falhou com {modelo}: {e}")
    return ""


async def _openrouter_json(prompt: str) -> dict:
    if not OPENROUTER_API_KEY:
        return {}
    for modelo in OPENROUTER_MODELS:
        try:
            txt = await _chat_completion(
                provider="OpenRouter",
                url="https://openrouter.ai/api/v1/chat/completions",
                api_key=OPENROUTER_API_KEY,
                model=modelo,
                prompt=prompt,
                json_mode=True,
                temperature=0.2,
            )
            logger.info(f"✅ OpenRouter respondeu (JSON) com modelo {modelo}")
            return _extrair_json(txt)
        except Exception as e:
            logger.warning(f"⚠️ OpenRouter falhou com {modelo}: {e}")
    return {}


async def _openrouter_text(prompt: str) -> str:
    if not OPENROUTER_API_KEY:
        return ""
    for modelo in OPENROUTER_MODELS:
        try:
            txt = await _chat_completion(
                provider="OpenRouter",
                url="https://openrouter.ai/api/v1/chat/completions",
                api_key=OPENROUTER_API_KEY,
                model=modelo,
                prompt=prompt,
                json_mode=False,
                temperature=0.7,
            )
            logger.info(f"✅ OpenRouter respondeu (texto) com modelo {modelo}")
            return txt
        except Exception as e:
            logger.warning(f"⚠️ OpenRouter falhou com {modelo}: {e}")
    return ""


async def ai_json_hibrido(prompt: str) -> dict:
    """Tenta Gemini, Groq e OpenRouter com fallback entre modelos."""
    
    for modelo in MODELOS_GEMINI:
        if not GEMINI_DISPONIVEL:
            break
            
        try:
            if GEMINI_USE_LEGACY:
                import google.generativeai as genai_legacy
                model = genai_legacy.GenerativeModel(modelo)
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
                        model=modelo,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2
                        )
                    ),
                    timeout=TIMEOUT_IA
                )
                txt = response.text if response.text else "{}"
            
            resultado = _extrair_json(txt)
            logger.info(f"✅ Gemini respondeu (JSON) com modelo {modelo}")
            return resultado
            
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Gemini timeout com {modelo}")
            continue
        except Exception as e:
            error_msg = str(e)
            if "503" in error_msg:
                logger.warning(f"⚠️ Gemini {modelo} sobrecarregado, tentando próximo...")
                continue
            elif "404" in error_msg:
                logger.warning(f"⚠️ Gemini {modelo} não disponível, tentando próximo...")
                continue
            logger.warning(f"⚠️ Gemini falhou com {modelo}: {e}")
            continue
    
    resultado = await _groq_json(prompt)
    if resultado:
        return resultado

    resultado = await _openrouter_json(prompt)
    if resultado:
        return resultado

    return {}


async def ai_text_hibrido(prompt: str) -> str:
    """Tenta Gemini, Groq e OpenRouter com fallback entre modelos."""
    
    for modelo in MODELOS_GEMINI:
        if not GEMINI_DISPONIVEL:
            break
            
        try:
            if GEMINI_USE_LEGACY:
                import google.generativeai as genai_legacy
                model = genai_legacy.GenerativeModel(modelo)
                response = await asyncio.wait_for(
                    model.generate_content_async(prompt),
                    timeout=TIMEOUT_IA
                )
                return response.text if response.text else "❌ Sem resposta do Gemini."
            else:
                client = genai.Client(api_key=config.GEMINI_API_KEY)
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=modelo,
                        contents=prompt,
                        config=types.GenerateContentConfig(temperature=0.7)
                    ),
                    timeout=TIMEOUT_IA
                )
                return response.text if response.text else "❌ Sem resposta do Gemini."
                
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Gemini timeout com {modelo}")
            continue
        except Exception as e:
            error_msg = str(e)
            if "503" in error_msg:
                logger.warning(f"⚠️ Gemini {modelo} sobrecarregado, tentando próximo...")
                continue
            elif "404" in error_msg:
                logger.warning(f"⚠️ Gemini {modelo} não disponível, tentando próximo...")
                continue
            logger.warning(f"⚠️ Gemini falhou com {modelo}: {e}")
            continue
    
    resultado = await _groq_text(prompt)
    if resultado:
        return resultado

    resultado = await _openrouter_text(prompt)
    if resultado:
        return resultado

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


async def validar_livro_existe(titulo: str, autor: str) -> bool:
    """Verifica se o livro existe na Open Library com busca flexível."""
    try:
        async with aiohttp.ClientSession() as session:
            queries = [
                f"{titulo} {autor}",
                titulo,
                autor,
                titulo.replace(" - ", " "),
            ]
            
            titulo_sem_acentos = ''.join(c for c in unicodedata.normalize('NFKD', titulo) if not unicodedata.combining(c))
            autor_sem_acentos = ''.join(c for c in unicodedata.normalize('NFKD', autor) if not unicodedata.combining(c))
            queries.append(f"{titulo_sem_acentos} {autor_sem_acentos}")
            
            for query in queries:
                url = f"https://openlibrary.org/search.json?q={query}&limit=3"
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        docs = data.get("docs", [])
                        if docs:
                            for doc in docs:
                                titulo_doc = doc.get("title", "").lower()
                                autores_doc = [a.lower() for a in doc.get("author_name", [])]
                                
                                titulo_clean = titulo.lower().replace(" - ", " ").replace("'", " ").replace(".", "")
                                titulo_clean = ''.join(c for c in unicodedata.normalize('NFKD', titulo_clean) if not unicodedata.combining(c))
                                titulo_doc_clean = ''.join(c for c in unicodedata.normalize('NFKD', titulo_doc) if not unicodedata.combining(c))
                                
                                autor_clean = autor.lower().replace(".", "").replace("'", " ")
                                autor_clean = ''.join(c for c in unicodedata.normalize('NFKD', autor_clean) if not unicodedata.combining(c))
                                
                                titulo_match = titulo_clean in titulo_doc_clean or titulo_doc_clean in titulo_clean
                                autor_match = any(
                                    autor_clean in a.lower().replace(".", "").replace("'", " ") or 
                                    a.lower().replace(".", "").replace("'", " ") in autor_clean
                                    for a in autores_doc
                                )
                                
                                if titulo_match and autor_match:
                                    logger.info(f"✅ Livro validado: {titulo} - {autor}")
                                    return True
                                
                                if titulo_match and autor_clean[:3] in str(autores_doc).lower():
                                    logger.info(f"✅ Livro validado (match parcial): {titulo} - {autor}")
                                    return True
                            
                            if docs:
                                doc = docs[0]
                                titulo_doc = doc.get("title", "").lower()
                                if titulo.lower().replace(" - ", " ") in titulo_doc or titulo_doc in titulo.lower():
                                    logger.info(f"✅ Livro validado (título similar): {titulo} - {autor}")
                                    return True
    except Exception as e:
        logger.warning(f"Erro ao validar livro: {e}")
    
    logger.warning(f"⚠️ Não foi possível validar {titulo} - {autor} na Open Library.")
    return False


async def detetar_e_agendar_serie(titulo_livro: str, mes_origem: str, canal) -> list:
    from storage import dados, guardar_dados, livros_tbr_flat
    from datetime import datetime

    # 🔥 PROMPT ANTI-ALUCINAÇÃO
    prompt = f"""
És um assistente literário especializado em séries de livros.

REGRAS ABSOLUTAS:
1. **NUNCA INVENTES LIVROS.** Se não tens a certeza absoluta que um livro existe e faz parte de uma série, NÃO o sugeres.
2. **NUNCA INVENTES AUTORES.** Apenas autores reais.
3. **NUNCA INVENTES TÍTULOS.** Apenas livros que existem no mundo real.
4. **Se não souberes, responde com {{"sequencias": []}}**

O utilizador adicionou o livro "{titulo_livro}" para leitura em "{mes_origem}".
IDENTIFICA APENAS OS PRÓXIMOS LIVROS DA SÉRIE (máximo 3) que tenham sido PUBLICADOS.
Responde apenas em JSON: {{"sequencias": ["Nome do Livro 2 - Autor", ...]}}
"""
    resposta = await ai_json_com_retry(prompt)
    sequencias = resposta.get("sequencias", [])
    if not sequencias:
        return []

    mensagens = []
    for prox in sequencias[:3]:
        if not any(prox.lower().strip() == x.lower().strip() for x in livros_tbr_flat()):
            try:
                titulo, autor = prox.rsplit(" - ", 1)
                if await validar_livro_existe(titulo, autor):
                    dados["tbr_por_mes"]["Geral"].append(prox)
                    mensagens.append(f"• **{prox}** adicionado à **TBR Geral**")
                else:
                    mensagens.append(f"⚠️ **{prox}** parece não existir. Não foi adicionado.")
            except ValueError:
                dados["tbr_por_mes"]["Geral"].append(prox)
                mensagens.append(f"• **{prox}** adicionado à **TBR Geral**")
        else:
            mensagens.append(f"• **{prox}** já estava na TBR")
    
    if mensagens:
        guardar_dados()
        mensagens.append("\n💡 **Dica:** Se quiseres agendar estes livros para meses específicos, usa `!addtbr Mês \"Livro - Autor\"`")
    
    return mensagens

