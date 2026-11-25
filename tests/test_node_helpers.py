import unittest
import node


class TestHelpers(unittest.TestCase):
    def test_cari_port_kosong_returns_int(self):
        p = node.cari_port_kosong(5900, 5)
        self.assertIsInstance(p, int)
        self.assertGreaterEqual(p, 5900)

    def test_deteksi_ip_returns_list(self):
        ips = node.deteksi_ip_non_loopback()
        self.assertIsInstance(ips, list)


class TestBeacon(unittest.TestCase):
    def setUp(self):
        from node import Blockchain, Node
        self.node = Node(5001, [], 4)
        node.NODE = self.node
        node.IFACE_IP = "192.168.137.10"
        node.PORT = 5001

    def test_difficulty_mismatch_ignored(self):
        data = {"type": "presma-node", "http_port": 5002, "difficulty": 2, "genesis": self.node.blockchain.chain[0].hash}
        self.assertIsNone(node.proses_beacon(data, ("192.168.137.20", 9999), self.node))

    def test_genesis_mismatch_ignored(self):
        data = {"type": "presma-node", "http_port": 5002, "difficulty": 4, "genesis": "deadbeef"}
        self.assertIsNone(node.proses_beacon(data, ("192.168.137.20", 9999), self.node))

    def test_self_ignored(self):
        data = {"type": "presma-node", "http_port": 5001, "difficulty": 4, "genesis": self.node.blockchain.chain[0].hash}
        self.assertIsNone(node.proses_beacon(data, ("192.168.137.10", 9999), self.node))

    def test_valid_beacon_adds_peer(self):
        data = {"type": "presma-node", "http_port": 5002, "difficulty": 4, "genesis": self.node.blockchain.chain[0].hash}
        res = node.proses_beacon(data, ("192.168.137.20", 9999), self.node)
        self.assertEqual(res, "192.168.137.20:5002")
        self.assertIn("192.168.137.20:5002", self.node.peers)


if __name__ == "__main__":
    unittest.main()
