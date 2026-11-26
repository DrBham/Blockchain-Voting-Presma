import hashlib
import random
import time


def deploy_contract(nama):
    """Hasilkan alamat contract (40 hex) dari nama + waktu + nonce."""
    benih = f"{nama}:{time.time()}:{random.getrandbits(64)}"
    return hashlib.sha256(benih.encode("utf-8")).hexdigest()[:40]


class PaslonContract:
    def __init__(self, alamat):
        self.alamat = alamat

    def tambah_paslon(self, state, args):
        state = [dict(p) for p in (state or [])]
        try:
            nomor = int(args.get("nomor"))
        except (TypeError, ValueError, AttributeError):
            return False, "nomor paslon harus berupa angka", state
        nama = (args.get("nama") or "").strip()
        if not nama:
            return False, "nama paslon tidak boleh kosong", state
        visi = (args.get("visi") or "").strip()
        if any(p.get("nomor") == nomor for p in state):
            return False, f"nomor paslon {nomor} sudah terdaftar", state
        new_id = (max((p.get("id", 0) for p in state), default=0) + 1)
        state.append({
            "id": new_id,
            "nomor": nomor,
            "nama": nama,
            "visi": visi,
            "aktif": True,
        })
        return True, "paslon ditambahkan", state

    def ubah_paslon(self, state, args):
        state = [dict(p) for p in (state or [])]
        try:
            pid = int(args.get("id"))
        except (TypeError, ValueError, AttributeError):
            return False, "id paslon tidak valid", state
        target = next((p for p in state if p.get("id") == pid), None)
        if target is None:
            return False, f"paslon id {pid} tidak ditemukan", state
        if not target.get("aktif", True):
            return False, "paslon sudah tidak aktif", state
        if "nama" in args and args.get("nama") is not None:
            nama = str(args.get("nama")).strip()
            if not nama:
                return False, "nama paslon tidak boleh kosong", state
            target["nama"] = nama
        if "visi" in args and args.get("visi") is not None:
            target["visi"] = str(args.get("visi")).strip()
        if "nomor" in args and args.get("nomor") is not None:
            try:
                nomor_baru = int(args.get("nomor"))
            except (TypeError, ValueError):
                return False, "nomor paslon harus berupa angka", state
            if any(p.get("id") != pid and p.get("nomor") == nomor_baru for p in state):
                return False, f"nomor paslon {nomor_baru} sudah terdaftar", state
            target["nomor"] = nomor_baru
        return True, "paslon diubah", state

    def hapus_paslon(self, state, args):
        state = [dict(p) for p in (state or [])]
        try:
            pid = int(args.get("id"))
        except (TypeError, ValueError, AttributeError):
            return False, "id paslon tidak valid", state
        target = next((p for p in state if p.get("id") == pid), None)
        if target is None:
            return False, f"paslon id {pid} tidak ditemukan", state
        if not target.get("aktif", True):
            return False, "paslon sudah tidak aktif", state
        target["aktif"] = False
        return True, "paslon dinonaktifkan (soft delete)", state

    def daftar_paslon(self, state):
        return [dict(p) for p in (state or [])]

    def baca_paslon(self, state, paslon_id):
        for p in (state or []):
            if p.get("id") == paslon_id:
                return dict(p)
        return None


def _isi_tx(chain):
    """Urutkan (index_block, tipe, payload, timestamp) dari chain berupa objek Block atau dict."""
    for idx, block in enumerate(chain):
        transaksi = getattr(block, "transaksi", None)
        if transaksi is None and isinstance(block, dict):
            transaksi = block.get("transaksi", [])
        for tx in (transaksi or []):
            if isinstance(tx, dict):
                yield idx, tx.get("tipe"), tx.get("payload"), tx.get("timestamp")
            else:
                yield idx, getattr(tx, "tipe", None), getattr(tx, "payload", None), getattr(tx, "timestamp", None)


def _replay(chain):
    """Jalankan ulang setiap CONTRACT_CALL yang sah.
    Menghasilkan (idx, fungsi, id_paslon, sebelum, sesudah, timestamp, state)."""
    state = []
    contract = PaslonContract("replay")
    fungsi_contract = {
        "tambah_paslon": contract.tambah_paslon,
        "ubah_paslon": contract.ubah_paslon,
        "hapus_paslon": contract.hapus_paslon,
    }
    for idx, tipe, payload, ts in _isi_tx(chain):
        if tipe != "CONTRACT_CALL" or not isinstance(payload, dict):
            continue
        fungsi = payload.get("fungsi")
        if fungsi not in fungsi_contract:
            continue
        args = payload.get("args", {}) or {}
        ok, _, state_baru = fungsi_contract[fungsi](state, args)
        if not ok:
            continue
        pid = state_baru[-1]["id"] if fungsi == "tambah_paslon" else args.get("id")
        sebelum = next((dict(p) for p in state if p.get("id") == pid), None)
        state = state_baru
        for p in state:
            if p.get("id") == pid:
                p["block_number"] = idx
                sesudah = dict(p)
        yield idx, fungsi, pid, sebelum, sesudah, ts, state


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


def kontrak_dari_chain(chain):
    """Alamat contract yang sudah dideploy lewat transaksi CONTRACT_DEPLOY di chain."""
    return {
        payload["contract_address"]
        for _, tipe, payload, _ in _isi_tx(chain)
        if tipe == "CONTRACT_DEPLOY" and isinstance(payload, dict) and payload.get("contract_address")
    }
