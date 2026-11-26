import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from node import KonteksRantai, Transaksi


def buat_kunci():
    pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = pk.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return pk, pub


class TestKonteksRantai(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = buat_kunci()
        cls.penyerang = buat_kunci()
        cls.alamat = "a" * 40

    def _tx(self, kunci, tipe, payload=None, voter_id="admin", kandidat=None):
        tx = Transaksi(voter_id, kandidat, kunci[1], tipe=tipe, payload=payload)
        tx.tanda_tangani(kunci[0])
        return tx

    def _panggil(self, kunci, fungsi, args):
        return self._tx(kunci, "CONTRACT_CALL", {"contract_address": self.alamat, "fungsi": fungsi, "args": args})

    def _konteks_dengan_paslon(self):
        k = KonteksRantai()
        self.assertTrue(k.terapkan(self._tx(self.admin, "CONTRACT_DEPLOY", {"contract_address": self.alamat, "nama": "P"}))[0])
        self.assertTrue(k.terapkan(self._panggil(self.admin, "tambah_paslon", {"nomor": 1, "nama": "A"}))[0])
        return k

    def test_contract_belum_dideploy_ditolak(self):
        ok, alasan = KonteksRantai().terapkan(self._panggil(self.admin, "tambah_paslon", {"nomor": 1, "nama": "A"}))
        self.assertFalse(ok)
        self.assertIn("belum dideploy", alasan)

    def test_fungsi_tidak_dikenal_dan_nama_kosong_ditolak(self):
        k = self._konteks_dengan_paslon()
        ok, alasan = k.terapkan(self._panggil(self.admin, "hack", {}))
        self.assertFalse(ok)
        self.assertIn("tidak dikenal", alasan)
        self.assertFalse(k.terapkan(self._panggil(self.admin, "tambah_paslon", {"nomor": 2, "nama": ""}))[0])

    def test_bukan_pemilik_tidak_bisa_ubah_state(self):
        k = self._konteks_dengan_paslon()
        ok, alasan = k.terapkan(self._panggil(self.penyerang, "hapus_paslon", {"id": 1}))
        self.assertFalse(ok)
        self.assertIn("pemilik", alasan)
        self.assertTrue(k.paslon[0]["aktif"])

    def test_deploy_kedua_ditolak(self):
        k = self._konteks_dengan_paslon()
        ok, _ = k.terapkan(self._tx(self.penyerang, "CONTRACT_DEPLOY", {"contract_address": "b" * 40, "nama": "X"}))
        self.assertFalse(ok)

    def test_replay_transaksi_lama_ditolak(self):
        k = self._konteks_dengan_paslon()
        lama = self._panggil(self.admin, "ubah_paslon", {"id": 1, "nama": "Lama"})
        self.assertTrue(k.terapkan(lama)[0])
        self.assertTrue(k.terapkan(self._panggil(self.admin, "ubah_paslon", {"id": 1, "nama": "Baru"}))[0])
        ok, alasan = k.terapkan(lama)
        self.assertFalse(ok)
        self.assertIn("replay", alasan)
        self.assertEqual(k.paslon[0]["nama"], "Baru")

    def test_vote_ganda_dan_input_aneh_ditolak(self):
        k = self._konteks_dengan_paslon()
        pemilih = buat_kunci()
        self.assertTrue(k.terapkan(self._tx(pemilih, "VOTE", voter_id="F55125001", kandidat=1))[0])
        for voter_id, kandidat in (("F55125001", 1), ("f55125001", 1), (" F55125001", 1),
                                   ("F55125002", True), ("F55125002", "1"), ("F55125002", 9)):
            ok, _ = k.terapkan(self._tx(pemilih, "VOTE", voter_id=voter_id, kandidat=kandidat))
            self.assertFalse(ok, (voter_id, kandidat))

    def test_tipe_tidak_dikenal_ditolak(self):
        ok, alasan = KonteksRantai().terapkan(self._tx(self.admin, "MINT", {}))
        self.assertFalse(ok)
        self.assertIn("tidak dikenal", alasan)

    def test_from_dict_tipe_data_salah(self):
        with self.assertRaises(TypeError):
            Transaksi.from_dict({"voter_id": ["x"], "public_key": "P", "signature": "s"})


if __name__ == "__main__":
    unittest.main()
