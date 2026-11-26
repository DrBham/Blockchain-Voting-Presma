# Dokumentasi Sesi: Mode Interaktif & Auto-Discovery

Dokumen ini merangkum perubahan yang dilakukan pada sesi ini untuk menambahkan
mode interaktif dan auto-discovery pada node dan client blockchain voting Presma.

## 1. Tujuan

Menghilangkan kebutuhan perintah manual seperti:

```bash
python node.py 5001 192.168.137.253:5002 4
```

dengan menyediakan:
- Node yang dapat start tanpa argumen, auto-pilih port, dan menemukan node lain di jaringan (hotspot) secara otomatis.
- Client dengan menu interaktif dan auto-discover node, serta dukungan banyak pemilih (NIM) dalam satu sesi.

## 2. File yang Diubah/Ditambah

| File | Perubahan |
| --- | --- |
| `node.py` | Mode interaktif (`python node.py`), auto-port, pemilihan interface, discovery UDP (port 9999), background resolve, menu manajemen node. Mode manual tetap ada. |
| `client.py` | Menu interaktif (`python client.py`), auto-discover node, multi-pemilih, semua fitur client tersedia di menu. Mode perintah lama tetap ada. |
| `README.md` | Penjelasan mode interaktif node & client. |
| `tests/test_node_helpers.py` | 6 unit test untuk helper & beacon processing. |
| `tests/__init__.py` | Package tests. |
| `docs/superpowers/specs/2026-11-26-auto-discovery-node-design.md` | Desain node. |
| `docs/superpowers/plans/2026-11-26-auto-discovery-node.md` | Plan implementasi node. |

## 3. Cara Menjalankan

### Node

```bash
python node.py          # mode interaktif (auto-discovery)
python node.py 5001     # mode manual (backward compat)
```

Node interaktif akan:
1. Memilih interface jaringan (otomatis jika satu; tanya jika >1, prioritas 192.168.137.x).
2. Mencari port kosong mulai 5001.
3. Menyiarkan keberadaan via UDP (port 9999) hanya di jaringan terpilih + loopback.
4. Menemukan node lain dengan difficulty & genesis yang sama.
5. Menyinkronkan chain otomatis (resolve).

### Client

```bash
python client.py        # mode interaktif (auto-discover)
python client.py vote localhost:5001 "Paslon 1" F55125001   # mode manual
```

Client interaktif menyediakan menu untuk memilih node, mengganti pemilih (NIM), vote, mine, tally, dan fitur pengujian.

## 4. Pengujian

```bash
python -m unittest tests.test_node_helpers -v
```

Hasil: 6/6 lulus.

Pengujian integrasi manual:
- Dua node di mesin yang sama saling menemukan via discovery.
- Node yang terlambat start otomatis mengambil chain & rekap dari node yang sudah jalan.
- Client interaktif berhasil menemukan node, membuat dompet, mengirim vote, dan menampilkan tally.

## 6. Aplikasi Web (Flask) - CRUD Paslon

Web app terintegrasi dengan node via `NODE_URL`.

Jalankan minimal 2 node:

```bash
python node.py 5001
python node.py 5002 localhost:5001 4
```

Jalankan web app:

```bash
set NODE_URL=http://localhost:5001
set AUTO_MINE=true
python -m flask --app web.app run --port 5000
```

Buka `http://localhost:5000`. Fitur: dashboard, CRUD Paslon, deploy smart contract, riwayat, verifikasi chain, rebuild state, status node.

Node interaktif juga bisa dipakai; sesuaikan `NODE_URL` dengan port yang tampil.

## 7. Cara Penggunaan Terintegrasi (Node + Web + Client)

1. Jalankan node (manual atau interaktif):
   ```bash
   python node.py 5001
   ```
2. Jalankan web app:
   ```bash
   set NODE_URL=http://localhost:5001
   set AUTO_MINE=true
   python -m flask --app web.app run --port 5000
   ```
   Buka `http://localhost:5000`, tambahkan Paslon (mis. nomor 7, nama King Dimss).
3. Jalankan client:
   ```bash
   python client.py
   ```
   - Pilih node (auto-discover).
   - Pilih/ganti pemilih (NIM).
   - Menu 4: pilih nomor paslon dari daftar (sesuai web).
   - Menu 7: mine.
   - Menu 10: tally (nama paslon + jumlah suara).
4. Uji checkpoint lain via menu client (validate, tamper, resolve, palsu) dan web (verify, rebuild).

## 5. Catatan

- Discovery memakai UDP broadcast; firewall/AP isolation dapat memblokirnya. Gunakan "Tambah peer manual" sebagai fallback.
- Data blockchain tetap disimpan di memori; restart node memerlukan `resolve`.
- Mode manual lama tetap tersedia untuk keperluan checkpoint/laporan.
