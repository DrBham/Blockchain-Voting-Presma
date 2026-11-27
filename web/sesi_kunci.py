"""Kunci privat pemilih yang sudah dibuka, disimpan di memori server (tidak pernah di cookie)."""
import secrets
import threading
import time

TTL = 900  # 15 menit

_kunci = {}
_lock = threading.Lock()


def _buang_kedaluwarsa(sekarang):
    for token in [t for t, (_, habis) in _kunci.items() if habis <= sekarang]:
        del _kunci[token]


def simpan(kunci):
    token = secrets.token_urlsafe(32)
    with _lock:
        sekarang = time.monotonic()
        _buang_kedaluwarsa(sekarang)
        _kunci[token] = (kunci, sekarang + TTL)
    return token


def ambil(token):
    """Kunci privat untuk token, atau None kalau tidak ada / sudah kedaluwarsa."""
    with _lock:
        _buang_kedaluwarsa(time.monotonic())
        isi = _kunci.get(token)
    return isi[0] if isi else None


def hapus(token):
    with _lock:
        _kunci.pop(token, None)
