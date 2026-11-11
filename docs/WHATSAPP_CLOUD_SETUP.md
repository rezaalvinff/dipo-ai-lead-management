# Aktivasi WhatsApp Cloud API — Checklist Phase 7

## Status saat ini

Fondasi webhook dan adapter Cloud API tersedia. Development tetap menggunakan WHATSAPP_PROVIDER=simulated dan WHATSAPP_CLOUD_SEND_ENABLED=false. Tidak ada nomor bisnis, token, Phone Number ID, App Secret, atau Verify Token asli yang disimpan di repository. Pengiriman nyata belum diaktifkan.

## Kemampuan yang sudah tersedia

- Webhook GET/POST /api/v1/webhooks/whatsapp.
- Verifikasi hub.verify_token dan signature X-Hub-Signature-256.
- Parsing pesan masuk teks, referral iklan CTWA, dan status sent/delivered/read/failed.
- Anti-duplikasi berdasarkan payload webhook dan wamid.
- Balasan teks melalui WhatsApp Cloud adapter.
- Kill switch: pengiriman ditolak kecuali APP_ENV=production dan WHATSAPP_CLOUD_SEND_ENABLED=true.
- Status readiness tanpa mengekspos secret: GET /api/v1/integrations/whatsapp/status.
- Aturan 24 jam: free-form text ditolak setelah 24 jam dari pesan customer terakhir; integrasi template message harus digunakan untuk menghubungi kembali.

## Belum tersedia / belum bisa diuji

- Template message API (termasuk parameter dan komponen template).
- Upload/kirim media.
- End-to-end test dengan nomor test Meta atau nomor bisnis DIPO.
- Verifikasi webhook melalui URL publik HTTPS.
- Validasi template yang sudah disetujui dan pengujian jendela layanan pada akun Meta.

## Checklist ketika nomor dan akses Meta sudah tersedia

1. Buat/akses Meta App dan tambahkan produk WhatsApp.
2. Tambahkan nomor test atau nomor bisnis yang memang disediakan untuk integrasi.
3. Simpan token akses, Phone Number ID, App Secret, dan Verify Token hanya di secret manager atau .env pada server; jangan pernah commit.
4. Deploy endpoint backend pada URL HTTPS publik.
5. Atur callback URL ke https://DOMAIN/api/v1/webhooks/whatsapp, subscribe ke field messages, dan lakukan verification handshake.
6. Uji pesan masuk dan status delivery dengan nomor yang diizinkan.
7. Pastikan balasan dalam jendela 24 jam berjalan, lalu uji bahwa free-form text ditolak di luar jendela tersebut.
8. Implementasikan dan uji approved template messages sebelum membuka kembali percakapan di luar jendela 24 jam.
9. Implementasikan media upload/send dan uji media yang dibutuhkan.
10. Lakukan aktivasi bertahap hanya setelah review keamanan, test, dan persetujuan pemilik project.

## Environment variables

```dotenv
APP_ENV=production
SIMULATOR_ENABLED=false
WHATSAPP_PROVIDER=whatsapp_cloud
WHATSAPP_ACCESS_TOKEN=<secret>
WHATSAPP_PHONE_NUMBER_ID=<phone-number-id>
WHATSAPP_APP_SECRET=<app-secret>
WHATSAPP_WEBHOOK_VERIFY_TOKEN=<random-verify-token>
WHATSAPP_CLOUD_SEND_ENABLED=false
```

Biarkan WHATSAPP_CLOUD_SEND_ENABLED=false selama konfigurasi dan uji webhook. Jangan mengubahnya menjadi true sebelum nomor, webhook, template, jendela 24 jam, dan proses rollback benar-benar diuji. Untuk tahap pertama, lakukan uji dengan nomor test Meta dan penerima yang diizinkan.

API version dikonfigurasi melalui WHATSAPP_API_VERSION; cek versi yang didukung Meta saat aktivasi dan ubah di environment server, bukan dengan menaruh credential di Git.