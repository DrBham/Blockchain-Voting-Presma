import tempfile
import unittest
from unittest import mock

from tests.test_web_dasar import app_uji

ALAMAT = "a" * 40
ADMIN = "PEM-ADMIN"


def tx_contract(fungsi, args, ts=1.0):
    return {"tipe": "CONTRACT_CALL", "public_key": ADMIN, "timestamp": ts,
            "payload": {"contract_address": ALAMAT, "fungsi": fungsi, "args": args}}


def chain_contoh(*calls):
    """Chain dict: genesis, deploy, lalu satu block per CONTRACT_CALL."""
    deploy = {"tipe": "CONTRACT_DEPLOY", "public_key": ADMIN, "timestamp": 0.5,
              "payload": {"contract_address": ALAMAT, "nama": "PaslonContract", "kunci_pemilu": "PEM"}}
    blocks = [{"index": 0, "transaksi": []}, {"index": 1, "transaksi": [deploy]}]
    blocks += [{"index": i + 2, "transaksi": [c]} for i, c in enumerate(calls)]
    return blocks


class NodePalsu:
    """Pengganti node_api.node_request: jawaban per (method, path), semua panggilan dicatat."""

    def __init__(self, jawaban=None):
        self.jawaban = {("GET", "/contract"): (200, {"alamat": ALAMAT}),
                        ("GET", "/chain"): (200, {"chain": chain_contoh(), "panjang": 2, "difficulty": 4}),
                        ("POST", "/transaksi"): (201, {"pesan": "ok"}),
                        ("POST", "/mine"): (201, {"block": {"index": 9}}),
                        **(jawaban or {})}
        self.panggilan = []

    def __call__(self, method, path, data=None, timeout=None):
        self.panggilan.append((method, path, data))
        return self.jawaban.get((method, path), (404, {"error": "tidak ada"}))

    def post(self, path):
        return [data for m, p, data in self.panggilan if m == "POST" and p == path]


class TestWebPanitia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = app_uji(self.tmp.name)
        self.client = self.app.test_client()

    def tearDown(self):
        from web.models import db
        with self.app.app_context():
            db.engine.dispose()
        self.tmp.cleanup()

    def masuk(self):
        with self.client.session_transaction() as s:
            s["panitia"] = True
            s["csrf_token"] = "t"

    def dengan_node(self, node):
        from web import node_api
        return mock.patch.object(node_api, "node_request", side_effect=node)

    def kirim(self, node, path, **form):
        self.masuk()
        with self.dengan_node(node):
            return self.client.post(path, data={"csrf_token": "t", **form}, follow_redirects=True)

    def test_dasbor_wajib_login(self):
        resp = self.client.get("/panitia/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/panitia/masuk", resp.headers["Location"])

    def test_masuk_dengan_password(self):
        with self.client.session_transaction() as s:
            s["csrf_token"] = "t"
        resp = self.client.post("/panitia/masuk", data={"csrf_token": "t", "password": "salah"})
        self.assertIn("Password panitia salah", resp.get_data(as_text=True))
        with self.dengan_node(NodePalsu()):
            resp = self.client.post("/panitia/masuk", data={"csrf_token": "t", "password": "panitia-demo"})
        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as s:
            self.assertTrue(s["panitia"])

    def test_tutup_menambang_dulu(self):
        node = NodePalsu()
        self.kirim(node, "/panitia/tutup")
        urutan = [(m, p) for m, p, _ in node.panggilan if m == "POST"]
        self.assertEqual(urutan[0], ("POST", "/mine"))
        self.assertEqual(node.post("/transaksi")[0]["payload"]["fungsi"], "tutup_pemungutan")

    def test_crud_paslon_saat_dibuka_ditolak(self):
        alasan = "paslon hanya bisa diubah saat status persiapan (sekarang dibuka)"
        node = NodePalsu({("POST", "/transaksi"): (400, {"error": alasan})})
        resp = self.kirim(node, "/panitia/paslon/1/hapus")
        self.assertIn(alasan, resp.get_data(as_text=True))
        self.assertEqual(node.post("/mine"), [])

    def test_nomor_ganda_ditolak_tampil_alasan(self):
        alasan = "nomor paslon 1 sudah dipakai paslon aktif"
        node = NodePalsu({("POST", "/transaksi"): (400, {"error": alasan})})
        resp = self.kirim(node, "/panitia/paslon/tambah", nomor="1", nama="Ganda", visi="")
        teks = resp.get_data(as_text=True)
        self.assertIn(alasan, teks)
        self.assertIn("Tidak ada block baru", teks)
        self.assertEqual(node.post("/mine"), [])

    def test_riwayat_paslon_tampil(self):
        chain = chain_contoh(tx_contract("tambah_paslon", {"nomor": 1, "nama": "Nama Lama", "visi": ""}),
                             tx_contract("ubah_paslon", {"id": 1, "nama": "Nama Baru"}))
        self.masuk()
        with self.dengan_node(NodePalsu({("GET", "/chain"): (200, {"chain": chain})})):
            teks = self.client.get("/panitia/paslon/1/riwayat").get_data(as_text=True)
        self.assertIn("Nama Lama", teks)
        self.assertIn("Nama Baru", teks)
        self.assertIn("#3", teks)

    def test_rebuild_state(self):
        from web.models import Paslon
        chain = chain_contoh(tx_contract("tambah_paslon", {"nomor": 1, "nama": "Dari Chain", "visi": ""}))
        resp = self.kirim(NodePalsu({("GET", "/chain"): (200, {"chain": chain})}), "/panitia/rebuild")
        self.assertIn("Dari Chain", resp.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual([p.nama for p in Paslon.query.all()], ["Dari Chain"])

    def test_verify_rusak_tampil_index(self):
        node = NodePalsu({("GET", "/validate"): (200, {"valid": False, "index_rusak": 2,
                                                       "alasan": "hash block tidak cocok", "panjang": 5})})
        self.masuk()
        with self.dengan_node(node):
            teks = self.client.get("/panitia/verify").get_data(as_text=True)
        self.assertIn("Rusak mulai block #2", teks)
        self.assertIn("hash block tidak cocok", teks)

    def test_nomor_default_terkecil_yang_kosong(self):
        from web.models import Paslon, db
        with self.app.app_context():
            db.session.add_all([Paslon(id=1, nomor=1, nama="A", aktif=True),
                                Paslon(id=2, nomor=2, nama="B", aktif=False),
                                Paslon(id=3, nomor=3, nama="C", aktif=True)])
            db.session.commit()
        self.masuk()
        with self.dengan_node(NodePalsu()):
            teks = self.client.get("/panitia/").get_data(as_text=True)
        self.assertIn('id="no" name="nomor" type="number" min="1" value="2"', teks)

    def test_api_papan_tanpa_hasil_saat_dibuka(self):
        node = NodePalsu({
            ("GET", "/status"): (200, {"status": "dibuka", "terdaftar": 4, "suara_masuk": 1, "panjang": 3,
                                       "block_terakhir": {"index": 2, "hash": "0000ab", "timestamp": 1.0}}),
            ("GET", "/tally"): (200, {"status": "dibuka", "suara_masuk": 1,
                                      "hasil": {"1": 1}, "tidak_sah": 0, "per_block": [{"index": 2}]}),
            ("GET", "/paslon"): (200, {"paslon": [{"nomor": 1, "nama": "A", "aktif": True}]}),
        })
        with self.dengan_node(node):
            data = self.client.get("/api/papan").get_json()
        self.assertEqual(data["status"], "dibuka")
        self.assertEqual(data["suara_masuk"], 1)
        self.assertIsNone(data["hasil"])
        self.assertIsNone(data["per_block"])

    def test_api_papan_tahan_hasil_rantai_rusak(self):
        tally = {"status": "dihitung", "suara_masuk": 3, "hasil": {"1": 0, "2": 2}, "tidak_sah": 1, "per_block": []}
        node = NodePalsu({
            ("GET", "/status"): (200, {"status": "dihitung", "terdaftar": 4, "suara_masuk": 3, "panjang": 9}),
            ("GET", "/validate"): (200, {"valid": False, "index_rusak": 7}),
            ("GET", "/tally"): (200, tally),
            ("GET", "/paslon"): (200, {"paslon": [{"nomor": 1, "nama": "A", "aktif": True}]}),
        })
        with self.dengan_node(node):
            data = self.client.get("/api/papan").get_json()
        self.assertIsNone(data["hasil"])
        self.assertIn("#7", data["peringatan"])
        node.jawaban[("GET", "/validate")] = (200, {"valid": True})
        with self.dengan_node(node):
            data = self.client.get("/api/papan").get_json()
        self.assertEqual(data["hasil"], {"1": 0, "2": 2})

    def test_tamper_wajib_panitia(self):
        with self.client.session_transaction() as s:
            s["csrf_token"] = "t"
        resp = self.client.post("/explorer/tamper", data={"csrf_token": "t", "index": "2"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/panitia/masuk", resp.headers["Location"])


if __name__ == "__main__":
    unittest.main()
