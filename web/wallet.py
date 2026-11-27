from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _muat_atau_buat(path):
    """Kunci RSA 2048 dari berkas PEM; dibuat (izin 600) kalau belum ada."""
    berkas = Path(path)
    if berkas.exists():
        return serialization.load_pem_private_key(berkas.read_bytes(), password=None)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    berkas.write_bytes(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    try:
        berkas.chmod(0o600)
    except OSError:
        pass
    return private_key


def _publik_pem(private_key):
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def muat_atau_buat_admin(path):
    """Kunci admin (pemilik contract). Mengembalikan (private_key, public_key_pem)."""
    private_key = _muat_atau_buat(path)
    return private_key, _publik_pem(private_key)


def muat_atau_buat_kunci_pemilu(path):
    """Kunci pemilu untuk enkripsi pilihan. Mengembalikan (privat_pem, publik_pem) sebagai teks."""
    private_key = _muat_atau_buat(path)
    privat_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return privat_pem, _publik_pem(private_key)
