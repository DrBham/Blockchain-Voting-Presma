import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URI = os.environ.get("DATABASE_URI", f"sqlite:///{BASE_DIR / 'web_state.db'}")
NODE_URL = os.environ.get("NODE_URL", "http://localhost:5001")
AUTO_MINE = os.environ.get("AUTO_MINE", "true").lower() == "true"
ADMIN_WALLET_PATH = os.environ.get("ADMIN_WALLET_PATH", str(BASE_DIR / "dompet_admin.pem"))
CONTRACT_NAME = os.environ.get("CONTRACT_NAME", "PaslonContract")
# Kunci privat pemilu: dibuat saat deploy, dipegang panitia, dibuka ke chain hanya setelah pemungutan ditutup.
KUNCI_PEMILU_PATH = os.environ.get("KUNCI_PEMILU_PATH", str(BASE_DIR / "kunci_pemilu.pem"))
# Password ruang panitia. Default hanya untuk demo lokal; ganti lewat env saat dipakai bersama.
PANITIA_PASSWORD = os.environ.get("PANITIA_PASSWORD", "panitia-demo")
MAIL_HOST = os.environ.get("MAIL_HOST", "localhost")
MAIL_PORT = int(os.environ.get("MAIL_PORT", "1025"))
MAIL_FROM = os.environ.get("MAIL_FROM", "pemira@untad.ac.id")
