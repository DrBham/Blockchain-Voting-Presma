// Papan pemilihan live: polling /api/papan tiap 3 detik. Angka per Paslon hanya ada saat status dihitung,
// lalu ditampilkan bertahap block demi block dari /tally.per_block (dijumlahkan di sini).
"use strict";

const wadah = document.getElementById("papan");
const tagStatus = document.getElementById("papan-status");
const fmt = (n) => Number(n || 0).toLocaleString("id-ID");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const jeda = (ms) => new Promise((r) => setTimeout(r, ms));
const tanpaGerak = matchMedia("(prefers-reduced-motion: reduce)").matches;
const persen = (a, b) => (b ? Math.round((100 * a) / b) : 0);
const powHtml = (h) => { const m = /^0+/.exec(h || ""); return m && m[0].length >= 2 ? `<span class="pow">${m[0]}</span>${esc(h.slice(m[0].length))}` : esc(h); };
const KELAS = { dibuka: "ok", ditutup: "wait", dihitung: "ok" };

let terakhir = "", menghitung = false;

function stat(label, nilai, meta, utama = false) {
  return `<div class="card tight stat ${utama ? "lead-stat" : ""}"><p class="stat-label">${label}</p><p class="stat-value num">${nilai}</p><p class="stat-meta">${meta}</p></div>`;
}

function daftarPaslon(paslon) {
  if (!paslon.length) return '<p class="note">Belum ada Paslon aktif</p>';
  return `<div class="grid g-paslon">${paslon.map((p) => `<div class="card tight row"><span class="paslon-no">${p.nomor}</span><div><b class="ink">${esc(p.nama)}</b>${p.visi ? `<p class="small muted">${esc(p.visi)}</p>` : ""}</div></div>`).join("")}</div>`;
}

function persiapan(d) {
  return `<p class="note">Pemungutan belum dibuka. Panitia membuka pemungutan dari ruang panitia setelah Paslon dan pemilih tercatat di chain</p>
    <section class="grid g-paslon">${stat("Pemilih terdaftar", fmt(d.terdaftar), "Tercatat lewat transaksi REGISTER")}${stat("Panjang chain", fmt(d.panjang), `Block terakhir #${d.block_terakhir?.index ?? "-"}`)}</section>
    <section class="card"><div class="card-head"><div><h2>Pasangan calon</h2><p>Dibaca dari PaslonContract di chain</p></div></div>${daftarPaslon(d.paslon)}</section>`;
}

function dibuka(d) {
  const p = persen(d.suara_masuk, d.terdaftar);
  const b = d.block_terakhir || {};
  const maks = Math.max(1, ...(d.per_jam || []).map((j) => j.jumlah));
  const jam = (d.per_jam || []).length
    ? `<ul class="per-jam">${d.per_jam.map((j) => `<li><span class="num soft">${esc(j.jam)}</span><span class="bar"><i style="width:${(100 * j.jumlah) / maks}%"></i></span><span class="num">${fmt(j.jumlah)}</span></li>`).join("")}</ul>`
    : '<p class="small muted">Belum ada suara yang ditambang</p>';
  return `<section class="grid g-stats g-3">
      ${stat("Suara masuk", fmt(d.suara_masuk), `Dari ${fmt(d.terdaftar)} pemilih terdaftar`, true)}
      <div class="card tight stat"><p class="stat-label">Partisipasi</p><p class="stat-value num">${p}%</p><div class="bar" role="img" aria-label="Partisipasi ${p} persen"><i style="width:${p}%"></i></div></div>
      ${stat("Block terbaru", `#${b.index ?? "-"}`, `<span class="mono trunc">${powHtml(b.hash || "")}</span>`)}
    </section>
    <section class="card"><div class="card-head"><div><h2>Suara per jam</h2><p>Dihitung dari waktu transaksi VOTE di chain. Isi pilihan tetap terenkripsi</p></div></div>${jam}</section>
    <p class="note">Perolehan per Paslon belum bisa dilihat siapa pun, termasuk panitia: pilihan dienkripsi kunci pemilu yang baru dibuka setelah pemungutan ditutup</p>`;
}

function ditutup(d) {
  return `<p class="note">Pemungutan ditutup. Menunggu kunci pemilu dibuka</p>
    <section class="grid g-paslon">${stat("Suara masuk", fmt(d.suara_masuk), `Dari ${fmt(d.terdaftar)} pemilih terdaftar`, true)}${stat("Partisipasi", `${persen(d.suara_masuk, d.terdaftar)}%`, "Suara masuk dibagi pemilih terdaftar")}</section>`;
}

function hasil(d, angka, tidakSah, catatan) {
  const total = Object.values(angka).reduce((a, b) => a + b, 0);
  const unggul = Math.max(0, ...Object.values(angka));
  return `<section class="grid g-paslon">${d.paslon.map((p) => {
      const n = angka[p.nomor] || 0;
      return `<div class="card hasil ${n && n === unggul ? "unggul" : ""}"><div class="row"><span class="paslon-no">${p.nomor}</span><b class="ink">${esc(p.nama)}</b></div>
        <p class="stat-value num">${fmt(n)}</p><div class="bar"><i style="width:${persen(n, total)}%"></i></div><p class="stat-meta">${persen(n, total)}% suara sah</p></div>`;
    }).join("")}</section>
    <p class="small soft">${catatan}${tidakSah === null ? "" : ` · Tidak sah ${fmt(tidakSah)}`}</p>`;
}

function dihitung(d) {
  if (d.peringatan) return `<p class="note bad">${esc(d.peringatan)}</p>`;
  return `${hasil(d, d.hasil || {}, d.tidak_sah, `Total ${fmt(d.suara_masuk)} suara masuk`)}
    <p class="note">Siapa pun bisa menghitung ulang dari chain: kunci privat pemilu sudah tercatat di transaksi buka_kunci, jadi setiap sandi di <a href="${wadah.dataset.explorer}">explorer</a> bisa didekripsi sendiri</p>`;
}

async function animasi(d) {
  // Penghitungan bertahap: tiap langkah menambahkan suara sah dari satu block.
  menghitung = true;
  const acc = {};
  for (const [i, pb] of (d.per_block || []).entries()) {
    for (const [no, n] of Object.entries(pb.hasil)) acc[no] = (acc[no] || 0) + n;
    wadah.innerHTML = hasil(d, acc, null, `Menghitung block #${pb.index} (${i + 1} dari ${d.per_block.length})`);
    await jeda(800);
  }
  menghitung = false;
}

async function muat() {
  if (menghitung) return;
  let d;
  try {
    d = await (await fetch(wadah.dataset.api, { headers: { Accept: "application/json" } })).json();
  } catch {
    d = { status: null };
  }
  const kunci = JSON.stringify(d);
  if (kunci === terakhir) return;
  const pertamaDihitung = d.status === "dihitung" && !terakhir.includes('"status":"dihitung"');
  terakhir = kunci;
  tagStatus.className = `tag ${d.status ? KELAS[d.status] || "off" : "bad"}`;
  tagStatus.textContent = d.status ? d.label : "Node tidak terjangkau";
  if (!d.status) { wadah.innerHTML = '<p class="note bad">Node tidak terjangkau. Papan mencoba lagi tiap 3 detik</p>'; return; }
  if (pertamaDihitung && !tanpaGerak && !d.peringatan) await animasi(d);
  wadah.innerHTML = { persiapan, dibuka, ditutup, dihitung }[d.status]?.(d) ?? "";
}

muat();
setInterval(muat, 3000);
