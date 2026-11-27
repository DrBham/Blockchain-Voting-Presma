# Smart contract mock-up pendaftaran paslon dan status pemilu. State contract hanya berubah
# lewat transaksi CONTRACT_CALL yang tercatat di chain, lalu dibangun ulang dengan replay.

import copy
import hashlib
import json
import secrets
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

STATUS = ("persiapan", "dibuka", "ditutup", "dihitung")
FUNGSI_STATUS = ("buka_pemungutan", "tutup_pemungutan", "buka_kunci")
FUNGSI_PENGUBAH = ("tambah_paslon", "ubah_paslon", "hapus_paslon") + FUNGSI_STATUS
MAKS_NAMA = 120
MAKS_VISI = 500


def deploy_contract(nama):
    """Hasilkan alamat contract (40 hex) dari nama + waktu + angka acak."""
    benih = f"{nama}:{time.time()}:{secrets.token_hex(8)}"
    return hashlib.sha256(benih.encode("utf-8")).hexdigest()[:40]


def bilangan_positif(nilai):
    """Angka bulat >= 1 dari int atau teks digit ASCII. None kalau tidak valid (bool dan float ditolak)."""
    if isinstance(nilai, str) and nilai.strip().isascii() and nilai.strip().isdigit():
        nilai = int(nilai)
    if isinstance(nilai, bool) or not isinstance(nilai, int) or nilai < 1:
        return None
    return nilai


def _teks(nilai, label, batas, wajib=False):
    """Mengembalikan (teks_bersih, pesan_error)."""
    if nilai is None:
        nilai = ""
    if not isinstance(nilai, str):
        return None, f"{label} harus berupa teks"
    nilai = nilai.strip()
    if wajib and not nilai:
        return None, f"{label} paslon tidak boleh kosong"
    if len(nilai) > batas:
        return None, f"{label} paslon maksimal {batas} karakter"
    return nilai, None


def _salin(state):
    return [dict(p) for p in (state or [])]


def _paslon_aktif(state, id_mentah):
    """Mengembalikan (paslon, pesan_error) untuk paslon aktif dengan id tersebut."""
    pid = bilangan_positif(id_mentah)
    if pid is None:
        return None, "id paslon tidak valid"
    target = next((p for p in state if p["id"] == pid), None)
    if target is None:
        return None, f"paslon id {pid} tidak ditemukan"
    if not target["aktif"]:
        return None, "paslon sudah tidak aktif"
    return target, None


class PaslonContract:
    """Fungsi contract tidak mengubah state masukan; mengembalikan (ok, alasan, state_baru)."""

    def __init__(self, alamat):
        self.alamat = alamat

    def tambah_paslon(self, state, args):
        state = _salin(state)
        nomor = bilangan_positif(args.get("nomor"))
        if nomor is None:
            return False, "nomor paslon harus angka bulat >= 1", state
        nama, salah = _teks(args.get("nama"), "nama", MAKS_NAMA, wajib=True)
        if salah:
            return False, salah, state
        visi, salah = _teks(args.get("visi"), "visi", MAKS_VISI)
        if salah:
            return False, salah, state
        if any(p["aktif"] and p["nomor"] == nomor for p in state):
            return False, f"nomor paslon {nomor} sudah dipakai paslon aktif", state
        state.append({
            "id": max((p["id"] for p in state), default=0) + 1,
            "nomor": nomor,
            "nama": nama,
            "visi": visi,
            "aktif": True,
        })
        return True, "paslon ditambahkan", state

    def ubah_paslon(self, state, args):
        state = _salin(state)
        target, salah = _paslon_aktif(state, args.get("id"))
        if salah:
            return False, salah, state

        # Semua argumen divalidasi dulu; state baru diubah kalau semuanya sah.
        perubahan = {}
        if args.get("nama") is not None:
            perubahan["nama"], salah = _teks(args["nama"], "nama", MAKS_NAMA, wajib=True)
            if salah:
                return False, salah, state
        if args.get("visi") is not None:
            perubahan["visi"], salah = _teks(args["visi"], "visi", MAKS_VISI)
            if salah:
                return False, salah, state
        if args.get("nomor") is not None:
            nomor = bilangan_positif(args["nomor"])
            if nomor is None:
                return False, "nomor paslon harus angka bulat >= 1", state
            if any(p["aktif"] and p["id"] != target["id"] and p["nomor"] == nomor for p in state):
                return False, f"nomor paslon {nomor} sudah dipakai paslon aktif", state
            perubahan["nomor"] = nomor
        target.update(perubahan)
        return True, "paslon diubah", state

    def hapus_paslon(self, state, args):
        state = _salin(state)
        target, salah = _paslon_aktif(state, args.get("id"))
        if salah:
            return False, salah, state
        target["aktif"] = False
        return True, "paslon dinonaktifkan (soft delete)", state

    def daftar_paslon(self, state):
        return _salin(state)

    def baca_paslon(self, state, paslon_id):
        return next((dict(p) for p in (state or []) if p["id"] == paslon_id), None)


# ---------------------------------------------------------------- kunci pemilu

def _oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def buat_kunci_pemilu():
    """Pasangan kunci RSA 2048 untuk mengenkripsi pilihan. Mengembalikan (privat_pem, publik_pem)."""
    kunci = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privat = kunci.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    publik = kunci.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return privat, publik


def enkripsi_pilihan(nomor, kunci_publik_pem):
    """RSA-OAEP SHA-256 atas JSON {"paslon": nomor}. OAEP teracak: pilihan sama, sandi berbeda."""
    kunci = serialization.load_pem_public_key(kunci_publik_pem.encode())
    return kunci.encrypt(json.dumps({"paslon": nomor}).encode("utf-8"), _oaep()).hex()


def dekripsi_pilihan(sandi_hex, kunci_privat_pem):
    """Nomor paslon dari sandi, atau None kalau sandi rusak / isinya bukan {"paslon": int}."""
    try:
        kunci = serialization.load_pem_private_key(kunci_privat_pem.encode(), password=None)
        isi = json.loads(kunci.decrypt(bytes.fromhex(sandi_hex), _oaep()))
    except (ValueError, TypeError, AttributeError):
        return None
    nomor = isi.get("paslon") if isinstance(isi, dict) else None
    return nomor if isinstance(nomor, int) and not isinstance(nomor, bool) else None


def _kunci_pasangan(kunci_privat_pem, kunci_publik_pem):
    try:
        privat = serialization.load_pem_private_key(kunci_privat_pem.encode(), password=None)
        publik = serialization.load_pem_public_key(kunci_publik_pem.encode())
        return privat.public_key().public_numbers() == publik.public_numbers()
    except (ValueError, TypeError, AttributeError):
        return False


# ---------------------------------------------------------------- state contract

def state_awal(kunci_publik):
    return {"paslon": [], "status": "persiapan", "kunci_publik": kunci_publik, "kunci_privat": None}


def _ubah_status(state, fungsi, args):
    """Fungsi status pemilu. state sudah berupa salinan; mengembalikan (ok, alasan)."""
    status = state["status"]
    if fungsi == "buka_pemungutan":
        if status != "persiapan":
            return False, f"pemungutan hanya bisa dibuka dari status persiapan (sekarang {status})"
        nomor = sorted(p["nomor"] for p in state["paslon"] if p["aktif"])
        if len(nomor) < 2:
            return False, "pemungutan butuh minimal 2 paslon aktif"
        if nomor != list(range(1, len(nomor) + 1)):
            return False, f"nomor paslon aktif harus berurutan mulai 1 (sekarang {nomor})"
        state["status"] = "dibuka"
        return True, "pemungutan dibuka"
    if fungsi == "tutup_pemungutan":
        if status != "dibuka":
            return False, f"pemungutan hanya bisa ditutup dari status dibuka (sekarang {status})"
        state["status"] = "ditutup"
        return True, "pemungutan ditutup"
    if status != "ditutup":  # buka_kunci
        return False, f"kunci pemilu hanya bisa dibuka dari status ditutup (sekarang {status})"
    kunci = args.get("kunci_privat")
    if not isinstance(kunci, str) or not _kunci_pasangan(kunci, state["kunci_publik"] or ""):
        return False, "kunci privat bukan pasangan kunci pemilu yang tercatat"
    state["status"], state["kunci_privat"] = "dihitung", kunci
    return True, "kunci pemilu dibuka, suara bisa dihitung"


def jalankan_contract(state, fungsi, args):
    """Eksekusi satu fungsi pengubah state (dict). Mengembalikan (ok, alasan, state_baru).
    State masukan tidak diubah; kalau ditolak, state masukan yang dikembalikan."""
    if fungsi not in FUNGSI_PENGUBAH:
        return False, f"fungsi contract '{fungsi}' tidak dikenal", state
    if not isinstance(args, dict):
        return False, "argumen contract harus berupa objek", state
    baru = copy.deepcopy(state)
    if fungsi in FUNGSI_STATUS:
        ok, alasan = _ubah_status(baru, fungsi, args)
    elif baru["status"] != "persiapan":
        ok, alasan = False, f"paslon hanya bisa diubah saat status persiapan (sekarang {baru['status']})"
    else:
        ok, alasan, baru["paslon"] = getattr(PaslonContract("-"), fungsi)(baru["paslon"], args)
    return ok, alasan, (baru if ok else state)


def _isi_tx(chain):
    """Urutkan (index_block, tx) dari chain; block dan tx boleh berupa objek atau dict."""
    for idx, block in enumerate(chain):
        transaksi = block.get("transaksi") if isinstance(block, dict) else getattr(block, "transaksi", None)
        for tx in (transaksi or []):
            yield idx, tx if isinstance(tx, dict) else vars(tx)


def _replay(chain):
    """Jalankan ulang setiap CONTRACT_CALL sah dari pemilik contract pertama yang dideploy.
    Menghasilkan (idx, fungsi, id_paslon, sebelum, sesudah, timestamp, state);
    untuk deploy dan fungsi status, id_paslon/sebelum/sesudah bernilai None."""
    state = state_awal(None)
    kontrak = pemilik = None
    for idx, tx in _isi_tx(chain):
        payload = tx.get("payload")
        if not isinstance(payload, dict):
            continue
        if tx.get("tipe") == "CONTRACT_DEPLOY" and kontrak is None:
            kontrak, pemilik = payload.get("contract_address"), tx.get("public_key")
            state = state_awal(payload.get("kunci_pemilu"))
            yield idx, "deploy", None, None, None, tx.get("timestamp"), state
            continue
        if (tx.get("tipe") != "CONTRACT_CALL" or kontrak is None
                or payload.get("contract_address") != kontrak or tx.get("public_key") != pemilik):
            continue
        fungsi, args = payload.get("fungsi"), payload.get("args")
        ok, _, state_baru = jalankan_contract(state, fungsi, args)
        if not ok:
            continue
        if fungsi in FUNGSI_STATUS:
            state = state_baru
            yield idx, fungsi, None, None, None, tx.get("timestamp"), state
            continue
        paslon = state_baru["paslon"]
        pid = paslon[-1]["id"] if fungsi == "tambah_paslon" else bilangan_positif(args.get("id"))
        sebelum = next((dict(p) for p in state["paslon"] if p["id"] == pid), None)
        state = state_baru
        target = next(p for p in paslon if p["id"] == pid)
        target["block_number"] = idx
        yield idx, fungsi, pid, sebelum, dict(target), tx.get("timestamp"), state


def state_contract_dari_chain(chain):
    """Replay chain menjadi state contract terkini (dict: paslon, status, kunci)."""
    state = state_awal(None)
    for *_, state in _replay(chain):
        pass
    return state


def state_paslon_dari_chain(chain):
    """Replay chain menjadi state paslon terkini (list of dict)."""
    return state_contract_dari_chain(chain)["paslon"]


def riwayat_paslon(chain, pid):
    """Riwayat perubahan satu paslon dari chain: nilai sebelum dan sesudah tiap operasi."""
    return [
        {"block": idx, "fungsi": fungsi, "sebelum": sebelum, "sesudah": sesudah, "timestamp": ts}
        for idx, fungsi, id_paslon, sebelum, sesudah, ts, _ in _replay(chain)
        if id_paslon is not None and id_paslon == pid
    ]
