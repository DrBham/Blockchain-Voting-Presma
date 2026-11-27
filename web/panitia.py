"""Ruang panitia: login, dasbor, aksi contract (Paslon, status pemilu), registrasi pemilih ke chain, verify, rebuild."""
import hashlib
import json
import secrets
import urllib.request
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from contract import riwayat_paslon
from node import Transaksi
from web import node_api
from web.app import info_node, wajib_panitia
from web.models import Paslon, Pemilih, db

bp = Blueprint("panitia", __name__)


def status_peer(peer):
    """GET /status langsung ke peer (host:port) dengan batas waktu pendek; None kalau tidak merespons."""
    try:
        with urllib.request.urlopen(f"http://{peer}/status", timeout=1.5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def nomor_kosong(paslon):
    """Nomor terkecil yang belum dipakai Paslon aktif (nomor Paslon nonaktif boleh dipakai lagi)."""
    dipakai = {p.nomor for p in paslon if p.aktif}
    return next(n for n in range(1, len(dipakai) + 2) if n not in dipakai)


def waktu(ts):
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return "-"
    return datetime.fromtimestamp(ts).strftime("%d-%m-%Y %H.%M.%S")


def hasil_aksi(error, berhasil):
    """Penolakan contract/node ditampilkan apa adanya; transaksi ditolak tidak membentuk block."""
    if error:
        flash(f"Ditolak: {error}. Tidak ada block baru", "danger")
    else:
        flash(berhasil, "success")
    return redirect(url_for("panitia.dasbor"))


@bp.route("/masuk", methods=["GET", "POST"])
def masuk():
    if request.method == "POST":
        # Bandingkan hash agar waktu pembandingan tidak bergantung panjang password.
        diketik = hashlib.sha256(request.form.get("password", "").encode()).digest()
        benar = hashlib.sha256(current_app.config["PANITIA_PASSWORD"].encode()).digest()
        if secrets.compare_digest(diketik, benar):
            session["panitia"] = True
            lanjut = request.args.get("lanjut", "")
            aman = lanjut.startswith("/") and not lanjut.startswith(("//", "/\\")) and "\\" not in lanjut
            return redirect(lanjut if aman else url_for("panitia.dasbor"))
        flash("Password panitia salah", "danger")
    return render_template("panitia/masuk.html")


@bp.route("/keluar")
def keluar():
    session.pop("panitia", None)
    flash("Kamu sudah keluar dari ruang panitia", "success")
    return redirect(url_for("publik.beranda"))


def tampil_dasbor(verify=None):
    info = info_node()
    if info and Paslon.query.count() == 0:
        node_api.rebuild_state()  # indeks SQLite kosong (mis. setelah seed_demo): isi otomatis dari chain
    paslon = Paslon.query.order_by(Paslon.nomor, Paslon.id).all()
    antrean = []
    for p in Pemilih.query.filter_by(terverifikasi=True).order_by(Pemilih.dibuat).all():
        status, data = node_api.node_request("GET", f"/pemilih/{node_api.kutip(p.nim)}")
        antrean.append({"nim": p.nim, "kunci": p.public_key,
                        "tercatat": bool(status == 200 and data.get("terdaftar"))})
    status, data = node_api.node_request("GET", "/peers")
    nodes = [{"alamat": current_app.config["NODE_URL"], "status": info, "ini": True}]
    nodes += [{"alamat": peer, "status": status_peer(peer), "ini": False}
              for peer in (data.get("peers", []) if status == 200 else [])]
    return render_template(
        "panitia/dasbor.html", menu="dasbor", info=info, verify=verify, nodes=nodes,
        aktif=[p for p in paslon if p.aktif], nonaktif=[p for p in paslon if not p.aktif],
        nomor_baru=nomor_kosong(paslon), antrean=antrean, menunggu=sum(not a["tercatat"] for a in antrean),
        alamat_contract=node_api.alamat_contract_di_chain() if info else None,
    )


@bp.route("/")
@wajib_panitia
def dasbor():
    return tampil_dasbor()


@bp.route("/verify")
@wajib_panitia
def verify():
    status, data = node_api.node_request("GET", "/validate")
    if status != 200:
        flash(f"Verify gagal: {node_api.pesan_error(data)}", "danger")
        return redirect(url_for("panitia.dasbor"))
    return tampil_dasbor(verify={**data, "waktu": datetime.now().strftime("%H.%M.%S")})


@bp.route("/deploy", methods=["POST"])
@wajib_panitia
def deploy():
    alamat, error = node_api.deploy_ke_chain()
    return hasil_aksi(error, f"Contract dideploy ke chain di alamat {alamat}")


def args_paslon():
    return {k: request.form.get(k, "").strip() for k in ("nomor", "nama", "visi")}


def block_paslon(pid=None, nomor=None):
    """Nomor block terakhir yang mengubah Paslon, dibaca dari indeks hasil rebuild."""
    p = db.session.get(Paslon, pid) if pid else Paslon.query.filter_by(nomor=nomor, aktif=True).first()
    return f" di block #{p.block_number}" if p else ""


@bp.route("/paslon/tambah", methods=["POST"])
@wajib_panitia
def paslon_tambah():
    args = args_paslon()
    error = node_api.panggil_contract("tambah_paslon", args)
    return hasil_aksi(error, f"Paslon {args['nomor']} ditambahkan{block_paslon(nomor=args['nomor'])}")


@bp.route("/paslon/<int:pid>/ubah", methods=["POST"])
@wajib_panitia
def paslon_ubah(pid):
    error = node_api.panggil_contract("ubah_paslon", {"id": pid, **args_paslon()})
    return hasil_aksi(error, f"Paslon diubah{block_paslon(pid)}")


@bp.route("/paslon/<int:pid>/hapus", methods=["POST"])
@wajib_panitia
def paslon_hapus(pid):
    error = node_api.panggil_contract("hapus_paslon", {"id": pid})
    return hasil_aksi(error, f"Paslon dinonaktifkan{block_paslon(pid)}, riwayatnya tetap di chain")


@bp.route("/paslon/<int:pid>/riwayat")
@wajib_panitia
def paslon_riwayat(pid):
    status, data = node_api.node_request("GET", "/chain")
    if status != 200:
        flash(f"Gagal mengambil chain: {node_api.pesan_error(data)}", "danger")
        return redirect(url_for("panitia.dasbor"))
    riwayat = riwayat_paslon(data.get("chain", []), pid)
    for r in riwayat:
        r["waktu"] = waktu(r["timestamp"])
    return render_template("panitia/riwayat.html", menu="dasbor", pid=pid, riwayat=riwayat,
                           paslon=db.session.get(Paslon, pid))


@bp.route("/catat", methods=["POST"])
@wajib_panitia
def catat():
    """REGISTER semua pemilih terverifikasi yang belum ada di chain, lalu tambang sekali (satu block)."""
    terkirim, gagal = 0, []
    for p in Pemilih.query.filter_by(terverifikasi=True).all():
        status, data = node_api.node_request("GET", f"/pemilih/{node_api.kutip(p.nim)}")
        if status != 200 or data.get("terdaftar"):
            continue
        tx = Transaksi("admin", None, current_app.config["ADMIN_PUBLIC_KEY"], tipe="REGISTER",
                       payload={"nim": p.nim, "public_key": p.public_key})
        tx.tanda_tangani(current_app.config["ADMIN_PRIVATE_KEY"])
        error = node_api.kirim_tx(tx, tambang_langsung=False)
        if error:
            gagal.append(f"{p.nim}: {error}")
        else:
            terkirim += 1
    for g in gagal:
        flash(f"Ditolak: {g}", "danger")
    if not terkirim:
        flash("Tidak ada registrasi baru yang dicatat", "warning")
        return redirect(url_for("panitia.dasbor"))
    error = node_api.tambang()
    return hasil_aksi(error, f"{terkirim} registrasi dicatat ke chain")


@bp.route("/buka", methods=["POST"])
@wajib_panitia
def buka():
    return hasil_aksi(node_api.panggil_contract("buka_pemungutan", {}), "Pemungutan dibuka")


@bp.route("/tutup", methods=["POST"])
@wajib_panitia
def tutup():
    # Suara yang masih di pool ditambang dulu, supaya tidak ada yang tertinggal setelah status ditutup.
    error = node_api.tambang()
    if error:
        flash(f"Pool belum bisa ditambang: {error}. Pemungutan belum ditutup", "danger")
        return redirect(url_for("panitia.dasbor"))
    return hasil_aksi(node_api.panggil_contract("tutup_pemungutan", {}), "Pemungutan ditutup")


@bp.route("/hitung", methods=["POST"])
@wajib_panitia
def hitung():
    berkas = Path(current_app.config["KUNCI_PEMILU_PATH"])
    if not berkas.exists():
        flash(f"Berkas kunci pemilu tidak ditemukan: {berkas}", "danger")
        return redirect(url_for("panitia.dasbor"))
    error = node_api.panggil_contract("buka_kunci", {"kunci_privat": berkas.read_text()})
    return hasil_aksi(error, "Kunci pemilu dibuka, hasil bisa dilihat di papan pemilihan")


@bp.route("/rebuild", methods=["POST"])
@wajib_panitia
def rebuild():
    ok, msg = node_api.rebuild_state()
    if not ok:
        flash(f"Rebuild gagal: {msg}", "danger")
    else:
        flash(f"State dibangun ulang dari chain: {Paslon.query.count()} Paslon", "success")
    return redirect(url_for("panitia.dasbor"))
