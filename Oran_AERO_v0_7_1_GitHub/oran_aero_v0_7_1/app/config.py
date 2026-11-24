"""Parámetros de ejecución: SQLite local de forma predeterminada."""
from pathlib import Path
import os
import secrets
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'oran_aero_v07.sqlite3').as_posix()}")
DISPLAY_TIMEZONE = os.getenv("DISPLAY_TIMEZONE", "America/Argentina/Salta")
if DATABASE_URL.lower().split("?")[0].rstrip("/").endswith(("/oran_aero", "/oran_aero_v2")):
    raise RuntimeError("No conectar a oran_aero ni a oran_aero_v2: son bases históricas. Usá una BD nueva.")


def secret_for_sessions():
    """Obtiene una clave de sesión segura desde la configuración."""
    explicit = os.getenv("APP_SECRET_KEY")
    if explicit and len(explicit) >= 32 and "CAMBIAR" not in explicit:
        return explicit
    if explicit:
        raise RuntimeError("APP_SECRET_KEY debe tener 32 caracteres o más y no puede ser una clave de ejemplo")
    local_file = BASE_DIR / ".local_session_secret"
    if not local_file.exists():
        local_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try: local_file.chmod(0o600)
        except OSError: pass
    return local_file.read_text(encoding="utf-8").strip()

APP_SECRET_KEY = secret_for_sessions()
