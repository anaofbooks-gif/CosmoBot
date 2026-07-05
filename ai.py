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
            try:
                resultado = json.loads(txt)
            except json.JSONDecodeError:
                inicio = txt.find("{")
                fim = txt.rfind("}")
                if inicio < 0 or fim <= inicio:
                    raise
                resultado = json.loads(txt[inicio:fim + 1])
            logger.info(f"✅ Gemini respondeu (JSON) com modelo {modelo}")
            return resultado
            
