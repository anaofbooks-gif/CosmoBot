import json
import shutil
import threading
from typing import List, Dict, Any
import config
from utils import formatar_livro, estrelas_para_nota

_dados_lock = threading.Lock()
dados: Dict[str, Any] = {}


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
    base["tbr_por_mes"] = {mes: list(livros) for mes, livros in bruto.get("tbr_por_mes", {}).items()}
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


def carregar_dados() -> Dict:
    global dados
    if config.DATA_FILE.exists():
        try:
            with open(config.DATA_FILE, "r", encoding="utf-8") as f:
                dados = aplicar_dados_carregados(json.load(f))
            print(f"📂 Dados carregados")
        except Exception as e:
            print(f"⚠️ Erro ao carregar: {e}")
            dados = estado_inicial()
    else:
        dados = estado_inicial()
    return dados


def guardar_dados():
    with _dados_lock:
        try:
            config.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(config.DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Erro ao guardar: {e}")


def resumo_persistencia() -> str:
    total_tbr = sum(len(v) for v in dados.get("tbr_por_mes", {}).values())
    total_lidos = len(dados.get("livros_lidos", []))
    return f"TBR: **{total_tbr}** livros | Lidos: **{total_lidos}**"
