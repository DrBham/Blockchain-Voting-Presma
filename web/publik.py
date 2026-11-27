"""Halaman publik tanpa login: beranda, papan pemilihan live, explorer chain (plus demo tamper khusus panitia)."""
from collections import Counter
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from web import node_api
from web.app import LABEL_STATUS, wajib_panitia

bp = Blueprint("publik", __name__)

BATAS_BLOCK = 50  # explorer menampilkan block terbaru saja; sisanya lewat pencarian


def ambil_chain():
    status, data = node_api.node_request("GET", "/chain")
    return data if status == 200 else None


def suara_per_jam(chain):
    """Jumlah VOTE per jam dari timestamp transaksi di chain (isi pilihan tidak dibaca)."""
    jam = Counter(
        datetime.fromtimestamp(tx["timestamp"]).strftime("%H.00")
        for b in chain for tx in b.get("transaksi", [])
        if tx.get("tipe") == "VOTE" and isinstance(tx.get("timestamp"), (int, float))
    )
    return [{"jam": j, "jumlah": n} for j, n in sorted(jam.items())]


@bp.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="logo-untad.png"))


def data_papan():
    """Isi papan sesuai status. Angka per Paslon hanya ikut saat status dihitung."""
    status, st = node_api.node_request("GET", "/status")
    if status != 200:
        return {"status": None, "error": node_api.pesan_error(st)}
    _, ps = node_api.node_request("GET", "/paslon")
    paslon = sorted(({"nomor": p["nomor"], "nama": p["nama"], "visi": p.get("visi", "")}
                     for p in ps.get("paslon", []) if p.get("aktif")), key=lambda p: p["nomor"])
    data = {
        "status": st["status"], "label": LABEL_STATUS.get(st["status"], st["status"]),
        "terdaftar": st.get("terdaftar", 0), "suara_masuk": st.get("suara_masuk", 0),
        "panjang": st.get("panjang"), "block_terakhir": st.get("block_terakhir"), "paslon": paslon,
        "per_jam": None, "hasil": None, "tidak_sah": None, "per_block": None,
    }
    if st["status"] == "dibuka":
        chain = ambil_chain()
        data["per_jam"] = suara_per_jam(chain["chain"]) if chain else []
    if st["status"] == "dihitung":
        # hasil dari rantai yang rusak tidak boleh tampil sebagai hasil akhir
        _, cek = node_api.node_request("GET", "/validate")
        if not cek.get("valid", False):
            data["peringatan"] = f"Rantai di node ini tidak valid mulai block #{cek.get('index_rusak')}. Hasil ditahan sampai rantai dipulihkan dari node lain"
            return data
        status, tally = node_api.node_request("GET", "/tally")
        if status == 200:
            data.update(hasil=tally.get("hasil"), tidak_sah=tally.get("tidak_sah"), per_block=tally.get("per_block"))
    return data


def ringkas_tx(tx):
    """Isi transaksi untuk explorer. Pilihan VOTE tetap terenkripsi: yang tampil NIM dan potongan sandi."""
    tipe, payload = tx.get("tipe", "VOTE"), tx.get("payload") or {}
    if tipe == "VOTE":
        isi = f"NIM {tx.get('voter_id')} · sandi {str(payload.get('sandi', ''))[:16]}…"
    elif tipe == "REGISTER":
        isi = f"NIM {payload.get('nim')}"
    elif tipe == "CONTRACT_DEPLOY":
        isi = f"{payload.get('nama')} di {str(payload.get('contract_address', ''))[:12]}…"
    else:
        args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        args = {k: ("(PEM kunci pemilu)" if k == "kunci_privat" else v) for k, v in args.items()}
        isi = f"{payload.get('fungsi')}({', '.join(f'{k}={v}' for k, v in args.items())})"
    return {"tipe": tipe, "isi": isi, "signature": str(tx.get("signature", ""))[:24]}


def data_explorer(q=""):
    chain = ambil_chain()
    if chain is None:
        return None
    status, v = node_api.node_request("GET", "/validate")
    valid = v if status == 200 else {"valid": None, "index_rusak": None, "alasan": node_api.pesan_error(v)}
    rusak = valid.get("index_rusak")
    blocks = []
    for b in reversed(chain["chain"]):
        if q and not (q.lstrip("#").isdigit() and int(q.lstrip("#")) == b["index"]
                      or b["hash"].startswith(q.lower())):
            continue
        blocks.append({
            "index": b["index"], "nonce": b["nonce"], "hash": b["hash"], "previous_hash": b["previous_hash"],
            "waktu": datetime.fromtimestamp(b["timestamp"]).strftime("%d-%m-%Y %H.%M.%S"),
            "transaksi": [ringkas_tx(tx) for tx in b.get("transaksi", [])],
            "rusak": None if rusak is None or b["index"] < rusak else ("ini" if b["index"] == rusak else "setelah"),
        })
    return {"panjang": chain["panjang"], "difficulty": chain["difficulty"], "valid": valid.get("valid"),
            "index_rusak": rusak, "alasan": valid.get("alasan"), "blocks": blocks[:BATAS_BLOCK]}


@bp.route("/")
def beranda():
    chain = ambil_chain()
    terakhir = chain["chain"][-3:] if chain else []
    return render_template("publik/beranda.html", terakhir=terakhir, difficulty=chain["difficulty"] if chain else 4)


@bp.route("/papan")
def papan():
    return render_template("publik/papan.html", menu="papan")


@bp.route("/api/papan")
def api_papan():
    return jsonify(data_papan())


@bp.route("/explorer")
def explorer():
    q = request.args.get("q", "").strip()
    return render_template("publik/explorer.html", menu="explorer", q=q, data=data_explorer(q))


@bp.route("/api/explorer")
def api_explorer():
    return jsonify(data_explorer(request.args.get("q", "").strip()))


@bp.route("/explorer/tamper", methods=["POST"])
@wajib_panitia
def tamper():
    """Demo checkpoint 9: node mengubah isi block lama tanpa menambang ulang, lalu validasi mendeteksinya."""
    index = request.form.get("index", "")
    status, data = node_api.node_request("POST", "/tamper", {"index": index})
    if status == 200:
        flash(f"Isi block #{index} diubah tanpa menambang ulang: {data.get('pesan')}", "success")
    else:
        flash(f"Tamper ditolak: {node_api.pesan_error(data)}", "danger")
    return redirect(url_for("publik.explorer"))
