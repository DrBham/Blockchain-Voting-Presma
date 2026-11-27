from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Paslon(db.Model):
    """Indeks state contract dari chain (dibangun ulang dengan rebuild_state), bukan sumber kebenaran."""
    __tablename__ = "paslon"
    id = db.Column(db.Integer, primary_key=True)
    nomor = db.Column(db.Integer, nullable=False)
    nama = db.Column(db.String(120), nullable=False)
    visi = db.Column(db.String(500), default="")
    aktif = db.Column(db.Boolean, default=True)
    block_number = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.now)


class Pemilih(db.Model):
    """Akun pemilih web. Rahasia tidak pernah disimpan polos: password dan kode pemilih berupa hash,
    kunci privat RSA terenkripsi dengan password pemilih (BestAvailableEncryption)."""
    __tablename__ = "pemilih"
    nim = db.Column(db.String(9), primary_key=True)
    email = db.Column(db.String(64), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    kunci_privat_enc = db.Column(db.Text, nullable=False)
    public_key = db.Column(db.Text, nullable=False)
    kode_hash = db.Column(db.String(255))
    kode_dikirim = db.Column(db.DateTime)
    salah_kode = db.Column(db.Integer, default=0, nullable=False)
    terverifikasi = db.Column(db.Boolean, default=False, nullable=False)
    kode_terpakai = db.Column(db.Boolean, default=False, nullable=False)
    signature_suara = db.Column(db.String(1024))
    dibuat = db.Column(db.DateTime, default=datetime.now)
