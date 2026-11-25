import unittest
from node import Transaksi


class TestTransaksiContract(unittest.TestCase):
    def test_to_dict_roundtrip_contract(self):
        tx = Transaksi("admin", None, "PUB", tipe="CONTRACT_CALL", payload={"f": "tambah_paslon"})
        d = tx.to_dict()
        tx2 = Transaksi.from_dict(d)
        self.assertEqual(tx2.tipe, "CONTRACT_CALL")
        self.assertEqual(tx2.payload, {"f": "tambah_paslon"})

    def test_pesan_changes_with_payload(self):
        tx = Transaksi("admin", None, "PUB", tipe="CONTRACT_CALL", payload={"a": 1})
        p1 = tx.pesan()
        tx.payload = {"a": 2}
        self.assertNotEqual(p1, tx.pesan())

    def test_vote_backward_compat(self):
        tx = Transaksi("F55125001", "Paslon 1", "PUB")
        self.assertEqual(tx.tipe, "VOTE")
        d = tx.to_dict()
        tx2 = Transaksi.from_dict(d)
        self.assertEqual(tx2.kandidat, "Paslon 1")


if __name__ == "__main__":
    unittest.main()
