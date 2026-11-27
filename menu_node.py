# Menu dan cara menjalankan node. Logika blockchain dan jaringan ada di node.py;
# file ini hanya berisi interaksi dengan pengguna (prompt, menu angka, pesan).
#   python menu_node.py                          mode interaktif (pilih interface, port otomatis)
#   python menu_node.py <port> [peers] [difficulty]   mode otomatis (dipakai Docker)

import sys
import threading
import time
from http.server import ThreadingHTTPServer

import node


def pilih_interface(otomatis=False):
    """Pilih IP interface utama. Prompt jika >1 dan tidak otomatis."""
    ips = node.deteksi_ip_non_loopback()
    if not ips:
        return "127.0.0.1"
    if otomatis:
        return ips[0]
    ips.append("127.0.0.1")  # opsi menjalankan node hanya di mesin yang sama
    print("Pilih interface jaringan:")
    for i, ip in enumerate(ips, 1):
        label = " (local only)" if ip == "127.0.0.1" else ""
        print(f"  {i}. {ip}{label}")
    while True:
        pilihan = input(f"Pilih interface [1-{len(ips)}] (default 1): ").strip()
        if pilihan == "":
            return ips[0]
        if pilihan.isdigit() and 1 <= int(pilihan) <= len(ips):
            return ips[int(pilihan) - 1]
        print("Pilihan tidak valid.")


def menu_interaktif(n):
    stop_event = threading.Event()
    node.mulai_discovery(node.IFACE_IP, stop_event)
    try:
        while True:
            print("\n=== Node Voting Presma (Interaktif) ===")
            print(f"Interface: {node.IFACE_IP} | Node: http://{node.IFACE_IP}:{n.port} (difficulty {n.blockchain.difficulty})")
            print("1. Status")
            print("2. Daftar peer")
            print("3. Cari node (tunggu 6 detik)")
            print("4. Tambah peer manual")
            print("5. Tampilkan alamat untuk menu_client.py")
            print("6. Hentikan node")
            pilihan = input("Pilih: ").strip()
            if pilihan == "1":
                with n.blockchain.lock:
                    print(f"Port: {n.port} | Peers: {len(n.peers)} | Rantai: {len(n.blockchain.chain)} block | Pool: {len(n.blockchain.pool)}")
                print("Peers:", n.peers)
            elif pilihan == "2":
                print("Peers:", n.peers)
            elif pilihan == "3":
                print("Mencari node lain selama 6 detik...")
                time.sleep(6)
                print("Peers sekarang:", n.peers)
            elif pilihan == "4":
                peer = input("Alamat peer (host:port): ").strip()
                if peer:
                    print(node.tambah_peer_manual(n, peer)[1])
            elif pilihan == "5":
                print(f"Gunakan di menu_client.py: {node.IFACE_IP}:{n.port}")
            elif pilihan == "6":
                break
            else:
                print("Pilihan tidak valid.")
    finally:
        stop_event.set()
        if n.http_server:
            n.http_server.shutdown()


def main():
    # node.py memakai PORT, IFACE_IP, dan NODE sebagai nilai global modul: isi di sini sebelum server jalan
    if len(sys.argv) == 1:
        node.IFACE_IP = pilih_interface(otomatis=False)
        node.PORT = node.cari_port_kosong()
        if node.PORT is None:
            print("Tidak ada port kosong di range 5001-5100.")
            sys.exit(1)
        peers_awal, difficulty, interaktif = [], 4, True
    else:
        node.PORT = int(sys.argv[1])
        peers_awal = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else []
        difficulty = int(sys.argv[3]) if len(sys.argv) > 3 else 4
        node.IFACE_IP = pilih_interface(otomatis=True)
        interaktif = False

    n = node.NODE = node.Node(node.PORT, peers_awal, difficulty)
    print(f"Node Voting UNTAD aktif di port {node.PORT}")
    print("Peers     : " + (", ".join(n.peers) if n.peers else "(belum ada)"))
    print(f"Difficulty: {difficulty} (hash harus diawali {'0' * difficulty})")
    print(f"Genesis   : {node.GENESIS_HASH[:20]}...")
    print(f"Interface : {node.IFACE_IP}")

    server = ThreadingHTTPServer(("0.0.0.0", node.PORT), node.NodeHandler)
    n.http_server = server
    if interaktif:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        menu_interaktif(n)
    else:
        stop_event = threading.Event()
        node.mulai_discovery(node.IFACE_IP, stop_event)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            stop_event.set()


if __name__ == "__main__":
    main()
