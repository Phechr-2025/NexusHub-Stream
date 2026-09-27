# NexusHub-Stream (MySeriesVideo / menuwed)

เว็บดูวิดีโอ/ซีรีส์ด้วย **Flask** + ตัวช่วยจัดการบนเครื่อง/ VPS ชื่อ `menuwed`.

- สตาร์ทโปรดักชันด้วย `sh start.sh` (พยายามใช้ `gunicorn` ก่อน และ fallback ไป `python app.py`)
- มี `nixpacks.toml` ขอ `ffmpeg` (เหมาะกับ Railway)

---

## Deploy บน Railway (สั้น ๆ)

1) Railway → **New Project** → **Deploy from GitHub repo** → เลือก repo นี้  
2) ตั้ง **Start Command**:
```bash
sh start.sh
```
3) ตั้ง **Variables** ขั้นต่ำ:
- `SECRET_KEY` = สุ่มยาว ๆ
- `ADMIN_PASSWORD` = เปลี่ยนจากค่า default
- (แนะนำ) `ADMIN_USERNAME`

4) ไปที่ **Networking / Domains** → สร้าง Public Domain  
5) ทดสอบ `GET /healthz`

> ถ้าต้องการให้ข้อมูลไม่หาย ให้เพิ่ม **Volume** และตั้ง `DATA_DIR` (ดูหัวข้อ Persistent Storage)

---

## รันบน VPS / เครื่องตัวเอง (Manual)

### Requirements
- Python 3
- ffmpeg (รวม ffprobe) — ใช้สำหรับแปลงวิดีโอให้ iOS เล่นได้

### Run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

sh start.sh
```

---

## ให้ iOS ดูได้ (ทำงานอัตโนมัติ)

ระบบจะพยายามทำให้ไฟล์วิดีโอที่ “นำเข้าแบบเก็บบนเซิร์ฟเวอร์” เล่นบน iOS Safari ได้ โดยทำตอนนำเข้า (ไม่ทำทุกครั้งตอนกดดู):
- **Upload** → แปลงเป็น MP4 (H.264/AAC) + `faststart` ในพื้นหลัง
- **Google Drive** → ดาวน์โหลดเป็นไฟล์ชั่วคราว แล้วแปลงเป็น MP4 (H.264/AAC) + `faststart`
- **YouTube download** → หลังโหลดเสร็จ จะทำให้เป็น MP4 (H.264/AAC) + `faststart`

หมายเหตุ:
- ถ้าเป็น **Direct URL** (ลิงก์ไปไฟล์นอกเซิร์ฟเวอร์) ระบบ proxy header ให้แล้ว แต่ “ถ้าไฟล์ต้นทางเป็น codec ที่ iOS ไม่รองรับ” จะยังเล่นไม่ได้ (เพราะเราไม่ได้ดาวน์โหลดมาแปลง)

---

## ใช้งาน `menuwed` บน VPS (เมนู/คำสั่ง)

> ใช้ได้เมื่อคุณมีคำสั่ง `menuwed` แล้ว (เช่น ติดตั้งด้วยสคริปต์/วิธีของคุณ) หรือรันตรงด้วย `python3 menuwed.py` ในโฟลเดอร์โปรเจกต์

### เมนูหลัก
รัน:
```bash
menuwed
```
เมนูหลัก:
- 1) ถอนการติดตั้ง
- 2) อัปเดตระบบ
- 3) อัปเดตแบบเจาะจง
- 4) อัปเดตไลบารี่
- 5) จัดการเว็บ
- 6) จัดการ config

### เมนู “จัดการเว็บ”
- ดู URL และอื่นๆ
- ผูกโดเมน (พยายามตั้ง nginx reverse proxy + Let's Encrypt แบบ best-effort)
- ดูสถานะเว็บ / รีสตาร์ท / หยุด / เริ่ม

### เมนู “จัดการ config”
- ดูค่าปัจจุบันทั้งหมด
- สร้าง/ซ่อม config
- แก้ค่าแบบถามทีละตัว
- เปิดไฟล์ config ใน editor

### คำสั่งแบบไม่ต้องเข้าหน้าเมนู
```bash
menuwed web-start
menuwed web-stop
menuwed web-status
menuwed web-info
menuwed web-restart
```

---

## Admin (ค่าเริ่มต้น)

ค่าเริ่มต้นในระบบ:
- `ADMIN_USERNAME=admin`
- `ADMIN_PASSWORD=1234`

**แนะนำให้เปลี่ยนทันที** โดยตั้ง Environment Variables บน Railway/VPS.

---

## Environment Variables

### ต้องตั้ง (แนะนำบนโปรดักชัน)
| ตัวแปร | ใช้ทำอะไร |
|---|---|
| `SECRET_KEY` | คีย์ลับสำหรับ session/cookie |
| `ADMIN_USERNAME` | ชื่อแอดมิน (default: `admin`) |
| `ADMIN_PASSWORD` | รหัสแอดมิน (default: `1234`) |

### Persistent Storage (กันข้อมูลหาย)
แอปใช้ SQLite + เก็บไฟล์ใน `DATA_DIR`.

- บน Railway: เพิ่ม **Volume** แล้วตั้ง `DATA_DIR=/data` (หรือ path ที่คุณ mount)
- บน VPS: ตั้ง `DATA_DIR` ไปยังโฟลเดอร์ถาวรที่คุณต้องการ

### Gunicorn tuning (ไม่จำเป็น)
| ตัวแปร | default | ใช้ทำอะไร |
|---|---:|---|
| `WEB_CONCURRENCY` | 2 | จำนวน workers |
| `GUNICORN_THREADS` | 2 | จำนวน threads ต่อ worker |
| `GUNICORN_TIMEOUT` | 120 | timeout (วินาที) |

> ถ้าใช้ SQLite แล้วเจอ `database is locked` ให้ลอง `WEB_CONCURRENCY=1`

### Cloudflare Turnstile (ไม่จำเป็น)
| ตัวแปร | ใช้ทำอะไร |
|---|---|
| `TURNSTILE_SITE_KEY` | แสดง widget |
| `TURNSTILE_SECRET_KEY` | verify หลังบ้าน |
| `TURNSTILE_ALLOWED_HOSTNAMES` | จำกัด hostname (คั่นด้วย ,) |
| `TURNSTILE_REQUIRED` | ถ้า `true` แต่ไม่มี key ครบ แอปจะไม่ยอมเริ่ม |

### OTP / Email (Brevo) — ปิดเป็นค่าเริ่มต้น
ระบบ OTP ถูกตั้งค่าเริ่มต้นให้ **ปิด** เพื่อให้ deploy ใหม่แล้วใช้งานได้ทันที แม้ยังไม่ได้ตั้งค่าอีเมล.

ถ้าต้องการเปิด OTP:
1) ตั้ง Brevo variables:
   - `BREVO_API_KEY`
   - `BREVO_SENDER_EMAIL`
   - `BREVO_SENDER_NAME`
2) ล็อกอินแอดมิน → ไปที่ `/admin/settings` → เปิดสวิตช์ที่ต้องการ:
   - บังคับผู้สมัครต้องใส่อีเมล์และยืนยัน OTP (`force_email`)
   - ฉันลืมรหัสผ่าน (`account_recovery_enabled`)
   - เปลี่ยนอีเมล์ (`email_change_enabled`)

---

## Health check

- `GET /healthz`

---

## Troubleshooting (สั้น ๆ)

- เปิดเว็บแล้ว 502/timeout → เช็ค logs ว่าฟังที่ `0.0.0.0:$PORT` และสตาร์ทด้วย `sh start.sh`
- Turnstile เปิดแบบ required แล้วบูตไม่ได้ → ตรวจ `TURNSTILE_*`
- ข้อมูลหายหลัง redeploy → ตั้ง `DATA_DIR` + ใช้ Volume (Railway)

---

## หมายเหตุเรื่องสคริปต์ติดตั้ง (install.sh / install.ps1)

สคริปต์ติดตั้งอาจอ้างอิง `github_repo` ใน `menuwed_config.json`.
ถ้าต้องการให้สคริปต์ติดตั้งชี้มาที่ repo นี้เสมอ ให้ตั้ง `github_repo` เป็น `Phechr-2025/NexusHub-Stream`.
