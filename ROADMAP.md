# ROADMAP — DIPO AI Lead Management System

Pengembangan dibagi menjadi beberapa phase. **Setiap phase harus disetujui
pemilik project sebelum phase berikutnya dimulai.** Isi phase berikutnya bisa
berubah mengikuti instruksi pemilik project.

Legenda status: ✅ selesai · 🔄 menunggu persetujuan · ⏳ belum dimulai

| Phase | Nama | Status |
|-------|------|--------|
| 0  | Fondasi & Dokumentasi | ✅ |
| 1  | Backend, Database, Simulated WhatsApp, Fondasi WhatsApp Cloud API | ✅ |
| 2  | AI Agent & Knowledge Base (nama, domisili, unit + handover) | 🔄 |
| 3  | Cold/Warm Tagging & Routing ke Sales | ⏳ |
| 4  | Admin Queue, Handover & Balasan Sales | ⏳ |
| 5  | Frontend: Kerangka, Login, Simulator Chat mirip WhatsApp | ⏳ |
| 6  | Frontend: Dashboard Admin, Supervisor & Sales | ⏳ |
| 7  | Aktivasi WhatsApp Cloud API (setelah nomor tersedia) | ⏳ |
| 8  | Conversion Event (Meta Conversions API) & Campaign Tracking | ⏳ |
| 9  | Deployment VPS & Hardening Keamanan | ⏳ |
| 10 | UAT & Go-Live | ⏳ |

---

## Phase 0 — Fondasi & Dokumentasi ✅
Struktur folder, `CLAUDE.md`, `README.md`, `ROADMAP.md`, dokumen arsitektur, database, API, panduan.

## Phase 1 — Backend, Database, Simulated WhatsApp ✅
- FastAPI, konfigurasi `.env`, logging, format error seragam, health check.
- Autentikasi JWT (header/cookie) + RBAC (admin, supervisor, sales).
- 15 tabel + migrasi Alembic + seed data dummy.
- Background worker (ARQ + Redis).
- Simulated WhatsApp: customer dummy, kirim pesan sebagai customer, balasan Mock AI,
  riwayat, waktu (WIB), status pesan, percakapan baru, hapus/reset.
- Fondasi WhatsApp Cloud API: verifikasi webhook, handler pesan masuk, outgoing
  service, status handler, validasi signature, proteksi duplikat. **Belum aktif.**
- Pengaman 3 lapis agar development tidak bisa mengirim pesan sungguhan.
- Docker Compose (postgres, redis, migrate, backend, worker).

## Phase 2 — AI Agent & Knowledge Base 🔄
- Provider layer modular: `mock` (gratis), `anthropic` (Claude API), `openai` (OpenAI API).
  API key terpisah dari langganan Claude Pro.
- AI mengumpulkan nama, domisili (kota/kabupaten), unit. Satu pertanyaan per balasan,
  paham informal/typo, menerima koreksi, tidak memaksa (maks. 2x per data).
- Conversation state (`qualification_states`) divalidasi backend. AI tidak menentukan status lead.
- Handover otomatis + closing message yang bisa diedit admin (`app_settings`).
- AI berhenti saat diambil alih manusia (termasuk saat AI sedang berpikir).
- Knowledge base: model, varian, spesifikasi, harga, promo, DP, angsuran, FAQ, dealer,
  dengan alur persetujuan (`draft` → `approved`) dan masa berlaku.
- Guard backend: angka harga/promo yang tidak ada di knowledge base diblokir.
- 24 skenario percakapan lewat Simulated WhatsApp. Detail: `docs/AI_AGENT.md`.

## Phase 3 — Cold/Warm Tagging & Routing
- Aturan Cold/Warm yang jelas & dapat diuji.
- Pencocokan domisili ke `territories` (alias), routing ke sales via `territory_mappings`
  (prioritas + round-robin + batas beban kerja), riwayat di `assignments`.

## Phase 4 — Admin Queue, Handover & Balasan Sales
- `admin_queue_items`: routing gagal, customer minta manusia, AI ragu, komplain.
- Admin assign manual. Handover: AI berhenti saat ditangani manusia.

## Phase 5 — Frontend: Kerangka & Simulator
- Next.js + TypeScript + Tailwind + shadcn/ui, login, layout.
- Halaman simulator mirip WhatsApp + panel data lead, banner **DEVELOPMENT MODE**.
- Update real-time (WebSocket/SSE).

## Phase 6 — Frontend: Dashboard
- Daftar & detail lead, Admin Queue, inbox sales, master data, statistik.

## Phase 7 — Aktivasi WhatsApp Cloud API
- Uji dengan nomor test Meta, template message, jendela 24 jam, media.
- Aktivasi bertahap dengan `WHATSAPP_CLOUD_SEND_ENABLED`.

## Phase 8 — Conversion Event & Campaign Tracking
- `MetaConversionProvider`, pengisian `campaigns` dari referral iklan CTWA.

## Phase 9 — Deployment VPS & Hardening
- Nginx + HTTPS, backup DB, monitoring, rate limiting (termasuk login), review keamanan.

## Phase 10 — UAT & Go-Live
