// Ruang panitia dan explorer: form ubah Paslon di halaman, konfirmasi aksi berisiko, tombol sibuk saat menambang.
"use strict";

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ubah]");
  if (!b) return;
  const baris = document.getElementById(`ubah-${b.dataset.ubah}`);
  baris.hidden = !baris.hidden;
  document.querySelectorAll(`[data-ubah="${b.dataset.ubah}"][aria-expanded]`).forEach((t) => t.setAttribute("aria-expanded", String(!baris.hidden)));
  if (!baris.hidden) baris.querySelector("input:not([type=hidden])").focus();
});

document.addEventListener("submit", (e) => {
  const form = e.target;
  if (form.dataset.konfirmasi && !confirm(form.dataset.konfirmasi)) { e.preventDefault(); return; }
  // Transaksi admin langsung ditambang (proof of work), jadi bisa butuh beberapa detik
  const tombol = form.querySelector("button[type=submit]");
  if (tombol && form.method === "post") { tombol.disabled = true; tombol.textContent = "Memproses"; }
});
