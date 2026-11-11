# DIPO AI Lead Management System

Sistem manajemen *leads* berbasis AI untuk **Mitsubishi DIPO**, terintegrasi dengan
**WhatsApp Business** melalui **Meta WhatsApp Cloud API**.

> **Status saat ini: Fase 0 — Fondasi & Dokumentasi.**
> Belum ada fitur aplikasi yang berjalan. Repository ini baru berisi struktur folder
> dan dokumen perencanaan. Lihat [ROADMAP.md](ROADMAP.md).

---

## 1. Apa yang dilakukan sistem ini?

1. Customer mengirim pesan WhatsApp ke nomor bisnis Mitsubishi DIPO.
2. **AI** membalas secara otomatis dan mengumpulkan data penting:
   **nama**, **domisili**, dan **unit kendaraan** yang diminati.
3. Lead diberi label **Cold** atau **Warm** berdasarkan tingkat ketertarikan.
4. Lead yang sudah lengkap di-*routing* (diteruskan) ke **sales** yang sesuai.
5. Kasus yang tidak bisa ditangani AI atau tidak bisa di-routing masuk ke **Admin Queue**.
6. Sales membalas customer langsung dari dashboard.
7. Semua riwayat percakapan tersimpan dan bisa ditelusuri.

## 2. Development Mode (Simulated WhatsApp)

Karena nomor WhatsApp API **belum tersedia**, aplikasi dirancang agar bisa dibangun dan
diuji sepenuhnya memakai **Simulated WhatsApp Mode**:

- Membuat customer dummy, mengirim pesan sebagai customer, dan melihat balasan AI
  dalam tampilan mirip WhatsApp.
- Menguji pengumpulan data, Cold/Warm tagging, routing ke sales, Admin Queue,
  balasan sales, dan riwayat percakapan.
- **Business logic yang dipakai sama persis dengan produksi.** Yang berbeda hanya
  "pintu keluar-masuk" pesan (adapter).
- Development Mode **dikunci** agar tidak bisa mengirim pesan WhatsApp sungguhan
  maupun *conversion event* produksi. Detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#5-pengaman-development-mode).

## 3. Teknologi

| Lapisan     | Teknologi                                                         |
|-------------|-------------------------------------------------------------------|
| Backend     | Python, FastAPI, SQLAlchemy, Alembic                              |
| Database    | PostgreSQL                                                        |
| Cache/Queue | Redis                                                             |
| Worker      | Background worker (Python, membaca antrian dari Redis)            |
| Frontend    | Next.js, TypeScript, Tailwind CSS, shadcn/ui                      |
| Deployment  | Docker, Docker Compose, VPS                                       |

## 4. Struktur Folder

```
dipo-ai-lead-management/
├── CLAUDE.md               # Aturan kerja untuk AI assistant (Claude Code)
├── README.md               # Dokumen ini
├── ROADMAP.md              # Rencana pengembangan per fase
├── docs/
│   ├── ARCHITECTURE.md     # Arsitektur sistem
│   ├── DATABASE_DESIGN.md  # Rancangan tabel database
│   ├── API_DESIGN.md       # Rancangan endpoint API
│   └── DEVELOPMENT_GUIDE.md# Panduan pengembangan & testing
├── backend/                # Aplikasi FastAPI + worker
│   ├── app/
│   │   ├── api/v1/         # Endpoint HTTP (router)
│   │   ├── core/           # Konfigurasi, keamanan, koneksi DB/Redis
│   │   ├── models/         # Model tabel (SQLAlchemy)
│   │   ├── schemas/        # Bentuk data request/response (Pydantic)
│   │   ├── repositories/   # Akses database (query)
│   │   ├── services/       # Business logic (inti sistem)
│   │   ├── adapters/
│   │   │   ├── whatsapp/   # Simulated & WhatsApp Cloud API
│   │   │   ├── ai/         # Mock AI & AI provider sungguhan
│   │   │   └── conversion/ # No-op (dev) & Meta Conversions API (prod)
│   │   └── workers/        # Background job (proses AI, kirim pesan)
│   ├── alembic/            # Migrasi database
│   └── tests/              # Automated test
├── frontend/               # Aplikasi Next.js (dashboard & simulator)
│   └── src/{app,components,lib}
├── infra/
│   ├── docker/             # Dockerfile
│   └── nginx/              # Reverse proxy untuk VPS
└── scripts/                # Script bantu (seed data dummy, dll.)
```

Folder yang masih kosong berisi file `.gitkeep` agar tetap tercatat di Git.

## 5. Dokumentasi

- [ROADMAP.md](ROADMAP.md) — urutan fase pengembangan
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — bagaimana komponen saling terhubung
- [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) — tabel dan relasinya
- [docs/API_DESIGN.md](docs/API_DESIGN.md) — daftar endpoint
- [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) — cara menjalankan & menguji
- [CLAUDE.md](CLAUDE.md) — aturan untuk AI assistant

## 6. Keamanan (Repository PUBLIC)

Repository ini **publik**. Jangan pernah meng-*commit*:

- Token / API key (Meta, AI provider, dll.), password, *secret*.
- Data customer asli (nama, nomor HP, percakapan).
- File `.env` (hanya `.env.example` berisi *placeholder* yang boleh di-commit).

Semua data contoh harus fiktif (misalnya nomor `+62800000000xx`).
