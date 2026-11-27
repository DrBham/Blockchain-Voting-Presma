"""Satu-satunya jalan web ke node: permintaan HTTP, transaksi admin, panggilan contract, rebuild state."""
import json
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app, flash

from contract import state_paslon_dari_chain
from node import Transaksi
from web.models import Paslon, db
from web.wallet import muat_atau_buat_kunci_pemilu

BATAS_WAKTU_NODE = 10
BATAS_WAKTU_MINE = 300  # PoW dengan difficulty tinggi bisa butuh > 1 menit


def node_request(method, path, data=None, timeout=BATAS_WAKTU_NODE):
    """Mengembalikan (status_http atau None kalau node tidak terjangkau, isi_json)."""
    url = current_app.config["NODE_URL"].rstrip("/") + path
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except ValueError:
            return e.code, {}
    except Exception as e:
        return None, {"error": str(e)}


def pesan_error(resp):
    return resp.get("error", "node tidak memberi alasan") if isinstance(resp, dict) else str(resp)


def tambang():
    """Bentuk block dari pool. Mengembalikan pesan error, atau None kalau berhasil atau pool kosong."""
    status, resp = node_request("POST", "/mine", {}, timeout=BATAS_WAKTU_MINE)
    if status == 201 or "kosong" in pesan_error(resp):
        return None
    return pesan_error(resp)


def kirim_tx(tx, tambang_langsung=True):
    """Kirim transaksi bertanda tangan ke pool node, lalu tambang kalau AUTO_MINE.
    Mengembalikan pesan error, atau None kalau transaksi diterima node."""
    status, resp = node_request("POST", "/transaksi", tx.to_dict())
    if status not in (200, 201):
        return pesan_error(resp)
    if tambang_langsung and current_app.config["AUTO_MINE"]:
        error = tambang()
        if error:
            flash(f"Transaksi sudah di pool, tetapi belum ditambang: {error}", "warning")
    return None


def kirim_tx_admin(tipe, payload):
    """Transaksi bertanda tangan kunci admin (pemilik contract)."""
    tx = Transaksi("admin", None, current_app.config["ADMIN_PUBLIC_KEY"], tipe=tipe, payload=payload)
    tx.tanda_tangani(current_app.config["ADMIN_PRIVATE_KEY"])
    return kirim_tx(tx)


def status_node():
    """Isi GET /status, atau None kalau node tidak terjangkau."""
    status, data = node_request("GET", "/status")
    return data if status == 200 else None


def alamat_contract_di_chain():
    """Alamat contract dibaca dari chain (lewat node), bukan dari basis data."""
    status, data = node_request("GET", "/contract")
    return data.get("alamat") if status == 200 else None


def deploy_ke_chain():
    """Deploy contract = transaksi CONTRACT_DEPLOY bertanda tangan yang membawa kunci publik pemilu.
    Kunci privat pemilu tetap di berkas panitia. Mengembalikan (alamat, error)."""
    from contract import deploy_contract
    _, kunci_publik = muat_atau_buat_kunci_pemilu(current_app.config["KUNCI_PEMILU_PATH"])
    alamat = deploy_contract(current_app.config["CONTRACT_NAME"])
    error = kirim_tx_admin("CONTRACT_DEPLOY", {
        "contract_address": alamat,
        "nama": current_app.config["CONTRACT_NAME"],
        "kunci_pemilu": kunci_publik,
    })
    return (None, error) if error else (alamat, None)


def panggil_contract(fungsi, args):
    """Kirim CONTRACT_CALL ke contract aktif (auto-deploy kalau belum ada), lalu sinkronkan SQLite.
    Aturan bisnis diputuskan contract di node, bukan di sini. Mengembalikan pesan error atau None."""
    alamat = alamat_contract_di_chain()
    if not alamat:
        alamat, error = deploy_ke_chain()
        if error:
            return f"auto-deploy contract gagal: {error}"
    error = kirim_tx_admin("CONTRACT_CALL", {"contract_address": alamat, "fungsi": fungsi, "args": args})
    if error:
        return error
    ok, msg = rebuild_state()
    if not ok:
        flash(f"Rebuild gagal: {msg}", "warning")
    return None


def rebuild_state():
    """Isi ulang SQLite dari chain. Chain diambil dulu, jadi data tidak terhapus kalau node mati."""
    status, data = node_request("GET", "/chain")
    if status != 200:
        return False, pesan_error(data)
    state = state_paslon_dari_chain(data.get("chain", []))
    Paslon.query.delete()
    db.session.add_all(Paslon(
        id=p["id"], nomor=p["nomor"], nama=p["nama"], visi=p.get("visi", ""),
        aktif=p["aktif"], block_number=p.get("block_number", 0),
    ) for p in state)
    db.session.commit()
    return True, "ok"


def kutip(nilai):
    """Aman untuk ditaruh di path URL node (NIM, signature hex)."""
    return urllib.parse.quote(str(nilai), safe="")
