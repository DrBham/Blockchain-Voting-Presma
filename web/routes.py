import json
import urllib.error
import urllib.request
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

from web.models import db, Paslon, ContractMeta
from web.config import CONTRACT_NAME
from contract import deploy_contract, state_paslon_dari_chain

bp = Blueprint("main", __name__)


def node_url():
    return current_app.config["NODE_URL"].rstrip("/")


def node_request(method, path, data=None, timeout=10):
    url = node_url() + path
    if data is None:
        req = urllib.request.Request(url, method=method)
    else:
        body = json.dumps(data).encode("utf-8")
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


def admin_sign_tx(payload):
    priv = current_app.config["ADMIN_PRIVATE_KEY"]
    pub = current_app.config["ADMIN_PUBLIC_KEY"]
    from node import Transaksi
    tx = Transaksi("admin", None, pub, tipe="CONTRACT_CALL", payload=payload)
    tx.tanda_tangani(priv)
    return tx.to_dict()


def get_contract_address():
    meta = ContractMeta.query.order_by(ContractMeta.id.desc()).first()
    if meta:
        return meta.address
    # auto-deploy if none
    addr = deploy_contract(CONTRACT_NAME)
    db.session.add(ContractMeta(address=addr, name=CONTRACT_NAME))
    db.session.commit()
    return addr


def rebuild_state():
    Paslon.query.delete()
    db.session.commit()
    status, data = node_request("GET", "/chain")
    if status != 200 or not data:
        return False, data.get("error") if isinstance(data, dict) else "node error"
    chain = data.get("chain", [])
    state = state_paslon_dari_chain(chain)
    for p in state:
        db.session.add(Paslon(
            id=p.get("id"),
            nomor=p.get("nomor", 0),
            nama=p.get("nama", ""),
            visi=p.get("visi", ""),
            aktif=p.get("aktif", True),
            block_number=p.get("block_number", 0),
        ))
    db.session.commit()
    return True, "ok"


@bp.route("/")
def index():
    status, data = node_request("GET", "/chain")
    chain_len = data.get("panjang") if isinstance(data, dict) else None
    paslons = Paslon.query.order_by(Paslon.nomor).all()
    meta = ContractMeta.query.order_by(ContractMeta.id.desc()).first()
    return render_template("index.html", paslons=paslons, chain_len=chain_len, contract=meta, node_status=status)


@bp.route("/paslon")
def paslon_list():
    paslons = Paslon.query.order_by(Paslon.nomor).all()
    return render_template("paslon_list.html", paslons=paslons)


@bp.route("/paslon/tambah", methods=["GET", "POST"])
def paslon_tambah():
    if request.method == "POST":
        nomor = request.form.get("nomor", "").strip()
        nama = request.form.get("nama", "").strip()
        visi = request.form.get("visi", "").strip()
        if not nomor or not nama:
            flash("Nomor dan nama wajib diisi.", "danger")
            return redirect(url_for("main.paslon_tambah"))
        try:
            nomor_int = int(nomor)
        except ValueError:
            flash("Nomor harus angka.", "danger")
            return redirect(url_for("main.paslon_tambah"))

        addr = get_contract_address()
        payload = {"contract_address": addr, "fungsi": "tambah_paslon", "args": {
            "nomor": nomor_int, "nama": nama, "visi": visi,
        }}
        tx = admin_sign_tx(payload)
        status, resp = node_request("POST", "/transaksi", tx)
        if status not in (200, 201):
            flash(f"Gagal: {resp.get('error') if isinstance(resp, dict) else resp}", "danger")
            return redirect(url_for("main.paslon_tambah"))
        if current_app.config["AUTO_MINE"]:
            node_request("POST", "/mine", {})
        ok, msg = rebuild_state()
        if not ok:
            flash(f"Rebuild gagal: {msg}", "warning")
        flash("Paslon ditambahkan.", "success")
        return redirect(url_for("main.paslon_list"))
    return render_template("paslon_form.html", paslon=None, action="Tambah")


@bp.route("/paslon/<int:pid>/ubah", methods=["GET", "POST"])
def paslon_ubah(pid):
    paslon = Paslon.query.get_or_404(pid)
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        visi = request.form.get("visi", "").strip()
        nomor = request.form.get("nomor", "").strip()
        args = {"id": pid}
        if nama:
            args["nama"] = nama
        if visi:
            args["visi"] = visi
        if nomor:
            try:
                args["nomor"] = int(nomor)
            except ValueError:
                flash("Nomor harus angka.", "danger")
                return redirect(url_for("main.paslon_ubah", pid=pid))

        addr = get_contract_address()
        payload = {"contract_address": addr, "fungsi": "ubah_paslon", "args": args}
        tx = admin_sign_tx(payload)
        status, resp = node_request("POST", "/transaksi", tx)
        if status not in (200, 201):
            flash(f"Gagal: {resp.get('error') if isinstance(resp, dict) else resp}", "danger")
            return redirect(url_for("main.paslon_ubah", pid=pid))
        if current_app.config["AUTO_MINE"]:
            node_request("POST", "/mine", {})
        ok, msg = rebuild_state()
        if not ok:
            flash(f"Rebuild gagal: {msg}", "warning")
        flash("Paslon diubah.", "success")
        return redirect(url_for("main.paslon_list"))
    return render_template("paslon_form.html", paslon=paslon, action="Ubah")


@bp.route("/paslon/<int:pid>/hapus", methods=["POST"])
def paslon_hapus(pid):
    addr = get_contract_address()
    payload = {"contract_address": addr, "fungsi": "hapus_paslon", "args": {"id": pid}}
    tx = admin_sign_tx(payload)
    status, resp = node_request("POST", "/transaksi", tx)
    if status not in (200, 201):
        flash(f"Gagal: {resp.get('error') if isinstance(resp, dict) else resp}", "danger")
        return redirect(url_for("main.paslon_list"))
    if current_app.config["AUTO_MINE"]:
        node_request("POST", "/mine", {})
    ok, msg = rebuild_state()
    if not ok:
        flash(f"Rebuild gagal: {msg}", "warning")
    flash("Paslon dinonaktifkan (soft delete).", "success")
    return redirect(url_for("main.paslon_list"))


@bp.route("/paslon/<int:pid>/riwayat")
def paslon_riwayat(pid):
    status, data = node_request("GET", "/chain")
    if status != 200 or not data:
        flash("Gagal mengambil chain.", "danger")
        return redirect(url_for("main.paslon_list"))
    chain = data.get("chain", [])
    riwayat = []
    for block in chain:
        for tx in block.get("transaksi", []):
            if tx.get("tipe") != "CONTRACT_CALL":
                continue
            payload = tx.get("payload", {})
            if payload.get("fungsi") in ("tambah_paslon", "ubah_paslon", "hapus_paslon"):
                args = payload.get("args", {})
                if args.get("id") == pid or (payload.get("fungsi") == "tambah_paslon" and args.get("nomor") == pid):
                    riwayat.append({
                        "block": block.get("index"),
                        "fungsi": payload.get("fungsi"),
                        "args": args,
                        "timestamp": tx.get("timestamp"),
                    })
    return render_template("paslon_riwayat.html", pid=pid, riwayat=riwayat)


@bp.route("/contract/deploy", methods=["POST"])
def contract_deploy():
    addr = deploy_contract(current_app.config["CONTRACT_NAME"])
    db.session.add(ContractMeta(address=addr, name=current_app.config["CONTRACT_NAME"]))
    db.session.commit()
    flash(f"Contract deployed: {addr}", "success")
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
    s1, chain_data = node_request("GET", "/chain")
    s2, peers_data = node_request("GET", "/peers")
    s3, tally_data = node_request("GET", "/tally")
    return render_template("node_status.html", chain=chain_data, peers=peers_data, tally=tally_data)