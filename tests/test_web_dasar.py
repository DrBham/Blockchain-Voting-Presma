import tempfile
import unittest
from pathlib import Path
from unittest import mock

from web.app import create_app


def app_uji(folder):
    """App Flask dengan basis data dan berkas kunci di folder sementara."""
    folder = Path(folder)
    return create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{folder / 'uji.db'}",
        "ADMIN_WALLET_PATH": str(folder / "admin.pem"),
        "KUNCI_PEMILU_PATH": str(folder / "pemilu.pem"),
        "AUTO_MINE": True,
    })


class TestFondasiWeb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = app_uji(self.tmp.name)

    def tearDown(self):
        from web.models import db
        with self.app.app_context():
            db.engine.dispose()
        self.tmp.cleanup()

    def test_kirim_tx_ditolak_node_mengembalikan_alasan(self):
        from web import node_api
        with self.app.test_request_context(), \
                mock.patch.object(node_api, "node_request", return_value=(400, {"error": "NIM belum terdaftar"})):
            tx = mock.Mock(to_dict=lambda: {})
            self.assertEqual(node_api.kirim_tx(tx), "NIM belum terdaftar")

    def test_deploy_membawa_kunci_pemilu(self):
        from web import node_api
        terkirim = []

        def palsu(method, path, data=None, timeout=None):
            terkirim.append((path, data))
            return 201, {"pesan": "ok", "pool": 1}

        with self.app.test_request_context(), mock.patch.object(node_api, "node_request", side_effect=palsu):
            alamat, error = node_api.deploy_ke_chain()
        self.assertIsNone(error)
        payload = terkirim[0][1]["payload"]
        self.assertEqual(payload["contract_address"], alamat)
        self.assertIn("BEGIN PUBLIC KEY", payload["kunci_pemilu"])
        self.assertTrue(Path(self.tmp.name, "pemilu.pem").exists())


if __name__ == "__main__":
    unittest.main()
