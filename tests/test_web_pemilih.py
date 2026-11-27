import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

from contract import buat_kunci_pemilu
from tests.test_web_dasar import app_uji

NIM = "F55124001"
PASSWORD = "rahasia-123"
_, KUNCI_PEMILU = buat_kunci_pemilu()


class NodePalsu:
    """Pengganti node_request: cukup untuk alur pemilih (status, pemilih, paslon, transaksi, tx)."""

    def __init__(self):
        self.status = "dibuka"
        self.terdaftar = set()
        self.memilih = set()
        self.tx = []
        self.tolak = None

    def __call__(self, method, path, data=None, timeout=None):
        if path == "/status":
            return 200, {"status": self.status, "terdaftar": len(self.terdaftar), "suara_masuk": len(self.memilih),
                         "pool": 0, "panjang": 3, "block_terakhir": {}, "kunci_pemilu": KUNCI_PEMILU, "kontrak": "x"}
        if path.startswith("/pemilih/"):
            nim = path.rsplit("/", 1)[1]
            return 200, {"terdaftar": nim in self.terdaftar, "public_key": None, "sudah_memilih": nim in self.memilih}
        if path == "/paslon":
            return 200, {"paslon": [{"id": 1, "nomor": 1, "nama": "Paslon A", "visi": "", "aktif": True},
                                    {"id": 2, "nomor": 2, "nama": "Paslon B", "visi": "", "aktif": True}]}
        if path == "/transaksi":
            if self.tolak:
                return 400, {"error": self.tolak}
            self.tx.append(data)
            self.memilih.add(data["voter_id"])
            return 201, {"pesan": "ok"}
        if path == "/mine":
            return 201, {"block": {"index": 4}}
        if path.startswith("/tx/"):
            return 200, {"status": "pool", "block": None}
        return 404, {"error": "tidak ada"}


class TestWebPemilih(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = app_uji(self.tmp.name)
        self.node = NodePalsu()
        self.kode = []
        patch_node = mock.patch("web.node_api.node_request", side_effect=self.node)
        patch_surel = mock.patch("web.surel.kirim_kode", side_effect=lambda email, kode: self.kode.append((email, kode)) or True)
        patch_node.start()
        patch_surel.start()
        self.addCleanup(mock.patch.stopall)
        self.c = self.app.test_client()
        with self.c.session_transaction() as s:
            s["csrf_token"] = "t"

    def tearDown(self):
        from web.models import db
        with self.app.app_context():
            db.engine.dispose()
        self.tmp.cleanup()

    def post(self, url, **data):
        return self.c.post(url, data={"csrf_token": "t", **data})

    def pemilih(self, nim=NIM):
        from web.models import Pemilih, db
        with self.app.app_context():
            p = db.session.get(Pemilih, nim)
            if p:
                db.session.expunge(p)
            return p

    def ubah(self, **kolom):
        from web.models import Pemilih, db
        with self.app.app_context():
            Pemilih.query.filter_by(nim=NIM).update(kolom)
            db.session.commit()

    def daftar(self):
        r = self.post("/daftar", nim=NIM, email="lain@contoh.com", pw=PASSWORD, pw2=PASSWORD)
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True))
        return self.kode[-1][1]

    def aktif(self):
        kode = self.daftar()
        self.assertEqual(self.post("/verifikasi", kode=kode).status_code, 302)
        return kode

    def masuk(self, kode):
        return self.post("/masuk", nim=NIM, pw=PASSWORD, kode=kode)

    def test_daftar_email_otomatis(self):
        self.daftar()
        self.assertEqual(self.pemilih().email, f"{NIM}@untad.ac.id")
        self.assertEqual(self.kode[-1][0], f"{NIM}@untad.ac.id")
        self.assertIn("readonly", self.c.get("/daftar").get_data(as_text=True))

    def test_daftar_nim_fakultas_salah_ditolak(self):
        r = self.post("/daftar", nim="Z55125001", pw=PASSWORD, pw2=PASSWORD)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Kode fakultas &#39;Z&#39; tidak terdaftar di UNTAD", r.get_data(as_text=True))
        self.assertIsNone(self.pemilih("Z55125001"))
        self.assertEqual(self.kode, [])

    def test_daftar_nim_sudah_di_chain_ditolak(self):
        self.node.terdaftar.add("A12119001")
        r = self.post("/daftar", nim="A12119001", pw=PASSWORD, pw2=PASSWORD)
        self.assertIn("sudah tercatat di chain", r.get_data(as_text=True))
        self.assertIsNone(self.pemilih("A12119001"))

    def test_daftar_ulang_akun_menunggu_ditolak(self):
        self.daftar()
        hash_lama = self.pemilih().password_hash
        r = self.post("/daftar", nim=NIM, pw="Penyerang#99", pw2="Penyerang#99")
        self.assertIn("menunggu verifikasi", r.get_data(as_text=True))
        self.assertEqual(self.pemilih().password_hash, hash_lama)  # password pemilik tidak tertimpa
        self.assertEqual(len(self.kode), 1)  # tidak ada email kode baru

    def test_kode_salah_lima_kali(self):
        kode = self.daftar()
        salah = "000000" if kode != "000000" else "111111"
        for _ in range(5):
            self.post("/verifikasi", kode=salah)
        r = self.post("/verifikasi", kode=kode)  # kode benar pun sudah hangus
        self.assertIn("kirim ulang", r.get_data(as_text=True).lower())
        self.assertFalse(self.pemilih().terverifikasi)
        # kirim ulang ditolak sebelum 60 detik, lalu boleh dan kode baru yang berlaku
        self.post("/verifikasi", aksi="kirim_ulang")
        self.assertEqual(len(self.kode), 1)
        self.ubah(kode_dikirim=datetime.now() - timedelta(seconds=61))
        self.post("/verifikasi", aksi="kirim_ulang")
        self.assertEqual(len(self.kode), 2)
        self.assertEqual(self.post("/verifikasi", kode=self.kode[-1][1]).status_code, 302)
        self.assertTrue(self.pemilih().terverifikasi)

    def test_masuk_kode_terpakai(self):
        kode = self.aktif()
        self.ubah(kode_terpakai=True)
        r = self.masuk(kode)
        teks = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Kamu sudah memilih", teks)
        self.assertIn('href="/bukti"', teks)
        with self.c.session_transaction() as s:
            self.assertNotIn("kunci", s)

    def test_setuju_dua_kali_satu_suara(self):
        kode = self.aktif()
        self.node.terdaftar.add(NIM)
        self.assertEqual(self.masuk(kode).headers["Location"], "/bilik")
        self.assertIn('name="paslon"', self.c.get("/bilik").get_data(as_text=True))
        r1 = self.post("/bilik", paslon="1")
        r2 = self.post("/bilik", paslon="2")
        self.assertEqual(r1.headers["Location"], "/bukti")
        self.assertEqual(r2.headers["Location"], "/bukti")
        self.assertEqual(len(self.node.tx), 1)
        tx = self.node.tx[0]
        self.assertIsNone(tx["kandidat"])
        self.assertEqual(len(tx["payload"]["sandi"]), 512)
        p = self.pemilih()
        self.assertTrue(p.kode_terpakai)
        self.assertEqual(p.signature_suara, tx["signature"])
        bukti = self.c.get("/bukti").get_data(as_text=True)
        self.assertIn(tx["signature"][:16], bukti)
        self.assertNotIn("Paslon A", bukti)
        self.assertEqual(self.c.get("/api/tx-status").get_json()["status"], "pool")

    def test_setuju_ditolak_node_kode_dikembalikan(self):
        kode = self.aktif()
        self.node.terdaftar.add(NIM)
        self.masuk(kode)
        self.node.tolak = "status pemilu bukan dibuka"
        r = self.post("/bilik", paslon="1")
        self.assertEqual(r.headers["Location"], "/bilik")
        self.assertFalse(self.pemilih().kode_terpakai)
        self.assertIn("status pemilu bukan dibuka", self.c.get("/bilik").get_data(as_text=True))

    def test_bilik_kunci_kedaluwarsa(self):
        kode = self.aktif()
        self.node.terdaftar.add(NIM)
        self.masuk(kode)
        nanti = time.monotonic() + 901
        with mock.patch("web.sesi_kunci.time.monotonic", return_value=nanti):
            r = self.c.get("/bilik")
            self.assertEqual(r.headers["Location"], "/masuk")
            r = self.post("/bilik", paslon="1")
            self.assertEqual(r.headers["Location"], "/masuk")
        self.assertIn("Sesi bilik habis, masuk lagi", self.c.get("/masuk").get_data(as_text=True))
        self.assertEqual(self.node.tx, [])
        self.assertFalse(self.pemilih().kode_terpakai)

    def test_bilik_tertutup_saat_persiapan(self):
        kode = self.aktif()
        self.node.terdaftar.add(NIM)
        self.node.status = "persiapan"
        self.masuk(kode)
        teks = self.c.get("/bilik").get_data(as_text=True)
        self.assertIn("belum dibuka", teks)
        self.assertNotIn('name="paslon"', teks)
        self.post("/bilik", paslon="1")
        self.assertEqual(self.node.tx, [])


if __name__ == "__main__":
    unittest.main()
