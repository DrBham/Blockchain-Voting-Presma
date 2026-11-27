// Pemira Presma — perilaku mockup. Tanpa backend: data disimpan di sessionStorage,
// email OTP disimulasikan sebagai kotak masuk Mailpit, hash dan proof of work dihitung sungguhan (SHA-256).
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const jeda = (ms) => new Promise((r) => setTimeout(r, ms));
const fmt = (n) => n.toLocaleString("id-ID");

// ---------- penyimpanan sesi ----------
const KUNCI = "pemira-mockup";
const store = {
  get() { try { return JSON.parse(sessionStorage.getItem(KUNCI)) || {}; } catch { return {}; } },
  set(patch) { const d = { ...store.get(), ...patch }; sessionStorage.setItem(KUNCI, JSON.stringify(d)); return d; },
};

// ---------- kriptografi ----------
async function sha256(teks) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(teks));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
const powHtml = (h, d = 4) => `<span class="pow">${h.slice(0, d)}</span>${h.slice(d)}`;

// proof of work sungguhan: cari nonce sampai hash diawali `difficulty` nol
async function tambang(isi, difficulty, onTick) {
  const target = "0".repeat(difficulty);
  let nonce = 0, hash = "";
  for (;;) {
    for (let i = 0; i < 400; i++, nonce++) {
      hash = await sha256(isi + nonce);
      if (hash.startsWith(target)) { onTick?.(nonce, hash, true); return { nonce, hash }; }
    }
    onTick?.(nonce, hash, false);
    await jeda(0); // beri napas ke browser agar angka terlihat bergerak
  }
}

// ---------- ikon ----------
const IKON = {
  check: '<path d="M20 6 9 17l-5-5"/>',
  key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
  mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  blocks: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><path d="M10 6.5h4a2 2 0 0 1 2 2V14"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  vote: '<path d="m9 12 2 2 4-4"/><path d="M5 7h14l-1 13H6z"/><path d="M8 7V4h8v3"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
};
const ikon = (n) => (IKON[n] ? `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${IKON[n]}</svg>` : "");
$$("[data-icon]").forEach((el) => el.insertAdjacentHTML("afterbegin", ikon(el.dataset.icon)));

// ---------- umpan balik ----------
function toast(pesan) {
  let t = $(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; t.setAttribute("role", "status"); document.body.append(t); }
  t.textContent = pesan;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), 2600);
}

// simulasi Mailpit: email OTP muncul di pojok kanan bawah
function kirimEmail(judul, kode, onIsi) {
  let box = $(".inbox");
  if (!box) {
    box = document.createElement("aside");
    box.className = "inbox";
    box.setAttribute("aria-live", "polite");
    document.body.append(box);
  }
  box.innerHTML = `
    <div class="from"><span>Mailpit · kotak masuk simulasi</span><span>baru saja</span></div>
    <p style="margin-top:8px">${judul}</p>
    <p class="code">${kode}</p>
    <div class="row"><button class="btn btn-secondary btn-sm" type="button" data-isi>Isi otomatis</button>
    <button class="btn btn-ghost btn-sm" type="button" data-tutup>Tutup</button></div>`;
  requestAnimationFrame(() => box.classList.add("show"));
  $("[data-isi]", box).onclick = () => { onIsi(kode); box.classList.remove("show"); };
  $("[data-tutup]", box).onclick = () => box.classList.remove("show");
}
const kodeAcak = () => String(crypto.getRandomValues(new Uint32Array(1))[0] % 1e6).padStart(6, "0");

// ---------- jendela pemungutan (dipakai rel pemilih dan panitia) ----------
function jendela() {
  const d = store.get();
  if (!d.tutup) store.set({ tutup: Date.now() + (4 * 3600 + 12 * 60) * 1000, buka: Date.now() - 2.8 * 3600 * 1000 });
  return store.get();
}
function sisa(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return [s / 3600, (s % 3600) / 60, s % 60].map((x) => String(Math.floor(x)).padStart(2, "0")).join(":");
}

// ---------- kerangka pemilih ----------
const LANGKAH = [
  ["daftar.html", "Daftar akun"], ["verifikasi-email.html", "Verifikasi email"], ["masuk.html", "Masuk"],
  ["bilik.html", "Bilik suara"], ["bukti.html", "Bukti suara"],
];
function kerangkaPemilih() {
  const now = Number(document.body.dataset.step);
  const maks = Math.max(now, store.get().maks || 0);
  store.set({ maks });
  const items = LANGKAH.map(([href, nama], i) => {
    const n = i + 1;
    const cls = n === now ? "now" : n < maks || n < now ? "done" : "";
    const isi = `<span class="n">${n < now || (n < maks && n !== now) ? "✓" : n}</span><span>${nama}</span>`;
    const bisa = n <= maks && n !== now;
    return `<li>${bisa ? `<a class="${cls}" href="${href}">${isi}</a>` : `<span class="step ${cls}" ${n === now ? 'aria-current="step"' : ""}>${isi}</span>`}</li>`;
  }).join("");
  const rail = `
    <aside class="rail" aria-label="Perjalanan pemilih">
      <a class="brand" href="index.html"><img src="assets/logo-untad.png" alt="" width="30" height="31"><span><b>Pemira Presma</b><small>Pemilihan Presiden Mahasiswa 2026</small></span></a>
      <div><p class="journey-label">Langkahmu</p><ol class="journey">${items}</ol></div>
      <div class="window">
        <p class="small soft">Pemungutan ditutup dalam</p>
        <p class="clock" data-clock>--:--:--</p>
        <div class="bar"><i data-progress style="width:0"></i></div>
        <p class="node-line"><span class="tag ok"></span>Terhubung ke node-1 · <span data-height>48</span> block</p>
      </div>
      <p class="rail-foot">Proyek mata kuliah Teknologi Blockchain. Bukan sistem resmi UNTAD.<br><button class="linkish" type="button" data-ulang>Ulang demo dari awal</button></p>
    </aside>
    <div class="mobilebar">
      <div class="spread"><a class="brand" href="index.html"><img src="assets/logo-untad.png" alt="" width="30" height="31"><b>Pemira Presma</b></a>
      <span class="small soft">Langkah ${now} dari ${LANGKAH.length}</span></div>
      <div class="bar"><i style="width:${(now / LANGKAH.length) * 100}%"></i></div>
    </div>`;
  document.body.insertAdjacentHTML("afterbegin", `<div class="voter">${rail}</div>`);
  const shell = $(".voter");
  shell.append($("main.stage"));
  const tick = () => {
    const d = jendela();
    $$("[data-clock]").forEach((el) => (el.textContent = sisa(d.tutup - Date.now())));
    const p = (Date.now() - d.buka) / (d.tutup - d.buka);
    $$("[data-progress]").forEach((el) => (el.style.width = `${Math.min(100, p * 100)}%`));
    $$("[data-height]").forEach((el) => (el.textContent = 48 + (d.block ? 1 : 0)));
  };
  tick(); setInterval(tick, 1000);
}

// ---------- kerangka panitia ----------
function kerangkaPanitia() {
  const page = document.body.dataset.page;
  const link = (href, ic, nama) => `<a href="${href}" ${href.startsWith(page) ? 'aria-current="page"' : ""}>${ikon(ic)}<span>${nama}</span></a>`;
  document.body.insertAdjacentHTML("afterbegin", `<div class="panel"><aside class="side" aria-label="Navigasi panitia">
      <a class="brand" href="index.html"><img src="assets/logo-untad.png" alt="" width="30" height="31"><span><b>Ruang panitia</b><small>KPU Mahasiswa</small></span></a>
      <nav>${link("admin.html", "grid", "Dasbor")}${link("explorer.html", "blocks", "Explorer chain")}
        <p class="side-label">Pratinjau</p>${link("bilik.html", "vote", "Bilik pemilih")}${link("index.html", "home", "Beranda")}</nav>
      <p class="side-foot">Bukan sistem resmi UNTAD</p>
    </aside></div>`);
  $(".panel").append($("main.work"));
}

// ---------- OTP 6 kotak ----------
function kotakOtp(wadah, onLengkap) {
  const kotak = $$("input", wadah);
  const nilai = () => kotak.map((k) => k.value).join("");
  kotak.forEach((k, i) => {
    k.addEventListener("input", () => {
      k.value = k.value.replace(/\D/g, "").slice(-1);
      k.classList.toggle("filled", !!k.value);
      wadah.classList.remove("bad");
      if (k.value && i < 5) kotak[i + 1].focus();
      if (nilai().length === 6) onLengkap(nilai());
    });
    k.addEventListener("keydown", (e) => { if (e.key === "Backspace" && !k.value && i) kotak[i - 1].focus(); });
    k.addEventListener("paste", (e) => {
      const angka = (e.clipboardData.getData("text").match(/\d/g) || []).slice(0, 6);
      if (!angka.length) return;
      e.preventDefault();
      isi(angka.join(""));
    });
  });
  function isi(kode) {
    kotak.forEach((k, i) => { k.value = kode[i] || ""; k.classList.toggle("filled", !!k.value); });
    kotak[Math.min(kode.length, 5)].focus();
    if (kode.length === 6) onLengkap(kode);
  }
  return {
    isi,
    salah() { wadah.classList.add("bad"); kotak.forEach((k) => { k.value = ""; k.classList.remove("filled"); }); kotak[0].focus(); },
  };
}

// ---------- halaman ----------
const FAKULTAS = "ABCDEFGKLNP";
const POLA_NIM = /^[A-Z]\d{7,8}$/;
function cekNim(nim) {
  if (!nim) return ["", ""];
  if (!/^[A-Z]/.test(nim)) return ["bad", "Diawali satu huruf kode fakultas"];
  if (!FAKULTAS.includes(nim[0])) return ["bad", `Kode fakultas '${nim[0]}' tidak terdaftar di UNTAD`];
  if (!POLA_NIM.test(nim)) return ["bad", "1 huruf diikuti 7 atau 8 angka"];
  return ["good", "Format NIM valid, akan dicocokkan dengan DPT"];
}
function tandai(input, msg, [kelas, teks]) {
  input.classList.remove("bad", "good");
  if (kelas) input.classList.add(kelas);
  msg.className = `msg ${kelas}`;
  msg.textContent = teks;
}
function intipSandi() {
  $$("[data-peek]").forEach((b) => b.addEventListener("click", () => {
    const inp = $(`#${b.dataset.peek}`);
    const lihat = inp.type === "password";
    inp.type = lihat ? "text" : "password";
    b.textContent = lihat ? "Sembunyikan" : "Tampilkan";
  }));
}

const HALAMAN = {
  async daftar() {
    intipSandi();
    const f = $("#form-daftar"), nim = $("#nim"), email = $("#email"), pw = $("#pw"), pw2 = $("#pw2");
    // email kampus UNTAD selalu NIM@untad.ac.id, jadi tidak diketik sendiri
    nim.addEventListener("input", () => {
      nim.value = nim.value.toUpperCase().replace(/\s/g, "");
      tandai(nim, $("#nim-msg"), cekNim(nim.value));
      email.value = cekNim(nim.value)[0] === "good" ? `${nim.value}@untad.ac.id` : "";
    });
    pw.addEventListener("input", () => {
      const v = pw.value;
      const s = [v.length >= 8, /[A-Z]/.test(v) && /[a-z]/.test(v), /\d/.test(v), /[^A-Za-z0-9]/.test(v)].filter(Boolean).length;
      $("#meter").dataset.s = v ? s : 0;
      $("#pw-msg").textContent = v ? ["Terlalu lemah", "Lemah", "Cukup", "Kuat", "Sangat kuat"][s] : "Minimal 8 karakter";
    });
    pw2.addEventListener("input", () => tandai(pw2, $("#pw2-msg"), !pw2.value ? ["", ""] : pw2.value === pw.value ? ["good", "Cocok"] : ["bad", "Belum sama dengan password"]));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const salah = [];
      if (cekNim(nim.value)[0] !== "good") salah.push(nim);
      if (pw.value.length < 8) salah.push(pw);
      if (pw2.value !== pw.value || !pw2.value) { salah.push(pw2); tandai(pw2, $("#pw2-msg"), ["bad", "Belum sama dengan password"]); }
      if (salah.length) { salah[0].focus(); tandai(nim, $("#nim-msg"), cekNim(nim.value) [0] ? cekNim(nim.value) : ["bad", "NIM wajib diisi"]); return; }
      const btn = $("button[type=submit]", f);
      btn.disabled = true; btn.textContent = "Membuat dompet RSA…";
      // kunci RSA-PSS 2048 dibuat sungguhan di browser, sama dengan Dompet di client.py
      const kunci = await crypto.subtle.generateKey({ name: "RSA-PSS", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
      const pub = await crypto.subtle.exportKey("spki", kunci.publicKey);
      const priv = await crypto.subtle.exportKey("jwk", kunci.privateKey);
      const pubHex = [...new Uint8Array(pub)].map((b) => b.toString(16).padStart(2, "0")).join("");
      // akun baru = sesi demo baru: status pilih, kode, dan block lama dibuang, jadwal pemungutan tetap
      const { buka, tutup } = store.get();
      sessionStorage.setItem(KUNCI, JSON.stringify({ buka, tutup, maks: 1 }));
      store.set({ nim: nim.value, email: email.value, pub: pubHex, priv, alamat: (await sha256(pubHex)).slice(0, 40) });
      $("#hasil").hidden = false;
      $("#alamat").textContent = store.get().alamat;
      $("#pub").textContent = `${pubHex.slice(0, 24)}…${pubHex.slice(-8)}`;
      btn.textContent = "Dompet dibuat";
      $("#hasil").scrollIntoView({ behavior: "smooth", block: "center" });
    });
  },

  verifikasi() {
    const d = store.get();
    $("#ke-email").textContent = d.email || "email kampusmu";
    // satu kode untuk semuanya: verifikasi akun, lalu masuk dan memilih (sekali pakai saat memilih)
    let kode = d.kode || kodeAcak();
    const otp = kotakOtp($("#otp"), (v) => {
      if (v === kode) { store.set({ terverifikasi: true, kode }); toast("Akun aktif. Simpan kode ini untuk hari pemilihan"); setTimeout(() => (location.href = "masuk.html"), 900); }
      else { otp.salah(); $("#otp-msg").className = "msg bad"; $("#otp-msg").textContent = "Kode salah. Cek lagi email terbaru"; }
    });
    const kirim = () => { store.set({ kode }); kirimEmail("Kode pemilih Pemira Presma: aktivasi akun dan hari pemilihan", kode, otp.isi); };
    setTimeout(kirim, 600);
    $("#kirim-ulang").addEventListener("click", kirim);
  },

  masuk() {
    intipSandi();
    const d = store.get();
    if (d.kodeTerpakai) {
      // sudah memilih: jangan tampilkan form yang pasti ditolak, beri jalan ke bukti atau ulang demo
      $("#form-masuk").innerHTML = `<div class="stack">
        <p class="tag ok">Kamu sudah memilih</p>
        <p class="soft">NIM ${d.nim || ""} sudah memakai kode pemilihnya. Satu NIM hanya satu suara, jadi bilik tidak dibuka lagi</p>
        <div class="actions"><a class="btn btn-primary" href="bukti.html">Lihat bukti suara</a>
        <button class="btn btn-secondary" type="button" data-ulang>Ulang demo dari awal</button></div></div>`;
      return;
    }
    if (d.nim) $("#nim").value = d.nim;
    let kode = "";
    const msg = $("#otp-msg");
    const otp = kotakOtp($("#otp"), (v) => { kode = v; msg.className = "msg"; msg.textContent = "Kode lengkap"; });
    $("#kirim-ulang").addEventListener("click", () => {
      if (!d.kode) return toast("Belum ada akun terdaftar di sesi ini. Daftar dulu");
      kirimEmail("Kode pemilih Pemira Presma (dikirim ulang, kode tetap sama)", d.kode, otp.isi);
    });
    $("#form-masuk").addEventListener("submit", (e) => {
      e.preventDefault();
      const nim = $("#nim"), pw = $("#pw");
      if (cekNim(nim.value.toUpperCase())[0] !== "good") { tandai(nim, $("#nim-msg"), ["bad", "NIM tidak valid"]); nim.focus(); return; }
      if (!pw.value) { tandai(pw, $("#pw-msg"), ["bad", "Password wajib diisi"]); pw.focus(); return; }
      const now = store.get();
      if (now.kodeTerpakai) { otp.salah(); msg.className = "msg bad"; msg.textContent = "Kode ini sudah dipakai untuk memilih. Satu NIM hanya satu suara"; return; }
      if (kode.length !== 6) { otp.salah(); msg.className = "msg bad"; msg.textContent = "Isi 6 digit kode pemilih"; return; }
      // tanpa akun di sesi ini (halaman dibuka langsung), kode apa pun diterima agar demo tetap jalan
      if (now.kode && kode !== now.kode) { otp.salah(); msg.className = "msg bad"; msg.textContent = "Kode pemilih salah. Cek email pendaftaran"; return; }
      store.set({ nim: nim.value.toUpperCase(), masuk: true });
      location.href = "bilik.html";
    });
  },

  bilik() {
    const kirim = $("#kirim"), dlg = $("#konfirmasi");
    $$("input[name=paslon]").forEach((r) => r.addEventListener("change", () => {
      kirim.disabled = false;
      $("#pilihan-teks").textContent = `Paslon ${r.value} dipilih. Periksa lagi sebelum mengirim`;
    }));
    kirim.addEventListener("click", () => {
      const p = $("input[name=paslon]:checked").value;
      $("#dlg-no").textContent = p; $("#dlg-nama").textContent = `Paslon ${p}`;
      $("#langkah-kirim").hidden = true; $("#dlg-form").hidden = false; $("#dlg-foot").hidden = false;
      dlg.showModal(); $("#batal").focus();  // fokus awal di Batal agar Enter tidak langsung mengirim
    });
    // batal: surat suara dikosongkan lagi, pemilih bebas memilih ulang selama pemungutan dibuka
    $("#batal").addEventListener("click", () => {
      dlg.close();
      $$("input[name=paslon]").forEach((r) => (r.checked = false));
      kirim.disabled = true;
      $("#pilihan-teks").textContent = "Pilihan dibatalkan. Silakan pilih lagi";
      toast("Suara belum dikirim. Silakan pilih lagi");
    });
    $("#dlg-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      $("#dlg-form").hidden = true; $("#dlg-foot").hidden = true; $("#langkah-kirim").hidden = false;
      const d = store.get(), p = Number($("input[name=paslon]:checked").value);
      const li = $$("#langkah-kirim li");
      const jalan = (i, catatan) => { li[i].className = "run"; if (catatan) $("small", li[i]).textContent = catatan; };
      const selesai = (i, catatan) => { li[i].className = "ok"; if (catatan) $("small", li[i]).innerHTML = catatan; };
      const tx = JSON.stringify({ voter_id: d.nim || "F55124111", kandidat: p, waktu: Date.now() });
      jalan(0);
      let sig;
      if (d.priv) {
        const k = await crypto.subtle.importKey("jwk", d.priv, { name: "RSA-PSS", hash: "SHA-256" }, false, ["sign"]);
        const s = await crypto.subtle.sign({ name: "RSA-PSS", saltLength: 32 }, k, new TextEncoder().encode(tx));
        sig = [...new Uint8Array(s)].map((b) => b.toString(16).padStart(2, "0")).join("");
      } else sig = (await sha256(tx)) + (await sha256(tx + "sig"));
      await jeda(500);
      selesai(0, `signature ${sig.slice(0, 32)}…`);
      jalan(1); await jeda(800); selesai(1, "node-1 menerima: signature cocok, NIM belum memilih");
      jalan(2); await jeda(600); selesai(2, "disiarkan ke node-2 dan node-3");
      store.set({ sig, tx, paslon: p, block: null, kodeTerpakai: true });
      await jeda(700);
      location.href = "bukti.html";
    });
  },

  async bukti() {
    const d = store.get();
    const sig = d.sig || "7f3a9c41e0b2d58a6c1e9f04b7d2a3c58e6f1b0a9d4c7e2f";
    $("#sig").textContent = `${sig.slice(0, 16)}…${sig.slice(-8)}`;
    const li = $$("#status li");
    const prev = "0000a81f4c2e9b079e2c41d07b5a3f86e1c2d90b47a6f3e8c1d5b2a9f0e4c7d3";
    if (d.block) return tampil(d.block);
    li[0].className = "ok"; li[1].className = "run";
    const isi = `49|${prev}|${sig}|`;
    const { nonce, hash } = await tambang(isi, 4, (n, h) => {
      $("#m-nonce").textContent = fmt(n);
      $("#m-hash").innerHTML = h;
    });
    const block = { index: 49, nonce, hash, prev, waktu: Date.now() };
    store.set({ block });
    tampil(block);
    function tampil(b) {
      li[0].className = "ok"; li[1].className = "ok"; li[2].className = "ok";
      $("small", li[1]).textContent = `nonce ${fmt(b.nonce)} ditemukan`;
      $("#m-nonce").textContent = fmt(b.nonce);
      $("#m-hash").innerHTML = powHtml(b.hash);
      $("#m-state").textContent = "hash diawali 0000, block sah";
      $("#judul").textContent = "Suaramu tercatat";
      $("#sub").textContent = `Ada di block #${b.index}. Simpan kode tanda tangan di bawah untuk mengecek kapan saja`;
      $("#b-index").textContent = `#${b.index}`;
      $("#b-hash").innerHTML = powHtml(b.hash);
      $("#rincian").hidden = false;
      let konf = Math.min(3, 1 + Math.floor((Date.now() - b.waktu) / 4000));
      const k = () => { $("#konf").textContent = `${konf} konfirmasi`; };
      k();
      const t = setInterval(() => { if (konf >= 3) return clearInterval(t); konf++; k(); }, 4000);
    }
  },

  async beranda() {
    const viz = $("#viz");
    const blok = [
      { i: 46, h: "0000c3e19a7d52f0b8e4a61d93c07f25e8b1d4a6c9f30e72b5d18a4c6e9f2b07", tx: 5 },
      { i: 47, h: "0000a81f4c2e9b079e2c41d07b5a3f86e1c2d90b47a6f3e8c1d5b2a9f0e4c7d3", tx: 6 },
    ];
    const tulis = (b, kelas = "") => `<div class="blk ${kelas}"><div class="top"><span>Block #${b.i}</span><span class="soft">${b.tx} suara</span></div><div class="trunc">${b.h.startsWith("0000") ? powHtml(b.h) : b.h}</div>${b.extra || ""}</div>`;
    let prev = blok[1].h, idx = 48;
    for (;;) {
      viz.innerHTML = blok.slice(-2).map((b) => tulis(b)).join("") + tulis({ i: idx, h: "menambang…", tx: 4, extra: '<div class="small" style="margin-top:6px">nonce <span class="num" data-n>0</span></div>' }, "mine");
      const hasil = await tambang(`${idx}|${prev}|demo`, 4, (n, h) => {
        const n_ = $("[data-n]", viz); if (n_) n_.textContent = fmt(n);
        const last = $(".blk.mine .trunc", viz); if (last) last.textContent = h;
      });
      blok.push({ i: idx, h: hasil.hash, tx: 4 });
      prev = hasil.hash; idx++;
      viz.innerHTML = blok.slice(-3).map((b) => tulis(b)).join("");
      await jeda(2500);
    }
  },

  admin() {
    const d = store.get();
    // jendela pemungutan
    const saklar = $("#buka"), state = () => {
      const buka = saklar.checked;
      $("#status-jendela").className = `tag ${buka ? "ok" : "off"}`;
      $("#status-jendela").textContent = buka ? "Pemungutan dibuka" : "Pemungutan ditutup";
      $$("#paslon [data-crud]").forEach((b) => (b.disabled = buka));
      $("#crud-note").textContent = buka ? "Ubah, hapus, dan tambah paslon terkunci selama pemungutan dibuka" : "Perubahan dikirim sebagai transaksi CONTRACT_CALL dari kunci admin";
    };
    saklar.addEventListener("change", () => { state(); toast(saklar.checked ? "Pemungutan dibuka" : "Pemungutan ditutup"); });
    state();
    // pemilih dari alur mockup ikut masuk antrean
    if (d.nim && !$(`[data-nim="${d.nim}"]`)) {
      $("#antrean tbody").insertAdjacentHTML("afterbegin", `<tr class="fresh" data-nim="${d.nim}"><td class="mono">${d.nim}</td><td class="mono">${(d.pub || "30820122").slice(0, 8)}…${(d.pub || "c4f1").slice(-4)}</td><td><span class="tag wait">Menunggu</span></td><td class="num">—</td></tr>`);
    }
    const hitungTunggu = () => {
      const n = $$("#antrean .tag.wait").length;
      $("#catat").textContent = n ? `Catat ${n} ke chain` : "Semua tercatat";
      $("#catat").disabled = !n;
    };
    hitungTunggu();
    $("#catat").addEventListener("click", async () => {
      const b = $("#catat"); b.disabled = true;
      const baris = $$("#antrean tr").filter((tr) => $(".tag.wait", tr));
      baris.forEach((tr) => { const t = $(".tag", tr); t.textContent = "Ditambang…"; });
      const { nonce } = await tambang(`reg|${baris.length}|${Date.now()}`, 4, (n) => (b.textContent = `Menambang · nonce ${fmt(n)}`));
      const tinggi = Number($("#tinggi").textContent) + 1;
      baris.forEach((tr) => { $(".tag", tr).className = "tag ok"; $(".tag", tr).textContent = "Tercatat"; tr.lastElementChild.textContent = `#${tinggi}`; tr.classList.remove("fresh"); });
      $("#tinggi").textContent = tinggi;
      toast(`${baris.length} registrasi tercatat di block #${tinggi} (nonce ${fmt(nonce)})`);
      hitungTunggu();
    });
    // CRUD paslon saat ditutup
    $("#paslon").addEventListener("click", (e) => {
      const b = e.target.closest("[data-crud]"); if (!b) return;
      const tr = b.closest("tr");
      if (b.dataset.crud === "hapus") { tr.querySelector(".tag").className = "tag off"; tr.querySelector(".tag").textContent = "Nonaktif"; toast("Paslon dinonaktifkan (soft delete)"); }
      if (b.dataset.crud === "ubah") { const sel = tr.querySelector("[data-nama]"); const v = prompt("Nama tampilan", sel.textContent); if (v) { sel.textContent = v; toast("Perubahan dicatat sebagai CONTRACT_CALL"); } }
    });
    $("#tambah").addEventListener("submit", (e) => {
      e.preventDefault();
      const no = $("#no").value, nama = $("#nama").value.trim();
      if (!no || !nama) return toast("Isi nomor dan nama tampilan");
      $("#paslon tbody").insertAdjacentHTML("beforeend", `<tr class="fresh"><td><span class="paslon-no">${no}</span></td><td data-nama>${nama}</td><td><span class="tag ok">Aktif</span></td><td><div class="row" style="justify-content:flex-end"><button class="btn btn-secondary btn-sm" data-crud="ubah" type="button">Ubah</button><button class="btn btn-danger btn-sm" data-crud="hapus" type="button">Hapus</button></div></td></tr>`);
      toast(`Paslon ${no} ditambahkan`);
    });
    // validasi ulang
    $("#cek").addEventListener("click", async () => {
      const v = $("#validitas"); v.textContent = "Memeriksa hash dan prev hash…";
      await jeda(900);
      v.textContent = `${$("#tinggi").textContent} block valid`;
      $("#dicek").textContent = `Dicek ${new Date().toLocaleTimeString("id-ID")}`;
    });
    // suara masuk bertambah pelan, seperti pemungutan yang sedang berjalan
    setInterval(() => {
      if (!saklar.checked) return;
      const el = $("#suara"); const n = Number(el.dataset.v) + 1; el.dataset.v = n; el.textContent = fmt(n);
      $("#persen").textContent = `${Math.round((n / 1284) * 100)}% dari pemilih terdaftar`;
    }, 3500);
  },

  async explorer() {
    const d = store.get();
    let chain = [];
    let prev = "0".repeat(64);
    // rantai contoh: hash dihitung sungguhan dari isi block (tanpa PoW agar cepat), awalan nol dipalsukan untuk tampilan
    for (let i = 0; i <= 49; i++) {
      const tx = i === 0 ? 0 : i === 49 && d.sig ? 1 : 3 + (i * 7) % 5;
      const nonce = i === 0 ? 0 : 10000 + ((i * 7919) % 80000);
      const h = i === 0 ? "13ae32641f0fd1ea2ac4" + (await sha256("genesis")).slice(20) : "0000" + (await sha256(`${i}|${prev}|${nonce}`)).slice(4);
      chain.push({ i, nonce, h, prev, tx, waktu: Date.now() - (49 - i) * 180e3 });
      prev = h;
    }
    if (d.block) { chain[49].h = d.block.hash; chain[49].nonce = d.block.nonce; }
    if (!d.sig) chain.pop();
    let rusak = null;
    const daftar = $("#blocks");
    const render = (q = "") => {
      const tampil = chain.slice().reverse().filter((b) => !q || `#${b.i}` === q || String(b.i) === q || b.h.startsWith(q.toLowerCase()));
      daftar.innerHTML = tampil.slice(0, 12).map((b) => {
        const salah = rusak !== null && b.i >= rusak;
        const milikku = d.sig && b.i === 49;
        return `<li><details class="block ${salah ? "broken" : ""} ${milikku ? "me" : ""}" ${milikku || b.i === rusak ? "open" : ""}>
          <summary><span class="idx">#${b.i}</span><span class="c-nonce num soft">${fmt(b.nonce)}</span>
          <span class="c-hash mono trunc">${b.i ? powHtml(b.h) : b.h}</span><span class="c-prev mono trunc soft">${b.i ? powHtml(b.prev) : "—"}</span>
          <span class="c-tx num soft">${b.tx}</span><span class="c-status">${salah ? `<span class="tag bad">${b.i === rusak ? "Data berubah" : "Prev tak cocok"}</span>` : '<span class="tag ok">Valid</span>'}</span>
          <span class="chev">${ikon("down")}</span></summary>
          <div class="block-detail"><dl class="kv">
            <dt>Hash</dt><dd class="mono">${b.i ? powHtml(b.h) : b.h}</dd><dt>Prev hash</dt><dd class="mono">${b.i ? powHtml(b.prev) : "0"}</dd>
            <dt>Waktu</dt><dd>${new Date(b.waktu).toLocaleString("id-ID")}</dd><dt>Transaksi</dt><dd>${b.tx} · isi suara disembunyikan, hanya tanda tangan yang tampil</dd>
            ${milikku ? `<dt>Milikmu</dt><dd class="mono">${d.sig.slice(0, 24)}… (tanda tangan suaramu)</dd>` : ""}
          </dl>${b.i ? `<div class="row" style="margin-top:12px"><button class="btn btn-secondary btn-sm" type="button" data-ubah="${b.i}">Uji: ubah isi block ini</button></div>` : ""}</div>
        </details></li>`;
      }).join("") || '<li class="note">Tidak ada block yang cocok</li>';
      const ok = rusak === null;
      $("#valid").className = `tag ${ok ? "ok" : "bad"}`;
      $("#valid").textContent = ok ? "Chain valid" : `Rusak mulai block #${rusak}`;
      $("#pulihkan").hidden = ok;
      $("#panjang").textContent = chain.length;
    };
    render();
    $("#cari").addEventListener("input", (e) => render(e.target.value.trim()));
    daftar.addEventListener("click", (e) => {
      const b = e.target.closest("[data-ubah]"); if (!b) return;
      rusak = Number(b.dataset.ubah);
      toast(`Isi block #${rusak} diubah tanpa menambang ulang: hash tidak cocok lagi`);
      render($("#cari").value.trim());
    });
    $("#pulihkan").addEventListener("click", () => { rusak = null; toast("Rantai diganti dengan salinan sah dari node lain"); render($("#cari").value.trim()); });
  },
};

// tombol "Ulang demo dari awal" di mana pun: hapus sesi demo lalu kembali ke pendaftaran
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-ulang]")) return;
  sessionStorage.removeItem(KUNCI);
  location.href = "daftar.html";
});

// ---------- jalankan ----------
const shell = document.body.dataset.shell;
if (shell === "voter") kerangkaPemilih();
if (shell === "panel") kerangkaPanitia();
HALAMAN[document.body.dataset.page]?.();
