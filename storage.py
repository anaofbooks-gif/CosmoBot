import json
import shutil
import threading
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from urllib import error as urlerror
from urllib import request as urlrequest

import config
from utils import formatar_livro, estrelas_para_nota

_dados_lock = threading.Lock()
_github_file_sha: Optional[str] = None
_ultimo_snapshot: Optional[str] = None
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


def _ler_ficheiro_dados(ficheiro: Path) -> Dict:
    with open(ficheiro, "r", encoding="utf-8") as f:
        bruto = json.load(f)
    return aplicar_dados_carregados(bruto)


def em_nuvem() -> bool:
    return any(os.getenv(var) for var in ("RENDER", "RAILWAY_ENVIRONMENT", "DYNO", "FLY_APP_NAME", "K_SERVICE", "VERCEL"))


def modo_armazenamento() -> str:
    if config.GITHUB_TOKEN and config.GITHUB_REPO:
        return "github"
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        return "supabase"
    if config.JSONBIN_BIN_ID and config.JSONBIN_API_KEY:
        return "jsonbin"
    if config.BOT_DATA_URL:
        return "url"
    return "local"


def _snapshot_dados() -> str:
    return json.dumps(dados, sort_keys=True, ensure_ascii=False)


def _github_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _parse_github_repo() -> Tuple[str, str]:
    repo = config.GITHUB_REPO.strip()
    if "/" not in repo:
        raise ValueError("GITHUB_REPO deve estar no formato owner/repo")
    owner, nome = repo.split("/", 1)
    return owner.strip(), nome.strip()


def _pedido_http(metodo: str, url: str, corpo: Optional[Dict] = None, cabecalhos: Optional[Dict] = None, timeout: int = 20) -> Any:
    cabecalhos = cabecalhos or {}
    dados_bytes = None
    if corpo is not None:
        dados_bytes = json.dumps(corpo).encode("utf-8")
        cabecalhos.setdefault("Content-Type", "application/json")
    pedido = urlrequest.Request(url, data=dados_bytes, headers=cabecalhos, method=metodo)
    with urlrequest.urlopen(pedido, timeout=timeout) as resposta:
        texto = resposta.read().decode("utf-8")
        if not texto.strip():
            return None
        return json.loads(texto)


# Funções de carregamento/guarda (github, supabase, jsonbin, url, local)
# ... (manter do bot5.py original, muito extenso)

def carregar_dados() -> Dict:
    global dados
    if config.DATA_FILE.exists():
        try:
            with open(config.DATA_FILE, "r", encoding="utf-8") as f:
                dados = json.load(f)
            print(f"📂 Dados carregados")
        except Exception as e:
            print(f"⚠️ Erro ao carregar: {e}")
            dados = estado_inicial()
    else:
        dados = estado_inicial()
        guardar_dados()  # Criar ficheiro inicial
    return dados


def guardar_dados() -> None:
    global _ultimo_snapshot
    # ... (manter implementação original)


def resumo_persistencia() -> str:
    total_tbr = sum(len(v) for v in dados.get("tbr_por_mes", {}).values())
    modo = modo_armazenamento()
    linhas = [f"Modo: **{modo}**", f"TBR: **{total_tbr}** livros | Lidos: **{len(dados.get('livros_lidos', []))}**"]
    return "\n".join(linhas)


def livros_tbr_flat() -> List[str]:
    return [livro for lista in dados["tbr_por_mes"].values() for livro in lista]


def adicionar_livro_a_tbr_mes(livro: str, mes: str) -> str:
    existente = buscar_livro_case_insensitive(dados["tbr_por_mes"][mes], livro)
    if existente:
        return f"📌 **{existente}** já estava na TBR de **{mes}**."
    dados["tbr_por_mes"][mes].append(livro)
    guardar_dados()
    return f"📚 **{livro}** foi adicionado à TBR de **{mes}**."


def marcar_livro_sorteio_lido(titulo_completo: str) -> List[str]:
    meses_desbloqueados = []
    alvo = titulo_completo.lower().strip()
    for mes, info in dados["sorteios_mes"].items():
        livros = [l.lower().strip() for l in info.get("livros", [])]
        if alvo in livros:
            lidos = info.setdefault("lidos", [])
            if titulo_completo not in lidos:
                for livro in info.get("livros", []):
                    if livro.lower().strip() == alvo:
                        lidos.append(livro)
                        break
            pendentes = [l for l in info.get("livros", []) if l.lower().strip() not in {x.lower().strip() for x in lidos}]
            if not pendentes:
                meses_desbloqueados.append(mes)
    guardar_dados()
    return meses_desbloqueados


def sorteio_mes_ativo(mes: str) -> Optional[Dict]:
    info = dados["sorteios_mes"].get(mes)
    if not info:
        return None
    livros = info.get("livros", [])
    lidos = {l.lower().strip() for l in info.get("lidos", [])}
    pendentes = [l for l in livros if l.lower().strip() not in lidos]
    if pendentes:
        info["pendentes"] = pendentes
        return info
    return None
