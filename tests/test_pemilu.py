import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import node
from contract import (STATUS, buat_kunci_pemilu, dekripsi_pilihan, enkripsi_pilihan, jalankan_contract,
                      state_awal)
from node import Block, Blockchain, KonteksRantai, Transaksi, validasi_block


def buat_kunci():
    pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = pk.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return pk, pub


ALAMAT = "a" * 40


def state_dengan_paslon(kunci_publik, nomor=(1, 2)):
    state = state_awal(kunci_publik)
    for n in nomor:
        ok, alasan, state = jalankan_contract(state, "tambah_paslon", {"nomor": n, "nama": f"P{n}"})
        assert ok, alasan
    return state


class TestContractPemilu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.privat, cls.publik = buat_kunci_pemilu()

    def test_status_berurutan(self):
        self.assertEqual(STATUS, ("persiapan", "dibuka", "ditutup", "dihitung"))
        state = state_dengan_paslon(self.publik)
        self.assertEqual(state["status"], "persiapan")
        self.assertFalse(jalankan_contract(state, "tutup_pemungutan", {})[0])
        self.assertFalse(jalankan_contract(state, "buka_kunci", {"kunci_privat": self.privat})[0])
        ok, _, state = jalankan_contract(state, "buka_pemungutan", {})
        self.assertTrue(ok)
        self.assertFalse(jalankan_contract(state, "buka_pemungutan", {})[0])
        ok, _, state = jalankan_contract(state, "tutup_pemungutan", {})
        self.assertTrue(ok)
        ok, _, state = jalankan_contract(state, "buka_kunci", {"kunci_privat": self.privat})
        self.assertTrue(ok)
        self.assertEqual(state["status"], "dihitung")
        self.assertEqual(state["kunci_privat"], self.privat)

    def test_buka_butuh_dua_paslon_berurutan(self):
        self.assertFalse(jalankan_contract(state_dengan_paslon(self.publik, (1,)), "buka_pemungutan", {})[0])
        self.assertFalse(jalankan_contract(state_dengan_paslon(self.publik, (1, 3)), "buka_pemungutan", {})[0])
        self.assertTrue(jalankan_contract(state_dengan_paslon(self.publik, (2, 1)), "buka_pemungutan", {})[0])

    def test_crud_terkunci_setelah_dibuka(self):
        _, _, state = jalankan_contract(state_dengan_paslon(self.publik), "buka_pemungutan", {})
        for fungsi, args in (("tambah_paslon", {"nomor": 3, "nama": "C"}),
                             ("ubah_paslon", {"id": 1, "nama": "X"}),
                             ("hapus_paslon", {"id": 1})):
            ok, alasan, baru = jalankan_contract(state, fungsi, args)
            self.assertFalse(ok, fungsi)
            self.assertIn("persiapan", alasan)
            self.assertEqual(baru["paslon"], state["paslon"])

    def test_nomor_nonaktif_boleh_dipakai_lagi(self):
        state = state_dengan_paslon(self.publik)
        self.assertFalse(jalankan_contract(state, "tambah_paslon", {"nomor": 2, "nama": "Ganda"})[0])
        ok, _, state = jalankan_contract(state, "hapus_paslon", {"id": 2})
        self.assertTrue(ok)
        ok, _, state = jalankan_contract(state, "tambah_paslon", {"nomor": 2, "nama": "Pengganti"})
        self.assertTrue(ok)
        ok, _, state = jalankan_contract(state, "ubah_paslon", {"id": 3, "nomor": 1})
        self.assertFalse(ok)  # nomor 1 masih dipakai paslon aktif
        self.assertTrue(jalankan_contract(state, "buka_pemungutan", {})[0])

    def test_buka_kunci_salah_ditolak(self):
        state = state_dengan_paslon(self.publik)
        _, _, state = jalankan_contract(state, "buka_pemungutan", {})
        _, _, state = jalankan_contract(state, "tutup_pemungutan", {})
        privat_lain, _ = buat_kunci_pemilu()
        for kunci in (privat_lain, "bukan pem", None):
            ok, _, baru = jalankan_contract(state, "buka_kunci", {"kunci_privat": kunci})
            self.assertFalse(ok)
            self.assertEqual(baru["status"], "ditutup")
            self.assertIsNone(baru["kunci_privat"])

    def test_enkripsi_teracak(self):
        a, b = enkripsi_pilihan(1, self.publik), enkripsi_pilihan(1, self.publik)
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), 512)
        self.assertEqual(dekripsi_pilihan(a, self.privat), 1)
        self.assertEqual(dekripsi_pilihan(b, self.privat), 1)
        self.assertIsNone(dekripsi_pilihan("ab" * 256, self.privat))


class TestNodePemilu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = buat_kunci()
        cls.penyerang = buat_kunci()
        cls.pemilih = {nim: buat_kunci() for nim in ("F55119001", "F55119002", "F55119003", "A12119001")}
        cls.privat, cls.publik = buat_kunci_pemilu()

    def _tx(self, kunci, tipe, payload, voter_id="admin"):
        tx = Transaksi(voter_id, None, kunci[1], tipe=tipe, payload=payload)
        tx.tanda_tangani(kunci[0])
        return tx

    def _panggil(self, fungsi, args=None, kunci=None):
        return self._tx(kunci or self.admin, "CONTRACT_CALL",
                        {"contract_address": ALAMAT, "fungsi": fungsi, "args": args or {}})

    def _register(self, nim, kunci_pemilih=None, kunci=None):
        pub = (kunci_pemilih or self.pemilih[nim])[1]
        return self._tx(kunci or self.admin, "REGISTER", {"nim": nim, "public_key": pub})

    def _vote(self, nim, nomor=1, kunci=None):
        return self._tx(kunci or self.pemilih[nim], "VOTE", {"sandi": enkripsi_pilihan(nomor, self.publik)}, nim)

    def _persiapan(self):
        tx = [self._tx(self.admin, "CONTRACT_DEPLOY", {"contract_address": ALAMAT, "nama": "P", "kunci_pemilu": self.publik}),
              self._panggil("tambah_paslon", {"nomor": 1, "nama": "A"}),
              self._panggil("tambah_paslon", {"nomor": 2, "nama": "B"})]
        tx += [self._register(nim) for nim in self.pemilih]
        return tx

    def _konteks(self, dibuka=True):
        k = KonteksRantai()
        for tx in self._persiapan() + ([self._panggil("buka_pemungutan")] if dibuka else []):
            ok, alasan = k.terapkan(tx)
            self.assertTrue(ok, alasan)
        return k

    def test_deploy_wajib_kunci_pemilu(self):
        tx = self._tx(self.admin, "CONTRACT_DEPLOY", {"contract_address": ALAMAT, "nama": "P"})
        self.assertFalse(KonteksRantai().terapkan(tx)[0])

    def test_register_hanya_pemilik(self):
        k = self._konteks(dibuka=False)
        ok, alasan = k.terapkan(self._register("F55125001", buat_kunci(), kunci=self.penyerang))
        self.assertFalse(ok)
        self.assertIn("pemilik", alasan)
        self.assertNotIn("F55125001", k.terdaftar)

    def test_register_nim_ganda_ditolak(self):
        k = self._konteks(dibuka=False)
        self.assertFalse(k.terapkan(self._register("F55119001", buat_kunci()))[0])  # NIM sudah terdaftar
        self.assertFalse(k.terapkan(self._register("F55125001", self.pemilih["F55119001"]))[0])  # kunci dipakai NIM lain
        self.assertFalse(k.terapkan(self._register("Z55125001", buat_kunci()))[0])  # fakultas tidak ada
        self.assertFalse(k.terapkan(self._tx(self.admin, "REGISTER", {"nim": "F55125001", "public_key": "x"}))[0])
        self.assertTrue(k.terapkan(self._register("F55125001", buat_kunci()))[0])

    def test_register_ditolak_setelah_tutup(self):
        k = self._konteks()
        self.assertTrue(k.terapkan(self._register("F55125002", buat_kunci()))[0])  # saat dibuka masih boleh
        self.assertTrue(k.terapkan(self._panggil("tutup_pemungutan"))[0])
        self.assertFalse(k.terapkan(self._register("F55125003", buat_kunci()))[0])

    def test_vote_kunci_tidak_terdaftar_ditolak(self):
        k = self._konteks()
        ok, alasan = k.terapkan(self._vote("F55119001", kunci=buat_kunci()))
        self.assertFalse(ok)
        self.assertIn("terdaftar", alasan)
        self.assertFalse(k.terapkan(self._tx(buat_kunci(), "VOTE", {"sandi": "ab" * 256}, "F55125009"))[0])
        self.assertTrue(k.terapkan(self._vote("F55119001"))[0])

    def test_vote_isi_tidak_sah_ditolak(self):
        k = self._konteks()
        kunci = self.pemilih["F55119001"]
        for payload in ({"sandi": "ab"}, {"sandi": "zz" * 256}, {"kandidat": 1}, {}):
            self.assertFalse(k.terapkan(self._tx(kunci, "VOTE", payload, "F55119001"))[0], payload)
        tx = Transaksi("F55119001", 1, kunci[1], tipe="VOTE", payload={"sandi": "ab" * 256})
        tx.tanda_tangani(kunci[0])
        self.assertFalse(k.terapkan(tx)[0])  # kandidat polos tidak boleh ikut

    def test_vote_sebelum_dibuka_ditolak(self):
        k = self._konteks(dibuka=False)
        ok, alasan = k.terapkan(self._vote("F55119001"))
        self.assertFalse(ok)
        self.assertIn("dibuka", alasan)

    def test_vote_ganda_di_pool_ditolak(self):
        bc = Blockchain(difficulty=1)
        for tx in self._konteks_tx():
            self.assertTrue(bc.tambah_transaksi(tx)[0])
        self.assertTrue(bc.tambah_transaksi(self._vote("F55119001", 1))[0])
        ok, alasan, _ = bc.tambah_transaksi(self._vote("F55119001", 2))
        self.assertFalse(ok)
        self.assertIn("sudah", alasan)

    def _konteks_tx(self):
        return self._persiapan() + [self._panggil("buka_pemungutan")]

    def test_vote_setelah_tutup_ditolak(self):
        bc = Blockchain(difficulty=1)
        for tx in self._konteks_tx():
            bc.tambah_transaksi(tx)
        self.assertIsNotNone(bc.tambang_pool()[0])
        vote = self._vote("F55119001")
        self.assertTrue(bc.tambah_transaksi(vote)[0])  # masuk pool saat masih dibuka
        block = Block(bc.terakhir().index + 1, [self._panggil("tutup_pemungutan"), vote], bc.terakhir().hash)
        block.tambang(bc.difficulty)
        ok, alasan, _ = validasi_block(block, bc.terakhir(), bc.difficulty, bc.konteks)
        self.assertFalse(ok)
        self.assertIn("dibuka", alasan)

    def test_salin_tidak_berbagi_state(self):
        k = self._konteks(dibuka=False)
        salinan = k.salin()
        self.assertTrue(salinan.terapkan(self._panggil("buka_pemungutan"))[0])
        self.assertEqual(k.state["status"], "persiapan")
        salinan.terdaftar["X"] = "y"
        self.assertNotIn("X", k.terdaftar)

    def test_tally_hanya_setelah_dihitung(self):
        bc = Blockchain(difficulty=1)
        for tx in self._konteks_tx():
            bc.tambah_transaksi(tx)
        bc.tambang_pool()
        for nim, nomor in (("F55119001", 1), ("F55119002", 1), ("F55119003", 2)):
            self.assertTrue(bc.tambah_transaksi(self._vote(nim, nomor))[0])
        rusak = self._tx(self.pemilih["A12119001"], "VOTE", {"sandi": "ab" * 256}, "A12119001")
        self.assertTrue(bc.tambah_transaksi(rusak)[0])
        bc.tambang_pool()

        hasil = bc.tally()
        self.assertEqual((hasil["status"], hasil["suara_masuk"]), ("dibuka", 4))
        self.assertIsNone(hasil["hasil"])
        self.assertIsNone(hasil["tidak_sah"])
        self.assertIsNone(hasil["per_block"])

        bc.tambah_transaksi(self._panggil("tutup_pemungutan"))
        bc.tambang_pool()
        self.assertIsNone(bc.tally()["hasil"])
        bc.tambah_transaksi(self._panggil("buka_kunci", {"kunci_privat": self.privat}))
        bc.tambang_pool()

        hasil = bc.tally()
        self.assertEqual(hasil["status"], "dihitung")
        self.assertEqual(hasil["hasil"], {"1": 2, "2": 1})
        self.assertEqual(hasil["tidak_sah"], 1)
        self.assertEqual(hasil["per_block"], [{"index": 2, "hasil": {"1": 2, "2": 1}}])

    def test_tamper_vote_terdeteksi(self):
        bc = Blockchain(difficulty=1)
        for tx in self._konteks_tx():
            bc.tambah_transaksi(tx)
        bc.tambang_pool()
        bc.tambah_transaksi(self._vote("F55119001"))
        bc.tambang_pool()
        self.assertTrue(bc.ubah_data_demo(2)[0])
        ok, rusak, _ = bc.periksa()
        self.assertFalse(ok)
        self.assertEqual(rusak, 2)


class TestDompet(unittest.TestCase):
    def test_dompet_terenkripsi_dan_vote_terenkripsi(self):
        import os
        import tempfile

        from client import Dompet
        privat, publik = buat_kunci_pemilu()
        asal = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            os.chdir(folder)
            try:
                dompet = Dompet("F55119001", b"rahasia")
                self.assertIn(b"ENCRYPTED", dompet.berkas.read_bytes())
                with self.assertRaises(ValueError):
                    Dompet("F55119001", b"salah")
                self.assertEqual(Dompet("F55119001", b"rahasia").public_key_pem, dompet.public_key_pem)
            finally:
                os.chdir(asal)
        tx = dompet.buat_transaksi(2, publik)
        self.assertEqual((tx.tipe, tx.voter_id, tx.kandidat), ("VOTE", "F55119001", None))
        self.assertTrue(tx.verifikasi())
        self.assertEqual(dekripsi_pilihan(tx.payload["sandi"], privat), 2)


if __name__ == "__main__":
    unittest.main()
