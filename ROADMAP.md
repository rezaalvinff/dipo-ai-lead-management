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
| 3  | Cold/Warm Tagging & Routing ke Sales | 🔄 review pemilik project |
| 4  | Admin Queue, Handover & Balasan Sales | 🔄 review/pengujian |
| 5  | Frontend: Kerangka, Login, Simulator Chat mirip WhatsApp | 🔄 review/pengujian |
| 6  | Frontend: Dashboard Admin, Supervisor & Sales | 🔄 review/pengujian |
| 7  | Aktivasi WhatsApp Cloud API (setelah nomor tersedia) | 🔄 fondasi siap; menunggu nomor Meta |
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

## Phase 3 — Cold/Warm Tagging & Routing 🔄
- WARM hanya setelah assignment aktif ke sales berhasil disimpan.
- Lead incomplete, wilayah tidak dikenal/tidak dipetakan, sales tidak tersedia, atau kapasitas penuh tetap COLD dan masuk Admin Queue.
- Exact-match domisili setelah normalisasi dan alias; kota sekitar tidak diasumsikan otomatis ikut terlayani.
- Routing memakai territories + territory_mappings, prioritas, pemeriksaan ketersediaan/kapasitas, dan pemilihan agent yang paling lama belum menerima lead.
- Assignment/reassignment dicatat di assignments; assignment lama diberi ended_at.
- Admin dapat mengelola wilayah, alias, mapping, melihat lead dan riwayat assignment, serta melakukan assignment manual.
- Seed development menyediakan lima akun sales dummy: Medan, Jakarta, Pekanbaru, Surabaya, Padang. Area lain harus ditambahkan admin secara eksplisit.
- Automated tests disiapkan untuk mapped territory, unmapped territory, dan lead incomplete.

## Phase 4 — Admin Queue, Handover & Balasan Sales 🔄
- Admin Queue diturunkan dari percakapan open dengan handler `admin_queue` (tidak menambah tabel queue duplikat).
- Endpoint daftar antrean dan claim untuk admin/supervisor; lead tetap COLD sampai di-assign ke sales.
- Admin dapat mengambil antrean dan membalas melalui endpoint pesan manual yang sama; AI berhenti setelah handler menjadi manusia.
- Assignment ke sales menggunakan endpoint Phase 3 dan menyimpan riwayat assignment.
- Customer yang meminta manusia, AI tidak tersedia, data parsial, dan routing gagal diarahkan ke Admin Queue oleh aturan handover backend.

## Phase 5 — Frontend: Kerangka & Simulator 🔄
- Next.js + TypeScript, login berbasis cookie, layout dashboard responsif.
- Inbox dan simulator chat, buat customer dummy, kirim pesan sebagai customer, tampilkan riwayat.
- Banner **DEVELOPMENT MODE**; tidak ada pengiriman ke WhatsApp asli.
- Data inbox diperbarui berkala (polling 5 detik); WebSocket/SSE belum diimplementasikan.

## Phase 6 — Frontend: Dashboard 🔄
- KPI dashboard, daftar leads dengan tag COLD/WARM dan assignment manual.
- Admin Queue, inbox sales/admin, riwayat chat dan balasan dari nomor pusat melalui backend provider.
- Tampilan profil sales, beban lead, daftar wilayah, alias, dan form tambah wilayah/mapping.
- Endpoint ringkasan dashboard dan inbox projection.
- Pengelolaan user tingkat lanjut dan edit/nonaktifkan profil sales masih perlu disempurnakan.

## Phase 7 — Aktivasi WhatsApp Cloud API 🔄
- Fondasi webhook verification/signature, parsing pesan teks, referral CTWA, status pesan, anti-duplikasi, dan outgoing text adapter tersedia.
- Status readiness endpoint tidak menampilkan credential; free-form text diblokir setelah jendela 24 jam.
- Pengiriman sungguhan tetap terkunci oleh `WHATSAPP_CLOUD_SEND_ENABLED=false`.
- Belum selesai: template messages, media upload/send, end-to-end test nomor Meta, URL HTTPS publik, dan aktivasi nomor DIPO. Memerlukan nomor serta credential Meta yang belum tersedia.
- Checklist: `docs/WHATSAPP_CLOUD_SETUP.md`.

## Phase 8 — Conversion Event & Campaign Tracking
- `MetaConversionProvider`, pengisian `campaigns` dari referral iklan CTWA.

## Phase 9 — Deployment VPS & Hardening
- Nginx + HTTPS, backup DB, monitoring, rate limiting (termasuk login), review keamanan.

## Phase 10 — UAT & Go-Live
