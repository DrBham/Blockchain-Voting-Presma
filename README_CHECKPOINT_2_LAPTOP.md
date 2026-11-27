# Panduan Checkpoint Blockchain dengan 2 Laptop

Panduan ini menjalankan seluruh checkpoint `node.py` dan `client.py` melalui dua laptop dalam jaringan yang sama. Laptop A berperan sebagai panitia: menjalankan seed, web, dan semua perintah client yang memakai dompet.

## Topologi jaringan yang digunakan

- Laptop A: `192.168.137.1`, node port `5001`
- Laptop B: `192.168.137.253`, node port `5002`
- Difficulty: `4`, sehingga hash Proof of Work harus diawali `0000`

Semua perintah di bawah memakai alamat IPv4 tersebut, bukan `localhost`.

## 1. Persiapan kedua laptop

Clone repository yang sama pada kedua laptop. Buka PowerShell pada folder tersebut.

Pasang dependensi:

```powershell
python -m pip install -r requirements.txt
```

Cek alamat IPv4:

```powershell
ipconfig
```

Pastikan kedua laptop terhubung ke Wi-Fi atau hotspot yang sama. Uji koneksi dari kedua arah:

```powershell
# Jalankan dari Laptop A
ping 192.168.137.253

# Jalankan dari Laptop B
ping 192.168.137.1
```

Jika Windows Firewall meminta izin, izinkan Python pada jaringan **Private**. Jika tidak muncul, buka PowerShell sebagai Administrator dan jalankan aturan sesuai laptop:

```powershell
# Laptop A
New-NetFirewallRule -DisplayName "Blockchain Node 5001" -Direction Inbound -Protocol TCP -LocalPort 5001 -Action Allow
New-NetFirewallRule -DisplayName "Blockchain Web 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow

# Laptop B
New-NetFirewallRule -DisplayName "Blockchain Node 5002" -Direction Inbound -Protocol TCP -LocalPort 5002 -Action Allow
```

## 2. Jalankan dua node

Buka terminal pertama pada Laptop A:

```powershell
python menu_node.py 5001 192.168.137.253:5002 4
```

Buka terminal pertama pada Laptop B:

```powershell
python menu_node.py 5002 192.168.137.1:5001 4
```

Kedua perintah langsung mendaftarkan peer memakai IP jaringan. Jangan gunakan `127.0.0.1` untuk peer di laptop lain.

Setelah node hidup, uji port:

```powershell
# Dari Laptop A
Test-NetConnection 192.168.137.253 -Port 5002

# Dari Laptop B
Test-NetConnection 192.168.137.1 -Port 5001
```

Nilai `TcpTestSucceeded` harus `True`. Difficulty (argumen ketiga) harus sama di kedua laptop.

## 3. Seed dan buka pemungutan (sekali, di Laptop A)

```powershell
python seed_demo.py 127.0.0.1:5001
$env:NODE_URL = "http://127.0.0.1:5001"
python -m flask --app web.app run --host 0.0.0.0 --port 5000
```

Seed mendeploy contract, menambah Paslon 1 dan 2, dan mendaftarkan NIM contoh `A12119001`, `A12119002`, `C30119001`, `C30119002`, `F55119001`, `F55119002` (dompet `dompet_<NIM>.pem`, password `demo123`). Jalankan seed hanya di Laptop A. Buka `http://127.0.0.1:5000/panitia` (password default `panitia-demo`, atur lewat `PANITIA_PASSWORD`), lalu klik **Buka pemungutan**.

Setiap perintah yang membuka dompet menanyakan password: ketik `demo123`.

## 4. Jalankan seluruh checkpoint

Jalankan perintah berikut dari terminal lain di Laptop A, kecuali jika tertulis lain.

### Checkpoint 1 — Pembuatan identitas pengirim

```powershell
python menu_client.py identitas F55125001
```

Hasil yang diperiksa:

- identitas voter tampil;
- alamat dan potongan public key tampil;
- private key tersimpan lokal dalam `dompet_F55125001.pem`, terenkripsi dengan password yang diketik.

NIM baru ini belum terdaftar di chain, jadi langkah berikutnya memakai NIM hasil seed.

### Checkpoint 2 dan 3 — Transaksi ditandatangani dan diverifikasi

Kirim transaksi valid ke node Laptop A:

```powershell
python menu_client.py vote 192.168.137.1:5001 1 A12119001
```

Hasil yang diperiksa:

- client mengenkripsi pilihan dengan kunci pemilu, lalu membuat signature menggunakan private key lokal;
- node Laptop A menampilkan `Signature VALID`;
- transaksi masuk ke pool dan disiarkan ke Laptop B.

Uji perubahan transaksi setelah ditandatangani menggunakan NIM lain:

```powershell
python menu_client.py vote_ubah 192.168.137.1:5001 1 2 A12119002
```

Hasil yang diharapkan: transaksi ditolak karena `signature tidak cocok`.

### Checkpoint 4 — Status transaction pool

Periksa pool kedua node:

```powershell
python menu_client.py pool 192.168.137.1:5001
python menu_client.py pool 192.168.137.253:5002
```

Transaksi valid `A12119001: pilihan terenkripsi (sandi ...)` harus terlihat pada kedua node.

### Checkpoint 5, 6, dan 7 — Block candidate, Proof of Work, dan penerimaan block

Tambang pool pada Laptop A:

```powershell
python menu_client.py mine 192.168.137.1:5001
```

Periksa terminal node Laptop A. Terminal harus menampilkan:

- `BLOCK CANDIDATE`;
- jumlah percobaan nonce;
- nonce yang ditemukan;
- hash yang diawali `0000`;
- `BLOCK DITERIMA RANTAI`.

Periksa rantai kedua node:

```powershell
python menu_client.py chain 192.168.137.1:5001
python menu_client.py chain 192.168.137.253:5002
```

Block baru harus tampil pada kedua node. Terminal Laptop B juga harus mencatat penerimaan block dari peer.

### Checkpoint 8 — Validasi rantai normal

```powershell
python menu_client.py validate 192.168.137.1:5001
python menu_client.py validate 192.168.137.253:5002
```

Hasil yang diharapkan: `Rantai VALID` pada kedua node.

### Checkpoint 10 — Broadcast dan sinkronisasi longest-chain

Broadcast transaksi dan block sudah terlihat pada Checkpoint 2–7. Gunakan langkah berikut untuk menguji node yang tertinggal.

1. Hentikan node Laptop B dengan `Ctrl+C`.
2. Saat Laptop B mati, jalankan pada Laptop A:

```powershell
python menu_client.py vote 192.168.137.1:5001 2 C30119001
python menu_client.py mine 192.168.137.1:5001
```

3. Jalankan kembali node Laptop B:

```powershell
python menu_node.py 5002 192.168.137.1:5001 4
```

4. Pada terminal kedua Laptop B, ambil rantai terpanjang dari Laptop A:

```powershell
python menu_client.py resolve 192.168.137.253:5002
python menu_client.py chain 192.168.137.253:5002
python menu_client.py validate 192.168.137.253:5002
```

Hasil yang diharapkan: rantai Laptop B diganti dengan rantai valid dan lebih panjang milik Laptop A.

> Data blockchain hanya disimpan di memori. Node yang dimatikan lalu dijalankan kembali mulai dari genesis block dan perlu menjalankan `resolve`.

### Checkpoint 11 — Penolakan block tanpa Proof of Work valid

Jalankan terhadap node Laptop A yang masih memiliki rantai valid:

```powershell
python menu_client.py palsu 192.168.137.1:5001
```

Hasil yang diharapkan:

- block palsu ditolak;
- status HTTP `409`;
- alasan menyebut Proof of Work tidak valid.

### Checkpoint 9 — Deteksi manipulasi data block lama

Jalankan di terminal kedua **Laptop B**, karena `tamper` hanya diterima dari mesin node itu sendiri (permintaan dari Laptop A ditolak HTTP 403). Perintah ini tidak butuh dompet:

```powershell
python menu_client.py tamper 127.0.0.1:5002 2
python menu_client.py validate 127.0.0.1:5002
```

Hasil yang diharapkan:

- isi transaksi dalam block index `2` berubah;
- hash tersimpan tidak lagi cocok dengan isi block;
- validasi menampilkan `Rantai TIDAK VALID` dan index block pertama yang rusak.

Rantai Laptop A tetap valid karena manipulasi hanya dilakukan pada Laptop B. Rantai Laptop B tetap rusak (sinkronisasi latar tidak memulihkan rantai rusak) sampai dipulihkan manual:

```powershell
python menu_client.py resolve 127.0.0.1:5002
python menu_client.py validate 127.0.0.1:5002
```

## 5. Perintah pemeriksaan tambahan

```powershell
# Daftar peer
Invoke-RestMethod http://192.168.137.1:5001/peers

# Rekap suara Laptop A (per Paslon baru tampil setelah panitia menutup dan menghitung)
python menu_client.py tally 192.168.137.1:5001

# Rekap suara Laptop B
python menu_client.py tally 192.168.137.253:5002
```

## 6. Masalah umum

### `ModuleNotFoundError: No module named 'cryptography'`

```powershell
python -m pip install -r requirements.txt
```

### `TcpTestSucceeded : False`

Pastikan:

- kedua laptop memakai jaringan yang sama;
- IP tujuan benar;
- kedua node masih berjalan;
- port `5001` dan `5002` diizinkan Windows Firewall;
- jaringan tidak mengaktifkan client isolation atau AP isolation.

### `Tidak dapat terhubung ke node`

Gunakan `127.0.0.1` hanya untuk node pada laptop yang sedang dipakai. Gunakan IPv4 laptop tujuan untuk koneksi antarlaptop.

### Transaksi ditolak karena NIM sudah memilih

Satu NIM hanya satu suara. Gunakan NIM hasil seed yang belum memilih, misalnya `A12119002`, `C30119002`, atau `F55119001`.

### Transaksi ditolak karena NIM belum terdaftar atau pemungutan belum dibuka

Jalankan `seed_demo.py` di Laptop A, lalu klik **Buka pemungutan** di ruang panitia.
