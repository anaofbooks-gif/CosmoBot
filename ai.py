import json
import re
import asyncio
import aiohttp
import logging

import config

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CosmoBot')

# ========== GEMINI ==========
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
        logger.warning("⚠️ Biblioteca google-genai não instalada")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao configurar Gemini: {e}")

# ========== CONFIGURAÇÕES ==========
TIMEOUT_IA = 25

MODELOS_GEMINI = [
    "gemini-2.0-flash-exp",
    "gemini-2.5-flash",
    "gemini-1.5-flash"
]


async def ai_json_hibrido(prompt: str) -> dict:
    """Tenta Gemini com fallback entre modelos"""
    
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
            
            txt = re.sub(r"^```json\s*|\s*```$", "", txt.strip(), flags=re.IGNORECASE)
            logger.info(f"✅ Gemini respondeu (JSON) com modelo {modelo}")
            return json.loads(txt)
            
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Gemini timeout com {modelo}")
            continue
        except Exception as e:
            if "503" in str(e):
                logger.warning(f"⚠️ Gemini {modelo} sobrecarregado, tentando próximo...")
                continue
            logger.warning(f"⚠️ Gemini falhou com {modelo}: {e}")
            continue
    
    return {}


async def ai_text_hibrido(prompt: str) -> str:
    """Tenta Gemini com fallback entre modelos"""
    
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
            if "503" in str(e):
                logger.warning(f"⚠️ Gemini {modelo} sobrecarregado, tentando próximo...")
                continue
            logger.warning(f"⚠️ Gemini falhou com {modelo}: {e}")
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
    """Verifica se o livro existe na Open Library antes de recomendar."""
    try:
        async with aiohttp.ClientSession() as session:
            query = f"{titulo} {autor}".replace(" ", "+")
            url = f"https://openlibrary.org/search.json?q={query}&limit=1"
            
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    docs = data.get("docs", [])
                    if docs:
                        doc = docs[0]
                        titulo_doc = doc.get("title", "").lower()
                        autores_doc = [a.lower() for a in doc.get("author_name", [])]
                        
                        titulo_match = titulo.lower() in titulo_doc or titulo_doc in titulo.lower()
                        autor_match = any(autor.lower() in a or a in autor.lower() for a in autores_doc)
                        
                        if titulo_match and autor_match:
                            logger.info(f"✅ Livro validado: {titulo} - {autor}")
                            return True
                        else:
                            logger.warning(f"⚠️ Livro não encontrado: {titulo} - {autor}")
                            return False
    except Exception as e:
        logger.warning(f"Erro ao validar livro: {e}")
    
    return False


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

    mensagens = []
    for prox in sequencias[:3]:
        # 🔥 CORRIGIDO: Adiciona SEMPRE à TBR Geral
        if not any(prox.lower().strip() == x.lower().strip() for x in livros_tbr_flat()):
            # 🔥 Valida se o livro existe antes de adicionar
            try:
                titulo, autor = prox.rsplit(" - ", 1)
                if await validar_livro_existe(titulo, autor):
                    dados["tbr_por_mes"]["Geral"].append(prox)
                    mensagens.append(f"• **{prox}** adicionado à **TBR Geral**")
                else:
                    mensagens.append(f"⚠️ **{prox}** parece não existir. Não foi adicionado.")
            except ValueError:
                # Se não tiver o formato "Título - Autor", adiciona mesmo assim
                dados["tbr_por_mes"]["Geral"].append(prox)
                mensagens.append(f"• **{prox}** adicionado à **TBR Geral**")
        else:
            mensagens.append(f"• **{prox}** já estava na TBR")
    
    if mensagens:
        guardar_dados()
        mensagens.append("\n💡 **Dica:** Se quiseres agendar estes livros para meses específicos, usa `!addtbr Mês \"Livro - Autor\"`")
    
    return mensagens
