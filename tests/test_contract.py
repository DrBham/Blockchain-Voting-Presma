import unittest
from contract import PaslonContract, deploy_contract, state_paslon_dari_chain


class TestContract(unittest.TestCase):
    def test_deploy_returns_address(self):
        addr = deploy_contract("PaslonContract")
        self.assertIsInstance(addr, str)
        self.assertEqual(len(addr), 40)

    def test_tambah_ok(self):
        c = PaslonContract("addr")
        state = []
        ok, alasan, state2 = c.tambah_paslon(state, {"nomor": 1, "nama": "A", "visi": "v"})
        self.assertTrue(ok)
        self.assertEqual(len(state2), 1)
        self.assertEqual(state2[0]["nama"], "A")
        self.assertTrue(state2[0]["aktif"])

    def test_tambah_empty_name_rejected(self):
        c = PaslonContract("addr")
        ok, alasan, state2 = c.tambah_paslon([], {"nomor": 1, "nama": "", "visi": "v"})
        self.assertFalse(ok)
        self.assertEqual(state2, [])

    def test_tambah_duplicate_nomor_rejected(self):
        c = PaslonContract("addr")
        state = [{"id": 1, "nomor": 1, "nama": "A", "visi": "v", "aktif": True}]
        ok, alasan, state2 = c.tambah_paslon(state, {"nomor": 1, "nama": "B", "visi": "w"})
        self.assertFalse(ok)

    def test_ubah_ok(self):
        c = PaslonContract("addr")
        state = [{"id": 1, "nomor": 1, "nama": "A", "visi": "v", "aktif": True}]
        ok, alasan, state2 = c.ubah_paslon(state, {"id": 1, "nama": "A2", "visi": "v2"})
        self.assertTrue(ok)
        self.assertEqual(state2[0]["nama"], "A2")

    def test_hapus_soft_delete(self):
        c = PaslonContract("addr")
        state = [{"id": 1, "nomor": 1, "nama": "A", "visi": "v", "aktif": True}]
        ok, alasan, state2 = c.hapus_paslon(state, {"id": 1})
        self.assertTrue(ok)
        self.assertFalse(state2[0]["aktif"])

    def test_baca(self):
        c = PaslonContract("addr")
        state = [{"id": 1, "nomor": 1, "nama": "A", "visi": "v", "aktif": True}]
        self.assertEqual(c.baca_paslon(state, 1)["nama"], "A")
        self.assertIsNone(c.baca_paslon(state, 999))

    def test_replay_state(self):
        # build a fake chain-like list of objects
        class Tx:
            def __init__(self, tipe, payload):
                self.tipe = tipe
                self.payload = payload
        class Block:
            def __init__(self, transaksi):
                self.transaksi = transaksi
        chain = [
            Block([Tx("CONTRACT_CALL", {"fungsi": "tambah_paslon", "args": {"nomor": 1, "nama": "A", "visi": "v"}})]),
            Block([Tx("CONTRACT_CALL", {"fungsi": "ubah_paslon", "args": {"id": 1, "nama": "A2"}})]),
            Block([Tx("CONTRACT_CALL", {"fungsi": "hapus_paslon", "args": {"id": 1}})]),
        ]
        state = state_paslon_dari_chain(chain)
        self.assertEqual(len(state), 1)
        self.assertEqual(state[0]["nama"], "A2")
        self.assertFalse(state[0]["aktif"])


if __name__ == "__main__":
    unittest.main()
