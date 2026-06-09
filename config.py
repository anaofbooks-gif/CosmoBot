import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
COMMAND_PREFIX = os.getenv("PREFIX", "!")

_DATA_DIR = Path("data")
_DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = _DATA_DIR / "dados_bot.json"
BACKUP_FILE = _DATA_DIR / "dados_bot.backup.json"

META_ANUAL = 80
MESES_ORDEM = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
SEPARADOR_LIVRO = " - "
NOTAS_DISPONIVEIS = [i * 0.25 for i in range(1, 21)]
VAZIO_ALFABETO = "❌ Vazio"
GEMINI_MODEL = "gemini-2.5-flash"

ARTIGOS_BANIDOS = {"o", "a", "os", "as", "um", "uma", "uns", "umas", "the", "a", "an"}GITHUB_DATA_PATH = os.getenv("GITHUB_DATA_PATH", "dados_bot.json")

# ==============================================================================
# CONSTANTES DO BOT
# ==============================================================================
META_ANUAL = 80
MESES_ORDEM = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]
SEPARADOR_LIVRO = " - "
NOTAS_DISPONIVEIS = [i * 0.25 for i in range(1, 21)]
READMORE_API_URL = os.getenv("READMORE_API_URL", "https://readmore.onrender.com")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
VAZIO_ALFABETO = "❌ Vazio"

# ==============================================================================
# ARTIGOS BANIDOS PARA DESAFIO A-Z
# ==============================================================================
ARTIGOS_BANIDOS = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "the", "a", "an"
}
