import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URI = os.environ.get("DATABASE_URI", f"sqlite:///{BASE_DIR / 'web_state.db'}")
NODE_URL = os.environ.get("NODE_URL", "http://localhost:5001")
AUTO_MINE = os.environ.get("AUTO_MINE", "true").lower() == "true"
ADMIN_WALLET_PATH = os.environ.get("ADMIN_WALLET_PATH", str(BASE_DIR / "dompet_admin.pem"))
CONTRACT_NAME = os.environ.get("CONTRACT_NAME", "PaslonContract")