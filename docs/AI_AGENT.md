# AI Agent & Knowledge Base

Dokumen ini menjelaskan cara kerja AI Agent (Phase 2) dengan bahasa sederhana.

## 1. Prinsip Utama: AI Mengusulkan, Backend Memutuskan

```
Pesan customer
     │
     ▼
AI Provider (Mock / Claude / OpenAI)
  "Saya kira namanya Andi, domisili Medan, dan ini usulan balasan saya"
     │
     ▼
Backend (QualificationService) ── memeriksa & memutuskan:
  ✔ Apakah "Andi" nama yang wajar?          ✔ Apakah "Xpander" ada di katalog?
  ✔ Data apa yang masih kurang?             ✔ Sudah ditanya berapa kali?
  ✔ Apakah balasan menyebut harga/promo yang tidak ada di knowledge base?
  ✔ Sudah lengkap? → handover ke tim sales (bukan AI yang memutuskan)
     │
     ▼
Balasan dikirim lewat adapter WhatsApp (Simulated / Cloud API)
```

AI **tidak pernah** mengubah status lead, memutuskan kelengkapan data, atau memutuskan handover.
Semua itu aturan backend yang bisa diuji.

## 2. Data yang Dikumpulkan

| Urutan | Data | Validasi backend |
|--------|------|------------------|
| 1 | Nama | Huruf, maks. 4 kata, bukan kata umum ("ok", "iya", "test"), sapaan "Pak/Bu" dibuang |
| 2 | Domisili (kota/kabupaten) | Huruf, bukan kata umum ("rumah", "sini"); singkatan dikenali ("bks" → Bekasi, "jaksel" → Jakarta Selatan) |
| 3 | Unit Mitsubishi | Wajib cocok dengan **katalog model yang disetujui** (typo dikenali: "expander" → Xpander, "pajero sprot" → Pajero Sport) |

Nomor WhatsApp **tidak ditanyakan**: diambil otomatis dari pengirim (Cloud API) atau nomor dummy (simulator).

## 3. Aturan Percakapan (dan siapa yang menjamin)

| Aturan | Dijamin oleh |
|--------|--------------|
| Bahasa Indonesia natural, singkat | Prompt AI |
| Bertanya satu per satu | Backend memilih **satu** data berikutnya; balasan AI yang menanyakan data lain diganti template |
| Paham bahasa informal & typo | AI + pencocokan alias/typo di backend |
| Tidak mengulang pertanyaan yang sudah dijawab | Backend menyimpan state per lead; data yang sudah ada tidak pernah ditanyakan lagi |
| Mengingat informasi | State disimpan di database (`qualification_states`), juga untuk percakapan baru |
| Menerima koreksi | Nilai terbaru menggantikan yang lama; tercatat di `history` sebagai `correction` |
| Tidak mengarang harga/promo | Knowledge base hanya berisi data **approved**; **guard** backend memblokir angka (Rp, juta, %, dll.) yang tidak ada di knowledge base |
| Tidak memaksa | Tiap data maksimal ditanya **2x** (bisa diatur 1–5). Setelah itu dilewati. Penolakan ("ga mau kasih nama") langsung dihormati |

## 4. Kapan AI Berhenti (Handover)

| Kondisi | Alasan (`handover_reason`) | Pesan ke customer |
|---------|----------------------------|-------------------|
| Nama + domisili + unit lengkap | `qualification_complete` | **Closing message** (bisa diedit admin) |
| Sebagian data ditolak/tidak dijawab, sisanya lengkap | `partial_data` | Closing message |
| Customer minta bicara dengan orang/sales | `human_requested` | Pesan handover manusia (bisa diedit) |
| Sales/admin membalas manual atau mengambil alih | `manual_takeover` | — |
| AI gagal 3x berturut-turut | `ai_unavailable` | Pesan "sistem sibuk" (bisa diedit) |
| Admin mematikan AI (`ai.enabled = false`) | `ai_disabled` | — |
| Customer yang datanya sudah lengkap chat lagi | `returning_customer` | Pesan customer kembali (bisa diedit) |

Setelah handover, percakapan masuk ke `admin_queue` (atau `sales`/`admin` bila diambil alih)
dan **AI tidak membalas lagi**. Admin/supervisor bisa mengembalikan ke AI
(`POST /conversations/{id}/handler` dengan `{"handler": "ai"}`). Data yang sudah terkumpul tetap disimpan.

Pengaman tambahan:
- Jika manusia mengambil alih **saat AI sedang berpikir**, balasan AI dibuang.
- Jika customer mengirim beberapa pesan cepat, AI hanya membalas **sekali** (pesan terbaru).

## 5. Pengaturan yang Bisa Diedit Admin (`/api/v1/settings`)

| Key | Isi default |
|-----|-------------|
| `qualification.closing_message` | "Baik, akan segera saya lanjutkan ke tim sales untuk diberikan informasi promo dan penawarannya. Mohon ditunggu, terima kasih." |
| `qualification.human_handover_message` | Pesan saat customer minta manusia |
| `qualification.returning_customer_message` | Pesan untuk customer yang kembali |
| `qualification.ai_unavailable_message` | Pesan saat AI bermasalah |
| `qualification.max_asks_per_field` | `2` |
| `ai.enabled` | `true` |

Placeholder yang boleh dipakai di pesan: `{nama}`, `{domisili}`, `{unit}`.
Contoh: `Terima kasih Pak/Bu {nama}, info {unit} segera dikirim tim sales kami.`

## 6. Knowledge Base

| Jenis informasi | Disimpan di |
|-----------------|-------------|
| Model kendaraan (+ alias/typo) | `vehicle_models` |
| Varian, spesifikasi, harga OTR | `vehicle_variants` |
| Promo, DP, angsuran, FAQ, info dealer, kebijakan, catatan spesifikasi | `knowledge_base_articles` (kategori `promo`, `dp`, `installment`, `faq`, `dealer`, `policy`, `spec`, `price`) |

**Alur persetujuan:**
- Data baru berstatus `draft` dan **tidak terlihat oleh AI**.
- Admin mengubah status menjadi `approved`, baru setelah itu AI boleh memakainya.
- Mengedit isi data yang sudah approved otomatis mengembalikannya ke `draft`, kecuali admin langsung meng-approve lagi di permintaan yang sama.
- Promo bisa diberi `valid_from` / `valid_until`. Promo yang kedaluwarsa otomatis tidak dipakai.
- `GET /api/v1/knowledge/ai-context` menampilkan **persis** informasi yang dilihat AI saat ini.

Hak akses: admin bisa tambah/edit/hapus/approve, supervisor hanya bisa melihat, sales tidak punya akses.

Seed development hanya mengisi **nama model** Mitsubishi (approved) dan beberapa placeholder artikel (draft).
Harga, promo, DP, dan angsuran harus diisi admin dari data resmi dealer.

## 7. AI Provider & Biaya

| `AI_PROVIDER` | Keterangan | Biaya |
|---------------|------------|-------|
| `mock` (default) | AI berbasis aturan, tanpa internet. Untuk development & test otomatis | Gratis |
| `anthropic` | Claude lewat **Anthropic API**. Default model `claude-opus-5-5` (ubah lewat `AI_MODEL`) | Per token, ditagih Anthropic |
| `openai` | OpenAI API. `AI_MODEL` wajib diisi | Per token, ditagih OpenAI |

> **Penting:** langganan **Claude Pro** (yang dipakai untuk coding) **bukan** API untuk aplikasi.
> Aplikasi memakai **API key terpisah** dari https://console.anthropic.com (akun & tagihan sendiri).
> Simpan key hanya di `.env` (`ANTHROPIC_API_KEY=...`), **jangan** di repository.

Untuk provider Claude, fitur *server-side fallback* aktif: jika Claude menolak sebuah permintaan,
API otomatis mencoba model cadangan. Pilihan model lebih murah (misalnya `claude-sonnet-5-5`
atau `claude-haiku-5-5`) bisa dipakai lewat `AI_MODEL`. Keputusan biaya vs. kualitas ada di
pemilik project dan sebaiknya diuji dengan skenario di bawah.

Setiap panggilan AI dicatat di tabel `ai_interactions`: usulan AI, keputusan backend, token, dan waktu respons.

## 8. Skenario Pengujian (Simulated WhatsApp)

File: `backend/tests/test_ai_scenarios.py`. Semuanya lewat endpoint simulator (jalur yang sama dengan produksi).

| # | Skenario |
|---|----------|
| s01 | Contoh dari brief ("Halo, saya mau tanya Xpander" → Andi → Medan → closing; unit tidak ditanya ulang) |
| s02 | Data diberikan satu per satu (setiap pertanyaan tepat 1x) |
| s03 | Semua data dalam satu pesan → langsung closing |
| s04 | Customer mengubah unit (Xpander → Pajero Sport, tercatat sebagai koreksi) |
| s05 | Customer mengoreksi domisili ("saya di Binjai bukan Medan") |
| s06 | Customer tidak menjawab → ditanya maks. 2x lalu dilewati |
| s07 | Customer menolak memberi nama → tidak dipaksa, handover `partial_data` |
| s08 | Customer bertanya promo yang belum tersedia → tidak mengarang (draft & promo kedaluwarsa tidak bocor) |
| s09 | Pertanyaan dijawab dari knowledge base yang approved |
| s10 | Harga hanya dari varian yang approved; nama tidak ditanya ulang |
| s11 | Bahasa informal & typo ("sy mw tny expander", "dr bks") |
| s12 | Typo nama model ("pajero sprot") |
| s13 | Customer minta bicara dengan sales → handover, AI diam |
| s14 | Admin mengambil alih → AI diam; dikembalikan ke AI → lanjut tanpa mengulang |
| s15 | Closing message diedit admin (dengan `{nama}`/`{unit}`) |
| s16 | Customer kembali di percakapan baru → tidak ditanya ulang |
| s17 | Unit di luar katalog (Avanza) ditolak, ditanya ulang dengan sopan |
| s18 | Domisili tidak valid ("rumah") ditanya ulang |
| s19 | AI mengarang harga → diblokir guard backend |
| s20 | AI bilang "sudah lengkap" padahal nama tidak valid → backend tidak handover |
| s21 | AI error → balasan template; 3x gagal → handover `ai_unavailable` |
| s22 | Manusia mengambil alih saat AI berpikir → balasan AI dibuang |
| s23 | AI dimatikan admin → semua chat ke Admin Queue |
| s24 | 3 pesan beruntun → hanya 1 balasan AI |

Assertion memeriksa **state yang divalidasi backend** (data, status, pertanyaan terakhir, alasan handover),
bukan kalimat persis AI. Karena itu skenario yang sama bisa dijalankan terhadap LLM sungguhan:

```bash
TEST_AI_PROVIDER=anthropic ANTHROPIC_API_KEY=... pytest -q tests/test_ai_scenarios.py
```

Perintah di atas **memakan biaya API** karena setiap pesan memanggil Claude. Skenario s19–s24 tetap memakai AI tiruan
karena memang menguji kondisi AI yang salah atau error.
