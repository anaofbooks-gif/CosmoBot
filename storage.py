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
