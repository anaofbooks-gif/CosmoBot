import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ========== TOKENS ==========
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
COMMAND_PREFIX = os.getenv("PREFIX", "!")

# ========== ARMAZENAMENTO REMOTO (opcional) ==========
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID", "")
JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY", "")
BOT_DATA_URL = os.getenv("BOT_DATA_URL", "")
BOT_DATA_SAVE_URL = os.getenv("BOT_DATA_SAVE_URL", BOT_DATA_URL)
BOT_DATA_TOKEN = os.getenv("BOT_DATA_TOKEN", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", os.getenv("GITHUB_REPOSITORY", ""))
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_DATA_PATH = os.getenv("GITHUB_DATA_PATH", "dados_bot.json")  # <-- LINHA SEPARADA

# ========== DIRETÓRIOS ==========
_DATA_DIR = Path("data")
_DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = _DATA_DIR / "dados_bot.json"
BACKUP_FILE = _DATA_DIR / "dados_bot.backup.json"

# ========== CONSTANTES DO BOT ==========
META_ANUAL = 80
MESES_ORDEM = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
SEPARADOR_LIVRO = " - "
NOTAS_DISPONIVEIS = [i * 0.25 for i in range(1, 21)]
VAZIO_ALFABETO = "❌ Vazio"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
READMORE_API_URL = os.getenv("READMORE_API_URL", "https://readmore.onrender.com")

# ========== ARTIGOS BANIDOS ==========
ARTIGOS_BANIDOS = {"o", "a", "os", "as", "um", "uma", "uns", "umas", "the", "a", "an"}
