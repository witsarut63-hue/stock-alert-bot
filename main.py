#!/usr/bin/env python3
"""
Stock Support Alert Bot v3
- แจ้งเตือนเมื่อราคาถึงแนวรับ → Telegram
- Watchlist เก็บใน Google Sheet (ไม่หายแม้ redeploy)
- รับคำสั่ง /add /remove /list /check /help ผ่าน Telegram
"""

import os
import json
import time
import threading
import requests
import yfinance as yf
from datetime import datetime

# ============================================================
# 🔧 Config จาก Environment Variables
# ============================================================

TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
SHEET_ID          = os.environ.get("SHEET_ID", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")  # JSON string ทั้งก้อน

CHECK_INTERVAL    = int(os.environ.get("CHECK_INTERVAL", "120"))
THRESHOLD_PCT     = float(os.environ.get("THRESHOLD_PCT", "1.0"))

# ============================================================
# 📊 Watchlist เริ่มต้น (ใช้เมื่อ Sheet ว่าง)
# ============================================================

DEFAULT_WATCHLIST = {
    # SEMICONDUCTORS
    "NVDA": 194.0, "ARM": 286.0, "MRVL": 168.0, "INTC": 111.0,
    "FORM": 128.0, "WOLF": 65.4, "NVTS": 25.8,
    # SPACE TECHNOLOGY
    "ASTS": 93.0, "RKLB": 119.0, "PL": 39.0, "SATL": 9.5,
    # PHOTONICS
    "COHR": 366.0, "LITE": 879.0, "AEHR": 90.0, "AAOI": 174.5,
    "LWLG": 12.7, "POET": 13.6,
    # DRONE & DEFENSE
    "PLTR": 120.0, "ONDS": 9.0, "OSS": 15.6,
    # MEMORY
    "SIMO": 237.0, "SNDK": 1355.0, "MRAM": 29.0,
    # QUANTUM COMPUTING
    "IONQ": 59.7, "RGTI": 26.4, "QBTS": 26.6,
    # ENERGY
    "BE": 274.0, "AMPX": 15.3,
}

# ============================================================
# 🔑 Google Sheets Auth
# ============================================================

def get_access_token() -> str:
    """แปลง Service Account JSON → Access Token"""
    import math, hashlib, hmac, base64, struct
    creds = json.loads(GOOGLE_CREDS_JSON)

    # Build JWT
    now = int(time.time())
    header  = base64.urlsafe_b64encode(json.dumps({"alg":"RS256","typ":"JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "iss": creds["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud": "https://oauth2.googleapis.com/token",
        "exp": now + 3600,
        "iat": now,
    }).encode()).rstrip(b"=")

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend

    private_key = serialization.load_pem_private_key(
        creds["private_key"].encode(),
        password=None,
        backend=default_backend()
    )
    signing_input = header + b"." + payload
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")

    jwt_token = (signing_input + b"." + sig_b64).decode()

    r = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_token,
    }, timeout=10)
    return r.json()["access_token"]


# Cache token
_token_cache = {"token": "", "expires": 0}

def sheets_token() -> str:
    if time.time() > _token_cache["expires"] - 60:
        _token_cache["token"]   = get_access_token()
        _token_cache["expires"] = time.time() + 3600
    return _token_cache["token"]

# ============================================================
# 📊 Google Sheet CRUD
# ============================================================

SHEET_RANGE = "Sheet1!A:B"

def sheet_read() -> dict:
    """อ่าน watchlist จาก Google Sheet
       ถ้า Sheet ว่าง → เขียน DEFAULT_WATCHLIST ลงไปอัตโนมัติ"""
    try:
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{SHEET_RANGE}"
        r = requests.get(url, headers={"Authorization": f"Bearer {sheets_token()}"}, timeout=10)
        rows = r.json().get("values", [])
        wl = {}
        for row in rows:
            if len(row) < 2:
                continue
            ticker = row[0].strip().upper().replace("$", "")
            if ticker == "TICKER":
                continue
            try:
                wl[ticker] = float(row[1])
            except ValueError:
                pass
        # Sheet ว่าง → เขียน DEFAULT_WATCHLIST ลงไปอัตโนมัติ
        if not wl:
            print("[Sheet] Sheet ว่าง → เขียน DEFAULT_WATCHLIST...")
            sheet_write(DEFAULT_WATCHLIST)
            return DEFAULT_WATCHLIST.copy()
        return wl
    except Exception as e:
        print(f"[Sheet] read ERROR: {e}")
        return DEFAULT_WATCHLIST.copy()


def sheet_write(watchlist: dict):
    """เขียน watchlist ทั้งหมดลง Google Sheet"""
    try:
        values = [["TICKER", "SUPPORT"]] + [[t, str(s)] for t, s in sorted(watchlist.items())]
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
               f"/values/{SHEET_RANGE}?valueInputOption=RAW")
        requests.put(url,
            headers={"Authorization": f"Bearer {sheets_token()}", "Content-Type": "application/json"},
            json={"range": SHEET_RANGE, "majorDimension": "ROWS", "values": values},
            timeout=10
        )
        # Clear แถวเกิน
        clear_url = (f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
                     f"/values/{SHEET_RANGE}:clear")
        requests.post(clear_url,
            headers={"Authorization": f"Bearer {sheets_token()}", "Content-Type": "application/json"},
            timeout=10
        )
        # เขียนใหม่หลัง clear
        requests.put(url,
            headers={"Authorization": f"Bearer {sheets_token()}", "Content-Type": "application/json"},
            json={"range": SHEET_RANGE, "majorDimension": "ROWS", "values": values},
            timeout=10
        )
        print(f"[Sheet] เขียน {len(watchlist)} รายการสำเร็จ")
    except Exception as e:
        print(f"[Sheet] write ERROR: {e}")

# ============================================================
# 📬 Telegram
# ============================================================

def send(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"[Telegram] ERROR: {e}")


def notify_alert(ticker: str, price: float, support: float, pct: float):
    now = datetime.utcnow()
    thai_h = (now.hour + 7) % 24
    time_str = f"{now.day:02d}/{now.month:02d}/{now.year} {thai_h:02d}:{now.minute:02d} น."
    status = f"🔴 <b>ต่ำกว่าแนวรับแล้ว! {pct:.2f}%</b>" if pct < 0 else f"📉 ห่างแนวรับอีก <b>{pct:.2f}%</b>"
    send(
        f"🚨 <b>แนวรับใกล้แล้ว!</b>\n"
        f"🕐 {time_str}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 <b>${ticker}</b>\n"
        f"💰 ราคาปัจจุบัน: <b>${price:.2f}</b>\n"
        f"🎯 แนวรับ: ${support:.2f}\n"
        f"{status}"
    )
    print(f"🚨 แจ้งเตือน ${ticker} ราคา={price:.2f} แนวรับ={support:.2f} ({pct:+.2f}%)")

# ============================================================
# 🤖 Commands
# ============================================================

HELP_TEXT = """
📖 <b>คำสั่งที่ใช้ได้</b>
━━━━━━━━━━━━━━━
➕ <b>เพิ่ม / แก้แนวรับ:</b>
<code>/add TICKER PRICE</code>
เช่น: <code>/add TSLA 250</code>

🗑 <b>ลบหุ้น:</b>
<code>/remove TICKER</code>
เช่น: <code>/remove TSLA</code>

📋 <b>ดูรายการทั้งหมด:</b>
<code>/list</code>

🔍 <b>เช็คราคาทันที:</b>
<code>/check</code>

❓ <b>ดูคำสั่ง:</b>
<code>/help</code>
"""

def handle_command(text: str, watchlist: dict, alerted: dict) -> dict:
    parts  = text.strip().split()
    cmd    = parts[0].lower()

    if cmd == "/help":
        send(HELP_TEXT)

    elif cmd == "/add":
        if len(parts) != 3:
            send("❌ รูปแบบผิด ใช้: <code>/add TICKER PRICE</code>\nเช่น <code>/add TSLA 250</code>")
        else:
            ticker = parts[1].upper().replace("$", "")
            try:
                price      = float(parts[2])
                is_update  = ticker in watchlist
                watchlist[ticker] = price
                alerted[ticker]   = False
                sheet_write(watchlist)
                action = "✏️ อัปเดต" if is_update else "✅ เพิ่ม"
                send(f"{action} <b>${ticker}</b> แนวรับ <b>${price:.2f}</b> ใน Watchlist + Google Sheet แล้วครับ!")
            except ValueError:
                send("❌ ราคาต้องเป็นตัวเลข เช่น <code>/add TSLA 250.5</code>")

    elif cmd == "/remove":
        if len(parts) != 2:
            send("❌ รูปแบบผิด ใช้: <code>/remove TICKER</code>")
        else:
            ticker = parts[1].upper().replace("$", "")
            if ticker in watchlist:
                del watchlist[ticker]
                alerted.pop(ticker, None)
                sheet_write(watchlist)
                send(f"🗑 ลบ <b>${ticker}</b> ออกจาก Watchlist + Google Sheet แล้วครับ!")
            else:
                send(f"⚠️ ไม่พบ <b>${ticker}</b> ใน Watchlist")

    elif cmd == "/list":
        if not watchlist:
            send("📋 Watchlist ว่างอยู่ครับ ใช้ /add เพื่อเพิ่มหุ้น")
        else:
            lines = [f"📋 <b>Watchlist ({len(watchlist)} ตัว)</b>", "━━━━━━━━━━━━━━━"]
            for t, s in sorted(watchlist.items()):
                lines.append(f"  📌 <b>${t}</b>  แนวรับ <b>${s:.2f}</b>")
            lines.append(f"\n🎯 แจ้งเมื่อห่าง ≤ {THRESHOLD_PCT}%")
            send("\n".join(lines))

    elif cmd == "/check":
        send("🔍 กำลังเช็คราคา รอแป๊บนึงครับ...")
        check_and_report(watchlist)

    else:
        send(f"❓ ไม่รู้จักคำสั่ง <code>{cmd}</code>\nพิมพ์ /help เพื่อดูคำสั่งทั้งหมด")

    return watchlist


def check_and_report(watchlist: dict):
    if not watchlist:
        send("📋 Watchlist ว่างอยู่ครับ")
        return
    tickers = list(watchlist.keys())
    try:
        data = yf.download(tickers, period="1d", interval="5m", progress=False, auto_adjust=True)
        if data.empty:
            send("⚠️ ดึงข้อมูลไม่ได้ (อาจนอกเวลาตลาด)")
            return
        prices = data["Close"].iloc[-1]
    except Exception as e:
        send(f"❌ Error: {e}")
        return

    lines = ["📊 <b>ราคาล่าสุด</b>", "━━━━━━━━━━━━━━━"]
    for ticker, support in sorted(watchlist.items()):
        try:
            price = float(prices[ticker])
            pct   = (price - support) / support * 100
            icon  = "⚠️" if pct <= THRESHOLD_PCT else "✅"
            lines.append(f"{icon} <b>${ticker}</b>  ${price:.2f}  แนวรับ ${support:.2f}  ({pct:+.1f}%)")
        except Exception:
            lines.append(f"❓ ${ticker} — ไม่มีข้อมูล")
    send("\n".join(lines))

# ============================================================
# 📥 Polling + Price Loop
# ============================================================

last_update_id = 0

def poll_commands(watchlist_ref: list, alerted_ref: list):
    global last_update_id
    print("[Polling] เริ่มรับคำสั่ง...")
    while True:
        try:
            r    = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 10},
                timeout=15
            )
            for update in r.json().get("result", []):
                last_update_id = update["update_id"]
                msg     = update.get("message", {})
                text    = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id == str(TELEGRAM_CHAT_ID) and text.startswith("/"):
                    print(f"[CMD] {text}")
                    watchlist_ref[0] = handle_command(text, watchlist_ref[0], alerted_ref[0])
        except Exception as e:
            print(f"[Polling] ERROR: {e}")
        time.sleep(3)


def is_market_open() -> bool:
    now = datetime.utcnow()
    if now.weekday() >= 5:
        return False
    h = now.hour + now.minute / 60
    return 14.5 <= h <= 21.0


def price_loop(watchlist_ref: list, alerted_ref: list):
    while True:
        # อ่านจาก Sheet ทุกรอบ (ดักกรณีแก้ตรงใน Sheet)
        watchlist_ref[0] = sheet_read()
        watchlist = watchlist_ref[0]
        alerted   = alerted_ref[0]

        if watchlist:
            tickers = list(watchlist.keys())
            print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')} UTC] เช็ค {len(tickers)} ตัว...")
            try:
                data = yf.download(tickers, period="1d", interval="5m", progress=False, auto_adjust=True)
                if not data.empty:
                    prices = data["Close"].iloc[-1]
                    for ticker, support in watchlist.items():
                        try:
                            price = float(prices[ticker])
                            if price != price: raise ValueError("NaN")
                            pct  = (price - support) / support * 100
                            near = pct <= THRESHOLD_PCT
                            print(f"  {'⚠️ ' if near else '✅'} ${ticker:6s}  {price:8.2f}  แนวรับ={support:.2f}  ({pct:+.2f}%)")
                            if near and not alerted.get(ticker, False):
                                notify_alert(ticker, price, support, pct)
                                alerted[ticker] = True
                            elif pct > 3.0:
                                alerted[ticker] = False
                        except Exception:
                            print(f"  ❓ ${ticker} — ข้ามไป")
            except Exception as e:
                print(f"  [yfinance] ERROR: {e}")

        sleep = CHECK_INTERVAL if is_market_open() else 600
        if not is_market_open():
            print("  💤 ตลาดปิด รอ 10 นาที")
        time.sleep(sleep)

# ============================================================
# 🚀 Main
# ============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("  📡 Stock Alert Bot v3 — Google Sheet Sync")
    print(f"  เช็คทุก {CHECK_INTERVAL}s | threshold ≤{THRESHOLD_PCT}%")
    print("=" * 55)

    wl = sheet_read()
    print(f"  โหลด watchlist จาก Sheet: {len(wl)} ตัว")

    al = {t: False for t in wl}
    watchlist_ref = [wl]
    alerted_ref   = [al]

    threading.Thread(target=poll_commands, args=(watchlist_ref, alerted_ref), daemon=True).start()

    send(
        f"✅ <b>Stock Alert Bot v3 เริ่มทำงานแล้ว!</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 โหลด <b>{len(wl)} หุ้น</b> จาก Google Sheet\n"
        f"⏱ เช็คทุก <b>{CHECK_INTERVAL} วินาที</b>\n"
        f"🎯 แจ้งเมื่อห่างแนวรับ ≤ <b>{THRESHOLD_PCT}%</b>\n\n"
        f"พิมพ์ /help เพื่อดูคำสั่งทั้งหมด"
    )

    price_loop(watchlist_ref, alerted_ref)
