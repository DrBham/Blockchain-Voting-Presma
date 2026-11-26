# Client perintah voting UNTAD. Private key disimpan lokal dan tidak dikirim ke node.

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from node import Block, Transaksi, alamat_dari_pem

BATAS_WAKTU_NODE = 300  # mining difficulty tinggi bisa > 1 menit
NODE_DISCOVERY_PORT = 9999
DISCOVERED_NODES = set()


class Dompet:
    def __init__(self, nim):
        self.nim = nim.upper().strip()
        self.berkas = Path(f"dompet_{self.nim}.pem")

        if self.berkas.exists():
            self.private_key = serialization.load_pem_private_key(
                self.berkas.read_bytes(), password=None
            )
            self.baru = False
        else:
            self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self.berkas.write_bytes(
                self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            try:
                self.berkas.chmod(0o600)
            except OSError:
                pass
            self.baru = True

        self.public_key_pem = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def alamat(self):
        return alamat_dari_pem(self.public_key_pem)

    # [CHECKPOINT 1] Pembuatan identitas: alamat/public key (dipotong) tercetak,
    # beserta keterangan private key disimpan lokal
    def tampilkan_identitas(self):
        isi_kunci = "".join(self.public_key_pem.strip().splitlines()[1:-1])
        status = "dibuat" if self.baru else "dipakai kembali"
        print(f"Identitas voter {self.nim} ({status})")
        print(f"  Alamat     : {self.alamat()}")
        print(f"  Public key : {isi_kunci[:40]}...")
        print(f"  Private key: disimpan lokal di '{self.berkas}' (tidak dikirim ke node)")

    # [CHECKPOINT 2] Transaksi dibuat dan ditandatangani dengan private key lokal
    def buat_transaksi(self, kandidat):
        tx = Transaksi(self.nim, kandidat, self.public_key_pem)
        tx.tanda_tangani(self.private_key)
        return tx

def panggil(url, data=None):
    """Mengembalikan (kode_http, isi_json). Tidak melempar error untuk status 4xx/5xx."""
    if data is None:
        permintaan = urllib.request.Request(url)
    else:
        permintaan = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    try:
        with urllib.request.urlopen(permintaan, timeout=BATAS_WAKTU_NODE) as balasan:
            return balasan.status, json.loads(balasan.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except ValueError:
            return e.code, {}


def ringkas(chain):
    for b in chain:
        print(f"  Block {b['index']} | nonce: {str(b['nonce']).ljust(8)} "
              f"| prev: {b['previous_hash'][:12]}... | hash: {b['hash'][:12]}... "
              f"| {len(b['transaksi'])} transaksi")
        for t in b["transaksi"]:
            print(f"      - {t['voter_id']} -> {t['kandidat']} | sig {t['signature'][:16]}...")


def discovery_listener(stop_event):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", NODE_DISCOVERY_PORT))
    except OSError:
        return
    sock.settimeout(1)
    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            continue
        try:
            obj = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if obj.get("type") == "presma-node":
            try:
                port = int(obj["http_port"])
            except (KeyError, ValueError, TypeError):
                continue
            DISCOVERED_NODES.add(f"{addr[0]}:{port}")
    sock.close()


def panggil_node(alamat, endpoint, data=None):
    return panggil(f"http://{alamat}/{endpoint}", data)


# [CHECKPOINT 3] Hasil verifikasi dari node: diterima ke pool, atau ditolak beserta alasannya
# [CHECKPOINT 4] Jumlah transaksi pending di pool ikut tercetak
def kirim_transaksi(alamat, tx):
    kode, hasil = panggil_node(alamat, "transaksi", tx.to_dict())
    if kode in (200, 201):
        print(f"Transaksi DITERIMA node: {hasil['pesan']} (pending di pool: {hasil['pool']})")
    else:
        print(f"Transaksi DITOLAK node (HTTP {kode}): {hasil.get('error')}")


BANTUAN = """Perintah:
  identitas <NIM>                               buat/lihat identitas voter
  vote <node> <nomor_paslon> <NIM>              buat, tanda tangani, kirim suara ke pool
  vote_ubah <node> <Paslon> <PaslonDiubah> <NIM>  suara diubah SETELAH ditandatangani (harus ditolak)
  pool <node>                                   lihat transaksi pending
  mine <node>                                   bentuk block dari pool + proof of work
  chain <node>                                  lihat rantai
  validate <node>                               validasi seluruh rantai
  tally <node>                                  rekap suara
  tamper <node> <index>                         DEMO: ubah suara di block lama
  add_peer <node> <peer>                        hubungkan dua node (dua arah)
  resolve <node>                                longest-chain rule
  palsu <node>                                  kirim block tanpa PoW valid (harus ditolak)"""


def perintah_identitas(arg):
    Dompet(arg[0]).tampilkan_identitas()


def perintah_vote(arg):
    alamat = arg[0] if arg else None
    # jika dipanggil interaktif, arg berisi [node, kandidat?, nim?]; pertahankan kompatibilitas
    # Mode manual lama: vote <node> <Paslon> <NIM>
    if len(arg) >= 3:
        node_addr = arg[0]
        kandidat = int(arg[1]) if arg[1].isdigit() else arg[1]  # nomor paslon disimpan sebagai angka
        nim = arg[2]
        dompet = Dompet(nim)
        dompet.tampilkan_identitas()
        tx = dompet.buat_transaksi(kandidat)
        print(f"Transaksi dibuat dan ditandatangani: {tx.voter_id} -> {tx.kandidat}")
        print(f"  Signature: {tx.signature[:32]}...")
        kirim_transaksi(node_addr, tx)
        return
    # Mode interaktif dipanggil dari menu dengan [node] saja? tangani di menu separately
    print("Penggunaan: vote <node> <nomor_paslon> <NIM>")


# [CHECKPOINT 3] Transaksi diubah SETELAH ditandatangani -> harus ditolak node
def perintah_vote_ubah(arg):
    alamat, asli, diubah, nim = arg[:4]
    tx = Dompet(nim).buat_transaksi(asli)
    print(f"Transaksi ditandatangani untuk '{asli}', lalu isinya diubah menjadi '{diubah}'")
    tx.kandidat = diubah
    kirim_transaksi(alamat, tx)


# [CHECKPOINT 4] Status pool
def perintah_pool(arg):
    alamat = arg[0]
    _, hasil = panggil_node(alamat, "pool")
    print(f"Transaksi pending di {alamat}: {hasil['jumlah']}")
    for tx in hasil["transaksi"]:
        print(f"  - {tx['voter_id']} -> {tx['kandidat']} | sig {tx['signature'][:16]}...")


# [CHECKPOINT 5, 6, 7] Bentuk block, jalankan PoW, lalu terima ke rantai.
def perintah_mine(arg):
    kode, hasil = panggil_node(arg[0], "mine", {})
    if kode != 201:
        print(f"Gagal menambang: {hasil.get('error')}")
        return
    block = hasil["block"]
    print(
        f"{hasil['pesan']}: Block {block['index']} "
        f"(nonce {block['nonce']}, hash {block['hash'][:20]}...)"
    )


def perintah_chain(arg):
    alamat = arg[0]
    _, hasil = panggil_node(alamat, "chain")
    print(f"Panjang rantai di {alamat}: {hasil['panjang']} block")
    ringkas(hasil["chain"])


# [CHECKPOINT 8-9] Rantai normal valid; manipulasi menampilkan block pertama yang rusak.
def perintah_validate(arg):
    _, hasil = panggil_node(arg[0], "validate")
    if hasil["valid"]:
        print(f"Rantai VALID untuk seluruh {hasil['panjang']} block")
        return
    print(f"Rantai TIDAK VALID. Block pertama yang rusak: index {hasil['index_rusak']}")
    print(f"Alasan: {hasil['alasan']}")


def perintah_tally(arg):
    alamat = arg[0]
    _, hasil = panggil_node(alamat, "tally")
    _, paslon_data = panggil_node(alamat, "paslon")
    paslons = paslon_data.get("paslon", []) if isinstance(paslon_data, dict) else []
    nama_map = {str(p.get("nomor")): p.get("nama") for p in paslons}
    print(f"Total Suara Masuk: {hasil['total_suara']}")
    print("Hasil Rekapitulasi Suara:")
    for kandidat, jumlah in hasil["rekap_suara"].items():
        nama = nama_map.get(str(kandidat), kandidat)
        print(f"  - {nama} (nomor {kandidat}): {jumlah} suara")


def tampilkan_pesan_node(alamat, endpoint, data):
    _, hasil = panggil_node(alamat, endpoint, data)
    print(hasil.get("pesan") or hasil.get("error"))


# [CHECKPOINT 9] Manipulasi data block lama (khusus demo)
def perintah_tamper(arg):
    tampilkan_pesan_node(arg[0], "tamper", {"index": int(arg[1])})


# [CHECKPOINT 10] Menghubungkan node (syarat broadcast antar-node)
def perintah_add_peer(arg):
    tampilkan_pesan_node(arg[0], "peers", {"peer": arg[1]})


# [CHECKPOINT 10] Node tertinggal mengambil rantai valid yang terpanjang.
def perintah_resolve(arg):
    _, hasil = panggil_node(arg[0], "resolve")
    status = "diganti. Panjang sekarang" if hasil["rantai_diganti"] else "tidak berubah. Panjang"
    print(f"Rantai {status}: {hasil['panjang']} block")


# [CHECKPOINT 11] Block tanpa proof of work valid -> harus ditolak node
def perintah_palsu(arg):
    alamat = arg[0]
    _, data = panggil_node(alamat, "chain")
    terakhir = Block.from_dict(data["chain"][-1])
    target = "0" * data["difficulty"]

    tx = Dompet("F55125999").buat_transaksi("Paslon 1")
    block = Block(terakhir.index + 1, [tx], terakhir.hash, nonce=1)
    while block.hash.startswith(target):
        block.nonce += 1
        block.hash = block.hitung_hash()

    kode, hasil = panggil_node(alamat, "block", block.to_dict())
    if kode == 200:
        print("Block palsu DITERIMA -- validasi node bermasalah.")
        return
    print(f"Block palsu DITOLAK oleh node. Status HTTP: {kode}")
    print(f"Alasan: {hasil.get('error')}")


def pilih_node_interaktif():
    global DISCOVERED_NODES
    print("Menunggu discovery node selama 6 detik...")
    time.sleep(6)
    nodes = sorted(DISCOVERED_NODES)
    if nodes:
        print("Node ditemukan:")
        for i, n in enumerate(nodes, 1):
            print(f"  {i}. {n}")
        print("  0. Input manual")
        pilihan = input("Pilih: ").strip()
        if pilihan.isdigit() and 1 <= int(pilihan) <= len(nodes):
            return nodes[int(pilihan) - 1]
    alamat = input("Alamat node (host:port): ").strip()
    return alamat or None


def menu_interaktif():
    stop_event = threading.Event()
    threading.Thread(target=discovery_listener, args=(stop_event,), daemon=True).start()

    target_node = None
    dompet = None

    try:
        while True:
            print("\n=== Client Voting Presma (Interaktif) ===")
            print(f"Node target : {target_node or '(belum dipilih)'}")
            print(f"Pemilih     : {dompet.nim if dompet else '(belum dipilih)'}")
            print("1. Pilih/refresh node (auto-discover)")
            print("2. Pilih/ganti pemilih (NIM)")
            print("3. Lihat identitas")
            print("4. Kirim vote")
            print("5. Uji vote_ubah (signature)")
            print("6. Lihat pool")
            print("7. Mine")
            print("8. Lihat chain")
            print("9. Validate")
            print("10. Tally")
            print("11. Tamper (demo)")
            print("12. Add peer")
            print("13. Resolve")
            print("14. Uji block palsu")
            print("0. Keluar")
            pilihan = input("Pilih: ").strip()

            if pilihan == "0":
                break
            if pilihan == "1":
                target_node = pilih_node_interaktif()
                continue
            if pilihan == "2":
                nim = input("NIM: ").strip()
                if nim:
                    dompet = Dompet(nim)
                    dompet.tampilkan_identitas()
                continue

            if not target_node:
                print("Pilih node terlebih dahulu (menu 1).")
                continue

            if pilihan == "3":
                if dompet:
                    dompet.tampilkan_identitas()
                else:
                    print("Pilih pemilih terlebih dahulu (menu 2).")
            elif pilihan == "4":
                if not dompet:
                    print("Pilih pemilih terlebih dahulu (menu 2).")
                    continue
                # ambil daftar paslon dari node
                _, data = panggil_node(target_node, "paslon")
                paslons = [p for p in (data.get("paslon", []) if isinstance(data, dict) else []) if p.get("aktif", True)]
                if not paslons:
                    print("Belum ada paslon aktif. Tambahkan via web terlebih dahulu.")
                    continue
                print("Daftar paslon:")
                for p in paslons:
                    print(f"  {p.get('nomor')}. {p.get('nama')} (block {p.get('block_number')})")
                nomor = input("Nomor paslon: ").strip()
                if not nomor:
                    continue
                try:
                    nomor_int = int(nomor)
                except ValueError:
                    print("Nomor harus angka.")
                    continue
                if not any(p.get("nomor") == nomor_int for p in paslons):
                    print("Nomor paslon tidak ditemukan.")
                    continue
                tx = dompet.buat_transaksi(nomor_int)
                print(f"Transaksi dibuat dan ditandatangani: {tx.voter_id} -> paslon {tx.kandidat}")
                print(f"  Signature: {tx.signature[:32]}...")
                kirim_transaksi(target_node, tx)
            elif pilihan == "5":
                if not dompet:
                    print("Pilih pemilih terlebih dahulu (menu 2).")
                    continue
                asli = input("Kandidat asli: ").strip()
                diubah = input("Kandidat diubah: ").strip()
                if asli and diubah:
                    perintah_vote_ubah([target_node, asli, diubah, dompet.nim])
            elif pilihan == "6":
                perintah_pool([target_node])
            elif pilihan == "7":
                perintah_mine([target_node])
            elif pilihan == "8":
                perintah_chain([target_node])
            elif pilihan == "9":
                perintah_validate([target_node])
            elif pilihan == "10":
                perintah_tally([target_node])
            elif pilihan == "11":
                idx = input("Index block: ").strip()
                if idx:
                    perintah_tamper([target_node, idx])
            elif pilihan == "12":
                peer = input("Alamat peer (host:port): ").strip()
                if peer:
                    perintah_add_peer([target_node, peer])
            elif pilihan == "13":
                perintah_resolve([target_node])
            elif pilihan == "14":
                perintah_palsu([target_node])
            else:
                print("Pilihan tidak valid.")
    finally:
        stop_event.set()


PERINTAH = {
    "identitas": perintah_identitas,
    "vote": perintah_vote,
    "vote_ubah": perintah_vote_ubah,
    "pool": perintah_pool,
    "mine": perintah_mine,
    "chain": perintah_chain,
    "validate": perintah_validate,
    "tally": perintah_tally,
    "tamper": perintah_tamper,
    "add_peer": perintah_add_peer,
    "resolve": perintah_resolve,
    "palsu": perintah_palsu,
}


def main():
    if len(sys.argv) == 1:
        menu_interaktif()
        return
    if len(sys.argv) < 3 or sys.argv[1] not in PERINTAH:
        print(BANTUAN)
        return
    PERINTAH[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as e:
        print(f"Tidak dapat terhubung ke node ({e.reason}). Pastikan node sudah berjalan.")
    except IndexError:
        print("Argumen kurang.\n")
        print(BANTUAN)
