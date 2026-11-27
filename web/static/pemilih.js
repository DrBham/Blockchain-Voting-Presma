// Perilaku halaman pemilih (daftar, verifikasi, masuk, bilik, bukti). Server tetap memeriksa semuanya;
// skrip ini hanya umpan balik langsung. Pola diambil dari docs/mockup/app.js.
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

// ---------- ikon ----------
const IKON = {
  key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
  mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
};
$$("[data-icon]").forEach((el) => IKON[el.dataset.icon] &&
  el.insertAdjacentHTML("afterbegin", `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${IKON[el.dataset.icon]}</svg>`));

// ---------- NIM ----------
const FAKULTAS = "ABCDEFGKLNP";
function cekNim(nim) {
  if (!nim) return ["", ""];
  if (!/^[A-Z]/.test(nim)) return ["bad", "Diawali satu huruf kode fakultas"];
  if (!FAKULTAS.includes(nim[0])) return ["bad", `Kode fakultas '${nim[0]}' tidak terdaftar di UNTAD`];
  if (!/^[A-Z]\d{7,8}$/.test(nim)) return ["bad", "1 huruf diikuti 7 atau 8 angka"];
  return ["good", "Format NIM valid. Kode dikirim ke email kampus NIM ini"];
}
function tandai(input, msg, [kelas, teks]) {
  input.classList.remove("bad", "good");
  if (kelas) input.classList.add(kelas);
  input.toggleAttribute("aria-invalid", kelas === "bad");
  msg.className = `msg ${kelas}`;
  msg.textContent = teks;
}

// ---------- tampilkan password ----------
$$("[data-peek]").forEach((b) => b.addEventListener("click", () => {
  const inp = $(`#${b.dataset.peek}`);
  const lihat = inp.type === "password";
  inp.type = lihat ? "text" : "password";
  b.textContent = lihat ? "Sembunyikan" : "Tampilkan";
}));

// ---------- kode 6 kotak ----------
function kotakOtp(wadah, onLengkap) {
  const kotak = $$("input", wadah);
  const nilai = () => kotak.map((k) => k.value).join("");
  const isi = (kode) => {
    kotak.forEach((k, i) => { k.value = kode[i] || ""; k.classList.toggle("filled", !!k.value); });
    kotak[Math.min(kode.length, 5)].focus();
    if (kode.length === 6) onLengkap(kode);
  };
  kotak.forEach((k, i) => {
    k.addEventListener("input", () => {
      const angka = k.value.replace(/\D/g, "");
      if (angka.length > 1) return isi(angka.slice(0, 6));  // autofill/IME memasukkan seluruh kode ke satu kotak
      k.value = angka;
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
  return { nilai };
}

// ---------- daftar ----------
const formDaftar = $("#form-daftar");
if (formDaftar) {
  const nim = $("#nim"), email = $("#email"), pw = $("#pw"), pw2 = $("#pw2");
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
    $("#pw-msg").className = "msg";
    $("#pw-msg").textContent = v ? ["Terlalu lemah", "Lemah", "Cukup", "Kuat", "Sangat kuat"][s] : "Minimal 8 karakter";
  });
  pw2.addEventListener("input", () => tandai(pw2, $("#pw2-msg"),
    !pw2.value ? ["", ""] : pw2.value === pw.value ? ["good", "Cocok"] : ["bad", "Belum sama dengan password"]));
  formDaftar.addEventListener("submit", (e) => {
    const salah = [];
    if (cekNim(nim.value)[0] !== "good") { salah.push(nim); tandai(nim, $("#nim-msg"), nim.value ? cekNim(nim.value) : ["bad", "NIM wajib diisi"]); }
    if (pw.value.length < 8) { salah.push(pw); tandai(pw, $("#pw-msg"), ["bad", "Minimal 8 karakter"]); }
    if (!pw2.value || pw2.value !== pw.value) { salah.push(pw2); tandai(pw2, $("#pw2-msg"), ["bad", "Belum sama dengan password"]); }
    if (salah.length) { e.preventDefault(); salah[0].focus(); return; }
    const btn = $("button[type=submit]", formDaftar);
    btn.disabled = true;
    btn.textContent = "Membuat dompet RSA…";
  });
}

// ---------- verifikasi: kirim otomatis begitu 6 digit terisi ----------
const formKode = $("#form-kode[data-otomatis]");
if (formKode) {
  kotakOtp($("#otp", formKode), () => { $("#otp-msg").className = "msg"; $("#otp-msg").textContent = "Memeriksa kode…"; formKode.submit(); });
  $("#otp input", formKode).focus();
}

// tombol kirim ulang menunggu jeda 60 detik dari server
const ulang = $("[data-sisa]");
if (ulang && Number(ulang.dataset.sisa) > 0) {
  const teks = ulang.textContent;
  let sisa = Number(ulang.dataset.sisa);
  ulang.disabled = true;
  const tick = () => {
    if (sisa <= 0) { ulang.disabled = false; ulang.textContent = teks; return; }
    ulang.textContent = `${teks} (${sisa} detik)`;
    sisa--;
    setTimeout(tick, 1000);
  };
  tick();
}

// ---------- masuk ----------
const formMasuk = $("#form-masuk");
if (formMasuk) {
  const nim = $("#nim");
  kotakOtp($("#otp", formMasuk), () => { $("#otp-msg").className = "msg"; $("#otp-msg").textContent = "Kode lengkap"; });
  nim.addEventListener("input", () => {
    nim.value = nim.value.toUpperCase().replace(/\s/g, "");
    tandai(nim, $("#nim-msg"), cekNim(nim.value)[0] === "bad" ? cekNim(nim.value) : ["", ""]);
  });
  formMasuk.addEventListener("submit", (e) => {
    const pw = $("#pw");
    if (cekNim(nim.value)[0] !== "good") { e.preventDefault(); tandai(nim, $("#nim-msg"), ["bad", "NIM tidak valid"]); nim.focus(); return; }
    if (!pw.value) { e.preventDefault(); tandai(pw, $("#pw-msg"), ["bad", "Password wajib diisi"]); pw.focus(); return; }
    const kirimUlang = e.submitter && e.submitter.value === "kirim_ulang";
    if (!kirimUlang && $$("#otp input", formMasuk).map((k) => k.value).join("").length !== 6) {
      e.preventDefault();
      $("#otp", formMasuk).classList.add("bad");
      $("#otp-msg").className = "msg bad";
      $("#otp-msg").textContent = "Isi 6 digit kode pemilih";
      $("#otp input", formMasuk).focus();
    }
  });
}

// ---------- bilik: dialog Setuju / Batal ----------
const formBilik = $("#form-bilik");
if (formBilik) {
  const kirim = $("#kirim"), dlg = $("#konfirmasi"), teks = $("#pilihan-teks");
  const dipilih = () => $("input[name=paslon]:checked", formBilik);
  kirim.disabled = true;
  $$("input[name=paslon]", formBilik).forEach((r) => r.addEventListener("change", () => {
    kirim.disabled = false;
    teks.textContent = `Paslon ${r.value} dipilih. Periksa lagi sebelum mengirim`;
  }));
  formBilik.addEventListener("submit", (e) => {
    if (formBilik.dataset.kirim) return;  // dikirim dari tombol Setuju
    e.preventDefault();
    const p = dipilih();
    if (!p) return;
    $("#dlg-no").textContent = p.value;
    $("#dlg-nama").textContent = p.dataset.nama;
    dlg.showModal();
    $("#batal").focus();  // fokus awal di Batal agar Enter tidak langsung mengirim
  });
  // batal: surat suara dikosongkan lagi, pemilih bebas memilih ulang
  $("#batal").addEventListener("click", () => {
    dlg.close();
    $$("input[name=paslon]", formBilik).forEach((r) => (r.checked = false));
    kirim.disabled = true;
    teks.textContent = "Pilihan dibatalkan. Silakan pilih lagi";
  });
  dlg.addEventListener("cancel", (e) => { if (formBilik.dataset.kirim) e.preventDefault(); });
  $("#setuju").addEventListener("click", () => {
    formBilik.dataset.kirim = "1";
    $("#dlg-foot").hidden = true;
    $("#dlg-teks").hidden = true;
    $("#langkah-kirim").hidden = false;
    formBilik.requestSubmit();
  });
}

// ---------- bukti: polling status transaksi tiap 2 detik ----------
const bukti = $("#bukti");
if (bukti) {
  const li = $$("#status li");
  const powHtml = (h) => `<span class="pow">${h.match(/^0*/)[0]}</span>${h.replace(/^0*/, "")}`;
  const cek = async () => {
    let d;
    try {
      const r = await fetch(bukti.dataset.api, { headers: { Accept: "application/json" } });
      d = await r.json();
      if (!r.ok) throw new Error(d.error || "node tidak menjawab");
    } catch (err) {
      $("#poll-msg").className = "msg bad";
      $("#poll-msg").textContent = `Gagal mengecek status: ${err.message}. Dicoba lagi`;
      return setTimeout(cek, 2000);
    }
    $("#poll-msg").textContent = "";
    if (d.status !== "block") {
      $("#m-state").textContent = d.status === "pool" ? "menunggu block berikutnya" : "transaksi belum terlihat di node ini";
      return setTimeout(cek, 2000);
    }
    li.forEach((x) => (x.className = "ok"));
    if (d.nonce !== undefined) {
      $("#m-nonce").textContent = d.nonce.toLocaleString("id-ID");
      $("#m-hash").innerHTML = powHtml(d.hash);
      $("small", li[1]).textContent = `nonce ${d.nonce.toLocaleString("id-ID")} ditemukan`;
    }
    $("#m-state").textContent = "hash memenuhi difficulty, block sah";
    $("small", li[2]).textContent = `block #${d.block}`;
    $("#judul").textContent = "Suaramu tercatat";
    $("#sub").textContent = `Ada di block #${d.block}. Simpan tanda tangan di bawah untuk mengecek kapan saja`;
    $("#b-index").textContent = `#${d.block}`;
    $("#tag-bukti").className = "tag ok";
    $("#tag-bukti").textContent = "Tercatat";
  };
  cek();
}
