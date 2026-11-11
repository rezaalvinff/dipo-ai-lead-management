# Rancangan Database — DIPO AI Lead Management

Database: **PostgreSQL 16**. Model: **SQLAlchemy 2.x** (`backend/app/models/`).
Perubahan skema: **Alembic** (`backend/alembic/versions/`).

> **Status:** sudah diimplementasikan di Phase 1 (migrasi `0001_initial_schema`).
> Ada 15 tabel. Kolom yang baru dipakai di phase berikutnya sudah disiapkan.

## Konvensi

- Primary key: `id` bertipe `UUID`.
- Setiap tabel punya `created_at` dan `updated_at` (`timestamptz`, UTC). Ditampilkan sebagai WIB di API/frontend.
- Nomor telepon dalam format **E.164** (`+628123...`).
- Nilai pilihan (enum) disimpan sebagai `varchar`. Daftar nilainya ada di `app/models/enums.py`.
- Nama constraint dibuat konsisten (`pk_`, `fk_`, `uq_`, `ix_`) agar migrasi mudah diprediksi.
- Data customer asli **tidak pernah** dimasukkan ke seed/test. Nomor simulasi wajib berawalan `+62800`.

## Diagram Relasi

```mermaid
erDiagram
    roles ||--o{ users : "punya"
    users ||--o| agent_profiles : "profil sales"
    agent_profiles ||--o{ territory_mappings : "melayani"
    territories ||--o{ territory_mappings : "dilayani"
    contacts ||--o{ leads : "punya"
    contacts ||--o{ conversations : "punya"
    conversations ||--o{ messages : "berisi"
    leads |o--o{ conversations : "terkait"
    leads ||--o{ assignments : "riwayat assign"
    agent_profiles ||--o{ assignments : "menerima"
    leads }o--o| territories : "domisili"
    leads }o--o| campaigns : "sumber iklan"
    leads ||--o{ conversion_events : "memicu"
    users ||--o{ audit_logs : "pelaku"
```

## Tabel

### 1. `roles` — peran pengguna (RBAC)
Diisi otomatis oleh migrasi: `admin`, `supervisor`, `sales`.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| name | varchar(30) unique | nama peran |
| description | text | penjelasan hak akses |

| Peran | Hak akses (Phase 1) |
|-------|---------------------|
| admin | semua, termasuk membuat user dan reset simulator |
| supervisor | melihat semua percakapan, memakai simulator |
| sales | hanya percakapan yang ditugaskan kepadanya |

### 2. `users` — pengguna dashboard
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| email | varchar(255) unique | untuk login (disimpan huruf kecil) |
| full_name | varchar(120) | |
| password_hash | varchar(255) | hash **bcrypt**, bukan password asli |
| role_id | uuid FK → roles | |
| is_active | bool | user nonaktif tidak bisa login |
| last_login_at | timestamptz | |

### 3. `agent_profiles` — data khusus sales
Dibuat otomatis ketika user ber-role `sales` dibuat.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| user_id | uuid FK → users, unique | |
| display_name | varchar(120) | nama yang tampil ke customer |
| phone_number | varchar(20) | |
| is_available | bool | sedang bisa menerima lead |
| max_active_leads | int | batas beban kerja |
| last_assigned_at | timestamptz | untuk round-robin |

### 4. `territories` — wilayah/domisili
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| name | varchar(100) unique | mis. "Bekasi" |
| aliases | jsonb | ejaan lain: `["bks", "bekasi kota"]` |
| is_active | bool | |

### 5. `territory_mappings` — sales melayani wilayah mana
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| territory_id | uuid FK → territories | |
| agent_profile_id | uuid FK → agent_profiles | |
| priority | int | semakin kecil semakin diutamakan |

Unik per pasangan (territory, agent).

### 6. `contacts` — customer WhatsApp
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| phone_number | varchar(20) unique | E.164 |
| wa_id | varchar(32) | ID WhatsApp dari Meta |
| display_name | varchar(120) | nama profil / nama dummy |
| is_simulated | bool, index | **true** = data uji (semua kontak di development) |
| opted_out | bool | customer minta berhenti dihubungi; pesan keluar diblokir |

### 7. `campaigns` — campaign tracking
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| name | varchar(150) | |
| platform | varchar(30) | `meta`, `google`, `offline` |
| external_campaign_id / external_adset_id / external_ad_id | varchar(64) | ID dari platform iklan |
| utm | jsonb | parameter UTM |
| is_active | bool | |

### 8. `leads` — prospek penjualan
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| contact_id | uuid FK → contacts | |
| campaign_id | uuid FK → campaigns | asal campaign (jika diketahui) |
| full_name | varchar(120) | dikumpulkan AI (phase berikutnya) |
| domicile_raw | varchar(150) | jawaban domisili apa adanya |
| territory_id | uuid FK → territories | hasil pencocokan domisili |
| vehicle_interest | varchar(150) | unit yang diminati |
| temperature | varchar(10) | `cold` · `warm` (default `cold`) |
| status | varchar(20) | `new` · `qualifying` · `qualified` · `assigned` · `contacted` · `won` · `lost` |
| source | varchar(20) | `whatsapp` · `simulator` · `ctwa_ad` (klik iklan WhatsApp) |
| ad_referral | jsonb | data `referral` iklan dari webhook Meta |
| assigned_agent_id | uuid FK → agent_profiles | sales saat ini |
| qualified_at | timestamptz | |
| is_simulated | bool | |

Satu kontak punya satu lead **aktif** (status selain `won`/`lost`).

### 9. `assignments` — riwayat penugasan lead
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| lead_id | uuid FK → leads | |
| agent_profile_id | uuid FK → agent_profiles | |
| assigned_by_type | varchar(10) | `system` · `user` |
| assigned_by_user_id | uuid FK → users | |
| reason | varchar(255) | mis. "territory match: Bekasi" |
| ended_at | timestamptz | saat dipindah ke sales lain |

### 10. `conversations` — satu utas chat
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| contact_id | uuid FK → contacts | |
| lead_id | uuid FK → leads | |
| provider | varchar(20) | `simulated` · `whatsapp_cloud` |
| status | varchar(10) | `open` · `closed` |
| handler | varchar(20) | `ai` · `admin_queue` · `sales` — AI hanya membalas bila `ai` |
| assigned_user_id | uuid FK → users | sales/admin pemegang percakapan |
| last_message_at | timestamptz | |
| last_inbound_at | timestamptz | untuk aturan jendela 24 jam WhatsApp |
| unread_count | int | |
| closed_at | timestamptz | |

Satu kontak hanya punya satu percakapan `open`. "Percakapan baru" menutup yang lama.

### 11. `messages` — setiap pesan masuk/keluar
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| conversation_id | uuid FK → conversations | |
| direction | varchar(10) | `inbound` · `outbound` |
| sender_type | varchar(10) | `contact` · `ai` · `sales` · `admin` · `system` |
| sender_user_id | uuid FK → users | bila dikirim manusia |
| provider | varchar(20) | adapter yang dipakai |
| message_type | varchar(20) | `text`, `image`, `interactive`, ... |
| content | text | isi pesan |
| provider_message_id | varchar(128) **unique** | `wamid...` dari Meta atau `sim-...` dari simulator — **pelindung duplikat** |
| status | varchar(15) | masuk: `received`; keluar: `queued` → `sent` → `delivered` → `read`, atau `failed` |
| error_detail | text | alasan gagal |
| raw_payload | jsonb | payload asli pesan masuk |
| sent_at / delivered_at / read_at | timestamptz | waktu setiap status |

Status pesan keluar **tidak pernah mundur** (status `delivered` yang datang terlambat tidak menimpa `read`).

### 12. `knowledge_base_articles` — basis pengetahuan untuk AI
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| title | varchar(200) | |
| category | varchar(50) | `vehicle` · `faq` · `promo` · `policy` |
| content | text | informasi resmi yang boleh dipakai AI |
| tags | jsonb | |
| is_active | bool | |

### 13. `conversion_events` — event konversi iklan
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| lead_id | uuid FK → leads | |
| event_name | varchar(40) | mis. `Lead`, `QualifiedLead` |
| provider | varchar(20) | `noop` · `meta_capi` |
| status | varchar(15) | `pending` · `sent` · `skipped_dev` · `failed` |
| payload | jsonb | data pribadi di-*hash* sesuai ketentuan Meta |
| sent_at | timestamptz | |
| error | text | |

Di development statusnya selalu `skipped_dev` (logika pengirimannya dibangun di phase berikutnya).

### 14. `audit_logs` — jejak audit
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| actor_type | varchar(10) | `user` · `system` · `ai` · `contact` |
| actor_user_id | uuid FK → users | |
| action | varchar(60) | mis. `auth.login`, `user.created`, `lead.created`, `simulator.reset` |
| entity_type | varchar(40) | |
| entity_id | varchar(64) | sengaja tanpa FK agar riwayat tetap ada walau data dihapus |
| data | jsonb | detail tambahan |

### 15. `webhook_events` — catatan mentah webhook
| Kolom | Tipe | Keterangan |
|-------|------|------------|
| source | varchar(20) | `whatsapp_cloud` |
| event_key | varchar(128) unique | SHA-256 dari body webhook — **pelindung duplikat** |
| payload | jsonb | |
| processed_at | timestamptz | |
| error | text | |

## Penghapusan Data Simulasi

Foreign key memakai `ON DELETE CASCADE`. Menghapus contact dummy otomatis menghapus
lead, percakapan, pesan, assignment, dan conversion event miliknya. `audit_logs` tetap disimpan.

## Rencana Tabel Berikutnya

| Tabel | Untuk | Phase |
|-------|-------|-------|
| `admin_queue_items` | antrian kasus untuk admin | Admin Queue |
| `ai_interactions` | log panggilan AI (biaya, kualitas) | AI & kualifikasi lead |
| `vehicle_units` | katalog unit terstruktur (saat ini cukup knowledge base) | bila dibutuhkan |

## Catatan Privasi

- Kolom berisi data pribadi: `contacts.phone_number`, `display_name`, `leads.full_name`,
  `messages.content`, `messages.raw_payload`. Akses dibatasi sesuai role.
- Nomor telepon di log aplikasi disamarkan (`+6280******123`).
- Kebijakan retensi (berapa lama data disimpan) diputuskan sebelum go-live.
