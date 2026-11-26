from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Paslon(db.Model):
    __tablename__ = "paslon"
    id = db.Column(db.Integer, primary_key=True)
    nomor = db.Column(db.Integer, nullable=False)
    nama = db.Column(db.String(120), nullable=False)
    visi = db.Column(db.String(500), default="")
    aktif = db.Column(db.Boolean, default=True)
    block_number = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

