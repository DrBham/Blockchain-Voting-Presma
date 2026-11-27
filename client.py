# Client voting UNTAD: identitas pemilih (dompet), tanda tangan transaksi, dan
# komunikasi dengan node. Private key disimpan lokal dan tidak dikirim ke node.
# Menu dan perintah CLI ada di menu_client.py.

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from contract import enkripsi_pilihan
from node import POLA_NIM, Block, Transaksi, alamat_dari_pem

BATAS_WAKTU_NODE = 300  # mining difficulty tinggi bisa > 1 menit
NODE_DISCOVERY_PORT = 9999
DISCOVERED_NODES = set()


class Dompet:
    def __init__(self, nim, password):
        """password (bytes) mengenkripsi private key di berkas dompet. Salah password -> ValueError."""
        self.nim = nim.upper().strip()
        # NIM dipakai sebagai nama berkas: tolak karakter seperti "../" sebelum menyentuh disk.
        if not POLA_NIM.fullmatch(self.nim):
            raise ValueError(f"NIM '{nim}' tidak valid (1 huruf + 7-8 digit)")
        if not password:
            raise ValueError("password dompet tidak boleh kosong")
        self.berkas = Path(f"dompet_{self.nim}.pem")

        if self.berkas.exists():
            try:
                self.private_key = serialization.load_pem_private_key(
                    self.berkas.read_bytes(), password=password
                )
            except (ValueError, TypeError):  # TypeError: berkas lama tanpa enkripsi
                raise ValueError(f"password dompet salah atau '{self.berkas}' bukan dompet terenkripsi")
            self.baru = False
        else:
            self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self.berkas.write_bytes(
                self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(password),
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

    # [CHECKPOINT 2] Transaksi dibuat dan ditandatangani dengan private key lokal.
    # Pilihan dienkripsi dulu dengan kunci pemilu, jadi chain tidak menyimpan pilihan polos.
    def buat_transaksi(self, nomor, kunci_pemilu_pem):
        sandi = enkripsi_pilihan(nomor, kunci_pemilu_pem)
        tx = Transaksi(self.nim, None, self.public_key_pem, tipe="VOTE", payload={"sandi": sandi})
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


# [CHECKPOINT 3] Node memverifikasi transaksi: diterima ke pool, atau ditolak beserta alasannya
def kirim_transaksi(alamat, tx):
    """Mengembalikan (kode_http, isi_json) dari node."""
    return panggil_node(alamat, "transaksi", tx.to_dict())


# [CHECKPOINT 11] Block tanpa proof of work valid -> harus ditolak node
def kirim_block_palsu(alamat):
    """Bentuk block yang hash-nya sengaja tidak memenuhi difficulty, kirim ke node.
    Mengembalikan (kode_http, isi_json)."""
    _, data = panggil_node(alamat, "chain")
    terakhir = Block.from_dict(data["chain"][-1])
    target = "0" * data["difficulty"]

    # Kunci sekali pakai: block ini ditolak karena PoW, isi transaksinya tidak penting.
    kunci = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = kunci.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    tx = Transaksi("F55125999", None, pem.decode(), tipe="VOTE", payload={"sandi": "0" * 512})
    tx.tanda_tangani(kunci)
    block = Block(terakhir.index + 1, [tx], terakhir.hash, nonce=1)
    while block.hash.startswith(target):
        block.nonce += 1
        block.hash = block.hitung_hash()
    return panggil_node(alamat, "block", block.to_dict())
