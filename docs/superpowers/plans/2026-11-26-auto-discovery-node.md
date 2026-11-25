# Auto-Discovery Node + Interactive Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `node.py` start without arguments in an interactive mode that auto-picks a free port, discovers peers only on the selected network interface via UDP broadcast, and auto-syncs chains; keep the manual CLI mode for checkpoints.

**Architecture:** Add helper functions (IP detection, free-port scan, beacon processing) and daemon threads (broadcaster, listener, resolver) to `node.py`. Add an interactive menu on the main thread for interactive mode; manual mode keeps `serve_forever` on the main thread. Discovery uses a UDP beacon on port 9999 and only connects peers with matching difficulty + genesis hash.

**Tech Stack:** Python 3.8+ stdlib (`socket`, `threading`, `json`, `time`) + existing `cryptography`. Tests use `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-26-auto-discovery-node-design.md`

## Global Constraints

- No new external dependencies (stdlib + cryptography only).
- Backward compat: `python node.py <port> [peers] [difficulty]` must still work.
- Discovery must not broadcast to interfaces other than the selected one + loopback.
- Difficulty & genesis hash must match before a peer is added.
- Keep existing endpoints/validation unchanged.

## Review Focus

- Multiple non-loopback IPs present → interface selection must not silently pick the wrong one.
- UDP broadcast blocked by firewall/AP isolation → node must still run and offer manual add.
- Late-joining node → must auto-sync via background resolve without manual command.
- Difficulty mismatch between nodes → beacons ignored, no partial/broken peer links.
- Beacon from self → must be ignored to avoid self-registration.

---

### Task 1: IP detection and free-port helpers

**Files:**
- Modify: `node.py` (imports + new helper functions near top)
- Create: `tests/test_node_helpers.py`

**Interfaces:**
- Produces: `deteksi_ip_non_loopback() -> list[str]`, `deteksi_ip_utama(otomatis: bool = False) -> str`, `cari_port_kosong(mulai: int = 5001, maks_percobaan: int = 100) -> int | None`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_node_helpers.py
import unittest
from node import deteksi_ip_non_loopback, cari_port_kosong

class TestHelpers(unittest.TestCase):
    def test_cari_port_kosong_returns_int(self):
        p = cari_port_kosong(5900, 5)
        self.assertIsInstance(p, int)
        self.assertGreaterEqual(p, 5900)

    def test_deteksi_ip_returns_list(self):
        ips = deteksi_ip_non_loopback()
        self.assertIsInstance(ips, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_node_helpers -v`
Expected: FAIL (ImportError / AttributeError)

- [ ] **Step 3: Implement helpers in `node.py`**

Add `import socket` (already? node.py doesn't import socket; add). Add functions:

```python
def deteksi_ip_non_loopback():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except socket.gaierror:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except socket.gaierror:
        pass
    return sorted(ips)

def deteksi_ip_utama(otomatis=False):
    ips = deteksi_ip_non_loopback()
    if not ips:
        return "127.0.0.1"
    if len(ips) == 1 or otomatis:
        return ips[0]
    print("Beberapa interface terdeteksi:")
    for i, ip in enumerate(ips, 1):
        print(f"  {i}. {ip}")
    while True:
        pilihan = input(f"Pilih interface [1-{len(ips)}] (default 1): ").strip()
        if pilihan == "":
            return ips[0]
        if pilihan.isdigit() and 1 <= int(pilihan) <= len(ips):
            return ips[int(pilihan) - 1]
        print("Pilihan tidak valid.")

def cari_port_kosong(mulai=5001, maks_percobaan=100):
    for port in range(mulai, mulai + maks_percobaan):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return None
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_node_helpers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add node.py tests/test_node_helpers.py
git commit -m "feat: add IP detection and free-port helpers"
```

---

### Task 2: Beacon processing logic

**Files:**
- Modify: `node.py`
- Modify: `tests/test_node_helpers.py`

**Interfaces:**
- Consumes: `NODE` global, `IFACE_IP` global
- Produces: `proses_beacon(data, addr, node) -> str | None`

- [ ] **Step 1: Write failing tests**

Append to tests:

```python
import node

class TestBeacon(unittest.TestCase):
    def setUp(self):
        from node import Blockchain, Node
        self.node = Node(5001, [], 4)
        node.NODE = self.node
        node.IFACE_IP = "192.168.137.10"
        node.PORT = 5001

    def test_difficulty_mismatch_ignored(self):
        data = {"type": "presma-node", "http_port": 5002, "difficulty": 2, "genesis": self.node.blockchain.chain[0].hash}
        self.assertIsNone(node.proses_beacon(data, ("192.168.137.20", 9999), self.node))

    def test_genesis_mismatch_ignored(self):
        data = {"type": "presma-node", "http_port": 5002, "difficulty": 4, "genesis": "deadbeef"}
        self.assertIsNone(node.proses_beacon(data, ("192.168.137.20", 9999), self.node))

    def test_self_ignored(self):
        data = {"type": "presma-node", "http_port": 5001, "difficulty": 4, "genesis": self.node.blockchain.chain[0].hash}
        self.assertIsNone(node.proses_beacon(data, ("192.168.137.10", 9999), self.node))

    def test_valid_beacon_adds_peer(self):
        data = {"type": "presma-node", "http_port": 5002, "difficulty": 4, "genesis": self.node.blockchain.chain[0].hash}
        res = node.proses_beacon(data, ("192.168.137.20", 9999), self.node)
        self.assertEqual(res, "192.168.137.20:5002")
        self.assertIn("192.168.137.20:5002", self.node.peers)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_node_helpers -v`
Expected: FAIL

- [ ] **Step 3: Implement `proses_beacon` in `node.py`**

```python
def proses_beacon(data, addr, node):
    if not isinstance(data, dict) or data.get("type") != "presma-node":
        return None
    try:
        http_port = int(data["http_port"])
        difficulty = int(data["difficulty"])
        genesis = str(data["genesis"])
    except (KeyError, ValueError, TypeError):
        return None
    if difficulty != node.blockchain.difficulty:
        return None
    if genesis != node.blockchain.chain[0].hash:
        return None
    host = addr[0]
    if host == IFACE_IP and http_port == node.port:
        return None
    peer = f"{host}:{http_port}"
    if peer in node.peers:
        return peer
    node.tambah_peer(peer, timbal_balik=False)
    node.jadwalkan_resolve()
    log(f"discovery: peer baru {peer}")
    return peer
```

Also add `jadwalkan_resolve` method to `Node` (Task 3 will use; add now with resolve):

```python
def jadwalkan_resolve(self):
    now = time.time()
    if now - getattr(self, "_resolve_terakhir", 0) < 5:
        return
    self._resolve_terakhir = now
    def _run():
        time.sleep(1.5)
        try:
            self.resolve()
        except Exception as e:
            log(f"resolve error: {e}")
    threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_node_helpers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add node.py tests/test_node_helpers.py
git commit -m "feat: add beacon processing logic"
```

---

### Task 3: Discovery threads + background resolve + interface selection wiring

**Files:**
- Modify: `node.py`

**Interfaces:**
- Consumes: `IFACE_IP`, `NODE`, `PORT` globals
- Produces: `mulai_discovery(node, iface_ip, stop_event)`, `thread_broadcaster`, `thread_listener`, `thread_resolver`

- [ ] **Step 1: Implement discovery threads in `node.py`**

Add functions (no new tests; manual verification):

```python
DISCOVERY_PORT = 9999

def thread_broadcaster(iface_ip, stop_event):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.bind((iface_ip, 0))
    except OSError:
        try:
            sock.bind(("0.0.0.0", 0))
        except OSError:
            return
    while not stop_event.is_set():
        payload = json.dumps({
            "type": "presma-node",
            "http_port": PORT,
            "difficulty": NODE.blockchain.difficulty,
            "genesis": NODE.blockchain.chain[0].hash,
        }).encode("utf-8")
        for target in ("255.255.255.255", "127.0.0.1"):
            try:
                sock.sendto(payload, (target, DISCOVERY_PORT))
            except OSError:
                pass
        stop_event.wait(5)
    sock.close()

def thread_listener(stop_event):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", DISCOVERY_PORT))
    except OSError as e:
        log(f"discovery listener gagal bind: {e}")
        return
    sock.settimeout(1)
    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            continue
        try:
            obj = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if NODE is not None:
            proses_beacon(obj, addr, NODE)
    sock.close()

def thread_resolver(stop_event):
    while not stop_event.is_set():
        if NODE is not None:
            try:
                NODE.resolve()
            except Exception as e:
                log(f"resolve background error: {e}")
        stop_event.wait(15)

def mulai_discovery(node, iface_ip, stop_event):
    threads = [
        threading.Thread(target=thread_broadcaster, args=(iface_ip, stop_event), daemon=True),
        threading.Thread(target=thread_listener, args=(stop_event,), daemon=True),
        threading.Thread(target=thread_resolver, args=(stop_event,), daemon=True),
    ]
    for t in threads:
        t.start()
    return threads
```

- [ ] **Step 2: Update `tambah_peer` reciprocal registration to use interface IP**

Modify `Node.tambah_peer`:

```python
def tambah_peer(self, peer, timbal_balik=True):
    if not peer or peer in self.peers:
        return False
    self.peers.append(peer)
    log(f"peer baru ditambahkan: {peer}")
    if timbal_balik:
        host_lokal = IFACE_IP if IFACE_IP else deteksi_ip_utama(otomatis=True)
        if not host_lokal or host_lokal == "127.0.0.1":
            host_lokal = "127.0.0.1"
        try:
            kirim_json(f"http://{peer}/peers", {"peer": f"{host_lokal}:{self.port}", "timbal_balik": False})
        except Exception as e:
            log(f" !! peer {peer} belum bisa menambahkan node ini ({e})")
    return True
```

- [ ] **Step 3: Commit**

```bash
git add node.py
git commit -m "feat: add UDP discovery threads and background resolve"
```

---

### Task 4: Interactive menu + entry-point mode selection

**Files:**
- Modify: `node.py` (`__main__` block + new `menu_interaktif`)

**Interfaces:**
- Consumes: all helpers/threads above
- Produces: interactive mode when run with no args

- [ ] **Step 1: Add `menu_interaktif` function**

```python
def tambah_peer_manual(node, peer):
    try:
        data = ambil_json(f"http://{peer}/chain")
    except Exception as e:
        print(f"Gagal menghubungi {peer}: {e}")
        return
    if data.get("difficulty") != node.blockchain.difficulty:
        print(f"Ditolak: difficulty peer ({data.get('difficulty')}) != lokal ({node.blockchain.difficulty})")
        return
    rantai_peer = data.get("chain", [])
    if not rantai_peer or rantai_peer[0].get("hash") != node.blockchain.chain[0].hash:
        print("Ditolak: genesis tidak cocok")
        return
    if node.tambah_peer(peer, timbal_balik=True):
        print(f"Peer {peer} ditambahkan.")
        node.jadwalkan_resolve()
    else:
        print("Peer tidak valid atau sudah ada.")

def menu_interaktif(node):
    stop_event = threading.Event()
    mulai_discovery(node, IFACE_IP, stop_event)
    try:
        while True:
            print("\n=== Node Voting Presma (Interaktif) ===")
            print(f"Interface: {IFACE_IP} | Node: http://{IFACE_IP}:{node.port} (difficulty {node.blockchain.difficulty})")
            print("1. Status")
            print("2. Daftar peer")
            print("3. Cari node (tunggu 6 detik)")
            print("4. Tambah peer manual")
            print("5. Tampilkan alamat untuk client.py")
            print("6. Hentikan node")
            pilihan = input("Pilih: ").strip()
            if pilihan == "1":
                with node.blockchain.lock:
                    print(f"Port: {node.port} | Peers: {len(node.peers)} | Rantai: {len(node.blockchain.chain)} block | Pool: {len(node.blockchain.pool)}")
                print("Peers:", node.peers)
            elif pilihan == "2":
                print("Peers:", node.peers)
            elif pilihan == "3":
                print("Mencari node lain selama 6 detik...")
                time.sleep(6)
                print("Peers sekarang:", node.peers)
            elif pilihan == "4":
                peer = input("Alamat peer (host:port): ").strip()
                if peer:
                    tambah_peer_manual(node, peer)
            elif pilihan == "5":
                print(f"Gunakan di client.py: {IFACE_IP}:{node.port}")
            elif pilihan == "6":
                break
            else:
                print("Pilihan tidak valid.")
    finally:
        stop_event.set()
        if getattr(node, "http_server", None):
            try:
                node.http_server.shutdown()
            except Exception:
                pass
```

- [ ] **Step 2: Rewrite `__main__` block**

```python
if __name__ == "__main__":
    global PORT, NODE, IFACE_IP
    if len(sys.argv) == 1:
        IFACE_IP = deteksi_ip_utama(otomatis=False)
        port = cari_port_kosong()
        if port is None:
            print("Tidak ada port kosong di range 5001-5100.")
            sys.exit(1)
        PORT = port
        peers_awal = []
        difficulty = 4
        interaktif = True
    else:
        PORT = int(sys.argv[1])
        peers_awal = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else []
        difficulty = int(sys.argv[3]) if len(sys.argv) > 3 else 4
        IFACE_IP = deteksi_ip_utama(otomatis=True)
        interaktif = False

    NODE = Node(PORT, peers_awal, difficulty)
    print(f"Node Voting UNTAD aktif di port {PORT}")
    print("Peers     : " + (", ".join(peers_awal) if peers_awal else "(belum ada)"))
    print(f"Difficulty: {difficulty} (hash harus diawali {'0' * difficulty})")
    print(f"Genesis   : {NODE.blockchain.chain[0].hash[:20]}...")
    print(f"Interface : {IFACE_IP}")

    if interaktif:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), NodeHandler)
        NODE.http_server = server
        threading.Thread(target=server.serve_forever, daemon=True).start()
        menu_interaktif(NODE)
    else:
        # discovery background tetap aktif
        stop_event = threading.Event()
        mulai_discovery(NODE, IFACE_IP, stop_event)
        try:
            ThreadingHTTPServer(("0.0.0.0", PORT), NodeHandler).serve_forever()
        except KeyboardInterrupt:
            stop_event.set()
```

Need ensure `IFACE_IP`, `PORT` declared global at module top: add `IFACE_IP = "127.0.0.1"` near `PORT = 0`.

- [ ] **Step 3: Syntax check**

Run: `python -m py_compile node.py`
Expected: no output (success)

- [ ] **Step 4: Commit**

```bash
git add node.py
git commit -m "feat: interactive mode with auto-port and discovery"
```

---

### Task 5: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add section after "Menjalankan jaringan tiga node" or in instalasi**

Add subsection:

```markdown
### Mode interaktif (auto-discovery)

Jalankan tanpa argumen:

```bash
python node.py
```

Node akan:
1. Memilih interface jaringan (otomatis jika hanya satu; tanya jika lebih dari satu).
2. Mencari port kosong mulai 5001.
3. Menyiarkan keberadaannya via UDP (port 9999) hanya di jaringan terpilih + loopback.
4. Menemukan node lain dengan difficulty & genesis yang sama dan menyinkronkan chain otomatis.

Menu interaktif menyediakan status, daftar peer, pencarian node, tambah peer manual, dan alamat untuk `client.py`. Voting tetap dilakukan via `client.py` menggunakan alamat yang ditampilkan.

Mode manual lama tetap tersedia: `python node.py <port> [peers] [difficulty]`.

Catatan: discovery memakai UDP broadcast; firewall/AP isolation dapat memblokirnya. Gunakan "Tambah peer manual" sebagai fallback.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: describe interactive auto-discovery mode"
```

---

### Task 6: Manual verification

- [ ] **Step 1: Run unit tests**

Run: `python -m unittest tests.test_node_helpers -v`
Expected: PASS

- [ ] **Step 2: Smoke test interactive start**

Run: `python node.py` then choose menu option 6 to exit.
Expected: node starts, prints interface/port, menu appears, exits cleanly.

- [ ] **Step 3: Smoke test manual mode**

Run: `python node.py 5010 "" 4` (Ctrl+C to stop)
Expected: starts on port 5010, manual mode.

- [ ] **Step 4: Two-node discovery on same machine**

Start `python node.py` (node A), then `python node.py` in another terminal (node B). Wait 6s, check peers on both. Expected: each lists the other.

- [ ] **Step 5: Commit (if any fixes)**

```bash
git add -A
git commit -m "chore: manual verification fixes"  # only if changes
```