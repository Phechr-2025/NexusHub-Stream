# NexusHub-Stream (MySeriesVideo / menuwed)

เว็บดูวิดีโอ/ซีรีส์ด้วย **Flask** พร้อมตัวจัดการ CLI ชื่อ `menuwed` สำหรับติดตั้ง/อัปเดต/จัดการ config และการรันบนเครื่องหรือบนคลาวด์

> Repo นี้มี `start.sh` ที่รันได้ทั้งแบบ `gunicorn` และ fallback ไป `python app.py` และมี `nixpacks.toml` ที่ขอ `ffmpeg` สำหรับแพลตฟอร์มที่รองรับ Nixpacks (เช่น Railway)

---

## TL;DR (รันบน Railway ให้ขึ้นเร็วที่สุด)

1. Railway → **New Project** → **Deploy from GitHub repo** → เลือก repo นี้
2. ตั้ง **Start Command** เป็น:
   ```bash
   sh start.sh
   ```
3. ไปที่ **Variables** แล้วตั้งอย่างน้อย:
   - `SECRET_KEY` = สุ่มยาวๆ (สำคัญมาก)
   - `ADMIN_PASSWORD` = เปลี่ยนจากค่า default
   - (แนะนำ) `ADMIN_USERNAME`
   - (ถ้าจะใช้ OTP/กู้บัญชี/เปลี่ยนอีเมล์) ตั้งค่า Brevo แล้วค่อยไปเปิดสวิตช์ในหน้าแอดมิน `/admin/settings`
4. ไปที่ **Networking / Domains** → สร้าง Public Domain
5. เปิดเว็บแล้วทดสอบ:
   - `/healthz` ต้องตอบ `{ "status": "ok" ... }`

> ถ้าต้องการให้ฐานข้อมูล/ไฟล์ไม่หายเวลามี redeploy ให้เพิ่ม **Volume** แล้วตั้ง `DATA_DIR` (ดูหัวข้อ “Persistent Storage”)

---

## โครงสร้างโปรเจกต์ (ไฟล์สำคัญ)

- `app.py` — เว็บหลัก (Flask)
- `start.sh` — สคริปต์สตาร์ท (พยายามใช้ gunicorn ก่อน แล้ว fallback)
- `requirements.txt` — dependencies (Flask, gunicorn, yt-dlp ฯลฯ)
- `nixpacks.toml` — ขอ `ffmpeg`
- `templates/` และ `static/` — UI
- `menuwed.py` — CLI สำหรับติดตั้ง/อัปเดต/จัดการเว็บ
- `menuwed_config.json` — ค่า config/ค่าเริ่มต้น (เหมาะกับรันบนเครื่อง)

---

## รันในเครื่อง (Local)

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# วิธีแนะนำ (เหมือน production มากกว่า)
sh start.sh
```

เปิดเว็บที่ `http://127.0.0.1:5000`

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python app.py
```

---

## Deploy บน Railway

### 1) Deploy from GitHub

- Railway → New Project → Deploy from GitHub repo → เลือก repo นี้

### 2) Start Command

ถ้า Railway ไม่ detect ให้ตั้งเอง:

```bash
sh start.sh
```

### 3) Variables (Environment Variables)

#### ✅ ต้องตั้งจริงๆ (แนะนำให้ตั้งทุกครั้งบน production)

| ตัวแปร | จำเป็น | ตัวอย่าง | ใช้ทำอะไร |
|---|---:|---|---|
| `SECRET_KEY` | ต้องมี | `a-very-long-random-string` | ใช้เข้ารหัส session/cookie ของ Flask (ห้ามใช้ค่าเดิม/เดาง่าย) |
| `ADMIN_PASSWORD` | ต้องมี (เพื่อความปลอดภัย) | `your-strong-password` | รหัสแอดมิน (ค่า default คือ `1234` ไม่ควรใช้) |
| `ADMIN_USERNAME` | แนะนำ | `admin` | ยูสเซอร์แอดมิน (ค่า default คือ `admin`) |

> หมายเหตุ: ถ้าไม่ตั้ง `ADMIN_*` ระบบจะ fallback ไปค่า default ได้ ทำให้ไม่ปลอดภัยเมื่อเปิด public

#### 🗂️ Persistent Storage (แนะนำมาก)

ถ้าคุณมีข้อมูล เช่น ฐานข้อมูล/ไฟล์วิดีโอ/ไฟล์ cookies และต้องการให้ **ไม่หาย** เมื่อ redeploy/restart:

1) Railway → Service → **Volumes** → Add Volume (ตัวอย่าง mount path: `/data`)

2) ตั้ง Variables:

| ตัวแปร | ตัวอย่าง | ใช้ทำอะไร |
|---|---|---|
| `DATA_DIR` | `/data` | โฟลเดอร์เก็บ `videos.db`, โฟลเดอร์วิดีโอ, backups, cookies ฯลฯ |

#### ⚙️ ปรับประสิทธิภาพ gunicorn (Optional)

| ตัวแปร | default | ใช้ทำอะไร |
|---|---:|---|
| `WEB_CONCURRENCY` | `2` | จำนวน worker processes |
| `GUNICORN_THREADS` | `2` | จำนวน threads ต่อ worker |
| `GUNICORN_TIMEOUT` | `120` | timeout (วินาที) |

> ถ้าใช้ SQLite แล้วเจอ error แนว `database is locked` ให้ลองตั้ง `WEB_CONCURRENCY=1`

#### 🛡️ Cloudflare Turnstile (Optional)

| ตัวแปร | ใช้ทำอะไร |
|---|---|
| `TURNSTILE_SITE_KEY` | คีย์สำหรับแสดง widget |
| `TURNSTILE_SECRET_KEY` | คีย์สำหรับ verify หลังบ้าน |
| `TURNSTILE_ALLOWED_HOSTNAMES` | อนุญาต hostname (คั่นด้วย comma) |
| `TURNSTILE_REQUIRED` | `true/false` ถ้าตั้ง `true` แต่ไม่ใส่คีย์ครบ แอปจะไม่ยอมเริ่ม |

#### ✉️ อีเมล OTP ผ่าน Brevo (Optional)

| ตัวแปร | ใช้ทำอะไร |
|---|---|
| `BREVO_API_KEY` | API key ของ Brevo |
| `BREVO_SENDER_EMAIL` | อีเมลผู้ส่ง |
| `BREVO_SENDER_NAME` | ชื่อผู้ส่ง |

> หมายเหตุ: **ระบบ OTP ถูกปิดเป็นค่าเริ่มต้น** เพื่อไม่ให้ deploy ใหม่แล้วเจอปัญหา “ส่ง OTP ไม่ได้” ทันที  
> หากต้องการเปิดใช้ ให้ทำ 2 ขั้นตอนนี้:
> 1) ตั้งค่า Brevo variables ให้ครบ (ตารางด้านบน)  
> 2) ล็อกอินแอดมิน → ไปที่ `/admin/settings` → เปิดสวิตช์ที่ต้องการ เช่น
>    - “บังคับผู้สมัครต้องใส่อีเมล์และยืนยัน OTP” (`force_email`)
>    - “ฉันลืมรหัสผ่าน” (`account_recovery_enabled`)
>    - “เปลี่ยนอีเมล์” (`email_change_enabled`)

### 4) Domains

ไปที่ Railway → **Networking / Domains** → สร้าง Public Domain แล้วเปิด URL นั้นได้เลย

---

## Deploy บน Render (มีตัวอย่างอยู่แล้ว)

ดู `render.yaml` (แนวทางเหมือนกัน: build ติดตั้ง requirements แล้ว start ด้วย `sh start.sh`)

---

## Health check

มี endpoint สำหรับเช็คสถานะ:

- `GET /healthz`

ควรตอบประมาณนี้:

```json
{"status":"ok","project":"...","version":"..."}
```

---

## Troubleshooting

### แอปไม่ยอมบูตทันที
- เช็คว่าไม่ได้ตั้ง `TURNSTILE_REQUIRED=true` แต่ยังไม่ได้ใส่ `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET_KEY`

### เปิดเว็บแล้ว 502/timeout
- ดู logs ของ Railway ว่า service “Listening on 0.0.0.0:$PORT” หรือไม่
- ตรวจว่า start command เป็น `sh start.sh`

### ข้อมูลหายหลัง deploy ใหม่
- ต้องใช้ **Railway Volume** + ตั้ง `DATA_DIR` ไปยัง path ที่ mount volume

### `database is locked` (SQLite)
- ตั้ง `WEB_CONCURRENCY=1` แล้ว redeploy

---

## Security checklist (ควรทำ)

- ตั้ง `SECRET_KEY` ใหม่เสมอ (สุ่มยาว ๆ)
- เปลี่ยน `ADMIN_PASSWORD` จากค่า default
- อย่าเปิด `FLASK_DEBUG=true` บน production

---

## หมายเหตุเกี่ยวกับสคริปต์ติดตั้ง (install.sh / install.ps1)

สคริปต์ติดตั้งใน repo นี้ยังอ้างอิง repo ค่าเริ่มต้นใน config (`menuwed_config.json`) ซึ่งอาจชี้ไปที่ repo อื่นได้ ขึ้นกับค่าที่ตั้งไว้ใน config

ถ้าคุณตั้งใจให้สคริปต์ติดตั้งชี้มาที่ repo นี้เสมอ ให้แก้ค่า `github_repo` ใน `menuwed_config.json` ให้เป็น `Phechr-2025/NexusHub-Stream`
