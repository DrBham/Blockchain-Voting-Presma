"""Blueprint pemilih: daftar -> verifikasi email -> masuk -> bilik suara -> bukti."""
import math
import secrets
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from contract import enkripsi_pilihan
from node import FAKULTAS_UNTAD, POLA_NIM, Transaksi
from web import node_api, sesi_kunci, surel
from web.models import Pemilih, db

bp = Blueprint("pemilih", __name__)

BATAS_SALAH = 5
JEDA_KIRIM_ULANG = 60
# Akun yang belum diverifikasi dikunci selama ini; setelahnya boleh didaftar ulang (mis. bila orang lain
# sempat mendaftarkan NIM kita, ia tetap tidak bisa verifikasi karena kode dikirim ke email kita).
MASA_TUNGGU_VERIFIKASI = 15 * 60
NODE_MATI = "Node tidak terjangkau. Coba lagi sebentar lagi"
ALASAN_STATUS = {
    "persiapan": "Pemungutan suara belum dibuka panitia. Kembali lagi saat pemungutan dibuka",
    "ditutup": "Pemungutan suara sudah ditutup. Suara baru tidak diterima lagi",
    "dihitung": "Pemungutan sudah selesai dan suara sudah dihitung",
}


# ---------------------------------------------------------------- bantuan

def salah_nim(nim):
    """Pola NIM + kode fakultas, aturan yang sama dengan validator node. None kalau sah."""
    if not POLA_NIM.fullmatch(nim):
        return "NIM harus 1 huruf kode fakultas diikuti 7 atau 8 angka"
    if nim[0] not in FAKULTAS_UNTAD:
        return f"Kode fakultas '{nim[0]}' tidak terdaftar di UNTAD"
    return None


def info_pemilih(nim):
    """Isi GET /pemilih/<nim> (terdaftar, sudah_memilih), atau None kalau node tidak terjangkau."""
    status, data = node_api.node_request("GET", f"/pemilih/{node_api.kutip(nim)}")
    return data if status == 200 else None


def paslon_aktif():
    status, data = node_api.node_request("GET", "/paslon")
    if status != 200:
        return []
    return sorted((p for p in data.get("paslon", []) if p.get("aktif")), key=lambda p: p["nomor"])


def kirim_kode_baru(p):
    """Kode baru menggantikan kode lama (yang lama langsung hangus). Hanya hash yang disimpan."""
    kode = f"{secrets.randbelow(10 ** 6):06d}"
    p.kode_hash = generate_password_hash(kode)
    p.kode_dikirim = datetime.now()
    p.salah_kode = 0
    db.session.commit()
    surel.kirim_kode(p.email, kode)


def sisa_jeda(p):
    """Detik sampai kirim ulang boleh lagi (0 = boleh)."""
    if not p.kode_dikirim:
        return 0
    return max(0, math.ceil(JEDA_KIRIM_ULANG - (datetime.now() - p.kode_dikirim).total_seconds()))


def cek_kode(p, kode):
    """None kalau kode benar, selain itu pesan untuk pemilih. Salah ke-5 menghanguskan kode."""
    if p.salah_kode >= BATAS_SALAH:
        return "Kode sudah hangus karena 5 kali salah. Kirim ulang kode baru"
    if p.kode_hash and len(kode) == 6 and check_password_hash(p.kode_hash, kode):
        return None
    p.salah_kode += 1
    db.session.commit()
    sisa = BATAS_SALAH - p.salah_kode
    return f"Kode salah. Sisa {sisa} percobaan" if sisa else "Kode salah 5 kali dan sudah hangus. Kirim ulang kode baru"


def kirim_ulang(p):
    """Pesan error, atau None kalau kode baru terkirim."""
    sisa = sisa_jeda(p)
    if sisa:
        return f"Tunggu {sisa} detik sebelum kirim ulang"
    kirim_kode_baru(p)
    flash(f"Kode baru dikirim ke {p.email}. Kode lama sudah tidak berlaku", "info")
    return None


def alasan_bilik_tutup(nim):
    """(alasan, status_node). Alasan None berarti NIM ini boleh memilih sekarang."""
    st = node_api.status_node()
    if st is None:
        return NODE_MATI, None
    if st.get("status") != "dibuka":
        return ALASAN_STATUS.get(st.get("status"), "Pemungutan suara tidak sedang dibuka"), st
    info = info_pemilih(nim)
    if info is None:
        return NODE_MATI, st
    if not info["terdaftar"]:
        return "Akun belum dicatat panitia ke chain. Tunggu panitia mencatat kunci publikmu, lalu muat ulang halaman ini", st
    if info["sudah_memilih"]:
        return "NIM ini sudah memilih. Satu NIM hanya satu suara", st
    return None, st


def pemilih_sesi():
    nim = session.get("nim")
    return db.session.get(Pemilih, nim) if nim else None


# ---------------------------------------------------------------- rute

@bp.route("/daftar", methods=["GET", "POST"])
def daftar():
    galat = {}
    nim = request.form.get("nim", "").strip().upper()
    if request.method == "POST":
        pw, pw2 = request.form.get("pw", ""), request.form.get("pw2", "")
        lama = None
        # Tidak ada DPT: bukti mahasiswa aktif = bisa menerima kode di NIM@untad.ac.id.
        galat["nim"] = salah_nim(nim)
        if not galat["nim"]:
            lama = db.session.get(Pemilih, nim)
            info = info_pemilih(nim)
            if lama and lama.terverifikasi:
                galat["nim"] = "NIM ini sudah punya akun. Silakan masuk"
            elif lama and lama.kode_dikirim and                     (datetime.now() - lama.kode_dikirim).total_seconds() < MASA_TUNGGU_VERIFIKASI:
                galat["nim"] = "NIM ini sedang menunggu verifikasi. Cek email kampus, atau coba lagi setelah 15 menit"
            elif info is None:
                galat["nim"] = NODE_MATI
            elif info["terdaftar"]:
                galat["nim"] = "NIM ini sudah tercatat di chain dengan kunci lain, jadi tidak bisa mendaftar lewat web"
        if len(pw) < 8:
            galat["pw"] = "Minimal 8 karakter"
        if not pw2 or pw2 != pw:
            galat["pw2"] = "Belum sama dengan password"
        galat = {k: v for k, v in galat.items() if v}
        if not galat:
            kunci = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            p = lama or Pemilih(nim=nim)
            p.email = f"{nim}@untad.ac.id"  # email kampus selalu dari NIM, isian form diabaikan
            p.password_hash = generate_password_hash(pw)
            p.kunci_privat_enc = kunci.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.BestAvailableEncryption(pw.encode()),
            ).decode()
            p.public_key = kunci.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            p.terverifikasi = p.kode_terpakai = False
            p.signature_suara = None
            db.session.add(p)
            kirim_kode_baru(p)
            session["nim_daftar"] = nim
            return redirect(url_for(".verifikasi"))
    return render_template("pemilih/daftar.html", nim=nim, galat=galat)


@bp.route("/verifikasi", methods=["GET", "POST"])
def verifikasi():
    nim = session.get("nim_daftar")
    p = db.session.get(Pemilih, nim) if nim else None
    if not p:
        flash("Daftar dulu untuk mendapat kode pemilih", "info")
        return redirect(url_for(".daftar"))
    if p.terverifikasi:
        return redirect(url_for(".masuk"))
    galat = None
    if request.method == "POST":
        if request.form.get("aksi") == "kirim_ulang":
            galat = kirim_ulang(p)
            if not galat:
                return redirect(url_for(".verifikasi"))
        else:
            galat = cek_kode(p, "".join(request.form.getlist("kode")).strip())
            if not galat:
                p.terverifikasi = True
                p.salah_kode = 0
                db.session.commit()
                flash("Akun aktif. Simpan kode pemilih ini untuk masuk dan memilih", "info")
                return redirect(url_for(".masuk"))
    return render_template("pemilih/verifikasi.html", email=p.email, galat=galat, sisa=sisa_jeda(p))


@bp.route("/masuk", methods=["GET", "POST"])
def masuk():
    galat = {}
    # NIM dari pendaftaran hanya diisikan sekali, supaya pengguna berikutnya di komputer yang sama tidak melihatnya
    nim = (request.form.get("nim") if request.method == "POST" else session.pop("nim_daftar", "")) or ""
    nim = nim.strip().upper()
    if request.method == "POST":
        p = db.session.get(Pemilih, nim)
        pw = request.form.get("pw", "")
        if not p or not check_password_hash(p.password_hash, pw):
            galat["pw"] = "NIM atau password salah"
        elif not p.terverifikasi:
            session["nim_daftar"] = nim
            flash("Akun belum aktif. Masukkan kode dari email pendaftaran", "info")
            return redirect(url_for(".verifikasi"))
        elif p.kode_terpakai:
            session["nim"] = nim  # boleh lihat bukti, tapi tanpa kunci: bilik tidak terbuka lagi
            return render_template("pemilih/masuk.html", nim=nim, galat={}, sudah_memilih=True)
        elif request.form.get("aksi") == "kirim_ulang":
            galat["kode"] = kirim_ulang(p)
        else:
            galat["kode"] = cek_kode(p, "".join(request.form.getlist("kode")).strip())
            if not galat["kode"]:
                kunci = serialization.load_pem_private_key(p.kunci_privat_enc.encode(), password=pw.encode())
                p.salah_kode = 0
                db.session.commit()
                if session.get("kunci"):
                    sesi_kunci.hapus(session["kunci"])
                session["nim"] = nim
                session["kunci"] = sesi_kunci.simpan(kunci)  # cookie hanya membawa token, kuncinya di memori server
                return redirect(url_for(".bilik"))
    return render_template("pemilih/masuk.html", nim=nim, galat=galat, sudah_memilih=False)


@bp.route("/bilik", methods=["GET", "POST"])
def bilik():
    p = pemilih_sesi()
    if not p:
        flash("Masuk dulu untuk membuka bilik suara", "info")
        return redirect(url_for(".masuk"))
    if p.kode_terpakai:
        return redirect(url_for(".bukti"))
    kunci = sesi_kunci.ambil(session.get("kunci", ""))
    if kunci is None:
        session.pop("kunci", None)
        flash("Sesi bilik habis, masuk lagi", "warning")
        return redirect(url_for(".masuk"))

    alasan, st = alasan_bilik_tutup(p.nim)
    paslon = [] if alasan else paslon_aktif()
    if request.method == "POST" and not alasan:
        nomor = request.form.get("paslon", "")
        if nomor not in {str(x["nomor"]) for x in paslon}:
            flash("Pilih satu pasangan calon dulu", "danger")
            return redirect(url_for(".bilik"))
        tx = Transaksi(p.nim, None, p.public_key, tipe="VOTE",
                       payload={"sandi": enkripsi_pilihan(int(nomor), st["kunci_pemilu"])})
        tx.tanda_tangani(kunci)
        # Tandai kode terpakai dulu dalam satu UPDATE: klik ganda atau tab kedua tidak lolos ke node.
        diambil = Pemilih.query.filter_by(nim=p.nim, kode_terpakai=False).update(
            {"kode_terpakai": True, "signature_suara": tx.signature})
        db.session.commit()
        if not diambil:
            return redirect(url_for(".bukti"))
        error = node_api.kirim_tx(tx)
        if error:
            Pemilih.query.filter_by(nim=p.nim).update({"kode_terpakai": False, "signature_suara": None})
            db.session.commit()
            flash(f"Suara belum terkirim: {error}", "danger")
            return redirect(url_for(".bilik"))
        sesi_kunci.hapus(session.pop("kunci"))
        return redirect(url_for(".bukti"))
    return render_template("pemilih/bilik.html", alasan=alasan, paslon=paslon)


@bp.route("/bukti")
def bukti():
    p = pemilih_sesi()
    if not p or not p.kode_terpakai:
        flash("Belum ada suara dari sesi ini. Masuk dulu", "info")
        return redirect(url_for(".masuk"))
    return render_template("pemilih/bukti.html", signature=p.signature_suara)


@bp.route("/api/tx-status")
def tx_status():
    """Proxy GET /tx/<signature> untuk polling halaman bukti. Pilihan tidak pernah ikut."""
    p = pemilih_sesi()
    if not p or not p.signature_suara:
        return jsonify({"status": "tidak_ada", "block": None}), 404
    status, data = node_api.node_request("GET", f"/tx/{node_api.kutip(p.signature_suara)}")
    if status != 200:
        return jsonify({"error": node_api.pesan_error(data)}), 502
    hasil = {"status": data.get("status"), "block": data.get("block")}
    if hasil["status"] == "block":
        # shortcut: hash dan nonce diambil dari /chain utuh, cukup untuk chain demo; ganti bila node punya /block/<n>
        kode, chain = node_api.node_request("GET", "/chain")
        blok = next((b for b in chain.get("chain", []) if b.get("index") == hasil["block"]), None) if kode == 200 else None
        if blok:
            hasil.update(hash=blok.get("hash"), nonce=blok.get("nonce"), panjang=len(chain["chain"]))
    return jsonify(hasil)


@bp.route("/keluar", methods=["GET", "POST"])
def keluar():
    if session.get("kunci"):
        sesi_kunci.hapus(session["kunci"])
    session.clear()
    flash("Kamu sudah keluar", "info")
    return redirect(url_for(".masuk"))
