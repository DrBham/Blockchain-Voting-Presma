# Seed demo: siapkan chain sampai status persiapan siap dibuka, supaya demo tidak mengulang langkah persiapan.
#   python seed_demo.py <host:port>
# Langkah: kunci pemilu -> deploy contract -> Paslon 1 dan 2 -> REGISTER beberapa NIM contoh untuk CLI
# (dompet CLI dompet_<NIM>.pem, password demo123) -> tambang. Pemungutan sengaja TIDAK dibuka.

import os
import sys
from pathlib import Path

from client import Dompet, kirim_transaksi, panggil_node
from contract import deploy_contract
from node import Transaksi
from web.config import ADMIN_WALLET_PATH, CONTRACT_NAME, KUNCI_PEMILU_PATH
from web.wallet import muat_atau_buat_admin, muat_atau_buat_kunci_pemilu

PASSWORD_DEMO = b"demo123"
# Kasus nyata Pemira UNTAD: hanya nomor urut, tanpa nama kandidat.
PASLON_DEMO = ((1, "Paslon 1", ""), (2, "Paslon 2", ""))
# NIM contoh untuk demo CLI (angkatan 19). Semua mahasiswa aktif lain bisa mendaftar sendiri lewat web.
NIM_CLI = ("A12119001", "A12119002", "C30119001", "C30119002", "F55119001", "F55119002")


def kirim(node, admin, tipe, payload, label):
    tx = Transaksi("admin", None, admin[1], tipe=tipe, payload=payload)
    tx.tanda_tangani(admin[0])
    kode, hasil = kirim_transaksi(node, tx)
    print(f"  {label}: {'diterima' if kode == 201 else 'DITOLAK (' + str(hasil.get('error')) + ')'}")
    return kode == 201


def main():
    if len(sys.argv) != 2:
        print("Penggunaan: python seed_demo.py <host:port>")
        sys.exit(1)
    node = sys.argv[1]
    os.chdir(Path(__file__).resolve().parent)  # dompet_<NIM>.pem ditulis di folder proyek, sama seperti CLI

    admin = muat_atau_buat_admin(ADMIN_WALLET_PATH)
    _, kunci_pemilu = muat_atau_buat_kunci_pemilu(KUNCI_PEMILU_PATH)
    print(f"Kunci pemilu: {KUNCI_PEMILU_PATH} (privat, simpan offline)")

    _, status = panggil_node(node, "status")
    if status["kontrak"] is None:
        alamat = deploy_contract(CONTRACT_NAME)
        kirim(node, admin, "CONTRACT_DEPLOY",
              {"contract_address": alamat, "nama": CONTRACT_NAME, "kunci_pemilu": kunci_pemilu}, "deploy contract")
    else:
        alamat = status["kontrak"]
        print(f"  contract sudah ada di {alamat}")
        if status["kunci_pemilu"] != kunci_pemilu:
            print("  PERINGATAN: kunci pemilu di chain bukan pasangan kunci_pemilu.pem lokal; rekap tidak bisa dibuka")

    if status["status"] == "persiapan":
        _, data = panggil_node(node, "paslon")
        aktif = {p["nomor"] for p in data["paslon"] if p["aktif"]}
        for nomor, nama, visi in PASLON_DEMO:
            if nomor not in aktif:
                kirim(node, admin, "CONTRACT_CALL", {"contract_address": alamat, "fungsi": "tambah_paslon",
                                                     "args": {"nomor": nomor, "nama": nama, "visi": visi}},
                      f"tambah paslon {nomor}")
    else:
        print(f"  status {status['status']}: paslon tidak diubah")

    for nim in NIM_CLI:
        _, info = panggil_node(node, f"pemilih/{nim}")
        if info["terdaftar"]:
            continue
        try:
            dompet = Dompet(nim, PASSWORD_DEMO)
        except ValueError as e:
            print(f"  {nim} dilewati: {e}")
            continue
        kirim(node, admin, "REGISTER", {"nim": nim, "public_key": dompet.public_key_pem}, f"REGISTER {nim}")

    kode, hasil = panggil_node(node, "mine", {})
    print(f"Tambang: {'block ' + str(hasil['block']['index']) if kode == 201 else hasil.get('error')}")
    _, status = panggil_node(node, "status")
    print(f"Status {status['status']} | terdaftar {status['terdaftar']} | panjang chain {status['panjang']}")
    print(f"Dompet CLI NIM contoh memakai password '{PASSWORD_DEMO.decode()}'. Buka pemungutan dari web panitia.")


if __name__ == "__main__":
    main()
