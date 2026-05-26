# 📡 Stock Support Alert Bot

แจ้งเตือนเมื่อราคาหุ้นถึงแนวรับ ผ่าน **Line Notify** + **Telegram**

---

## 🚀 วิธี Deploy บน Railway (ทีละขั้น)

### ขั้นที่ 1 — สร้าง GitHub Repository

1. ไปที่ https://github.com → **New repository**
2. ตั้งชื่อ เช่น `stock-alert-bot`
3. กด **Create repository**
4. อัปโหลดไฟล์ทั้ง 4 ไฟล์นี้:
   - `main.py`
   - `requirements.txt`
   - `Procfile`
   - `railway.toml`

---

### ขั้นที่ 2 — ได้ Token ต่างๆ

#### Line Notify Token
1. ไปที่ https://notify-bot.line.me/
2. Login → **My page**
3. เลื่อนลงหา **Generate access token**
4. ตั้งชื่อ → เลือก chat ที่อยากรับแจ้งเตือน → **Generate**
5. คัดลอก token เก็บไว้

#### Telegram Bot Token + Chat ID
1. เปิด Telegram → ค้นหา **@BotFather**
2. พิมพ์ `/newbot` → ตั้งชื่อบอท
3. คัดลอก **token** ที่ได้
4. ค้นหา **@userinfobot** → พิมพ์ `/start` → จะได้ **Chat ID** ของคุณ
5. ถ้าจะส่งเข้า Group: เพิ่มบอทเข้ากลุ่ม → ใช้ https://api.telegram.org/bot{TOKEN}/getUpdates เพื่อดู group chat ID

---

### ขั้นที่ 3 — Deploy บน Railway

1. ไปที่ https://railway.app → **Login with GitHub**
2. กด **New Project** → **Deploy from GitHub repo**
3. เลือก repo `stock-alert-bot`
4. Railway จะเริ่ม build อัตโนมัติ

---

### ขั้นที่ 4 — ตั้งค่า Environment Variables

ใน Railway Dashboard → เลือก Project → **Variables** → เพิ่มตามนี้:

| Variable | ค่า |
|----------|-----|
| `LINE_TOKEN` | token จาก Line Notify |
| `TELEGRAM_TOKEN` | token จาก BotFather |
| `TELEGRAM_CHAT_ID` | chat ID ของคุณ |
| `CHECK_INTERVAL` | `120` (เช็คทุก 2 นาที) |
| `THRESHOLD_PCT` | `1.0` (แจ้งเมื่อห่างแนวรับ ≤ 1%) |

กด **Deploy** → บอทจะเริ่มทำงานทันที!

---

## 📊 หุ้นที่ติดตาม

| กลุ่ม | หุ้น |
|-------|------|
| Semiconductors | NVDA, ARM, MRVL, INTC, FORM, WOLF, NVTS |
| Space Tech | ASTS, RKLB, PL, SATL |
| Photonics | COHR, LITE, AEHR, AAOI, LWLG, POET |
| Drone & Defense | PLTR, ONDS, OSS |
| Memory | SIMO, SNDK, MRAM |
| Quantum | IONQ, RGTI, QBTS |
| Energy | BE, AMPX |

---

## 💬 ตัวอย่างข้อความแจ้งเตือน

```
🚨 แนวรับใกล้แล้ว! [25/05/2026 14:32 UTC]
📌 $NVDA
💰 ราคาปัจจุบัน: $195.80
🎯 แนวรับ: $194.00
📉 ห่างแนวรับ 0.93%
```

---

## ⚙️ การปรับแต่ง

- **THRESHOLD_PCT=2.0** → แจ้งเมื่อห่างแนวรับ ≤ 2%
- **CHECK_INTERVAL=60** → เช็คทุก 1 นาที (ใช้ quota yfinance มากขึ้น)
- ตลาดปิด (เสาร์-อาทิตย์ / นอกเวลา) → บอทจะ sleep อัตโนมัติ ไม่เปลืองทรัพยากร
