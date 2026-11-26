import json
import urllib.error
import urllib.request
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from contract import deploy_contract, riwayat_paslon, state_paslon_dari_chain
from node import Transaksi
from web.models import Paslon, db

BATAS_WAKTU_NODE = 10
BATAS_WAKTU_MINE = 300  # PoW dengan difficulty tinggi bisa butuh > 1 menit

bp = Blueprint("main", __name__)


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


def kirim_tx_admin(tipe, payload):
    """Tanda tangani transaksi dengan kunci admin, kirim ke pool node, lalu tambang (kalau AUTO_MINE).
    Mengembalikan pesan error, atau None kalau transaksi diterima node."""
    tx = Transaksi("admin", None, current_app.config["ADMIN_PUBLIC_KEY"], tipe=tipe, payload=payload)
    tx.tanda_tangani(current_app.config["ADMIN_PRIVATE_KEY"])
    status, resp = node_request("POST", "/transaksi", tx.to_dict())
    if status not in (200, 201):
        return pesan_error(resp)
    if current_app.config["AUTO_MINE"]:
        status, resp = node_request("POST", "/mine", {}, timeout=BATAS_WAKTU_MINE)
        if status != 201:
            flash(f"Transaksi sudah di pool, tetapi belum ditambang: {pesan_error(resp)}", "warning")
    return None


def alamat_contract_di_chain():
    """Alamat contract dibaca dari chain (lewat node), bukan dari basis data."""
    status, data = node_request("GET", "/contract")
    return data.get("alamat") if status == 200 else None


def deploy_ke_chain():
    """Deploy contract = transaksi CONTRACT_DEPLOY bertanda tangan yang ditambang ke block.
    Mengembalikan (alamat, error)."""
    alamat = deploy_contract(current_app.config["CONTRACT_NAME"])
    error = kirim_tx_admin("CONTRACT_DEPLOY", {"contract_address": alamat, "nama": current_app.config["CONTRACT_NAME"]})
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
        id=p["id"],
        nomor=p["nomor"],
        nama=p["nama"],
        visi=p["visi"],
        aktif=p["aktif"],
        block_number=p["block_number"],
    ) for p in state)
    db.session.commit()
    return True, "ok"


def format_waktu(timestamp):
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return "-"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


@bp.route("/")
def index():
    status, data = node_request("GET", "/chain")
    chain_len = data.get("panjang") if status == 200 else None
    paslons = Paslon.query.order_by(Paslon.nomor).all()
    contract = alamat_contract_di_chain() if status == 200 else None
    return render_template("index.html", paslons=paslons, chain_len=chain_len, contract=contract, node_status=status)


@bp.route("/paslon")
def paslon_list():
    paslons = Paslon.query.order_by(Paslon.nomor).all()
    return render_template("paslon_list.html", paslons=paslons)


def args_form():
    return {k: request.form.get(k, "").strip() for k in ("nomor", "nama", "visi")}


@bp.route("/paslon/tambah", methods=["GET", "POST"])
def paslon_tambah():
    if request.method == "GET":
        return render_template("paslon_form.html", paslon=None, action="Tambah")
    error = panggil_contract("tambah_paslon", args_form())
    if error:
        flash(f"Gagal: {error}", "danger")
        return redirect(url_for("main.paslon_tambah"))
    flash("Paslon ditambahkan.", "success")
    return redirect(url_for("main.paslon_list"))


@bp.route("/paslon/<int:pid>/ubah", methods=["GET", "POST"])
def paslon_ubah(pid):
    paslon = db.get_or_404(Paslon, pid)
    if request.method == "GET":
        return render_template("paslon_form.html", paslon=paslon, action="Ubah")
    error = panggil_contract("ubah_paslon", {"id": pid, **args_form()})
    if error:
        flash(f"Gagal: {error}", "danger")
        return redirect(url_for("main.paslon_ubah", pid=pid))
    flash("Paslon diubah.", "success")
    return redirect(url_for("main.paslon_list"))


@bp.route("/paslon/<int:pid>/hapus", methods=["POST"])
def paslon_hapus(pid):
    error = panggil_contract("hapus_paslon", {"id": pid})
    flash(f"Gagal: {error}" if error else "Paslon dinonaktifkan (soft delete).", "danger" if error else "success")
    return redirect(url_for("main.paslon_list"))


@bp.route("/paslon/<int:pid>/riwayat")
def paslon_riwayat(pid):
    status, data = node_request("GET", "/chain")
    if status != 200:
        flash(f"Gagal mengambil chain: {pesan_error(data)}", "danger")
        return redirect(url_for("main.paslon_list"))
    riwayat = riwayat_paslon(data.get("chain", []), pid)
    for r in riwayat:
        r["waktu"] = format_waktu(r["timestamp"])
    return render_template("paslon_riwayat.html", pid=pid, riwayat=riwayat)


@bp.route("/contract/deploy", methods=["POST"])
def contract_deploy():
    alamat, error = deploy_ke_chain()
    if error:
        flash(f"Deploy gagal: {error}", "danger")
    else:
        flash(f"Contract dideploy ke chain di alamat {alamat}", "success")
    return redirect(url_for("main.index"))


@bp.route("/chain/verify")
def chain_verify():
    status, data = node_request("GET", "/validate")
    return render_template("verify.html", status=status, data=data)


@bp.route("/state/rebuild", methods=["POST"])
def state_rebuild():
    ok, msg = rebuild_state()
    if ok:
        flash("State SQLite dibangun ulang dari chain.", "success")
    else:
        flash(f"Rebuild gagal: {msg}", "danger")
    return redirect(url_for("main.index"))


@bp.route("/node/status")
def node_status():
    _, chain_data = node_request("GET", "/chain")
    _, peers_data = node_request("GET", "/peers")
    _, tally_data = node_request("GET", "/tally")
    return render_template("node_status.html", chain=chain_data, peers=peers_data, tally=tally_data)
