# Node voting blockchain terdistribusi Universitas Tadulako.

import hashlib
import json
import re
import socket
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from contract import jalankan_contract, state_paslon_dari_chain

PORT = 0
IFACE_IP = "127.0.0.1"

ANGKATAN_VALID = {"23", "24", "25"}  # Angkatan 2023 (Sem 7), 2024 (Sem 5), 2025 (Sem 3)
FAKULTAS_UNTAD = {"A", "B", "C", "D", "E", "F", "G", "K", "L", "N", "P"}
POLA_NIM = re.compile(r"[A-Z]\d{7,8}")
POLA_ALAMAT_CONTRACT = re.compile(r"[0-9a-f]{40}")
POLA_PEER = re.compile(r"[A-Za-z0-9.-]+:\d{1,5}")

BATAS_WAKTU_JARINGAN = 5
BATAS_ISI_PERMINTAAN = 5 * 1024 * 1024  # byte; mencegah body raksasa menghabiskan memori
MAKS_PEER = 32
DISCOVERY_PORT = 9999
JEDA_RESOLVE_LATAR = 30


def log(pesan):
    """Cetak pesan ke console node dengan awalan [port]."""
    print(f"[{PORT}] {pesan}", flush=True)


def validasi_nim_untad(nim):
    """
    Format NIM UNTAD: [Kode Fakultas][3 Digit Prodi][2 Digit Tahun][3 Digit No Urut]
    Contoh: F55125001 -> Fakultas 'F', Angkatan '25'
    """
    nim = nim.upper().strip()
    if len(nim) < 8:
        return False, "Format NIM terlalu pendek!"

    kode_fakultas = nim[0]
    if kode_fakultas not in FAKULTAS_UNTAD:
        return False, f"Kode Fakultas '{kode_fakultas}' tidak terdaftar di UNTAD!"

    angkatan = nim[4:6] if len(nim) >= 9 else nim[1:3]
    if angkatan not in ANGKATAN_VALID:
        return False, f"Angkatan '20{angkatan}' tidak memenuhi syarat (Hanya Semester 3-7 / Angkatan 2023-2025)!"

    return True, "Valid"


# ---------------------------------------------------------------- jaringan lokal

def deteksi_ip_non_loopback():
    """Kembalikan daftar IPv4 non-loopback yang dimiliki mesin (diurutkan prioritas hotspot/LAN)."""
    ips = set()
    try:
        ips.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None))
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except socket.gaierror:
        pass
    ips = {ip for ip in ips if "." in ip and not ip.startswith(("127.", "169.254."))}

    def prioritas(ip):
        if ip.startswith("192.168.137."):
            return 0
        if ip.startswith("192.168."):
            return 1
        if ip.startswith("10."):
            return 2
        bagian = ip.split(".")
        if bagian[0] == "172" and bagian[1].isdigit() and 16 <= int(bagian[1]) <= 31:
            return 3
        return 4

    return sorted(ips, key=prioritas)


def ip_milik_sendiri():
    """Semua alamat yang menunjuk ke mesin ini."""
    return set(deteksi_ip_non_loopback()) | {"127.0.0.1", "localhost", "::1", IFACE_IP}


def deteksi_ip_utama(otomatis=False):
    """Pilih IP interface utama. Prompt jika >1 dan tidak otomatis."""
    ips = deteksi_ip_non_loopback()
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


def cari_port_kosong(mulai=5001, maks_percobaan=100):
    """Cari port TCP kosong mulai dari `mulai`. Kembalikan None jika tidak ada."""
    for port in range(mulai, mulai + maks_percobaan):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                continue  # ada yang mendengarkan: port terpakai
        except OSError:
            pass
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return None


def peer_valid(peer):
    """Peer harus berbentuk host:port, agar node tidak dipakai mengirim request ke URL sembarang."""
    if not isinstance(peer, str) or not POLA_PEER.fullmatch(peer):
        return False
    return 0 < int(peer.rpartition(":")[2]) < 65536


def proses_beacon(data, addr, node):
    """Proses satu beacon discovery. Kembalikan peer string jika peer dikenal/ditambah, else None."""
    if not isinstance(data, dict) or data.get("type") != "presma-node":
        return None
    try:
        http_port = int(data["http_port"])
        difficulty = int(data["difficulty"])
        genesis = str(data["genesis"])
    except (KeyError, ValueError, TypeError):
        return None
    if difficulty != node.blockchain.difficulty or genesis != node.blockchain.chain[0].hash:
        return None
    host = addr[0]
    if http_port == node.port and host in ip_milik_sendiri():
        return None
    peer = f"{host}:{http_port}"
    if peer in node.peers or node.peer_duplikat(peer):
        return peer
    if not node.tambah_peer(peer, timbal_balik=False):
        return None
    node.jadwalkan_resolve()
    log(f"discovery: peer baru {peer}")
    return peer


# ---------------------------------------------------------------- kriptografi

def alamat_dari_pem(public_key_pem):
    """Alamat pengirim = potongan hash SHA-256 dari public key."""
    return hashlib.sha256(public_key_pem.encode()).hexdigest()[:40]


def _padding_pss():
    return padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)


def _ke_json_bytes(data):
    """Serialisasi JSON yang konsisten untuk hashing, signing, dan jaringan."""
    return json.dumps(data, sort_keys=True).encode("utf-8")


# [FITUR WAJIB: Transaksi bertanda tangan] ditandatangani private key pengirim,
# diverifikasi node sebelum diterima.
class Transaksi:
    def __init__(self, voter_id, kandidat, public_key, timestamp=None, signature="", tipe="VOTE", payload=None):
        self.voter_id = voter_id
        self.kandidat = kandidat
        self.public_key = public_key
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.signature = signature
        self.tipe = tipe or "VOTE"
        if payload is None:
            payload = {"kandidat": kandidat} if self.tipe == "VOTE" else {}
        self.payload = payload

    def pesan(self):
        """Isi yang ditandatangani. Kalau salah satu isinya diubah, signature jadi tidak cocok."""
        return _ke_json_bytes({
            "tipe": self.tipe,
            "payload": self.payload,
            "voter_id": self.voter_id,
            "kandidat": self.kandidat,
            "timestamp": self.timestamp,
        })

    # [CHECKPOINT 2] Transaksi ditandatangani dengan private key pengirim (dipanggil dari client.py)
    def tanda_tangani(self, private_key):
        """Dipanggil di sisi client (private key tidak pernah dikirim ke node)."""
        self.signature = private_key.sign(self.pesan(), _padding_pss(), hashes.SHA256()).hex()

    # [CHECKPOINT 3] Node memverifikasi signature saat transaksi masuk
    def verifikasi(self):
        """Dipanggil node: benarkah signature dibuat oleh pemilik public key ini?"""
        try:
            kunci = serialization.load_pem_public_key(self.public_key.encode())
            kunci.verify(bytes.fromhex(self.signature), self.pesan(), _padding_pss(), hashes.SHA256())
            return True
        except (InvalidSignature, ValueError, TypeError, AttributeError):
            return False

    def alamat(self):
        return alamat_dari_pem(self.public_key)

    def ringkas(self):
        """Deskripsi singkat isi transaksi untuk log console."""
        payload = self.payload if isinstance(self.payload, dict) else {}
        if self.tipe == "CONTRACT_DEPLOY":
            return f"DEPLOY {payload.get('nama')} @ {payload.get('contract_address')}"
        if self.tipe == "CONTRACT_CALL":
            alamat = str(payload.get("contract_address", ""))
            return f"{payload.get('fungsi')}({json.dumps(payload.get('args', {}))}) @ {alamat[:12]}..."
        return f"vote paslon {self.kandidat}"

    def to_dict(self):
        return {
            "tipe": self.tipe,
            "payload": self.payload,
            "voter_id": self.voter_id,
            "kandidat": self.kandidat,
            "timestamp": self.timestamp,
            "public_key": self.public_key,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d):
        """Melempar KeyError/TypeError kalau format tidak lengkap atau tipe datanya salah."""
        if not all(isinstance(d.get(k), str) for k in ("voter_id", "public_key", "signature")):
            raise TypeError("voter_id, public_key, dan signature harus berupa teks")
        if not isinstance(d.get("tipe", "VOTE"), str):
            raise TypeError("tipe transaksi harus berupa teks")
        return cls(
            voter_id=d["voter_id"],
            kandidat=d.get("kandidat"),
            public_key=d["public_key"],
            timestamp=d.get("timestamp"),
            signature=d["signature"],
            tipe=d.get("tipe", "VOTE"),
            payload=d.get("payload"),
        )


# [CHECKPOINT 3] Aturan penerimaan transaksi. Transaksi yang isinya diubah setelah
# ditandatangani GAGAL di sini dan ditolak dengan alasan yang dikembalikan.
class KonteksRantai:
    """Keadaan hasil menjalankan rantai: pemilih, state paslon, contract aktif, signature tercatat.
    Satu aturan yang sama dipakai di pool, di block baru, dan saat memvalidasi seluruh rantai."""

    def __init__(self):
        self.signature = set()  # signature yang sudah tercatat: mencegah transaksi lama dikirim ulang
        self.pemilih = set()
        self.paslon = []
        self.kontrak = None     # alamat contract aktif = deploy pertama di rantai
        self.pemilik = None     # public key yang mendeploy contract

    def salin(self):
        baru = KonteksRantai()
        baru.signature = set(self.signature)
        baru.pemilih = set(self.pemilih)
        baru.paslon = [dict(p) for p in self.paslon]
        baru.kontrak, baru.pemilik = self.kontrak, self.pemilik
        return baru

    def terapkan(self, tx):
        """Validasi tx; kalau sah, konteks diperbarui. Mengembalikan (ok, alasan)."""
        if not tx.verifikasi():
            return False, "signature tidak cocok (isi transaksi diubah setelah ditandatangani atau kunci salah)"
        if tx.signature in self.signature:
            return False, "transaksi ini sudah pernah tercatat (replay ditolak)"
        aturan = {
            "VOTE": self._vote,
            "CONTRACT_DEPLOY": self._deploy,
            "CONTRACT_CALL": self._panggil_contract,
        }.get(tx.tipe)
        if aturan is None:
            return False, f"tipe transaksi '{tx.tipe}' tidak dikenal"
        ok, alasan = aturan(tx)
        if ok:
            self.signature.add(tx.signature)
        return ok, alasan

    def _vote(self, tx):
        nim = tx.voter_id
        if not POLA_NIM.fullmatch(nim):
            return False, f"NIM '{nim}' harus 1 huruf kapital + 7-8 digit, tanpa spasi"
        nim_valid, pesan_err = validasi_nim_untad(nim)
        if not nim_valid:
            return False, f"NIM '{nim}' ditolak: {pesan_err}"
        if isinstance(tx.kandidat, bool) or not isinstance(tx.kandidat, int):
            return False, "nomor paslon harus berupa angka bulat"
        if not any(p["nomor"] == tx.kandidat and p["aktif"] for p in self.paslon):
            return False, f"Paslon '{tx.kandidat}' tidak ditemukan atau tidak aktif"
        if nim in self.pemilih:
            return False, f"NIM '{nim}' sudah menggunakan hak pilihnya!"
        self.pemilih.add(nim)
        return True, "valid"

    def _deploy(self, tx):
        payload = tx.payload if isinstance(tx.payload, dict) else {}
        alamat, nama = payload.get("contract_address"), payload.get("nama")
        if self.kontrak is not None:
            return False, f"contract sudah dideploy di alamat {self.kontrak}"
        if not isinstance(alamat, str) or not POLA_ALAMAT_CONTRACT.fullmatch(alamat):
            return False, "alamat contract harus 40 karakter hex"
        if not isinstance(nama, str) or not nama.strip():
            return False, "nama contract wajib diisi"
        self.kontrak, self.pemilik = alamat, tx.public_key
        return True, "valid"

    def _panggil_contract(self, tx):
        payload = tx.payload if isinstance(tx.payload, dict) else {}
        if self.kontrak is None:
            return False, "contract belum dideploy di chain"
        if payload.get("contract_address") != self.kontrak:
            return False, f"alamat contract salah, contract aktif: {self.kontrak}"
        if tx.public_key != self.pemilik:
            return False, "hanya pemilik contract (pendeploy) yang boleh mengubah state"
        ok, alasan, state = jalankan_contract(self.paslon, payload.get("fungsi"), payload.get("args", {}))
        if ok:
            self.paslon = state
        return ok, alasan


# [FITUR WAJIB: Struktur block] index, timestamp, daftar transaksi, previous hash, nonce, hash
class Block:
    def __init__(self, index, transaksi, previous_hash, timestamp=None, nonce=0, hash_nilai=None):
        self.index = index
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.transaksi = transaksi
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = hash_nilai if hash_nilai is not None else self.hitung_hash()

    def hitung_hash(self):
        data = {
            "index": self.index,
            "timestamp": self.timestamp,
            "transaksi": [t.to_dict() for t in self.transaksi],
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
        }
        return hashlib.sha256(_ke_json_bytes(data)).hexdigest()

    # [FITUR WAJIB: Proof of Work] nonce dicari terhadap difficulty, disimpan sebagai atribut block
    # [CHECKPOINT 6] Mengembalikan jumlah percobaan dan lama waktu untuk dicetak di tambang_pool()
    def tambang(self, difficulty, berhenti=None):
        """Proof of Work: naikkan nonce sampai hash diawali nol sebanyak difficulty.
        berhenti() dicek berkala; kalau True, penambangan dibatalkan dan mengembalikan None.
        Mengembalikan (jumlah percobaan, lama detik)."""
        target = "0" * difficulty
        mulai = time.time()
        self.nonce = 0
        self.hash = self.hitung_hash()
        while not self.hash.startswith(target):
            self.nonce += 1
            if berhenti and self.nonce % 2000 == 0 and berhenti():
                return None
            self.hash = self.hitung_hash()
        return self.nonce + 1, time.time() - mulai

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transaksi": [t.to_dict() for t in self.transaksi],
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d.get("transaksi"), list):
            raise TypeError("transaksi block harus berupa list")
        return cls(
            index=d["index"],
            transaksi=[Transaksi.from_dict(t) for t in d["transaksi"]],
            previous_hash=d["previous_hash"],
            timestamp=d["timestamp"],
            nonce=d["nonce"],
            hash_nilai=d["hash"],
        )


def buat_genesis():
    # Timestamp dibuat tetap (0) supaya genesis SAMA di semua node.
    return Block(index=0, transaksi=[], previous_hash="0", timestamp=0)


GENESIS_HASH = buat_genesis().hash


# [CHECKPOINT 11] Block tanpa proof of work valid ditolak di sini (alasan dikembalikan).
# [CHECKPOINT 9] Pemeriksaan hash/previous hash di sini juga yang mendeteksi data block yang diubah.
def validasi_block(block, induk, difficulty, konteks):
    """Periksa satu block terhadap block sebelumnya dan konteks rantai sampai block itu.
    Mengembalikan (ok, alasan, konteks_setelah_block). Konteks masukan tidak diubah."""
    if isinstance(block.index, bool) or block.index != induk.index + 1:
        if isinstance(block.index, int) and block.index > induk.index + 1:
            return False, f"index {block.index} melompat, node ini tertinggal (jalankan resolve)", None
        return False, f"index {block.index} tidak sesuai, seharusnya {induk.index + 1}", None
    if block.previous_hash != induk.hash:
        return False, "previous hash tidak cocok dengan hash block sebelumnya", None
    if block.hash != block.hitung_hash():
        return False, "hash tidak cocok dengan isi block (data berubah)", None
    target_hash = "0" * difficulty
    if not block.hash.startswith(target_hash):
        return False, f"proof of work tidak valid (hash tidak diawali {target_hash})", None
    if not block.transaksi:
        return False, "block tidak berisi transaksi", None

    konteks = konteks.salin()
    for tx in block.transaksi:
        ok, alasan = konteks.terapkan(tx)
        if not ok:
            return False, alasan, None
    return True, "valid", konteks


# [FITUR WAJIB: Validasi chain]
# [CHECKPOINT 8] Rantai normal -> (True, None, ...)
# [CHECKPOINT 9] Rantai dimanipulasi -> (False, index block pertama yang rusak, alasan)
def validasi_rantai(chain, difficulty):
    """Periksa seluruh rantai. Mengembalikan (ok, index_block_pertama_yang_rusak, alasan, konteks)."""
    if not chain or chain[0].hash != GENESIS_HASH or chain[0].hitung_hash() != GENESIS_HASH:
        return False, 0, "genesis block tidak sah", None

    konteks = KonteksRantai()
    for i in range(1, len(chain)):
        ok, alasan, konteks = validasi_block(chain[i], chain[i - 1], difficulty, konteks)
        if not ok:
            return False, i, alasan, None
    return True, None, "rantai valid", konteks


class Blockchain:
    def __init__(self, difficulty=4):
        self.difficulty = difficulty
        self.chain = [buat_genesis()]
        self.konteks = KonteksRantai()       # keadaan setelah block terakhir
        self.pool = []
        self.konteks_pool = KonteksRantai()  # keadaan setelah block terakhir + seluruh isi pool
        self.lock = threading.RLock()
        self.lock_tambang = threading.Lock()  # satu proses mining per node

    def terakhir(self):
        return self.chain[-1]

    def _saring_pool(self):
        """Susun ulang pool di atas rantai terbaru: transaksi yang sudah tercatat
        atau menjadi tidak sah (bentrok dengan block dari peer) dibuang."""
        konteks = self.konteks.salin()
        self.pool = [tx for tx in self.pool if konteks.terapkan(tx)[0]]
        self.konteks_pool = konteks

    def _tambah_block(self, block, konteks):
        self.chain.append(block)
        self.konteks = konteks
        self._saring_pool()

    def ganti_rantai(self, chain, konteks):
        self.chain = chain
        self.konteks = konteks
        self._saring_pool()

    def tambah_transaksi(self, tx):
        """Mengembalikan (ok, pesan, baru). baru=False kalau transaksi ini sudah ada di pool."""
        with self.lock:
            if any(p.signature == tx.signature for p in self.pool):
                return True, "transaksi sudah ada di pool", False

            # [CHECKPOINT 2] Isi transaksi + potongan signature tercetak di console node
            log("=== TRANSAKSI MASUK ===")
            log(f"Pengirim : {tx.voter_id} (alamat {tx.alamat()[:12]}...)")
            log(f"Isi      : {tx.ringkas()}")
            log(f"Signature: {tx.signature[:32]}...")

            # [CHECKPOINT 3] Verifikasi signature + aturan; diperiksa terhadap rantai DAN pool,
            # jadi dua transaksi yang saling bentrok tidak bisa masuk block yang sama.
            ok, alasan = self.konteks_pool.terapkan(tx)
            if not ok:
                log(f"DITOLAK: {alasan}")
                return False, alasan, False
            log("Signature VALID, transaksi sesuai aturan")

            # [CHECKPOINT 4] Status pool: jumlah transaksi pending bertambah setiap transaksi sah masuk
            self.pool.append(tx)
            log(f"Transaksi masuk pool. Transaksi pending sekarang: {len(self.pool)}")
            return True, "transaksi diterima ke pool", True

    def tambang_pool(self):
        """Bentuk block dari isi pool, jalankan PoW, tambahkan ke rantai.
        Mengembalikan (block, None) atau (None, alasan)."""
        if not self.lock_tambang.acquire(blocking=False):
            return None, "node sedang menambang block lain"
        try:
            return self._tambang_pool()
        finally:
            self.lock_tambang.release()

    def _tambang_pool(self):
        with self.lock:
            if not self.pool:
                return None, "pool kosong, tidak ada transaksi untuk ditambang"
            induk, konteks_induk = self.terakhir(), self.konteks
            block = Block(index=induk.index + 1, transaksi=list(self.pool), previous_hash=induk.hash)

            # [CHECKPOINT 5] Block candidate: daftar transaksi dan previous hash yang dipakai
            log("=== BLOCK CANDIDATE ===")
            log(f"Index         : {block.index}")
            log(f"Previous hash : {block.previous_hash[:20]}...")
            log(f"Transaksi ({len(block.transaksi)}):")
            for tx in block.transaksi:
                log(f"   - {tx.voter_id}: {tx.ringkas()} | sig {tx.signature[:16]}...")
            log(f"=== PROOF OF WORK (target: hash diawali {'0' * self.difficulty}) ===")

        # PoW berjalan di luar lock: node tetap bisa menerima transaksi/block dari peer.
        # Kalau peer lebih dulu menemukan block (ujung rantai berubah), mining dibatalkan.
        hasil = block.tambang(self.difficulty, berhenti=lambda: self.terakhir() is not induk)

        with self.lock:
            if hasil is None or self.terakhir() is not induk:
                alasan = (f"block {self.terakhir().index} dari peer diterima lebih dulu; "
                          f"mining block {block.index} dibatalkan")
                log(f"MINING DIBATALKAN: {alasan}. Pool: {len(self.pool)} transaksi")
                return None, alasan
            ok, alasan, konteks = validasi_block(block, induk, self.difficulty, konteks_induk)
            if not ok:
                log(f"MINING GAGAL: block hasil tambang tidak sah ({alasan})")
                return None, alasan

            # [CHECKPOINT 6] Proof of work: jumlah percobaan, nonce, hash hasil, lama penambangan
            percobaan, detik = hasil
            log(f"Percobaan nonce : {percobaan}")
            log(f"Nonce ditemukan : {block.nonce}")
            log(f"Hash hasil      : {block.hash}")
            log(f"Lama menambang  : {detik:.3f} detik")

            # [CHECKPOINT 7] Block diterima rantai: index baru, rantai bertambah panjang, pool dikosongkan
            self._tambah_block(block, konteks)
            log("=== BLOCK DITERIMA RANTAI ===")
            log(f"Index block baru : {block.index}")
            log(f"Panjang rantai   : {len(self.chain)} block")
            sisa = " (kosong)" if not self.pool else " (masuk selama mining)"
            log(f"Pool sekarang    : {len(self.pool)} transaksi{sisa}")
            for tx in block.transaksi:
                if tx.tipe == "CONTRACT_DEPLOY":
                    log(f"CONTRACT DEPLOYED: {tx.payload['nama']} di alamat {tx.payload['contract_address']}")
                elif tx.tipe == "CONTRACT_CALL":
                    log(f"STATE CONTRACT BERUBAH: {tx.ringkas()} tercatat di block {block.index}")
            return block, None

    def terima_block(self, block):
        with self.lock:
            if any(b.hash == block.hash for b in self.chain):
                log(f"block {block.index} sudah ada di rantai (hasil mining yang sama), diabaikan")
                return True, "block sudah ada"
            ok, alasan, konteks = validasi_block(block, self.terakhir(), self.difficulty, self.konteks)
            if not ok:
                # [CHECKPOINT 11] Status penolakan block tidak sah tercetak (409)
                log(f"block {block.index} DITOLAK: {alasan} (status 409)")
                return False, alasan

            self._tambah_block(block, konteks)
            # [CHECKPOINT 10] Log PENERIMAAN di node tujuan
            log(f"block {block.index} DITERIMA dari peer | hash {block.hash[:20]}...")
            log(f"Panjang rantai: {len(self.chain)} | pool: {len(self.pool)} transaksi")
            return True, "block diterima"

    # [CHECKPOINT 8 dan 9] Validasi rantai; hasilnya dicetak (valid, atau index block rusak + alasan)
    def periksa(self):
        with self.lock:
            ok, rusak, alasan, _ = validasi_rantai(self.chain, self.difficulty)
        if ok:
            log(f"VALIDASI RANTAI: rantai valid untuk seluruh {len(self.chain)} block")
        else:
            log(f"VALIDASI RANTAI: TIDAK VALID. Block pertama yang rusak: index {rusak}. Alasan: {alasan}")
        return ok, rusak, alasan

    def rekap(self):
        hasil = {}
        with self.lock:
            for tx in (tx for block in self.chain for tx in block.transaksi if tx.tipe == "VOTE"):
                hasil[tx.kandidat] = hasil.get(tx.kandidat, 0) + 1
        return sum(hasil.values()), hasil

    # [CHECKPOINT 9] Memanipulasi data block lama (khusus demo), hash sengaja TIDAK dihitung ulang
    def ubah_data_demo(self, index):
        """HANYA UNTUK DEMO: mengubah isi transaksi di block lama tanpa menghitung ulang hash."""
        with self.lock:
            if index < 1 or index >= len(self.chain) or not self.chain[index].transaksi:
                return False, "index block tidak ada atau tidak berisi transaksi"
            tx = self.chain[index].transaksi[0]
            lama = tx.ringkas()
            if tx.tipe == "VOTE":
                tx.kandidat = 2 if tx.kandidat == 1 else 1
            else:
                tx.payload = json.loads(json.dumps(tx.payload))  # salinan, lalu diubah
                sasaran = tx.payload.setdefault("args", {}) if tx.tipe == "CONTRACT_CALL" else tx.payload
                sasaran["nama"] = f"{sasaran.get('nama', '')} (DIMANIPULASI)"
            baru = tx.ringkas()
            log(f"DEMO MANIPULASI: block {index}, '{lama}' diubah menjadi '{baru}' (hash tidak dihitung ulang)")
            return True, f"data di block {index} diubah menjadi '{baru}'"


def kirim_json(url, isi):
    permintaan = urllib.request.Request(
        url,
        data=_ke_json_bytes(isi),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(permintaan, timeout=BATAS_WAKTU_JARINGAN) as balasan:
        return json.loads(balasan.read().decode("utf-8"))


def ambil_json(url):
    with urllib.request.urlopen(url, timeout=BATAS_WAKTU_JARINGAN) as balasan:
        return json.loads(balasan.read().decode("utf-8"))


class Node:
    def __init__(self, port, peers, difficulty):
        self.port = port
        self.peers = [p for p in peers if peer_valid(p)]
        self.blockchain = Blockchain(difficulty)
        self._resolve_terakhir = 0
        self.http_server = None

    # [CHECKPOINT 10] Broadcast transaksi antar-node (log pengiriman tercetak)
    def broadcast_transaksi(self, tx):
        isi = tx.to_dict()
        isi["diteruskan"] = True  # penanda agar penerima tidak menyebarkan ulang (hindari putaran tak berujung)
        self._broadcast("transaksi", isi, f"transaksi {tx.voter_id}")

    # [CHECKPOINT 10] Broadcast block antar-node: log PENGIRIMAN di node asal
    def broadcast_block(self, block):
        self._broadcast("block", block.to_dict(), f"block {block.index}")

    def _broadcast(self, endpoint, isi, label):
        """Kirim data ke semua peer; kegagalan satu peer tidak menghentikan peer lain."""
        for peer in list(self.peers):
            try:
                kirim_json(f"http://{peer}/{endpoint}", isi)
                log(f" -> {label} dikirim ke {peer} (diterima)")
            except Exception as e:
                log(f" !! {label} ke {peer} tidak diterima ({e})")

    def peer_duplikat(self, peer):
        """Peer lokal yang sama dengan alamat berbeda (mis. 127.0.0.1:5001 vs 192.168.x:5001 di mesin ini)."""
        host, _, port = peer.rpartition(":")
        lokal = ip_milik_sendiri()
        return host in lokal and any(
            p.rpartition(":")[2] == port and p.rpartition(":")[0] in lokal for p in self.peers
        )

    def tambah_peer(self, peer, timbal_balik=True):
        if not peer_valid(peer) or peer in self.peers or self.peer_duplikat(peer):
            return False
        if len(self.peers) >= MAKS_PEER:
            log(f" !! peer {peer} diabaikan: batas {MAKS_PEER} peer tercapai")
            return False
        self.peers.append(peer)
        log(f"peer baru ditambahkan: {peer}")
        if timbal_balik:
            try:
                kirim_json(f"http://{peer}/peers", {"peer": f"{IFACE_IP}:{self.port}", "timbal_balik": False})
            except Exception as e:
                log(f" !! peer {peer} belum bisa menambahkan node ini ({e})")
        return True

    # [FITUR WAJIB: Longest-chain rule]
    # [CHECKPOINT 10] Sinkronisasi: node yang sempat mati memperoleh rantai terpanjang setelah resolve
    def resolve(self, verbose=True):
        """Longest-chain rule: ambil rantai terpanjang yang VALID dari peer.
        Kalau rantai lokal sendiri rusak, rantai valid dari peer dipakai walau tidak lebih panjang."""
        bc = self.blockchain
        with bc.lock:
            lokal_valid = validasi_rantai(bc.chain, bc.difficulty)[0]
            panjang_lokal = len(bc.chain)
        if not lokal_valid:
            log("RESOLVE: rantai lokal TIDAK VALID, mencari rantai valid dari peer")

        terbaik, batas = None, panjang_lokal if lokal_valid else 0
        for peer in list(self.peers):
            try:
                rantai_peer = [Block.from_dict(b) for b in ambil_json(f"http://{peer}/chain")["chain"]]
            except Exception as e:
                if verbose:
                    log(f" !! gagal mengambil rantai dari {peer} ({e})")
                continue
            ok, rusak, alasan, konteks = validasi_rantai(rantai_peer, bc.difficulty)
            if not ok:
                log(f" !! rantai dari {peer} ditolak (block {rusak}: {alasan})")
                continue
            if verbose:
                log(f" -> {peer} punya rantai {len(rantai_peer)} block (valid)")
            if len(rantai_peer) > batas:
                terbaik, batas = (rantai_peer, konteks), len(rantai_peer)

        with bc.lock:
            # Rantai lokal bisa bertambah selama resolve berjalan; bandingkan ulang di dalam lock.
            if terbaik is None or (lokal_valid and len(terbaik[0]) <= len(bc.chain)):
                if verbose:
                    log(f"RESOLVE: rantai lokal ({len(bc.chain)} block) sudah yang terpanjang")
                return False
            bc.ganti_rantai(*terbaik)
        log(f"RESOLVE: rantai diganti dengan rantai terpanjang ({len(terbaik[0])} block)")
        return True

    def jadwalkan_resolve(self):
        """Resolve di thread latar (paling sering 1x per 5 detik)."""
        sekarang = time.time()
        if sekarang - self._resolve_terakhir < 5:
            return
        self._resolve_terakhir = sekarang

        def _jalan():
            time.sleep(1.5)
            try:
                self.resolve()
            except Exception as e:
                log(f"resolve error: {e}")

        threading.Thread(target=_jalan, daemon=True).start()


NODE = None


def thread_broadcaster(iface_ip, stop_event):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.bind((iface_ip, 0))
    except OSError:
        try:
            sock.bind(("0.0.0.0", 0))
        except OSError:
            return
    while not stop_event.is_set():
        payload = json.dumps({
            "type": "presma-node",
            "http_port": PORT,
            "difficulty": NODE.blockchain.difficulty,
            "genesis": GENESIS_HASH,
        }).encode("utf-8")
        for target in ("255.255.255.255", "127.0.0.1"):
            try:
                sock.sendto(payload, (target, DISCOVERY_PORT))
            except OSError:
                pass
        stop_event.wait(5)
    sock.close()


def thread_listener(stop_event):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", DISCOVERY_PORT))
    except OSError as e:
        log(f"discovery listener gagal bind: {e}")
        return
    sock.settimeout(1)
    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(65535)
            obj = json.loads(data.decode("utf-8"))
        except (OSError, ValueError):  # timeout/socket error, atau beacon bukan JSON
            continue
        proses_beacon(obj, addr, NODE)
    sock.close()


def thread_resolver(stop_event):
    while not stop_event.is_set():
        try:
            NODE.resolve(verbose=False)
        except Exception as e:
            log(f"resolve background error: {e}")
        stop_event.wait(JEDA_RESOLVE_LATAR)


def mulai_discovery(iface_ip, stop_event):
    threads = [
        threading.Thread(target=thread_broadcaster, args=(iface_ip, stop_event), daemon=True),
        threading.Thread(target=thread_listener, args=(stop_event,), daemon=True),
        threading.Thread(target=thread_resolver, args=(stop_event,), daemon=True),
    ]
    for t in threads:
        t.start()
    return threads


class PermintaanSalah(Exception):
    """Isi permintaan HTTP tidak valid; dibalas 400/413 tanpa menjatuhkan handler."""

    def __init__(self, pesan, kode=400):
        super().__init__(pesan)
        self.kode = kode


class NodeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # matikan log bawaan http.server agar console bersih

    def _balas(self, kode, isi):
        badan = json.dumps(isi, indent=2).encode("utf-8")
        self.send_response(kode)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(badan)))
        self.end_headers()
        self.wfile.write(badan)

    def _baca_json(self):
        try:
            panjang = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise PermintaanSalah("Content-Length tidak valid")
        if not 0 <= panjang <= BATAS_ISI_PERMINTAAN:
            raise PermintaanSalah("ukuran isi permintaan terlalu besar", 413)
        try:
            isi = json.loads(self.rfile.read(panjang) or b"{}")
        except ValueError:
            raise PermintaanSalah("isi permintaan bukan JSON")
        if not isinstance(isi, dict):
            raise PermintaanSalah("isi permintaan harus berupa objek JSON")
        return isi

    def _layani(self, rute):
        aksi = rute.get(self.path)
        if aksi is None:
            self._balas(404, {"error": "endpoint tidak dikenal"})
            return
        try:
            aksi()
        except PermintaanSalah as e:
            self._balas(e.kode, {"error": str(e)})
        except Exception as e:  # jangan sampai satu request aneh memutus koneksi tanpa jawaban
            log(f"ERROR {self.command} {self.path}: {e!r}")
            self._balas(500, {"error": "kesalahan internal node"})

    def do_GET(self):
        self._layani({
            "/chain": self._get_chain,
            "/pool": self._get_pool,
            "/validate": self._get_validate,
            "/tally": self._get_tally,
            "/resolve": self._get_resolve,
            "/peers": lambda: self._balas(200, {"peers": NODE.peers}),
            "/contract": self._get_contract,
            "/paslon": self._get_paslon,
        })

    def do_POST(self):
        self._layani({
            "/transaksi": self._post_transaksi,
            "/mine": self._post_mine,
            "/block": self._post_block,
            "/peers": self._post_peers,
            "/tamper": self._post_tamper,
        })

    def _get_chain(self):
        bc = NODE.blockchain
        with bc.lock:
            self._balas(200, {
                "panjang": len(bc.chain),
                "difficulty": bc.difficulty,
                "chain": [b.to_dict() for b in bc.chain],
            })

    def _get_pool(self):
        bc = NODE.blockchain
        with bc.lock:
            self._balas(200, {"jumlah": len(bc.pool), "transaksi": [t.to_dict() for t in bc.pool]})

    def _get_validate(self):
        ok, rusak, alasan = NODE.blockchain.periksa()
        self._balas(200, {"valid": ok, "index_rusak": rusak, "alasan": alasan, "panjang": len(NODE.blockchain.chain)})

    def _get_tally(self):
        total, rekap = NODE.blockchain.rekap()
        self._balas(200, {"total_suara": total, "rekap_suara": rekap})

    def _get_resolve(self):
        log("menjalankan longest-chain rule")
        berubah = NODE.resolve()
        self._balas(200, {"rantai_diganti": berubah, "panjang": len(NODE.blockchain.chain)})

    def _get_contract(self):
        konteks = NODE.blockchain.konteks
        pemilik = alamat_dari_pem(konteks.pemilik) if konteks.pemilik else None
        self._balas(200, {"alamat": konteks.kontrak, "pemilik": pemilik})

    def _get_paslon(self):
        bc = NODE.blockchain
        with bc.lock:
            state = state_paslon_dari_chain(bc.chain)
        self._balas(200, {"paslon": state})

    def _post_transaksi(self):
        isi = self._baca_json()
        try:
            tx = Transaksi.from_dict(isi)
        except (KeyError, TypeError) as e:
            raise PermintaanSalah(f"format transaksi tidak lengkap ({e})")
        ok, pesan, baru = NODE.blockchain.tambah_transaksi(tx)
        if not ok:
            raise PermintaanSalah(pesan)
        if baru and not isi.get("diteruskan"):
            NODE.broadcast_transaksi(tx)
        self._balas(201, {"pesan": pesan, "pool": len(NODE.blockchain.pool)})

    def _post_mine(self):
        block, alasan = NODE.blockchain.tambang_pool()
        if block is None:
            self._balas(400 if "pool kosong" in alasan else 409, {"error": alasan})
            return
        NODE.broadcast_block(block)
        self._balas(201, {"pesan": "block berhasil ditambang dan ditambahkan", "block": block.to_dict()})

    def _post_block(self):
        isi = self._baca_json()
        try:
            block = Block.from_dict(isi)
        except (KeyError, TypeError, AttributeError):
            self._balas(409, {"pesan": "block ditolak", "error": "format block tidak lengkap"})
            return
        ok, alasan = NODE.blockchain.terima_block(block)
        if ok:
            self._balas(200, {"pesan": alasan})
            return
        if "melompat" in alasan:
            NODE.jadwalkan_resolve()  # node tertinggal: sinkron otomatis ke rantai terpanjang
        self._balas(409, {"pesan": "block ditolak", "error": alasan})

    def _post_peers(self):
        isi = self._baca_json()
        peer_baru = isi.get("peer")
        if not NODE.tambah_peer(peer_baru, isi.get("timbal_balik", True)):
            raise PermintaanSalah("peer tidak valid (format host:port) atau sudah ada")
        self._balas(200, {"pesan": f"peer {peer_baru} berhasil ditambahkan", "peers": NODE.peers})

    def _post_tamper(self):
        # Fitur demo perusak data: hanya boleh dipanggil dari mesin node itu sendiri.
        if self.client_address[0] not in ip_milik_sendiri():
            self._balas(403, {"error": "tamper hanya boleh dari mesin node ini"})
            return
        try:
            index = int(self._baca_json().get("index", 0))
        except (TypeError, ValueError):
            raise PermintaanSalah("index harus berupa angka")
        ok, pesan = NODE.blockchain.ubah_data_demo(index)
        self._balas(200 if ok else 400, {"pesan" if ok else "error": pesan})


def tambah_peer_manual(node, peer):
    if not peer_valid(peer):
        print("Format peer harus host:port")
        return
    try:
        data = ambil_json(f"http://{peer}/chain")
    except Exception as e:
        print(f"Gagal menghubungi {peer}: {e}")
        return
    if data.get("difficulty") != node.blockchain.difficulty:
        print(f"Ditolak: difficulty peer ({data.get('difficulty')}) != lokal ({node.blockchain.difficulty})")
        return
    rantai_peer = data.get("chain", [])
    if not rantai_peer or rantai_peer[0].get("hash") != GENESIS_HASH:
        print("Ditolak: genesis tidak cocok")
        return
    if node.tambah_peer(peer, timbal_balik=True):
        print(f"Peer {peer} ditambahkan.")
        node.jadwalkan_resolve()
    else:
        print("Peer tidak valid atau sudah ada.")


def menu_interaktif(node):
    stop_event = threading.Event()
    mulai_discovery(IFACE_IP, stop_event)
    try:
        while True:
            print("\n=== Node Voting Presma (Interaktif) ===")
            print(f"Interface: {IFACE_IP} | Node: http://{IFACE_IP}:{node.port} (difficulty {node.blockchain.difficulty})")
            print("1. Status")
            print("2. Daftar peer")
            print("3. Cari node (tunggu 6 detik)")
            print("4. Tambah peer manual")
            print("5. Tampilkan alamat untuk client.py")
            print("6. Hentikan node")
            pilihan = input("Pilih: ").strip()
            if pilihan == "1":
                with node.blockchain.lock:
                    print(f"Port: {node.port} | Peers: {len(node.peers)} | Rantai: {len(node.blockchain.chain)} block | Pool: {len(node.blockchain.pool)}")
                print("Peers:", node.peers)
            elif pilihan == "2":
                print("Peers:", node.peers)
            elif pilihan == "3":
                print("Mencari node lain selama 6 detik...")
                time.sleep(6)
                print("Peers sekarang:", node.peers)
            elif pilihan == "4":
                peer = input("Alamat peer (host:port): ").strip()
                if peer:
                    tambah_peer_manual(node, peer)
            elif pilihan == "5":
                print(f"Gunakan di client.py: {IFACE_IP}:{node.port}")
            elif pilihan == "6":
                break
            else:
                print("Pilihan tidak valid.")
    finally:
        stop_event.set()
        if node.http_server:
            node.http_server.shutdown()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        IFACE_IP = deteksi_ip_utama(otomatis=False)
        PORT = cari_port_kosong()
        if PORT is None:
            print("Tidak ada port kosong di range 5001-5100.")
            sys.exit(1)
        peers_awal, difficulty, interaktif = [], 4, True
    else:
        PORT = int(sys.argv[1])
        peers_awal = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else []
        difficulty = int(sys.argv[3]) if len(sys.argv) > 3 else 4
        IFACE_IP = deteksi_ip_utama(otomatis=True)
        interaktif = False

    NODE = Node(PORT, peers_awal, difficulty)
    print(f"Node Voting UNTAD aktif di port {PORT}")
    print("Peers     : " + (", ".join(NODE.peers) if NODE.peers else "(belum ada)"))
    print(f"Difficulty: {difficulty} (hash harus diawali {'0' * difficulty})")
    print(f"Genesis   : {GENESIS_HASH[:20]}...")
    print(f"Interface : {IFACE_IP}")

    server = ThreadingHTTPServer(("0.0.0.0", PORT), NodeHandler)
    NODE.http_server = server
    if interaktif:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        menu_interaktif(NODE)
    else:
        stop_event = threading.Event()
        mulai_discovery(IFACE_IP, stop_event)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            stop_event.set()
