# Smart contract mock-up pendaftaran paslon. State contract hanya berubah lewat
# transaksi CONTRACT_CALL yang tercatat di chain, lalu dibangun ulang dengan replay.

import hashlib
import secrets
import time

FUNGSI_PENGUBAH = ("tambah_paslon", "ubah_paslon", "hapus_paslon")
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
        if any(p["nomor"] == nomor for p in state):
            return False, f"nomor paslon {nomor} sudah terdaftar", state
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
            if any(p["id"] != target["id"] and p["nomor"] == nomor for p in state):
                return False, f"nomor paslon {nomor} sudah terdaftar", state
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


def jalankan_contract(state, fungsi, args):
    """Eksekusi satu fungsi pengubah state. Mengembalikan (ok, alasan, state_baru)."""
    if fungsi not in FUNGSI_PENGUBAH:
        return False, f"fungsi contract '{fungsi}' tidak dikenal", state
    if not isinstance(args, dict):
        return False, "argumen contract harus berupa objek", state
    return getattr(PaslonContract("-"), fungsi)(state, args)


def _isi_tx(chain):
    """Urutkan (index_block, tx) dari chain; block dan tx boleh berupa objek atau dict."""
    for idx, block in enumerate(chain):
        transaksi = block.get("transaksi") if isinstance(block, dict) else getattr(block, "transaksi", None)
        for tx in (transaksi or []):
            yield idx, tx if isinstance(tx, dict) else vars(tx)


def _replay(chain):
    """Jalankan ulang setiap CONTRACT_CALL sah dari pemilik contract pertama yang dideploy.
    Menghasilkan (idx, fungsi, id_paslon, sebelum, sesudah, timestamp, state)."""
    state = []
    kontrak = pemilik = None
    for idx, tx in _isi_tx(chain):
        payload = tx.get("payload")
        if not isinstance(payload, dict):
            continue
        if tx.get("tipe") == "CONTRACT_DEPLOY" and kontrak is None:
            kontrak, pemilik = payload.get("contract_address"), tx.get("public_key")
            continue
        if (tx.get("tipe") != "CONTRACT_CALL" or kontrak is None
                or payload.get("contract_address") != kontrak or tx.get("public_key") != pemilik):
            continue
        fungsi, args = payload.get("fungsi"), payload.get("args")
        ok, _, state_baru = jalankan_contract(state, fungsi, args)
        if not ok:
            continue
        pid = state_baru[-1]["id"] if fungsi == "tambah_paslon" else bilangan_positif(args.get("id"))
        sebelum = next((dict(p) for p in state if p["id"] == pid), None)
        state = state_baru
        target = next(p for p in state if p["id"] == pid)
        target["block_number"] = idx
        yield idx, fungsi, pid, sebelum, dict(target), tx.get("timestamp"), state


def state_paslon_dari_chain(chain):
    """Replay chain menjadi state paslon terkini (list of dict)."""
    state = []
    for *_, state in _replay(chain):
        pass
    return state


def riwayat_paslon(chain, pid):
    """Riwayat perubahan satu paslon dari chain: nilai sebelum dan sesudah tiap operasi."""
    return [
        {"block": idx, "fungsi": fungsi, "sebelum": sebelum, "sesudah": sesudah, "timestamp": ts}
        for idx, fungsi, id_paslon, sebelum, sesudah, ts, _ in _replay(chain)
        if id_paslon == pid
    ]
