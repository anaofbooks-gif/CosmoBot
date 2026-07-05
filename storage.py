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
        "aliases_livros": {},
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
    base["aliases_livros"] = dict(bruto.get("aliases_livros", {})) if isinstance(bruto.get("aliases_livros", {}), dict) else {}
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


def _github_get_file_sha(force: bool = False):
    global _github_file_sha
    if _github_file_sha and not force:
        return _github_file_sha
    try:
        owner, repo = _parse_github_repo()
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{config.GITHUB_DATA_PATH}"
        headers = _github_headers()
        data = _pedido_http("GET", url, cabecalhos=headers)
        if data and isinstance(data, dict):
            _github_file_sha = data.get("sha")
            return _github_file_sha
    except Exception as e:
        print(f"⚠️ Erro ao obter SHA do GitHub: {e}")
    return None


# ========== FUNÇÕES DE CARREGAMENTO/GUARDA ==========

def carregar_github():
    global _github_file_sha, _ultimo_snapshot_remoto
    try:
        owner, repo = _parse_github_repo()
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{config.GITHUB_DATA_PATH}"
        headers = _github_headers()
        data = _pedido_http("GET", url, cabecalhos=headers)
        if data and isinstance(data, dict) and "content" in data:
            conteudo = base64.b64decode(data["content"]).decode("utf-8")
            bruto = json.loads(conteudo)
            substituir_dados(aplicar_dados_carregados(bruto))
            _github_file_sha = data.get("sha")
            _ultimo_snapshot_remoto = _snapshot_dados()
            print("✅ Dados carregados do GitHub")
            return True
    except Exception as e:
        print(f"⚠️ Erro ao carregar do GitHub: {e}")
    return False


def guardar_github():
    global _github_file_sha, _ultimo_snapshot_remoto
    snapshot = _snapshot_dados()
    if snapshot == _ultimo_snapshot_remoto:
        return
    try:
        owner, repo = _parse_github_repo()
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{config.GITHUB_DATA_PATH}"
        headers = _github_headers()
        conteudo_base64 = base64.b64encode(snapshot.encode("utf-8")).decode("utf-8")
        corpo = {
            "message": f"Auto-save em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "content": conteudo_base64,
            "branch": config.GITHUB_BRANCH
        }
        sha = _github_get_file_sha()
        if sha:
            corpo["sha"] = sha

        try:
            resposta = _pedido_http("PUT", url, corpo=corpo, cabecalhos=headers)
        except urlerror.HTTPError as e:
            if e.code != 409:
                raise
            sha = _github_get_file_sha(force=True)
            if sha:
                corpo["sha"] = sha
            resposta = _pedido_http("PUT", url, corpo=corpo, cabecalhos=headers)

        if isinstance(resposta, dict):
            novo_sha = resposta.get("content", {}).get("sha")
            if novo_sha:
                _github_file_sha = novo_sha
        _ultimo_snapshot_remoto = snapshot
        print("💾 Dados guardados no GitHub")
    except Exception as e:
        print(f"⚠️ Erro ao guardar no GitHub: {e}")

def carregar_supabase():
    try:
        url = f"{config.SUPABASE_URL}/rest/v1/bot_data?select=*&limit=1"
        headers = {"apikey": config.SUPABASE_KEY, "Authorization": f"Bearer {config.SUPABASE_KEY}"}
        data = _pedido_http("GET", url, cabecalhos=headers)
        if data and len(data) > 0:
            bruto = json.loads(data[0].get("dados", "{}"))
            substituir_dados(aplicar_dados_carregados(bruto))
            print("✅ Dados carregados do Supabase")
            return True
    except Exception as e:
        print(f"⚠️ Erro ao carregar do Supabase: {e}")
    return False


def guardar_supabase():
    global _ultimo_snapshot_remoto
    snapshot = _snapshot_dados()
    if snapshot == _ultimo_snapshot_remoto:
        return
    try:
        url = f"{config.SUPABASE_URL}/rest/v1/bot_data?id=eq.1"
        headers = {"apikey": config.SUPABASE_KEY, "Authorization": f"Bearer {config.SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
        corpo = {"dados": snapshot, "updated_at": datetime.now().isoformat()}
        _pedido_http("PATCH", url, corpo=corpo, cabecalhos=headers)
        _ultimo_snapshot_remoto = snapshot
        print("💾 Dados guardados no Supabase")
    except Exception as e:
        print(f"⚠️ Erro ao guardar no Supabase: {e}")


def carregar_jsonbin():
    try:
        url = f"https://api.jsonbin.io/v3/b/{config.JSONBIN_BIN_ID}/latest"
        headers = {"X-Master-Key": config.JSONBIN_API_KEY}
        data = _pedido_http("GET", url, cabecalhos=headers)
        if data and isinstance(data, dict):
            bruto = data.get("record", {})
            substituir_dados(aplicar_dados_carregados(bruto))
            print("✅ Dados carregados do JSONbin")
            return True
    except Exception as e:
        print(f"⚠️ Erro ao carregar do JSONbin: {e}")
    return False


def guardar_jsonbin():
    global _ultimo_snapshot_remoto
    snapshot = _snapshot_dados()
    if snapshot == _ultimo_snapshot_remoto:
        return
    try:
        url = f"https://api.jsonbin.io/v3/b/{config.JSONBIN_BIN_ID}"
        headers = {"X-Master-Key": config.JSONBIN_API_KEY, "Content-Type": "application/json"}
        corpo = json.loads(snapshot)
        _pedido_http("PUT", url, corpo=corpo, cabecalhos=headers)
        _ultimo_snapshot_remoto = snapshot
        print("💾 Dados guardados no JSONbin")
    except Exception as e:
        print(f"⚠️ Erro ao guardar no JSONbin: {e}")


def carregar_url():
    try:
        data = _pedido_http("GET", config.BOT_DATA_URL)
        if data:
            bruto = json.loads(data) if isinstance(data, str) else data
            substituir_dados(aplicar_dados_carregados(bruto))
            print("✅ Dados carregados da URL")
            return True
    except Exception as e:
        print(f"⚠️ Erro ao carregar da URL: {e}")
    return False


def guardar_url():
    if not config.BOT_DATA_SAVE_URL or not config.BOT_DATA_TOKEN:
        return
    global _ultimo_snapshot_remoto
    snapshot = _snapshot_dados()
    if snapshot == _ultimo_snapshot_remoto:
        return
    try:
        headers = {"Authorization": f"Bearer {config.BOT_DATA_TOKEN}", "Content-Type": "application/json"}
        _pedido_http("POST", config.BOT_DATA_SAVE_URL, corpo=json.loads(snapshot), cabecalhos=headers)
        _ultimo_snapshot_remoto = snapshot
        print("💾 Dados guardados via URL")
    except Exception as e:
        print(f"⚠️ Erro ao guardar via URL: {e}")


def carregar_local():
    try:
        if config.DATA_FILE.exists():
            with open(config.DATA_FILE, "r", encoding="utf-8") as f:
                bruto = json.load(f)
            substituir_dados(aplicar_dados_carregados(bruto))
            print(f"📂 Dados carregados localmente de {config.DATA_FILE}")
            return True
    except Exception as e:
        print(f"⚠️ Erro ao carregar local: {e}")
    return False


# 🔥 VERSÃO SEGURA E ATÓMICA DE GUARDA LOCAL
def guardar_local():
    """Grava os dados com segurança acrescida para evitar corrupção e perdas em restarts."""
    global _ultimo_snapshot_local
    
    snapshot = _snapshot_dados()
    if snapshot == _ultimo_snapshot_local and config.DATA_FILE.exists():
        return
    
    try:
        # Criar diretório se não existir
        config.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. Criar um ficheiro temporário para evitar que uma quebra de energia/restart a meio apague o original
        temp_file = config.DATA_FILE.with_suffix('.tmp')
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())  # Força o sistema operativo a gravar no disco IMEDIATAMENTE
        
        # 2. Fazer um backup do antigo antes de substituir
        if config.DATA_FILE.exists():
            backup_file = config.DATA_FILE.with_suffix('.backup.json')
            shutil.copy2(config.DATA_FILE, backup_file)
            print(f"📋 Backup criado em {backup_file}")
        
        # 3. Substituir o ficheiro oficial de forma atómica
        temp_file.replace(config.DATA_FILE)
        _ultimo_snapshot_local = snapshot
        
        print(f"💾 Dados guardados localmente em {config.DATA_FILE}")
        
        # Backup extra para o ficheiro de backup principal
        if config.BACKUP_FILE:
            shutil.copy(config.DATA_FILE, config.BACKUP_FILE)
            
    except Exception as e:
        print(f"❌ ERRO CRÍTICO AO GRAVAR DADOS LOCALMENTE: {e}")
        import traceback
        traceback.print_exc()

def carregar_dados() -> Dict:
    modo = modo_armazenamento()
    sucesso = False
    
    # Tentar carregar da nuvem primeiro se configurado
    if modo == "github":
        sucesso = carregar_github()
    elif modo == "supabase":
        sucesso = carregar_supabase()
    elif modo == "jsonbin":
        sucesso = carregar_jsonbin()
    elif modo == "url":
        sucesso = carregar_url()
    
    # Se falhou na nuvem ou não há nuvem configurada, carregar local
    if not sucesso:
        # Tentar backup primeiro
        if config.BACKUP_FILE.exists():
            try:
                with open(config.BACKUP_FILE, "r", encoding="utf-8") as f:
                    bruto = json.load(f)
                substituir_dados(aplicar_dados_carregados(bruto))
                print(f"📂 Dados carregados do backup {config.BACKUP_FILE}")
                sucesso = True
            except Exception as e:
                print(f"⚠️ Erro ao carregar backup: {e}")
        
        if not sucesso:
            sucesso = carregar_local()
    
    if not dados:
        substituir_dados(estado_inicial())
        guardar_dados()
    
    return dados


def guardar_dados() -> None:
    """Grava os dados localmente e na nuvem se configurado."""
    if not dados:
        return
    
    with _dados_lock:
        # 1. Guarda sempre localmente com segurança atómica
        guardar_local()
        
        # 2. Guarda na nuvem se configurado
        modo = modo_armazenamento()
        if modo == "github":
            guardar_github()
        elif modo == "supabase":
            guardar_supabase()
        elif modo == "jsonbin":
            guardar_jsonbin()
        elif modo == "url":
            guardar_url()


def forcar_upload(mensagem: str = "Upload forçado") -> bool:
    """
    Força o upload dos dados para a nuvem (GitHub/Supabase/JSONBin).
    Retorna True se o upload foi bem sucedido.
    """
    if not dados:
        print("❌ Sem dados para fazer upload")
        return False
    
    modo = modo_armazenamento()
    print(f"📤 A forçar upload para {modo}...")
    
    # Reset do snapshot para forçar o upload
    global _ultimo_snapshot_local, _ultimo_snapshot_remoto
    _ultimo_snapshot_local = None
    _ultimo_snapshot_remoto = None
    
    try:
        if modo == "github":
            guardar_github()
        elif modo == "supabase":
            guardar_supabase()
        elif modo == "jsonbin":
            guardar_jsonbin()
        elif modo == "url":
            guardar_url()
        else:
            print("⚠️ Modo local - a guardar apenas localmente")
            guardar_local()
        
        print(f"✅ Upload forçado concluído para {modo}")
        return True
    except Exception as e:
        print(f"❌ Erro no upload forçado: {e}")
        return False


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

