# Menu interaktif dan perintah CLI untuk client voting UNTAD.
# Logika blockchain (dompet, transaksi, komunikasi node) ada di client.py.
#   python menu_client.py                 -> menu angka
#   python menu_client.py <perintah> ...  -> satu perintah langsung

import getpass
import sys
import threading
import time
import urllib.error

import client
from client import Dompet, discovery_listener, kirim_block_palsu, kirim_transaksi, panggil_node
from contract import enkripsi_pilihan
from node import Transaksi


def buka_dompet(nim):
    """Dompet terenkripsi password; password ditanya tanpa ditampilkan di layar."""
    return Dompet(nim, getpass.getpass(f"Password dompet {nim.upper().strip()}: ").encode("utf-8"))


def kunci_pemilu(alamat):
    """Kunci publik pemilu dari node (GET /status). ValueError kalau contract belum dideploy."""
    _, status = panggil_node(alamat, "status")
    if not status.get("kunci_pemilu"):
        raise ValueError("contract/kunci pemilu belum dideploy di node (jalankan seed_demo.py)")
    print(f"Status pemilu: {status['status']}")
    return status["kunci_pemilu"]


def kirim_vote(alamat, dompet, nomor):
    tx = dompet.buat_transaksi(nomor, kunci_pemilu(alamat))
    print(f"Transaksi dibuat dan ditandatangani: {tx.voter_id} -> pilihan terenkripsi")
    print(f"  Sandi    : {tx.payload['sandi'][:32]}...")
    print(f"  Signature: {tx.signature[:32]}...")
    tampilkan_kirim(alamat, tx)


def isi_tx(t):
    return Transaksi.from_dict(t).ringkas()


def ringkas(chain):
    for b in chain:
        print(f"  Block {b['index']} | nonce: {str(b['nonce']).ljust(8)} "
              f"| prev: {b['previous_hash'][:12]}... | hash: {b['hash'][:12]}... "
              f"| {len(b['transaksi'])} transaksi")
        for t in b["transaksi"]:
            print(f"      - {t['voter_id']}: {isi_tx(t)} | sig {t['signature'][:16]}...")



# [CHECKPOINT 1] Pembuatan identitas: alamat/public key (dipotong) tercetak,
# beserta keterangan private key disimpan lokal
def tampilkan_identitas(dompet):
    isi_kunci = "".join(dompet.public_key_pem.strip().splitlines()[1:-1])
    status = "dibuat" if dompet.baru else "dipakai kembali"
    print(f"Identitas voter {dompet.nim} ({status})")
    print(f"  Alamat     : {dompet.alamat()}")
    print(f"  Public key : {isi_kunci[:40]}...")
    print(f"  Private key: disimpan lokal di '{dompet.berkas}' (tidak dikirim ke node)")


# [CHECKPOINT 3] Hasil verifikasi dari node: diterima ke pool, atau ditolak beserta alasannya
# [CHECKPOINT 4] Jumlah transaksi pending di pool ikut tercetak
def tampilkan_kirim(alamat, tx):
    kode, hasil = kirim_transaksi(alamat, tx)
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
  tamper <node> <index>                         DEMO: ubah isi block lama
  add_peer <node> <peer>                        hubungkan dua node (dua arah)
  resolve <node>                                longest-chain rule
  palsu <node>                                  kirim block tanpa PoW valid (harus ditolak)"""


def perintah_identitas(arg):
    tampilkan_identitas(buka_dompet(arg[0]))


def perintah_vote(arg):
    if len(arg) < 3:
        print("Penggunaan: vote <node> <nomor_paslon> <NIM>")
        return
    dompet = buka_dompet(arg[2])
    tampilkan_identitas(dompet)
    kirim_vote(arg[0], dompet, int(arg[1]))


# [CHECKPOINT 3] Transaksi diubah SETELAH ditandatangani -> harus ditolak node
def perintah_vote_ubah(arg):
    alamat, asli, diubah, nim = arg[:4]
    perintah_vote_ubah_dompet(alamat, int(asli), int(diubah), buka_dompet(nim))


def perintah_vote_ubah_dompet(alamat, asli, diubah, dompet):
    kunci = kunci_pemilu(alamat)
    tx = dompet.buat_transaksi(asli, kunci)
    print(f"Transaksi ditandatangani untuk paslon {asli}, lalu sandinya diganti menjadi pilihan {diubah}")
    tx.payload = {"sandi": enkripsi_pilihan(diubah, kunci)}
    tampilkan_kirim(alamat, tx)


# [CHECKPOINT 4] Status pool
def perintah_pool(arg):
    alamat = arg[0]
    _, hasil = panggil_node(alamat, "pool")
    print(f"Transaksi pending di {alamat}: {hasil['jumlah']}")
    for tx in hasil["transaksi"]:
        print(f"  - {tx['voter_id']}: {isi_tx(tx)} | sig {tx['signature'][:16]}...")


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
    print(f"Status pemilu    : {hasil['status']}")
    print(f"Total Suara Masuk: {hasil['suara_masuk']}")
    if hasil["hasil"] is None:
        print("Perolehan per paslon masih rahasia: suara terenkripsi sampai kunci pemilu dibuka (status dihitung).")
        return
    _, paslon_data = panggil_node(alamat, "paslon")
    nama_map = {str(p.get("nomor")): p.get("nama") for p in paslon_data.get("paslon", []) if p.get("aktif")}
    print("Hasil Rekapitulasi Suara:")
    for nomor, jumlah in hasil["hasil"].items():
        print(f"  - {nama_map.get(nomor, nomor)} (nomor {nomor}): {jumlah} suara")
    print(f"  - Tidak sah: {hasil['tidak_sah']} suara")


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
    kode, hasil = kirim_block_palsu(arg[0])
    if kode == 200:
        print("Block palsu DITERIMA -- validasi node bermasalah.")
        return
    print(f"Block palsu DITOLAK oleh node. Status HTTP: {kode}")
    print(f"Alasan: {hasil.get('error')}")


def pilih_node_interaktif():
    print("Menunggu discovery node selama 6 detik...")
    time.sleep(6)
    nodes = sorted(client.DISCOVERED_NODES)
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
            try:
                if pilihan == "0":
                    break
                if pilihan == "1":
                    target_node = pilih_node_interaktif()
                    continue
                if pilihan == "2":
                    nim = input("NIM: ").strip()
                    if nim:
                        dompet = buka_dompet(nim)
                        tampilkan_identitas(dompet)
                    continue

                if not target_node:
                    print("Pilih node terlebih dahulu (menu 1).")
                    continue

                if pilihan == "3":
                    if dompet:
                        tampilkan_identitas(dompet)
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
                    kirim_vote(target_node, dompet, nomor_int)
                elif pilihan == "5":
                    if not dompet:
                        print("Pilih pemilih terlebih dahulu (menu 2).")
                        continue
                    asli = input("Kandidat asli: ").strip()
                    diubah = input("Kandidat diubah: ").strip()
                    if asli and diubah:
                        perintah_vote_ubah_dompet(target_node, int(asli), int(diubah), dompet)
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
            except (OSError, ValueError, KeyError) as e:  # URLError/timeout termasuk OSError
                print(f"Gagal: {getattr(e, 'reason', e)}")
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
    except ValueError as e:
        print(f"Input tidak valid: {e}")
    except IndexError:
        print("Argumen kurang.\n")
        print(BANTUAN)
