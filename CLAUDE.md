# CLAUDE.md — Aturan Kerja untuk AI Assistant

File ini dibaca oleh Claude Code setiap kali bekerja di repository ini.
Ikuti semua aturan di bawah tanpa pengecualian.

## Konteks Project

- Nama: **DIPO AI Lead Management System** untuk Mitsubishi DIPO.
- Tujuan: AI membalas customer WhatsApp, mengumpulkan **nama, domisili, unit**,
  memberi tag **Cold/Warm**, me-routing lead ke **sales**, dan menyediakan **Admin Queue**.
- Nomor WhatsApp API **belum ada** → semua fitur harus bisa diuji lewat
  **Simulated WhatsApp Mode**.
- Pemilik project **bukan programmer profesional**: jelaskan dengan bahasa sederhana.

## Bahasa

- Dokumentasi & penjelasan: **Bahasa Indonesia**.
- Kode, nama variabel, nama tabel, commit message: **Bahasa Inggris** boleh.

## Alur Kerja

1. Kerjakan **satu fase** dari [ROADMAP.md](ROADMAP.md) setiap kali.
2. **Jangan lanjut ke fase berikutnya** sebelum pemilik project menyetujui.
3. Jangan membuat repository baru. Jangan menghapus branch `main`.
4. Kembangkan di branch development yang ditentukan; jangan push ke `main` langsung.
5. Setiap fase diakhiri dengan: ringkasan perubahan, hasil testing **yang benar-benar
   dijalankan**, dan usulan langkah berikutnya.
6. **Jangan mengarang hasil testing.** Jika test tidak dijalankan atau gagal, katakan apa adanya.

## Keamanan (Repository PUBLIC)

- **Dilarang** meng-commit token, API key, password, secret, atau file `.env`.
- **Dilarang** meng-commit data customer asli. Gunakan data fiktif
  (nomor `+62800000000xx`, nama seperti "Customer Dummy 01").
- Semua credential dibaca dari environment variable. Contoh nilai hanya di
  `.env.example` dan harus berupa *placeholder* (`changeme`, `your-token-here`).
- Sebelum commit, periksa `git diff` untuk memastikan tidak ada rahasia.

## Aturan Arsitektur (wajib)

- **Adapter pattern** untuk semua sistem eksternal:
  - WhatsApp: `SimulatedWhatsAppAdapter` dan `WhatsAppCloudAdapter`
    (keduanya mengikuti interface `MessagingProvider`).
  - AI: `MockAIProvider` dan provider LLM sungguhan (interface `AIProvider`).
  - Conversion event: `NoopConversionProvider` dan `MetaConversionProvider`
    (interface `ConversionProvider`).
- **Business logic hanya ada di `backend/app/services/`.** Endpoint (`api/`), webhook,
  simulator, dan worker hanya memanggil service. Simulator **tidak boleh** punya
  logika bisnis sendiri.
- Pesan masuk dari simulator dan dari webhook WhatsApp **harus** melewati handler
  yang sama (`InboundMessageService`).
- Proses lambat (panggilan AI, kirim pesan) dijalankan di **background worker**.

## Pengaman Development Mode (wajib dijaga)

- `APP_ENV=development` → aplikasi **wajib** memakai `WHATSAPP_PROVIDER=simulated`
  dan `CONVERSION_PROVIDER=noop`. Jika konfigurasi lain terdeteksi, aplikasi
  **menolak start** (fail fast).
- `WhatsAppCloudAdapter` dan `MetaConversionProvider` wajib mengecek ulang
  `APP_ENV == "production"` sebelum mengirim apa pun (pengaman lapis kedua).
- Endpoint `/api/v1/simulator/*` hanya aktif bila `SIMULATOR_ENABLED=true`
  dan **tidak boleh** aktif di production.
- Jangan pernah menghapus atau melemahkan pengaman ini.

## Konvensi Kode

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x (style typed), Alembic, Pydantic v2,
  `ruff` untuk lint/format, `pytest` untuk test.
- Frontend: Next.js (App Router), TypeScript strict, Tailwind CSS, shadcn/ui,
  ESLint + Prettier.
- Perubahan skema database **selalu** lewat migrasi Alembic.
- Nomor telepon disimpan dalam format E.164 (`+628...`).
- Waktu disimpan dalam UTC (`timestamptz`), ditampilkan dalam WIB di frontend.

## Dokumen Rujukan

- Arsitektur: `docs/ARCHITECTURE.md`
- Database: `docs/DATABASE_DESIGN.md`
- API: `docs/API_DESIGN.md`
- Panduan dev: `docs/DEVELOPMENT_GUIDE.md`

Jika implementasi berbeda dari dokumen, perbarui dokumennya dalam commit yang sama.
