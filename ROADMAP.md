# ROADMAP — DIPO AI Lead Management System

Pengembangan dibagi menjadi beberapa fase kecil. **Setiap fase harus disetujui
pemilik project sebelum fase berikutnya dimulai.**

Legenda status: ✅ selesai · 🔄 sedang dikerjakan · ⏳ belum dimulai

| Fase | Nama | Status |
|------|------|--------|
| 0  | Fondasi & Dokumentasi | 🔄 (menunggu persetujuan) |
| 1  | Kerangka Backend & Docker Compose | ⏳ |
| 2  | Database Model & Migrasi | ⏳ |
| 3  | Messaging Adapter & Simulator Backend | ⏳ |
| 4  | AI Provider & Pengumpulan Data Lead | ⏳ |
| 5  | Cold/Warm Tagging & Routing ke Sales | ⏳ |
| 6  | Admin Queue & Balasan Sales | ⏳ |
| 7  | Kerangka Frontend & Login | ⏳ |
| 8  | Frontend Simulator (Chat mirip WhatsApp) | ⏳ |
| 9  | Dashboard Admin & Sales | ⏳ |
| 10 | Adapter WhatsApp Cloud API (setelah nomor tersedia) | ⏳ |
| 11 | Conversion Event (Meta Conversions API) | ⏳ |
| 12 | Deployment VPS & Hardening Keamanan | ⏳ |
| 13 | UAT & Go-Live | ⏳ |

---

## Fase 0 — Fondasi & Dokumentasi
**Hasil:** struktur folder, `CLAUDE.md`, `README.md`, `ROADMAP.md`, dokumen arsitektur,
database, API, dan panduan pengembangan. Tidak ada kode fitur.

## Fase 1 — Kerangka Backend & Docker Compose
- Project FastAPI minimal, konfigurasi via environment variable (`pydantic-settings`).
- **Pengaman Development Mode** (validasi konfigurasi saat start).
- `docker-compose.yml`: `backend`, `worker`, `postgres`, `redis`.
- Endpoint `GET /api/v1/health` (cek koneksi DB & Redis).
- Setup `pytest` + `ruff`; test pertama untuk health & pengaman konfigurasi.
- **Uji keberhasilan:** `docker compose up` berjalan, health check mengembalikan OK.

## Fase 2 — Database Model & Migrasi
- Model SQLAlchemy sesuai `docs/DATABASE_DESIGN.md`.
- Migrasi awal Alembic.
- Script seed data dummy (sales, unit kendaraan, area domisili).
- **Uji:** migrasi naik/turun berhasil, seed berhasil.

## Fase 3 — Messaging Adapter & Simulator Backend
- Interface `MessagingProvider` + `SimulatedWhatsAppAdapter`.
- `InboundMessageService` (satu pintu untuk semua pesan masuk).
- Endpoint simulator: buat customer dummy, kirim pesan sebagai customer, lihat percakapan.
- Worker dasar (antrian Redis) untuk memproses pesan.
- **Uji:** kirim pesan dummy → tersimpan → muncul di riwayat percakapan.

## Fase 4 — AI Provider & Pengumpulan Data Lead
- Interface `AIProvider` + `MockAIProvider` (deterministik, untuk test tanpa biaya).
- Integrasi provider LLM sungguhan (opsional di dev, API key lewat `.env`).
- `LeadQualificationService`: AI menanyakan nama, domisili, unit; data diekstrak ke tabel `leads`.
- **Uji:** skenario percakapan dummy menghasilkan data lead lengkap.

## Fase 5 — Cold/Warm Tagging & Routing ke Sales
- Aturan tagging (misalnya: data lengkap + minta harga/test drive → Warm).
- `RoutingService`: pilih sales berdasarkan area domisili & beban kerja (round-robin).
- Riwayat perubahan tag & assignment tercatat.
- **Uji:** skenario Cold, Warm, dan routing ke sales yang benar.

## Fase 6 — Admin Queue & Balasan Sales
- Lead masuk Admin Queue bila: routing gagal, customer minta manusia, AI ragu, dll.
- Admin dapat meng-assign lead secara manual.
- Sales membalas customer (pesan keluar lewat adapter yang sama).
- AI berhenti membalas otomatis saat percakapan sudah ditangani manusia (*handover*).
- **Uji:** alur Admin Queue end-to-end via API simulator.

## Fase 7 — Kerangka Frontend & Login
- Next.js + TypeScript + Tailwind + shadcn/ui.
- Login (role: admin, sales, supervisor), layout dashboard.

## Fase 8 — Frontend Simulator
- Halaman simulator: daftar customer dummy, jendela chat mirip WhatsApp,
  panel samping berisi data lead, tag, dan sales yang ditugaskan.
- Update *real-time* (WebSocket/SSE).
- Banner jelas: **"DEVELOPMENT MODE — pesan tidak dikirim ke WhatsApp sungguhan"**.

## Fase 9 — Dashboard Admin & Sales
- Daftar leads (filter tag, status, sales, tanggal), detail lead, Admin Queue,
  inbox sales, statistik sederhana.

## Fase 10 — Adapter WhatsApp Cloud API
*(Dikerjakan setelah nomor WhatsApp Business API tersedia.)*
- `WhatsAppCloudAdapter`: kirim pesan, verifikasi webhook, validasi signature,
  status pesan (sent/delivered/read), aturan jendela 24 jam & template message.
- Pengujian di nomor test Meta sebelum nomor produksi.

## Fase 11 — Conversion Event
- `MetaConversionProvider` (mis. event Lead / QualifiedLead) untuk optimasi iklan.
- Di development hanya dicatat (log), tidak dikirim.

## Fase 12 — Deployment VPS & Hardening
- Docker image produksi, Nginx + HTTPS, backup database, monitoring & log,
  rate limiting, review keamanan.

## Fase 13 — UAT & Go-Live
- Uji coba bersama tim sales/admin, perbaikan, lalu rilis bertahap.
