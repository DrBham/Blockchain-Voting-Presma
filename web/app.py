import os
import secrets

from flask import Flask, abort, request, session

from web.config import DATABASE_URI, NODE_URL, AUTO_MINE, ADMIN_WALLET_PATH, CONTRACT_NAME
from web.models import db
from web.wallet import muat_atau_buat_admin


def token_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def cek_csrf():
    """Tolak POST tanpa token form yang cocok (mencegah situs lain memicu CRUD lewat browser)."""
    if request.method == "POST":
        token = request.form.get("csrf_token", "").encode()
        benar = session.get("csrf_token", "").encode()
        if not benar or not secrets.compare_digest(token, benar):
            abort(400, "token CSRF tidak valid, muat ulang halaman")


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["NODE_URL"] = NODE_URL
    app.config["AUTO_MINE"] = AUTO_MINE
    app.config["ADMIN_WALLET_PATH"] = ADMIN_WALLET_PATH
    app.config["CONTRACT_NAME"] = CONTRACT_NAME
    # Tanpa SECRET_KEY, kunci acak dipakai: cookie sesi tidak bisa dipalsukan, tapi reset saat restart.
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.before_request(cek_csrf)
    app.jinja_env.globals["csrf_token"] = token_csrf

    db.init_app(app)
    with app.app_context():
        db.create_all()
        pk, pub = muat_atau_buat_admin(ADMIN_WALLET_PATH)
        app.config["ADMIN_PRIVATE_KEY"] = pk
        app.config["ADMIN_PUBLIC_KEY"] = pub

    from web.routes import bp
    app.register_blueprint(bp)

    return app


if __name__ == "__main__":
    # Debugger Werkzeug bisa menjalankan kode sembarang: hanya aktif kalau diminta, dan default localhost saja.
    create_app().run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
