# Dokumentasi Sesi: Mode Interaktif & Auto-Discovery

Dokumen ini merangkum perubahan yang dilakukan pada sesi ini untuk menambahkan
mode interaktif dan auto-discovery pada node dan client blockchain voting Presma.

## 1. Tujuan

Menghilangkan kebutuhan perintah manual seperti:

```bash
python menu_node.py 5001 192.168.137.253:5002 4
```

dengan menyediakan:
- Node yang dapat start tanpa argumen, auto-pilih port, dan menemukan node lain di jaringan (hotspot) secara otomatis.
- Client dengan menu interaktif dan auto-discover node, serta dukungan banyak pemilih (NIM) dalam satu sesi.

## 2. File yang Diubah/Ditambah

| File | Perubahan |
| --- | --- |
| `node.py`, `menu_node.py` | Mode interaktif (`python menu_node.py`), auto-port, pemilihan interface, discovery UDP (port 9999), background resolve, menu manajemen node. Mode manual tetap ada. |
| `client.py`, `menu_client.py` | Menu interaktif (`python menu_client.py`), auto-discover node, multi-pemilih, semua fitur client tersedia di menu. Mode perintah lama tetap ada. |
| `README.md` | Penjelasan mode interaktif node & client. |
| `tests/test_node_helpers.py` | 6 unit test untuk helper & beacon processing. |
| `tests/__init__.py` | Package tests. |
| `docs/superpowers/specs/2026-11-26-auto-discovery-node-design.md` | Desain node. |
| `docs/superpowers/plans/2026-11-26-auto-discovery-node.md` | Plan implementasi node. |

## 3. Cara Menjalankan

### Node

```bash
python menu_node.py          # mode interaktif (auto-discovery)
python menu_node.py 5001     # mode manual (backward compat)
```

Node interaktif akan:
1. Memilih interface jaringan (otomatis jika satu; tanya jika >1, prioritas 192.168.137.x).
2. Mencari port kosong mulai 5001.
3. Menyiarkan keberadaan via UDP (port 9999) hanya di jaringan terpilih + loopback.
4. Menemukan node lain dengan difficulty & genesis yang sama.
5. Menyinkronkan chain otomatis (resolve).

### Client

```bash
python menu_client.py        # mode interaktif (auto-discover)
python menu_client.py vote localhost:5001 1 A12119001   # mode manual (NIM terdaftar, password dompet demo123)
```

Client interaktif menyediakan menu untuk memilih node, mengganti pemilih (NIM), vote, mine, tally, dan fitur pengujian.

## 4. Pengujian

```bash
python -m unittest tests.test_node_helpers -v
```

Hasil saat sesi ini: 6/6 lulus. Seluruh suite sekarang dijalankan dengan `python -m unittest discover -s tests`.

Pengujian integrasi manual:
- Dua node di mesin yang sama saling menemukan via discovery.
- Node yang terlambat start otomatis mengambil chain & rekap dari node yang sudah jalan.
- Client interaktif berhasil menemukan node, membuat dompet, mengirim vote, dan menampilkan tally.

## 6. Aplikasi Web (Flask) - CRUD Paslon

Web app terintegrasi dengan node via `NODE_URL`.

Jalankan minimal 2 node:

```bash
python menu_node.py 5001
python menu_node.py 5002 localhost:5001 4
```

Jalankan web app:

```powershell
python seed_demo.py localhost:5001
$env:NODE_URL = "http://localhost:5001"
python -m flask --app web.app run --port 5000
```

Buka `http://localhost:5000`. Fitur: alur pemilih (daftar, verifikasi kode email, masuk, bilik suara, bukti), papan pemilihan, explorer chain, dan ruang panitia di `/panitia` (password default `panitia-demo`): deploy contract, CRUD Paslon, riwayat, catat registrasi ke chain, buka/tutup/hitung, verify chain, rebuild state.

Node interaktif juga bisa dipakai; sesuaikan `NODE_URL` dengan port yang tampil.

## 7. Cara Penggunaan Terintegrasi (Node + Web + Client)

1. Jalankan node (manual atau interaktif):
   ```bash
   python menu_node.py 5001
   ```
2. Seed lalu jalankan web app:
   ```powershell
   python seed_demo.py localhost:5001
   $env:NODE_URL = "http://localhost:5001"
   python -m flask --app web.app run --port 5000
   ```
   Seed menambah Paslon 1 dan 2 serta mendaftarkan NIM contoh. Buka `http://localhost:5000/panitia` dan klik **Buka pemungutan**.
3. Jalankan client:
   ```bash
   python menu_client.py
   ```
   - Pilih node (auto-discover).
   - Pilih/ganti pemilih (NIM hasil seed, misalnya `A12119001`, password `demo123`).
   - Menu 4: pilih nomor paslon dari daftar (sesuai web).
   - Menu 7: mine.
   - Menu 10: tally (jumlah suara masuk; perolehan per paslon baru tampil setelah panitia menutup dan menghitung).
4. Uji checkpoint lain via menu client (validate, tamper, resolve, palsu) dan web (verify, rebuild).

## 5. Catatan

- Discovery memakai UDP broadcast; firewall/AP isolation dapat memblokirnya. Gunakan "Tambah peer manual" sebagai fallback.
- Data blockchain tetap disimpan di memori; restart node memerlukan `resolve`.
- Sinkronisasi latar hanya mengejar rantai yang lebih panjang; rantai yang dirusak dengan `tamper` dipulihkan lewat `resolve` manual.
- Mode manual lama tetap tersedia untuk keperluan checkpoint/laporan.
