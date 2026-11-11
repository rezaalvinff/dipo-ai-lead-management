# DIPO AI Lead Management System

Sistem manajemen *leads* berbasis AI untuk **Mitsubishi DIPO**, terintegrasi dengan
**WhatsApp Business** melalui **Meta WhatsApp Cloud API**.

> **Status saat ini: Phase 4–6 implemented; Phase 7 WhatsApp Cloud readiness** (branch `development`, menunggu review dan pengujian).
> Dashboard Next.js, inbox, simulator, Admin Queue, lead routing, dan fondasi webhook Cloud API tersedia. Aktivasi nomor sungguhan belum dilakukan karena nomor dan credential Meta belum tersedia. Lihat [ROADMAP.md](ROADMAP.md).

## Mulai Cepat

```bash
cp .env.example .env
```

```bash
docker compose up --build -d
```

```bash
docker compose exec backend python -m app.scripts.seed
```

Lalu buka http://localhost:8000/docs. Langkah lengkap ada di [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md).

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
├── docker-compose.yml      # postgres, redis, migrate, backend, worker
├── .env.example            # contoh konfigurasi (placeholder saja)
├── docs/
│   ├── ARCHITECTURE.md     # Arsitektur sistem
│   ├── AI_AGENT.md         # Cara kerja AI Agent, knowledge base, skenario uji
│   ├── DATABASE_DESIGN.md  # Rancangan tabel database
│   ├── API_DESIGN.md       # Rancangan endpoint API
│   └── DEVELOPMENT_GUIDE.md# Panduan pengembangan & testing
├── backend/                # Aplikasi FastAPI + worker
│   ├── app/
│   │   ├── api/v1/         # Endpoint HTTP (router)
│   │   ├── core/           # Konfigurasi & pengaman, DB/Redis, logging, error, JWT
│   │   ├── models/         # 20 tabel database (SQLAlchemy)
│   │   ├── schemas/        # Bentuk data request/response (Pydantic)
│   │   ├── services/       # Business logic (inti sistem)
│   │   ├── adapters/
│   │   │   ├── whatsapp/   # Simulated & WhatsApp Cloud API
│   │   │   ├── ai/         # Mock AI, Claude (Anthropic API), OpenAI + prompt
│   │   │   └── conversion/ # (menyusul) No-op & Meta Conversions API
│   │   ├── workers/        # Antrian job & background worker (ARQ)
│   │   └── scripts/        # seed data dummy
│   ├── alembic/            # Migrasi database
│   └── tests/              # Automated test (pytest)
├── frontend/               # Aplikasi Next.js (dashboard & simulator)
│   ├── app/                 # Login, inbox, dashboard, simulator, master data
├── infra/
│   ├── docker/             # backend.Dockerfile
│   └── nginx/              # Reverse proxy untuk VPS
└── scripts/                # Script bantu (seed data dummy, dll.)
```

Frontend dijalankan sebagai service Docker pada port 3000. Lihat panduan pengembangan untuk cara menjalankan seluruh stack.

## 5. Dokumentasi

- [ROADMAP.md](ROADMAP.md) — urutan fase pengembangan
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — bagaimana komponen saling terhubung
- [docs/AI_AGENT.md](docs/AI_AGENT.md) — AI Agent, knowledge base, handover, biaya AI
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
