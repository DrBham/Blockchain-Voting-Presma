"""Kirim kode pemilih lewat SMTP (Mailpit saat demo). Gagal kirim tidak menghentikan demo."""
import smtplib
from email.message import EmailMessage

from flask import current_app


def kirim_kode(email, kode):
    """True kalau email terkirim. Kalau SMTP gagal, kode dicetak di terminal web dan False."""
    cfg = current_app.config
    pesan = EmailMessage()
    pesan["Subject"] = "Kode pemilih Pemira Presma"
    pesan["From"] = cfg["MAIL_FROM"]
    pesan["To"] = email
    pesan.set_content(
        f"Kode pemilihmu: {kode}\n\n"
        "Kode ini mengaktifkan akun dan dipakai lagi saat masuk ke bilik suara. "
        "Simpan baik-baik dan jangan bagikan ke siapa pun.\n"
    )
    try:
        with smtplib.SMTP(cfg["MAIL_HOST"], cfg["MAIL_PORT"], timeout=5) as smtp:
            smtp.send_message(pesan)
        return True
    except (OSError, smtplib.SMTPException) as e:
        print(f"[EMAIL GAGAL] SMTP {cfg['MAIL_HOST']}:{cfg['MAIL_PORT']} ({e}). Kode pemilih untuk {email}: {kode}", flush=True)
        return False
