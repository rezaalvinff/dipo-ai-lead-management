# Panduan Pengembangan — DIPO AI Lead Management

Panduan ini untuk siapa pun, termasuk non-programmer, yang ingin menjalankan dan menguji aplikasi.

> **Status:** backend Phase 1 sudah bisa dijalankan. Frontend belum ada. Pengujian
> dilakukan lewat halaman Swagger (`/docs`) atau perintah `curl`.

## 1. Yang Perlu Di-install

| Software | Kegunaan |
|----------|----------|
| Git | Mengambil & menyimpan kode |
| Docker Desktop (atau Docker Engine + Compose v2) | Menjalankan seluruh aplikasi |
| (Opsional) Python 3.12+ | Menjalankan backend/test tanpa Docker |

Dengan Docker, Anda **tidak perlu** meng-install PostgreSQL atau Redis.

## 2. Branch Git

| Branch | Fungsi |
|--------|--------|
| `main` | Versi stabil. **Jangan dihapus**, tidak di-push langsung |
| branch development | Tempat pengembangan. Perubahan masuk ke `main` lewat Pull Request |

## 3. Konfigurasi (`.env`)

```bash
cp .env.example .env
```

- File `.env` **tidak pernah di-commit** karena sudah ada di `.gitignore`.
- Nilai default sudah aman untuk development (simulator, mock AI, noop conversion).
- Ganti `SEED_DEFAULT_PASSWORD` dengan password dev pilihan Anda (min. 8 karakter).
- Untuk menguji webhook dengan payload dummy, isi `WHATSAPP_APP_SECRET` dan
  `WHATSAPP_WEBHOOK_VERIFY_TOKEN` dengan teks bebas, **bukan** nilai asli dari Meta.

| Variabel | Development | Production |
|----------|-------------|------------|
| `APP_ENV` | `development` | `production` |
| `WHATSAPP_PROVIDER` | `simulated` (**wajib**) | `whatsapp_cloud` |
| `CONVERSION_PROVIDER` | `noop` (**wajib**) | `meta_capi` |
| `SIMULATOR_ENABLED` | `true` | `false` (**wajib**) |
| `WHATSAPP_CLOUD_SEND_ENABLED` | `false` (**wajib**) | `true` hanya saat siap go-live |
| `JWT_SECRET` | bebas | string acak ≥ 32 karakter (**wajib**) |

Jika kombinasi tidak sesuai, backend **dan** worker **menolak start** dengan pesan
`Unsafe configuration: ...`. Ini disengaja sebagai pengaman.

## 4. Menjalankan Aplikasi

```bash
docker compose up --build -d
```

Yang berjalan:

| Service | Fungsi |
|---------|--------|
| `postgres` | Database |
| `redis` | Antrian job |
| `migrate` | Menjalankan migrasi database sekali, lalu berhenti |
| `backend` | API di http://localhost:8000 |
| `worker` | Background worker yang membuat balasan AI |

Isi data dummy (admin, supervisor, 2 sales, 3 wilayah, contoh knowledge base):

```bash
docker compose exec backend python -m app.scripts.seed
```

Login admin: email `SEED_ADMIN_EMAIL`, password `SEED_DEFAULT_PASSWORD` (dari `.env`).

Cek kesehatan: buka http://localhost:8000/api/v1/health

Melihat log:

```bash
docker compose logs -f backend worker
```

Berhenti:

```bash
docker compose down
```

Hapus juga isi database:

```bash
docker compose down -v
```

## 5. Menguji Simulated WhatsApp (lewat Swagger)

1. Buka http://localhost:8000/docs
2. `POST /api/v1/auth/login` → klik **Try it out**, isi email & password admin → **Execute**.
   Browser otomatis menyimpan cookie login.
3. `POST /api/v1/simulator/contacts` → `{"display_name": "Customer Dummy 01"}`. Salin `id`-nya.
4. `POST /api/v1/simulator/contacts/{id}/messages` → `{"text": "Halo, mau tanya Pajero Sport"}`
5. Tunggu 1–2 detik, lalu `GET /api/v1/simulator/contacts/{id}/chat` → terlihat pesan customer dan balasan AI, lengkap dengan waktu (WIB) dan status.
6. Ubah status balasan AI: `POST /api/v1/simulator/messages/{message_id}/status` → `{"status": "read"}`
7. Percakapan baru: `POST /api/v1/simulator/contacts/{id}/conversations`
8. Bersihkan: `DELETE /api/v1/simulator/contacts/{id}` atau `POST /api/v1/simulator/reset`

| # | Skenario | Phase |
|---|----------|-------|
| 1 | Buat customer dummy, kirim pesan, terima balasan AI, lihat riwayat & status | ✅ Phase 1 |
| 2 | AI mengumpulkan nama, domisili, unit | ⏳ berikutnya |
| 3 | Cold/Warm tagging | ⏳ |
| 4 | Routing ke sales | ⏳ |
| 5 | Admin Queue | ⏳ |
| 6 | Sales membalas & AI berhenti (handover) | sebagian (balasan manual sudah ada) |

Catatan: balasan AI saat ini dibuat oleh **Mock AI**, yaitu jawaban tetap untuk pengujian.
Percakapan cerdas dibangun di phase berikutnya.

## 6. Automated Test

Test memakai database khusus `dipo_test` (dibuat sekali):

```bash
docker compose exec postgres createdb -U dipo dipo_test
```

Jalankan test:

```bash
docker compose run --rm -e TEST_DATABASE_URL=postgresql+psycopg://dipo:changeme@postgres:5432/dipo_test -e TEST_REDIS_URL=redis://redis:6379/15 backend pytest -q
```

Ganti `changeme` bila `POSTGRES_PASSWORD` di `.env` berbeda.

Lint (pemeriksa kualitas kode):

```bash
docker compose run --rm --no-deps backend ruff check .
```

Prinsip:
- Test memakai `MockAIProvider`, `SimulatedWhatsAppAdapter`, dan HTTP palsu. Tidak butuh internet, tidak ada biaya, tidak ada pesan sungguhan.
- Hasil test dilaporkan **apa adanya**.

## 7. Migrasi Database

```bash
docker compose run --rm backend alembic upgrade head
```

```bash
docker compose run --rm backend alembic revision --autogenerate -m "describe change"
```

File migrasi baru harus disalin keluar container (atau dibuat dengan Python lokal) lalu di-commit.

## 8. Tanpa Docker (opsional, untuk developer)

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
```

Jalankan PostgreSQL & Redis sendiri, isi `DATABASE_URL`/`REDIS_URL` ke `localhost` di `.env`, lalu:

```bash
alembic upgrade head
```

```bash
uvicorn app.main:create_app --factory --reload
```

```bash
arq app.workers.worker.WorkerSettings
```

Tanpa worker, set `JOB_QUEUE=inline` agar balasan AI dibuat langsung.

## 9. Checklist Sebelum Commit

- [ ] Tidak ada token, password, API key, atau file `.env` di perubahan (`git diff`).
- [ ] Tidak ada data customer asli (nomor simulasi `+62800…`, email `@example.com`).
- [ ] Test & lint dijalankan dan hasilnya dicatat jujur.
- [ ] Dokumen di `docs/` diperbarui bila desain berubah.
- [ ] Pengaman Development Mode tidak diubah/dilemahkan.

## 10. Jika Credential Tidak Sengaja Ter-commit

1. **Segera cabut (revoke) credential tersebut** di dashboard penyedianya (Meta, AI provider, dll.).
2. Buat credential baru dan simpan hanya di `.env`.
3. Menghapus file dari Git **tidak cukup** karena repository ini publik dan riwayat commit tetap bisa dilihat.
