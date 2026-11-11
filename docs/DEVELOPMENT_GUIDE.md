# Panduan Pengembangan — DIPO AI Lead Management

Panduan ini untuk siapa pun (termasuk non-programmer) yang ingin menjalankan
dan menguji aplikasi di komputer sendiri.

> **Catatan Fase 0:** aplikasi belum bisa dijalankan. Perintah di bawah adalah
> rencana dan akan aktif mulai Fase 1. Bagian ini diperbarui di setiap fase.

## 1. Yang Perlu Di-install

| Software | Kegunaan |
|----------|----------|
| Git | Mengambil & menyimpan kode |
| Docker Desktop (atau Docker Engine + Compose) | Menjalankan seluruh aplikasi dalam "kotak" terisolasi |
| (Opsional) Python 3.12 | Menjalankan backend tanpa Docker |
| (Opsional) Node.js 20 LTS | Menjalankan frontend tanpa Docker |

Dengan Docker, Anda **tidak perlu** meng-install PostgreSQL atau Redis secara manual.

## 2. Branch Git

| Branch | Fungsi |
|--------|--------|
| `main` | Versi stabil. **Jangan dihapus**, tidak di-push langsung. |
| branch development | Tempat pengembangan. Perubahan masuk ke `main` lewat Pull Request. |

## 3. Konfigurasi (`.env`)

1. Salin file contoh: `cp .env.example .env`
2. File `.env` **tidak pernah di-commit** (sudah ada di `.gitignore`).
3. Untuk development, nilai default sudah aman:
   ```
   APP_ENV=development
   WHATSAPP_PROVIDER=simulated
   AI_PROVIDER=mock
   CONVERSION_PROVIDER=noop
   SIMULATOR_ENABLED=true
   ```

| Variabel | Development | Production |
|----------|-------------|------------|
| `APP_ENV` | `development` | `production` |
| `WHATSAPP_PROVIDER` | `simulated` (**wajib**) | `whatsapp_cloud` |
| `AI_PROVIDER` | `mock` atau LLM sungguhan | LLM sungguhan |
| `CONVERSION_PROVIDER` | `noop` (**wajib**) | `meta_capi` |
| `SIMULATOR_ENABLED` | `true` | `false` (**wajib**) |

Jika kombinasi tidak sesuai, aplikasi **menolak start** — ini disengaja sebagai pengaman.

## 4. Menjalankan Aplikasi (mulai Fase 1)

```bash
docker compose up --build
```

Rencana alamat:
- Backend API & Swagger: http://localhost:8000/docs
- Frontend: http://localhost:3000
- Simulator: http://localhost:3000/simulator

Berhenti: `Ctrl + C`, lalu `docker compose down`.

## 5. Menguji dengan Simulator

Skenario uji yang wajib bisa dilakukan:

| # | Skenario | Hasil yang diharapkan |
|---|----------|-----------------------|
| 1 | Buat customer dummy | Muncul di daftar simulator, ditandai "SIMULATED" |
| 2 | Kirim "Halo" sebagai customer | AI membalas dan menanyakan nama |
| 3 | Jawab nama, domisili, unit | Data terisi di panel lead |
| 4 | Customer hanya tanya-tanya | Tag **Cold** |
| 5 | Customer tanya harga/kredit/test drive dengan data lengkap | Tag **Warm** |
| 6 | Domisili cocok dengan area sales | Lead di-assign ke sales yang tepat |
| 7 | Domisili tidak dikenal / customer minta bicara dengan orang | Masuk **Admin Queue** |
| 8 | Admin assign lead dari Admin Queue | Lead pindah ke sales |
| 9 | Sales membalas dari dashboard | Balasan muncul di chat simulator; AI berhenti membalas |
| 10 | Buka riwayat percakapan | Semua pesan (customer, AI, sales, admin) tampil berurutan |

## 6. Automated Test (mulai Fase 1)

```bash
docker compose run --rm backend pytest
```

Prinsip:
- Test memakai `MockAIProvider` dan `SimulatedWhatsAppAdapter` → tanpa internet, tanpa biaya.
- Hasil test dilaporkan **apa adanya**. Test yang gagal tidak boleh disembunyikan.

## 7. Migrasi Database (mulai Fase 2)

```bash
docker compose run --rm backend alembic upgrade head      # terapkan migrasi
docker compose run --rm backend alembic revision --autogenerate -m "pesan"  # buat migrasi baru
```

## 8. Checklist Sebelum Commit

- [ ] Tidak ada token, password, API key, atau file `.env` di perubahan (`git diff`).
- [ ] Tidak ada data customer asli (hanya data fiktif).
- [ ] Test dijalankan dan hasilnya dicatat jujur.
- [ ] Dokumen di `docs/` diperbarui bila desain berubah.
- [ ] Pengaman Development Mode tidak diubah/dilemahkan.

## 9. Jika Credential Tidak Sengaja Ter-commit

1. **Segera cabut (revoke) credential tersebut** di dashboard penyedianya (Meta, AI provider, dll.).
2. Buat credential baru dan simpan hanya di `.env`.
3. Menghapus file dari Git **tidak cukup** karena repository publik dan riwayat
   commit tetap bisa dilihat — mencabut credential adalah langkah terpenting.
