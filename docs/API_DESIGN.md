# Rancangan API — DIPO AI Lead Management

Backend: **FastAPI**. Prefix semua endpoint: `/api/v1`.
Dokumentasi interaktif (Swagger) tersedia di **http://localhost:8000/docs** (hanya di development).

Legenda: ✅ sudah dibuat · ⏳ direncanakan

## Konvensi

- Format data: JSON. Waktu: ISO 8601 UTC. Pesan juga punya `created_at_wib` (mis. `11/11/2026 12:55:23 WIB`).
- Autentikasi: JWT, dikirim sebagai header `Authorization: Bearer <token>` **atau** cookie httpOnly `access_token`.
- Format error selalu sama:
  ```json
  { "error": { "code": "INVALID_CREDENTIALS", "message": "Email atau password salah" } }
  ```
- Role: `admin`, `supervisor`, `sales`.

## 1. Sistem

| | Method | Path | Akses | Fungsi |
|-|--------|------|-------|--------|
| ✅ | GET | `/health` | publik | Status aplikasi, database, Redis, mode, provider aktif. HTTP 503 bila ada yang mati |

```json
{
  "status": "ok",
  "app_env": "development",
  "simulator_enabled": true,
  "providers": { "whatsapp": "simulated", "ai": "mock", "conversion": "noop", "job_queue": "arq" },
  "checks": { "database": "ok", "redis": "ok" }
}
```

## 2. Autentikasi & User

| | Method | Path | Akses | Fungsi |
|-|--------|------|-------|--------|
| ✅ | POST | `/auth/login` | publik | `{email, password}` → token + cookie |
| ✅ | POST | `/auth/logout` | publik | Hapus cookie |
| ✅ | GET | `/auth/me` | login | Data user yang sedang login |
| ✅ | GET | `/users` | admin, supervisor | Daftar user |
| ✅ | POST | `/users` | admin | Buat user `{email, full_name, password, role, agent_phone?}`. Role `sales` otomatis dibuatkan agent profile |
| ⏳ | PATCH | `/users/{id}` | admin | Ubah / nonaktifkan user |

## 3. Percakapan & Pesan

| | Method | Path | Akses | Fungsi |
|-|--------|------|-------|--------|
| ✅ | GET | `/conversations` | login* | Filter: `contact_id`, `status`, `handler`, `limit` |
| ✅ | GET | `/conversations/{id}` | login* | Detail percakapan |
| ✅ | GET | `/conversations/{id}/messages` | login* | Riwayat pesan, urut dari yang terlama |
| ✅ | POST | `/conversations/{id}/messages` | login* | Balasan manual `{text}` dari sales/admin, lewat outgoing message service yang sama |
| ✅ | GET | `/conversations/{id}/state` | login* | Conversation state: data terkumpul, status tiap data, pertanyaan terakhir, alasan handover, riwayat koreksi |
| ✅ | POST | `/conversations/{id}/handler` | admin, supervisor | Ambil alih / kembalikan: `{"handler": "ai" \| "admin_queue" \| "admin" \| "sales"}` |

Membalas manual (`POST /conversations/{id}/messages`) otomatis **mengambil alih** percakapan:
handler menjadi `sales`/`admin` dan AI berhenti membalas.

\* Sales hanya bisa melihat percakapan yang `assigned_user_id`-nya adalah dirinya. Selain itu hasilnya 404.

## 3a. Knowledge Base (Phase 2)

Akses: admin (tulis), supervisor (baca). Data baru berstatus `draft`; hanya `approved` yang dipakai AI.
Mengubah isi data `approved` mengembalikannya ke `draft` kecuali `status: "approved"` dikirim bersamaan.

| | Method | Path | Fungsi |
|-|--------|------|--------|
| ✅ | GET/POST | `/knowledge/vehicle-models` | Daftar / tambah model (`name`, `aliases`, `category`, `description`, `status`) |
| ✅ | PATCH/DELETE | `/knowledge/vehicle-models/{id}` | Ubah / hapus model (varian ikut terhapus) |
| ✅ | GET/POST | `/knowledge/vehicle-models/{id}/variants` | Daftar / tambah varian (`name`, `transmission`, `fuel_type`, `specs`, `price_otr`, `price_note`) |
| ✅ | PATCH/DELETE | `/knowledge/variants/{id}` | Ubah / hapus varian |
| ✅ | GET/POST | `/knowledge/articles` | Daftar (filter `category`, `status`, `vehicle_model_id`) / tambah artikel promo, DP, angsuran, FAQ, dealer, kebijakan |
| ✅ | PATCH/DELETE | `/knowledge/articles/{id}` | Ubah / hapus artikel |
| ✅ | GET | `/knowledge/ai-context?vehicle=` | Pratinjau **persis** informasi yang dilihat AI |

## 3b. Pengaturan Admin (Phase 2)

| | Method | Path | Akses | Fungsi |
|-|--------|------|-------|--------|
| ✅ | GET | `/settings` | admin, supervisor | Semua pengaturan + nilai default |
| ✅ | PUT | `/settings/{key}` | admin | Ubah `{ "value": ... }`. Placeholder pesan: `{nama}`, `{domisili}`, `{unit}` |
| ✅ | DELETE | `/settings/{key}` | admin | Kembali ke default |

Daftar key: lihat `docs/AI_AGENT.md` bagian 5.

## 4. Simulator — Simulated WhatsApp (hanya development)

Endpoint ini **tidak ada sama sekali** bila `SIMULATOR_ENABLED=false` atau `APP_ENV=production` (hasilnya 404).
Akses: admin & supervisor (reset: admin saja).

| | Method | Path | Fungsi |
|-|--------|------|--------|
| ✅ | GET | `/simulator/contacts` | Daftar customer dummy |
| ✅ | POST | `/simulator/contacts` | Buat customer dummy `{display_name, phone_number?}`. Nomor wajib berawalan `+62800`. Kosongkan untuk dibuatkan otomatis |
| ✅ | DELETE | `/simulator/contacts/{id}` | Hapus satu customer dummy beserta seluruh datanya |
| ✅ | POST | `/simulator/contacts/{id}/messages` | Kirim pesan **sebagai customer** `{text}` → melewati `InboundMessageService` (sama dengan webhook) → AI membalas lewat worker |
| ✅ | POST | `/simulator/contacts/{id}/conversations` | Mulai percakapan baru (yang lama ditutup) |
| ✅ | GET | `/simulator/contacts/{id}/chat` | Seluruh riwayat (semua percakapan + pesan, dengan waktu dan status) |
| ✅ | POST | `/simulator/messages/{id}/status` | Simulasikan status pesan keluar `{status: delivered/read/failed}` lewat status handler yang sama dengan webhook |
| ✅ | POST | `/simulator/reset` | Hapus **semua** data simulasi (`is_simulated = true`) |
| ⏳ | POST | `/simulator/contacts/{id}/ad-click` | Simulasi customer datang dari iklan Click-to-WhatsApp |

Contoh respons `POST /simulator/contacts/{id}/messages`:
```json
{
  "conversation_id": "…",
  "lead_id": "…",
  "duplicate": false,
  "ai_reply_queued": true,
  "message": { "direction": "inbound", "status": "received", "content": "Halo", "created_at_wib": "11/11/2026 12:55:23 WIB" }
}
```
Balasan AI muncul beberapa saat kemudian. Ambil lewat `GET /simulator/contacts/{id}/chat`
(respons ini juga berisi `state`, yaitu conversation state percakapan terakhir).

## 5. Webhook WhatsApp Cloud API (fondasi, belum aktif dengan nomor asli)

| | Method | Path | Fungsi |
|-|--------|------|--------|
| ✅ | GET | `/webhooks/whatsapp` | Verifikasi Meta: `hub.mode=subscribe`, `hub.verify_token` harus sama dengan `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, lalu membalas `hub.challenge` |
| ✅ | POST | `/webhooks/whatsapp` | Terima pesan masuk + status pesan |

Aturan `POST`:
1. **Signature validation:** header `X-Hub-Signature-256` dicek dengan HMAC-SHA256 memakai `WHATSAPP_APP_SECRET`. Kalau salah atau secret kosong, hasilnya 403.
2. **Duplicate protection lapis 1:** body yang persis sama hanya diproses sekali (`webhook_events.event_key`). Kiriman ulang dijawab `{"status":"duplicate"}`.
3. **Duplicate protection lapis 2:** `wamid` pesan bersifat unik di tabel `messages`.
4. Pesan masuk diteruskan ke **`InboundMessageService`**, handler yang sama dengan simulator.
5. Status (`sent/delivered/read/failed`) diteruskan ke **`MessageService.apply_status_update`**, juga sama dengan simulator.
6. Payload dengan `object` selain `whatsapp_business_account` diabaikan.

Respons: `{"status":"ok","messages_stored":1,"messages_duplicate":0,"statuses_applied":0}`

## 6. Direncanakan (phase berikutnya)

| Method | Path | Fungsi |
|--------|------|--------|
| GET/PATCH | `/leads`, `/leads/{id}` | Daftar & ubah lead |
| POST | `/leads/{id}/assign` | Assign manual ke sales |
| GET/POST | `/admin-queue`, `/admin-queue/{id}/claim`, `/admin-queue/{id}/resolve` | Admin Queue |
| GET/POST | `/territories`, `/territory-mappings` | Master wilayah & pemetaan sales |
| GET/POST | `/campaigns` | Kelola campaign |
| GET | `/stats/overview` | Statistik |
| WS | `/ws` | Update real-time ke frontend |
