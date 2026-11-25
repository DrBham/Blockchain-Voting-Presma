import os
from flask import Flask

from web.config import DATABASE_URI, NODE_URL, AUTO_MINE, ADMIN_WALLET_PATH, CONTRACT_NAME
from web.models import db
from web.wallet import muat_atau_buat_admin


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["NODE_URL"] = NODE_URL
    app.config["AUTO_MINE"] = AUTO_MINE
    app.config["ADMIN_WALLET_PATH"] = ADMIN_WALLET_PATH
    app.config["CONTRACT_NAME"] = CONTRACT_NAME
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

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
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)