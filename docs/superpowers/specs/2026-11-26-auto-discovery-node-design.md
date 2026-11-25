# Design: Auto-Discovery Node + Interactive Menu (Blockchain Voting Presma)

**Date:** 2026-11-26
**Project:** Blockchain---Voting-Presma
**Status:** Draft for approval (rev 2)

## 1. Intent & Why

Saat ini menjalankan node terdistribusi membutuhkan perintah manual:

```
python node.py 5001 192.168.137.253:5002 4
```

User harus tahu IP/port peer dan difficulty. Tujuan fitur ini: **node dapat start tanpa argumen, auto-pilih port kosong, menemukan node lain di jaringan hotspot yang sama secara otomatis di background, dan menyediakan menu interaktif** untuk manajemen node. Mode manual tetap ada untuk keperluan checkpoint/laporan.

Catatan jaringan: perangkat terhubung ke **hotspot laptop**, jadi discovery hanya boleh memakai interface jaringan yang dipilih (bukan scan/broadcast semua interface). Node yang terlambat start harus langsung menemukan node yang sudah jalan dan menyinkronkan chain (longest-chain rule) tanpa perintah manual.

## 2. Goals

- Start node tanpa argumen → masuk mode interaktif.
- Auto-pilih port HTTP kosong (mulai 5001, naik sampai tersedia).
- Auto-discovery peer hanya pada interface jaringan yang dipilih (hotspot), via UDP broadcast, di background.
- Hanya menghubungkan node dengan difficulty & genesis hash yang cocok.
- Saat node baru menemukan peer, langsung mencoba sinkronisasi (resolve) agar data terbarui.
- Menu interaktif untuk: status node, daftar peer, refresh discovery, tambah peer manual, tampilkan alamat untuk client, hentikan node.
- Backward compat: `python node.py <port> [peers] [difficulty]` tetap bekerja.

## 3. Non-Goals

- Tidak membuat web UI.
- Tidak mengubah protokol blockchain / validasi / PoW.
- Tidak menambah dependency eksternal (tetap stdlib + cryptography).
- Tidak mengintegrasikan voting ke menu (tetap via client.py).
- Tidak menjamin discovery di jaringan dengan AP isolation / firewall ketat (fallback manual tetap ada).
- Tidak scan semua interface; hanya interface yang dipilih.

## 4. Anti-Goals

- Jangan sampai auto-discovery membuat node menerima chain dari jaringan yang tidak tepercaya tanpa validasi (tetap validasi_rantai).
- Jangan broadcast ke semua interface (hanya interface terpilih + loopback).

## 5. Constraints

- Python 3.8+, stdlib + cryptography.
- Windows & Linux; UDP broadcast mungkin diblokir firewall → sediakan fallback manual & status jelas.
- Difficulty default 4; auto-discovery hanya menghubungkan difficulty yang sama.
- Genesis hash harus identik (sudah, timestamp=0).
- Hotspot biasanya memberi subnet /24; broadcast dibatasi ke interface terpilih.

## 6. Approaches Considered

- **A. UDP broadcast pada interface terpilih + auto-port + menu di node.py (DIPILIH)**: stdlib only, sederhana, cocok untuk hotspot.
- **B. mDNS/Zeroconf**: lebih robust tapi dependency baru + konfigurasi firewall; ditolak untuk scope ini.
- **C. Subnet TCP scan**: lambat & noisy; ditolak.

## 7. Design

### 7.1 Mode Pemilihan

- `python node.py` (tanpa argumen) → mode interaktif.
- `python node.py <port> [peers] [difficulty]` → mode manual lama.
- Discovery background tetap aktif di kedua mode (konsisten); menu hanya di mode interaktif.

### 7.2 Pemilihan Interface Jaringan

- Deteksi semua IPv4 non-loopback (`socket.gethostbyname_ex(socket.gethostname())` atau `getaddrinfo`).
- Jika **tepat satu** IP non-loopback → pakai otomatis (log).
- Jika **lebih dari satu** → tampilkan daftar dan minta user pilih (default = yang pertama). Ini satu-satunya prompt sebelum menu; menjamin hanya jaringan terpilih yang dipakai.
- Jika **tidak ada** → fallback loopback (127.0.0.1) dengan peringatan (discovery hanya same-machine).

### 7.3 Auto-port

- Mulai dari 5001, coba bind `0.0.0.0:port` (socket). Jika gagal (OSError), naik 1. Maksimal coba 100 port (5001–5100). Jika semua penuh → error & keluar.
- Port yang dipilih disimpan di global `PORT` dan `NODE.port`.

### 7.4 UDP Discovery Protocol

- **Discovery port:** 9999 (UDP).
- **Broadcast target:** hanya interface terpilih (bind socket ke IP interface terpilih, lalu sendto `255.255.255.255`) + `127.0.0.1` (same-machine). Tidak broadcast ke interface lain.
- **Beacon payload (JSON):**
  ```json
  {"type":"presma-node","http_port":5001,"difficulty":4,"genesis":"<hash>"}
  ```
  Tidak menyertakan `host`; penerima memakai **IP sumber paket UDP** (`addr[0]` dari `recvfrom`) sebagai alamat peer.
- **Interval broadcast:** 5 detik.
- **Listener:** bind UDP 9999 (`SO_REUSEADDR`) pada `0.0.0.0` (agar bisa menerima dari interface terpilih). Saat menerima beacon:
  - Validasi `type == "presma-node"`.
  - Jika `difficulty != local` atau `genesis != local genesis` → abaikan.
  - Peer host = `addr[0]`; peer addr = `host:http_port`.
  - Jika `(host, http_port)` == (local, local port) → abaikan (self).
  - Jika belum ada di `NODE.peers` → `NODE.tambah_peer(peer, timbal_balik=False)` + jadwalkan resolve segera (thread). Catat log.
- **Self-detection:** filter berdasarkan port & source; difficulty/genesis juga membatasi.

### 7.5 Threading

- Thread 1: HTTP server (daemon).
- Thread 2: discovery broadcaster (daemon, interval 5s).
- Thread 3: discovery listener (daemon).
- Thread 4: background resolve (daemon, interval 15s).
- Main thread: menu loop (hanya mode interaktif). Di mode manual, HTTP server di main thread (`serve_forever`), discovery threads daemon.

### 7.6 Interactive Menu

```
=== Node Voting Presma (Interaktif) ===
Interface: <ip>  |  Node: http://<ip>:<port>  (difficulty 4)
1. Status (port, peers, panjang rantai, pool)
2. Daftar peer
3. Cari node (tunggu 6 detik)
4. Tambah peer manual (preflight difficulty/genesis)
5. Tampilkan alamat untuk client.py
6. Hentikan node
Pilih:
```

- Input dibaca dengan `input()`. Validasi angka.
- "Cari node" cukup menunggu 6 detik (satu+ siklus broadcast) lalu tampilkan peer baru.
- Tidak ada voting di menu.

### 7.7 Sinkronisasi Otomatis

- Saat peer baru ditambah (discovery atau manual), jadwalkan `NODE.resolve()` segera (thread, delay 1–2 detik) agar node yang terlambat start langsung menyinkronkan chain.
- Thread 4 tetap menjalankan resolve setiap 15 detik sebagai fallback.
- Resolve hanya mengganti jika rantai peer **valid & lebih panjang** (sudah ada di kode).

### 7.8 Manual Peer Addition (menu)

- Preflight: fetch `/chain` dari peer, cek difficulty & genesis. Jika mismatch → tolak dengan pesan jelas.
- Reciprocal registration memakai IP interface terpilih (bukan `127.0.0.1` hardcoded) agar cross-laptop bekerja; jika tidak ada, fallback `127.0.0.1` + log peringatan.
- Peer dari argumen startup (mode manual) tetap ditambah tanpa preflight (peer mungkin belum up); validasi terjadi saat resolve.

### 7.9 Backward Compat & Logging

- Mode manual: output tetap seperti sekarang (startup info). Discovery background tetap aktif; log discovery dicetak dengan prefix port.
- Jangan ubah endpoint/validasi.

### 7.10 Error Handling

- Jika bind UDP 9999 gagal → log peringatan, discovery dinonaktifkan, node tetap jalan (fallback manual).
- Jika tidak ada port HTTP kosong → error & exit 1.
- Discovery listener swallow exception per-beacon (jangan crash thread).
- Jika interface terpilih tidak bisa broadcast → log peringatan, discovery tetap listener-only.

### 7.11 Security Note

- Discovery tidak autentikasi. Cocok untuk demo LAN/hotspot. Peer yang ditemukan tetap divalidasi lewat validasi_rantai saat resolve/receive block. Dokumentasikan di README.

## 8. Files to Touch

- `node.py`: tambah pemilihan interface, auto-port, UDP discovery threads (interface terpilih + loopback), background resolve, resolve-on-new-peer, mode interaktif menu, argumen handling, reciprocal host.
- `README.md`: tambah bagian "Mode interaktif & auto-discovery" + catatan firewall/hotspot.

## 9. What's Left to Builder

- Detail implementasi enumerasi IP non-loopback (Windows/Linux).
- Format menu & input validation.
- Tests manual (dua node di mesin yang sama, dua laptop via hotspot).

## 10. Approval

Menunggu persetujuan user sebelum implementasi.