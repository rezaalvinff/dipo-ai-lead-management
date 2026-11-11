# Rancangan API — DIPO AI Lead Management

Backend: **FastAPI**. Prefix semua endpoint: `/api/v1`.
Dokumentasi interaktif otomatis (Swagger) akan tersedia di `/docs` saat development.

> Rancangan awal (Fase 0). Endpoint dibuat bertahap sesuai [ROADMAP](../ROADMAP.md).

## Konvensi

- Format data: JSON. Waktu: ISO 8601 UTC (`2026-01-01T08:00:00Z`).
- Autentikasi: JWT di cookie httpOnly (kecuali webhook & health).
- Paginasi: `?page=1&page_size=20` → respons `{ "items": [...], "total": 120, "page": 1, "page_size": 20 }`.
- Format error:
  ```json
  { "error": { "code": "LEAD_NOT_FOUND", "message": "Lead tidak ditemukan" } }
  ```
- Role: `admin`, `supervisor`, `sales`. Sales hanya melihat lead miliknya.

## 1. Sistem

| Method | Path | Akses | Fungsi |
|--------|------|-------|--------|
| GET | `/health` | publik | Status aplikasi, DB, Redis, mode (`development`/`production`), provider aktif |

Contoh respons:
```json
{
  "status": "ok",
  "app_env": "development",
  "providers": { "whatsapp": "simulated", "ai": "mock", "conversion": "noop" },
  "checks": { "database": "ok", "redis": "ok" }
}
```

## 2. Autentikasi

| Method | Path | Fungsi |
|--------|------|--------|
| POST | `/auth/login` | Login dengan email & password |
| POST | `/auth/logout` | Logout |
| GET | `/auth/me` | Data user yang sedang login |

## 3. Leads

| Method | Path | Akses | Fungsi |
|--------|------|-------|--------|
| GET | `/leads` | semua | Daftar lead. Filter: `temperature`, `status`, `assigned_sales_id`, `area_id`, `is_simulated`, `q`, `date_from`, `date_to` |
| GET | `/leads/{id}` | semua* | Detail lead + data customer |
| PATCH | `/leads/{id}` | admin, sales* | Ubah data (nama, domisili, unit, status) |
| POST | `/leads/{id}/assign` | admin | Assign manual ke sales `{ "sales_id": "..." , "reason": "..." }` |
| GET | `/leads/{id}/events` | semua* | Riwayat perubahan lead |

\* sales hanya untuk lead miliknya.

## 4. Percakapan & Pesan

| Method | Path | Akses | Fungsi |
|--------|------|-------|--------|
| GET | `/conversations` | semua* | Daftar percakapan (filter `handler`, `assigned_user_id`, `unread`) |
| GET | `/conversations/{id}` | semua* | Detail percakapan |
| GET | `/conversations/{id}/messages` | semua* | Riwayat pesan (paginasi berdasarkan waktu) |
| POST | `/conversations/{id}/messages` | admin, sales* | Kirim balasan manual `{ "text": "..." }` → lewat `MessagingProvider` aktif |
| POST | `/conversations/{id}/handover` | admin, sales* | Ubah handler: `{ "to": "ai" | "sales" | "admin_queue" | "closed" }` |
| POST | `/conversations/{id}/read` | admin, sales* | Tandai sudah dibaca |

## 5. Admin Queue

| Method | Path | Akses | Fungsi |
|--------|------|-------|--------|
| GET | `/admin-queue` | admin, supervisor | Daftar item (filter `status`, `reason`) |
| POST | `/admin-queue/{id}/claim` | admin | Ambil item untuk ditangani |
| POST | `/admin-queue/{id}/resolve` | admin | Selesaikan `{ "action": "assign" | "return_to_ai" | "close", "sales_id": "...", "note": "..." }` |

## 6. Master Data

| Method | Path | Akses | Fungsi |
|--------|------|-------|--------|
| GET/POST | `/users` | admin | Daftar / tambah user (admin, sales, supervisor) |
| PATCH | `/users/{id}` | admin | Ubah user, aktif/nonaktif |
| GET/POST | `/areas` | admin | Daftar / tambah area |
| PUT | `/users/{id}/areas` | admin | Atur area yang dilayani sales |
| GET/POST | `/vehicle-units` | admin | Daftar / tambah unit kendaraan |
| PATCH | `/vehicle-units/{id}` | admin | Ubah unit |

## 7. Statistik

| Method | Path | Akses | Fungsi |
|--------|------|-------|--------|
| GET | `/stats/overview` | admin, supervisor | Jumlah lead per tag/status/sales, waktu respons rata-rata |

## 8. Webhook WhatsApp (produksi)

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/webhooks/whatsapp` | Verifikasi webhook Meta (`hub.mode`, `hub.verify_token`, `hub.challenge`) |
| POST | `/webhooks/whatsapp` | Terima pesan & status pesan dari Meta. Wajib validasi header `X-Hub-Signature-256` |

Aturan: balas `200` secepat mungkin; pemrosesan dilakukan di worker.
Payload diubah oleh `WhatsAppCloudAdapter.parse_webhook()` menjadi `InboundMessage`
lalu diteruskan ke `InboundMessageService` — **handler yang sama dengan simulator**.

## 9. Simulator (hanya Development Mode)

Hanya terdaftar bila `SIMULATOR_ENABLED=true`. Di production → `404`.

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/simulator/customers` | Daftar customer dummy |
| POST | `/simulator/customers` | Buat customer dummy `{ "profile_name": "Customer Dummy 01", "phone_number": "+6280000000001" }` (nomor otomatis bila kosong) |
| DELETE | `/simulator/customers/{id}` | Hapus customer dummy beserta datanya |
| POST | `/simulator/customers/{id}/messages` | Kirim pesan **sebagai customer** `{ "text": "Halo, mau tanya Xpander" }` |
| POST | `/simulator/customers/{id}/ad-click` | Simulasi customer datang dari iklan Click-to-WhatsApp |
| POST | `/simulator/reset` | Hapus semua data simulasi (`is_simulated = true`) |

Contoh alur uji:
```
POST /simulator/customers                       → customer dummy dibuat
POST /simulator/customers/{id}/messages "Halo"  → AI membalas menanyakan nama
POST ... "Saya Budi"                            → AI menanyakan domisili
POST ... "Bekasi"                               → AI menanyakan unit
POST ... "Mau tanya harga Pajero, bisa kredit?" → lead lengkap, tag Warm, di-routing ke sales
GET  /conversations/{id}/messages               → lihat seluruh riwayat
```

## 10. Real-time

| Path | Fungsi |
|------|--------|
| `WS /ws` | Kirim event ke frontend: `message.created`, `message.status_updated`, `lead.updated`, `admin_queue.updated` |

Format event:
```json
{ "type": "message.created", "data": { "conversation_id": "...", "message": { } } }
```
