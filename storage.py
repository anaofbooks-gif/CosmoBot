import json
import shutil
import threading
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from urllib import error as urlerror
from urllib import request as urlrequest
from datetime import datetime
import os

import config
from utils import buscar_livro_case_insensitive, formatar_livro, estrelas_para_nota

_dados_lock = threading.Lock()
_github_file_sha: Optional[str] = None
_ultimo_snapshot_local: Optional[str] = None
_ultimo_snapshot_remoto: Optional[str] = None
dados: Dict[str, Any] = {}

# ========== FUNÇÕES DE ESTADO INICIAL ==========

def estado_inicial() -> Dict[str, Any]:
    return {
        "livros_lidos": [],
        "review_em_andamento": {},
        "lembretes_metas": [],
        "sugestoes_vistas": [],
        "sorteios_mes": {},
        "tbr_por_mes": {
            "Geral": [],
            **{mes: [] for mes in config.MESES_ORDEM}
        },
        "desafio_alfabeto": {letra: config.VAZIO_ALFABETO for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
    }


def normalizar_tbr_por_mes(tbr: Any) -> Dict[str, List[str]]:
    base = estado_inicial()["tbr_por_mes"]
    if not isinstance(tbr, dict):
        return {mes: list(livros) for mes, livros in base.items()}
    resultado = {mes: list(base[mes]) for mes in base}
    for mes, livros in tbr.items():
        if mes not in resultado:
            continue
        if isinstance(livros, list):
            resultado[mes] = [str(livro) for livro in livros if str(livro).strip()]
        else:
            resultado[mes] = []
    return resultado


def migrar_livros_lidos(livros: List[Dict]) -> List[Dict]:
    resultado = []
    for livro in livros:
        if not isinstance(livro, dict):
            continue
        copia = dict(livro)
        titulo = str(copia.get("titulo", "")).strip()
        if config.SEPARADOR_LIVRO not in titulo and copia.get("autor"):
            copia["titulo"] = formatar_livro(titulo, str(copia["autor"]))
        if "nota" not in copia and copia.get("estrelas") not in (None, "Sem avaliação"):
            copia["nota"] = estrelas_para_nota(str(copia.get("estrelas", "")))
        if "data_leitura" not in copia:
            copia["data_leitura"] = copia.get("data_leitura", "")
        resultado.append(copia)
    return resultado


def aplicar_dados_carregados(bruto: Dict) -> Dict:
    base = estado_inicial()
    base.update(bruto)
    base["tbr_por_mes"] = normalizar_tbr_por_mes(bruto.get("tbr_por_mes"))
    base["desafio_alfabeto"] = {
        **estado_inicial()["desafio_alfabeto"],
        **(bruto.get("desafio_alfabeto") if isinstance(bruto.get("desafio_alfabeto"), dict) else {})
    }
    base["sugestoes_vistas"] = list(bruto.get("sugestoes_vistas", []))
    base["sorteios_mes"] = dict(bruto.get("sorteios_mes", {}))
    base["livros_lidos"] = migrar_livros_lidos(bruto.get("livros_lidos", []))
    base["lembretes_metas"] = list(bruto.get("lembretes_metas", []))
    base["review_em_andamento"] = dict(bruto.get("review_em_andamento", {}))
    return base


def substituir_dados(novos_dados: Dict) -> None:
    """Mantém a mesma referência de dados usada pelos cogs já importados."""
    dados.clear()
    dados.update(novos_dados)


def _ler_ficheiro_dados(ficheiro: Path) -> Dict:
    with open(ficheiro, "r", encoding="utf-8") as f:
        bruto = json.load(f)
    return aplicar_dados_carregados(bruto)


def em_nuvem() -> bool:
    return any(os.getenv(var) for var in ("RENDER", "RAILWAY_ENVIRONMENT", "DYNO", "FLY_APP_NAME", "K_SERVICE", "VERCEL"))
