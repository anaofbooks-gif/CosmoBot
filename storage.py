import json
import shutil
import threading
import atexit
import base64
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote
from urllib import error as urlerror
from urllib import request as urlrequest

import config
from utils import hoje_str, parsear_livro, formatar_livro, estrelas_para_nota
from config import DATA_FILE, BACKUP_FILE, VAZIO_ALFABETO, MESES_ORDEM, SEPARADOR_LIVRO

_dados_lock = threading.Lock()
_github_file_sha: Optional[str] = None
_ultimo_snapshot: Optional[str] = None
dados: Dict[str, Any] = {}

# ==============================================================================
# ESTADO INICIAL
# ==============================================================================

def estado_inicial() -> Dict[str, Any]:
    return {
        "livros_lidos": [],
        "review_em_andamento": {},
        "lembretes_metas": [],
        "sugestoes_vistas": [],
        "sorteios_mes": {},
        "tbr_por_mes": {
            "Geral": [],
            **{mes: [] for mes in MESES_ORDEM}
        },
        "desafio_alfabeto": {letra: VAZIO_ALFABETO for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
    }


def _snapshot_dados() -> str:
    return json.dumps(dados, sort_keys=True, ensure_ascii=False)

# ==============================================================================
# MIGRAÇÕES
# ==============================================================================

def migrar_livros_lidos(livros: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    resultado = []
    for livro in livros:
        if not isinstance(livro, dict):
            continue
        copia = dict(livro)
        titulo = str(copia.get("titulo", "")).strip()
        if SEPARADOR_LIVRO not in titulo and copia.get("autor"):
            copia["titulo"] = formatar_livro(titulo, str(copia["autor"]))
        if "nota" not in copia and copia.get("estrelas") not in (None, "Sem avaliação"):
            copia["nota"] = estrelas_para_nota(str(copia.get("estrelas", "")))
        if "data_leitura" not in copia:
            copia["data_leitura"] = copia.get("data_leitura", "")
        resultado.append(copia)
    return resultado


def normalizar_tbr_por_mes(tbr: Any) -> Dict[str, list]:
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


def aplicar_dados_carregados(bruto: Dict[str, Any]) -> Dict[str, Any]:
    base = estado_inicial()
    base.update(bruto)
    base["tbr_por_mes"] = normalizar_tbr_por_mes(bruto.get("tbr_por_mes"))
    base["desafio_alfabeto"] = {
        **estado_inicial()["desafio_alfabeto"],
        **(bruto.get("desafio_alfabeto") if isinstance(bruto.get("desafio_alfabeto"), dict) else {}),
    }
    base["sugestoes_vistas"] = list(bruto.get("sugestoes_vistas", []))
    base["sorteios_mes"] = dict(bruto.get("sorteios_mes", {}))
    base["livros_lidos"] = migrar_livros_lidos(bruto.get("livros_lidos", []))
    base["lembretes_metas"] = list(bruto.get("lembretes_metas", []))
    base["review_em_andamento"] = dict(bruto.get("review_em_andamento", {}))
    return base


def _ler_ficheiro_dados(ficheiro: Path) -> Dict[str, Any]:
    with open(ficheiro, "r", encoding="utf-8") as f:
        bruto = json.load(f)
    if not isinstance(bruto, dict):
        raise ValueError("Formato inválido")
    return aplicar_dados_carregados(bruto)

# ==============================================================================
# MODO DE ARMAZENAMENTO
# ==============================================================================

def em_nuvem() -> bool:
    return any(
        os.getenv(var)
        for var in ("RENDER", "RAILWAY_ENVIRONMENT", "DYNO", "FLY_APP_NAME", "K_SERVICE", "VERCEL")
    )


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

# ==============================================================================
# GITHUB
# ==============================================================================

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


def carregar_github() -> Dict[str, Any]:
    global _github_file_sha
    owner, repo = _parse_github_repo()
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/contents/"
        f"{quote(config.GITHUB_DATA_PATH)}?ref={quote(config.GITHUB_BRANCH)}"
    )
    try:
        payload = _pedido_http("GET", url, cabecalhos=_github_headers())
    except urlerror.HTTPError as erro:
        if erro.code == 404:
            _github_file_sha = None
            return estado_inicial()
        raise

    if not isinstance(payload, dict):
        return estado_inicial()

    _github_file_sha = payload.get("sha")
    conteudo_b64 = str(payload.get("content", "")).replace("\n", "")
    if not conteudo_b64:
        return estado_inicial()

    bruto = json.loads(base64.b64decode(conteudo_b64).decode("utf-8"))
    if not isinstance(bruto, dict):
        return estado_inicial()
    return aplicar_dados_carregados(bruto)


def guardar_github() -> None:
    global _github_file_sha
    owner, repo = _parse_github_repo()
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(config.GITHUB_DATA_PATH)}"
    conteudo = json.dumps(dados, ensure_ascii=False, indent=2)
    corpo: Dict[str, Any] = {
        "message": f"chore(bot): atualizar {config.GITHUB_DATA_PATH}",
        "content": base64.b64encode(conteudo.encode("utf-8")).decode("ascii"),
        "branch": config.GITHUB_BRANCH,
    }
    if _github_file_sha:
        corpo["sha"] = _github_file_sha

    payload = _pedido_http("PUT", url, corpo=corpo, cabecalhos=_github_headers())
    if isinstance(payload, dict) and isinstance(payload.get("content"), dict):
        _github_file_sha = payload["content"].get("sha", _github_file_sha)

# ==============================================================================
# SUPABASE
# ==============================================================================

def carregar_supabase() -> Dict[str, Any]:
    url = f"{config.SUPABASE_URL}/rest/v1/bot_state?id=eq.1&select=data"
    cabecalhos = {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
    }
    payload = _pedido_http("GET", url, cabecalhos=cabecalhos)
    if not payload:
        return estado_inicial()
    if isinstance(payload, list) and payload:
        bruto = payload[0].get("data", {})
    elif isinstance(payload, dict):
        bruto = payload.get("data", payload)
    else:
        return estado_inicial()
    if not isinstance(bruto, dict):
        return estado_inicial()
    return aplicar_dados_carregados(bruto)


def guardar_supabase() -> None:
    url = f"{config.SUPABASE_URL}/rest/v1/bot_state?id=eq.1"
    cabecalhos = {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Prefer": "return=minimal",
    }
    try:
        _pedido_http("PATCH", url, corpo={"data": dados}, cabecalhos=cabecalhos)
    except urlerror.HTTPError as erro:
        if erro.code != 404:
            raise
        criar_url = f"{config.SUPABASE_URL}/rest/v1/bot_state"
        cabecalhos["Prefer"] = "resolution=merge-duplicates"
        _pedido_http("POST", criar_url, corpo={"id": 1, "data": dados}, cabecalhos=cabecalhos)

# ==============================================================================
# JSONBIN
# ==============================================================================

def carregar_jsonbin() -> Dict[str, Any]:
    url = f"https://api.jsonbin.io/v3/b/{config.JSONBIN_BIN_ID}/latest"
    cabecalhos = {"X-Master-Key": config.JSONBIN_API_KEY}
    payload = _pedido_http("GET", url, cabecalhos=cabecalhos)
    if not isinstance(payload, dict):
        return estado_inicial()
    bruto = payload.get("record", payload)
    if not isinstance(bruto, dict):
        return estado_inicial()
    return aplicar_dados_carregados(bruto)


def guardar_jsonbin() -> None:
    url = f"https://api.jsonbin.io/v3/b/{config.JSONBIN_BIN_ID}"
    cabecalhos = {
        "X-Master-Key": config.JSONBIN_API_KEY,
        "Content-Type": "application/json",
    }
    _pedido_http("PUT", url, corpo=dados, cabecalhos=cabecalhos)

# ==============================================================================
# URL
# ==============================================================================

def carregar_url() -> Dict[str, Any]:
    cabecalhos = {}
    if config.BOT_DATA_TOKEN:
        cabecalhos["Authorization"] = f"Bearer {config.BOT_DATA_TOKEN}"
    payload = _pedido_http("GET", config.BOT_DATA_URL, cabecalhos=cabecalhos)
    if not isinstance(payload, dict):
        return estado_inicial()
    return aplicar_dados_carregados(payload)


def guardar_url() -> None:
    cabecalhos = {}
    if config.BOT_DATA_TOKEN:
        cabecalhos["Authorization"] = f"Bearer {config.BOT_DATA_TOKEN}"
    _pedido_http("PUT", config.BOT_DATA_SAVE_URL, corpo=dados, cabecalhos=cabecalhos)

# ==============================================================================
# LOCAL
# ==============================================================================

def _guardar_local() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA_FILE.with_suffix(".tmp.json")
    conteudo = json.dumps(dados, ensure_ascii=False, indent=2)
    temp.write_text(conteudo, encoding="utf-8")
    if DATA_FILE.exists():
        shutil.copy2(DATA_FILE, BACKUP_FILE)
    temp.replace(DATA_FILE)

# ==============================================================================
# HTTP HELPER
# ==============================================================================

def _pedido_http(
    metodo: str,
    url: str,
    corpo: Optional[Dict[str, Any]] = None,
    cabecalhos: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> Any:
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

# ==============================================================================
# CARREGAR E GUARDAR PRINCIPAIS
# ==============================================================================

def carregar_dados() -> Dict[str, Any]:
    import logging
    logger = logging.getLogger('CosmoBot')
    
    modo = modo_armazenamento()

    if modo == "github":
        try:
            estado = carregar_github()
            logger.info(f"🐙 Dados carregados do GitHub: {config.GITHUB_REPO}/{config.GITHUB_DATA_PATH}")
            return estado
        except (OSError, urlerror.URLError, urlerror.HTTPError, json.JSONDecodeError, ValueError, TypeError) as erro:
            logger.warning(f"⚠️ Falha GitHub, a tentar local: {erro}")
    elif modo == "supabase":
        try:
            estado = carregar_supabase()
            logger.info("☁️ Dados carregados do Supabase.")
            return estado
        except (OSError, urlerror.URLError, urlerror.HTTPError, json.JSONDecodeError, ValueError, TypeError) as erro:
            logger.warning(f"⚠️ Falha Supabase, a tentar local: {erro}")
    elif modo == "jsonbin":
        try:
            estado = carregar_jsonbin()
            logger.info("☁️ Dados carregados do JSONBin.")
            return estado
        except (OSError, urlerror.URLError, urlerror.HTTPError, json.JSONDecodeError, ValueError, TypeError) as erro:
            logger.warning(f"⚠️ Falha JSONBin, a tentar local: {erro}")
    elif modo == "url":
        try:
            estado = carregar_url()
            logger.info(f"☁️ Dados carregados de: {config.BOT_DATA_URL}")
            return estado
        except (OSError, urlerror.URLError, urlerror.HTTPError, json.JSONDecodeError, ValueError, TypeError) as erro:
            logger.warning(f"⚠️ Falha URL remota, a tentar local: {erro}")

    for ficheiro in (DATA_FILE, BACKUP_FILE):
        if not ficheiro.exists():
            continue
        try:
            estado = _ler_ficheiro_dados(ficheiro)
            logger.info(f"📂 Dados carregados de: {ficheiro}")
            return estado
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as erro:
            logger.warning(f"⚠️ Falha ao ler {ficheiro}: {erro}")

    if em_nuvem() and modo == "local":
        logger.warning(
            "⚠️ ATENÇÃO: Bot na nuvem sem armazenamento remoto. "
            "A TBR perde-se a cada reinício/deploy. Configura GitHub, Supabase ou JSONBin."
        )
    else:
        logger.info(f"📂 Ficheiro novo — a criar em: {DATA_FILE}")
    return estado_inicial()


def guardar_dados() -> None:
    global _ultimo_snapshot
    import logging
    logger = logging.getLogger('CosmoBot')
    
    with _dados_lock:
        snapshot = _snapshot_dados()
        if snapshot == _ultimo_snapshot:
            return

        modo = modo_armazenamento()
        erro_remoto = None

        if modo == "github":
            try:
                guardar_github()
            except (OSError, urlerror.URLError, urlerror.HTTPError) as erro:
                erro_remoto = erro
        elif modo == "supabase":
            try:
                guardar_supabase()
            except (OSError, urlerror.URLError, urlerror.HTTPError) as erro:
                erro_remoto = erro
        elif modo == "jsonbin":
            try:
                guardar_jsonbin()
            except (OSError, urlerror.URLError, urlerror.HTTPError) as erro:
                erro_remoto = erro
        elif modo == "url":
            try:
                guardar_url()
            except (OSError, urlerror.URLError, urlerror.HTTPError) as erro:
                erro_remoto = erro

        if modo == "local" or not erro_remoto:
            try:
                _guardar_local()
            except OSError as erro:
                if modo == "local":
                    raise
                logger.warning(f"⚠️ Cache local indisponível: {erro}")

        if erro_remoto:
            raise RuntimeError(f"Falha ao guardar no remoto ({modo}): {erro_remoto}") from erro_remoto

        _ultimo_snapshot = snapshot


def resumo_persistencia() -> str:
    total_tbr = sum(len(v) for v in dados.get("tbr_por_mes", {}).values())
    modo = modo_armazenamento()
    linhas = [f"Modo: **{modo}**", f"TBR: **{total_tbr}** livros | Lidos: **{len(dados.get('livros_lidos', []))}**"]

    if modo == "github":
        linhas.append(f"Repositório: `{config.GITHUB_REPO}` · ficheiro `{config.GITHUB_DATA_PATH}` · branch `{config.GITHUB_BRANCH}`")
    elif modo == "local":
        linhas.append(f"Ficheiro local: `{DATA_FILE}`")
        if em_nuvem():
            linhas.append(
                "⚠️ **Bot na nuvem com disco temporário** — os dados apagam-se ao reiniciar. "
                "Configura **GitHub** (usa `!armazenamento`)."
            )
    elif modo == "supabase":
        linhas.append(f"Remoto: `{config.SUPABASE_URL}` (tabela `bot_state`)")
    elif modo == "jsonbin":
        linhas.append(f"Remoto: JSONBin `{config.JSONBIN_BIN_ID}`")
    elif modo == "url":
        linhas.append(f"Remoto: `{config.BOT_DATA_URL}`")

    return "\n".join(linhas)