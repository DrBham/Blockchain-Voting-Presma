import functools
import os
import secrets

from flask import Flask, abort, flash, redirect, request, session, url_for

from web import config
from web.models import db
from web.wallet import muat_atau_buat_admin


def token_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def cek_csrf():
    """Tolak POST tanpa token form yang cocok (mencegah situs lain memicu aksi lewat browser)."""
    if request.method == "POST":
        token = (request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or "").encode()
        benar = session.get("csrf_token", "").encode()
        if not benar or not secrets.compare_digest(token, benar):
            abort(400, "token CSRF tidak valid, muat ulang halaman")


def panitia_masuk():
    return session.get("panitia") is True


def wajib_panitia(fungsi):
    """Halaman dan aksi panitia hanya untuk yang sudah masuk dengan PANITIA_PASSWORD."""
    @functools.wraps(fungsi)
    def bungkus(*args, **kwargs):
        if not panitia_masuk():
            flash("Masuk sebagai panitia dulu", "warning")
            return redirect(url_for("panitia.masuk", lanjut=request.path))
        return fungsi(*args, **kwargs)
    return bungkus


def info_node():
    """Isi /status node untuk rel dan sidebar, cukup sekali per permintaan halaman."""
    from flask import g
    from web.node_api import status_node
    if "info_node" not in g:
        g.info_node = status_node()
    return g.info_node


LABEL_STATUS = {"persiapan": "Belum dibuka", "dibuka": "Pemungutan dibuka",
                "ditutup": "Pemungutan ditutup", "dihitung": "Suara sudah dihitung"}


def create_app(uji=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=config.DATABASE_URI,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        NODE_URL=config.NODE_URL,
        AUTO_MINE=config.AUTO_MINE,
        ADMIN_WALLET_PATH=config.ADMIN_WALLET_PATH,
        CONTRACT_NAME=config.CONTRACT_NAME,
        KUNCI_PEMILU_PATH=config.KUNCI_PEMILU_PATH,
        PANITIA_PASSWORD=config.PANITIA_PASSWORD,
        MAIL_HOST=config.MAIL_HOST,
        MAIL_PORT=config.MAIL_PORT,
        MAIL_FROM=config.MAIL_FROM,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if uji:
        app.config.update(uji)  # tes: basis data sementara, berkas kunci di folder tmp
    # Tanpa SECRET_KEY, kunci acak dipakai: cookie sesi tidak bisa dipalsukan, tapi reset saat restart.
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.before_request(cek_csrf)
    app.jinja_env.globals.update(csrf_token=token_csrf, panitia_masuk=panitia_masuk,
                                 info_node=info_node, LABEL_STATUS=LABEL_STATUS)

    db.init_app(app)
    with app.app_context():
        from web import models  # noqa: F401  (semua model terdaftar sebelum create_all)
        db.create_all()
        pk, pub = muat_atau_buat_admin(app.config["ADMIN_WALLET_PATH"])
        app.config["ADMIN_PRIVATE_KEY"] = pk
        app.config["ADMIN_PUBLIC_KEY"] = pub

    from web.panitia import bp as bp_panitia
    from web.pemilih import bp as bp_pemilih
    from web.publik import bp as bp_publik
    app.register_blueprint(bp_publik)
    app.register_blueprint(bp_pemilih)
    app.register_blueprint(bp_panitia, url_prefix="/panitia")
    return app


if __name__ == "__main__":
    # Debugger Werkzeug bisa menjalankan kode sembarang: hanya aktif kalau diminta, dan default localhost saja.
    create_app().run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
