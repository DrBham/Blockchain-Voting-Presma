import unittest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from node import validasi_transaksi, Transaksi


class TestContractValidation(unittest.TestCase):
    def _buat_tx(self, payload):
        pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub = pk.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        tx = Transaksi("admin", None, pub, tipe="CONTRACT_CALL", payload=payload)
        tx.tanda_tangani(pk)
        return tx

    def test_empty_name_rejected(self):
        tx = self._buat_tx({
            "contract_address": "addr", "fungsi": "tambah_paslon",
            "args": {"nomor": 1, "nama": "", "visi": "v"},
        })
        ok, alasan = validasi_transaksi(tx, [])
        self.assertFalse(ok)

    def test_unknown_function_rejected(self):
        tx = self._buat_tx({
            "contract_address": "addr", "fungsi": "hack", "args": {},
        })
        ok, alasan = validasi_transaksi(tx, [])
        self.assertFalse(ok)
        self.assertIn("tidak dikenal", alasan)


if __name__ == "__main__":
    unittest.main()
