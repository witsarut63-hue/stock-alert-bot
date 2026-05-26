#!/usr/bin/env python3
"""
Stock Support Alert Bot v2
- แจ้งเตือนเมื่อราคาถึงแนวรับ
- รับคำสั่งผ่าน Telegram chat
"""

import os
import json
import time
import threading
import requests
import yfinance as yf
from datetime import datetime

# ============================================================
# 🔧 Config
# ============================================================

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CHECK_INTERVAL   = int(os.environ.get("CHECK_INTERVAL", "120"))
THRESHOLD_PCT    = float(os.environ.get("THRESHOLD_PCT", "1.0"))

DATA_FILE = "watchlist.json"  # เก็บ watchlist ไว้ใน file (persist ใน Railway Volume)

# ============================================================
# 📊 Watchlist เริ่มต้น (แก้ได้ผ่าน Telegram)
# ============================================================

DEFAULT_WATCHLIST = {
    "NVDA": 194.0, "ARM": 286.0, "MRVL": 168.0, "INTC": 111.0,
    "FORM": 128.0, "WOLF": 65.4, "NVTS": 25.8,
    "ASTS": 93.0,  "RKLB": 119.0, "PL": 39.0, "SATL": 9.5,
    "COHR": 366.0, "LITE": 879.0, "AEHR": 90.0, "AAOI": 174.5,
    "LWLG": 12.7,  "POET": 13.6,
    "PLTR": 120.0, "ONDS": 9.0,  "OSS": 15.6,
    "SIMO": 237.0, "SNDK": 1355.0, "MRAM": 29.0,
    "IONQ": 59.7,  "RGTI": 26.4, "QBTS": 26.6,
    "BE": 274.0,   "AMPX": 15.3,
}

# ============================================================
# 💾 โหลด / บันทึก Watchlist
# ============================================================

def load_watchlist() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    save_watchlist(DEFAULT_WATCHLIST)
    return DEFAULT_WATCHLIST.copy()


def save_watchlist(wl: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(wl, f, indent=2)

# ============================================================
# 📬 Telegram
# ============================================================

def send(message: str, parse_mode: str = "HTML"):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] ❌ ไม่มี TOKEN/CHAT_ID")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": parse_mode,
        }, timeout=10)
    except Exception as e:
        print(f"[Telegram] ERROR: {e}")


def notify_alert(ticker: str, price: float, support: float, pct: float):
    thai_hour = (datetime.utcnow().hour + 7) % 24
    thai_min  = datetime.utcnow().minute
    t = datetime.utcnow()
    time_str  = f"{t.day:02d}/{t.month:02d}/{t.year} {thai_hour:02d}:{thai_min:02d} น."

    status = f"🔴 <b>ต่ำกว่าแนวรับ! {pct:.2f}%</b>" if pct < 0 else f"📉 ห่างแนวรับอีก <b>{pct:.2f}%</b>"

    send(
        f"🚨 <b>แนวรับใกล้แล้ว!</b>\n"
        f"🕐 {time_str}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 <b>${ticker}</b>\n"
        f"💰 ราคาปัจจุบัน: <b>${price:.2f}</b>\n"
        f"🎯 แนวรับ: ${support:.2f}\n"
        f"{status}"
    )

# ============================================================
# 🤖 Command Handler
# ============================================================

HELP_TEXT = """
📖 <b>คำสั่งที่ใช้ได้</b>
━━━━━━━━━━━━━━━
➕ <b>เพิ่มหุ้น:</b>
<code>/add TICKER PRICE</code>
ตัวอย่าง: <code>/add TSLA 250</code>

🗑 <b>ลบหุ้น:</b>
<code>/remove TICKER</code>
ตัวอย่าง: <code>/remove TSLA</code>

✏️ <b>แก้แนวรับ:</b>
<code>/add TICKER PRICE</code>
(ใช้ /add ซ้ำกับตัวเดิมเพื่ออัปเดต)

📋 <b>ดูรายการทั้งหมด:</b>
<code>/list</code>

🔍 <b>เช็คราคาตอนนี้:</b>
<code>/check</code>

❓ <b>ดูคำสั่ง:</b>
<code>/help</code>
"""

def handle_command(text: str, watchlist: dict, alerted: dict) -> dict:
    """ประมวลผลคำสั่ง แล้ว return watchlist ที่อัปเดต"""
    parts = text.strip().split()
    cmd   = parts[0].lower()

    # /help
    if cmd == "/help":
        send(HELP_TEXT)

    # /add TICKER PRICE
    elif cmd == "/add":
        if len(parts) != 3:
            send("❌ รูปแบบผิด ใช้: <code>/add TICKER PRICE</code>\nเช่น <code>/add TSLA 250</code>")
        else:
            ticker = parts[1].upper().replace("$", "")
            try:
                price = float(parts[2])
                is_update = ticker in watchlist
                watchlist[ticker] = price
                alerted[ticker]   = False
                save_watchlist(watchlist)
                action = "✏️ อัปเดต" if is_update else "✅ เพิ่ม"
                send(f"{action} <b>${ticker}</b> แนวรับ <b>${price:.2f}</b> แล้วครับ!")
            except ValueError:
                send("❌ ราคาต้องเป็นตัวเลข เช่น <code>/add TSLA 250.5</code>")

    # /remove TICKER
    elif cmd == "/remove":
        if len(parts) != 2:
            send("❌ รูปแบบผิด ใช้: <code>/remove TICKER</code>\nเช่น <code>/remove TSLA</code>")
        else:
            ticker = parts[1].upper().replace("$", "")
            if ticker in watchlist:
                del watchlist[ticker]
                alerted.pop(ticker, None)
                save_watchlist(watchlist)
                send(f"🗑 ลบ <b>${ticker}</b> ออกจาก watchlist แล้วครับ!")
            else:
                send(f"⚠️ ไม่พบ <b>${ticker}</b> ใน watchlist")

    # /list
    elif cmd == "/list":
        if not watchlist:
            send("📋 Watchlist ว่างอยู่ครับ ใช้ /add เพื่อเพิ่มหุ้น")
        else:
            lines = [f"📋 <b>Watchlist ({len(watchlist)} ตัว)</b>", "━━━━━━━━━━━━━━━"]
            for t, s in sorted(watchlist.items()):
                lines.append(f"  ${t:8s} แนวรับ <b>${s:.2f}</b>")
            lines.append(f"\n🎯 แจ้งเมื่อห่าง ≤ {THRESHOLD_PCT}%")
            send("\n".join(lines))

    # /check
    elif cmd == "/check":
        send("🔍 กำลังเช็คราคาทั้งหมด รอแป๊บนึงครับ...")
        check_and_report(watchlist)

    else:
        send(f"❓ ไม่รู้จักคำสั่ง <code>{cmd}</code>\nพิมพ์ /help เพื่อดูคำสั่งทั้งหมด")

    return watchlist


def check_and_report(watchlist: dict):
    """เช็คราคาแล้วส่งรายงานกลับ Telegram ทันที"""
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
            lines.append(f"{icon} <b>${ticker}</b>  ราคา ${price:.2f}  แนวรับ ${support:.2f}  ({pct:+.1f}%)")
        except Exception:
            lines.append(f"❓ ${ticker} — ไม่มีข้อมูล")

    send("\n".join(lines))

# ============================================================
# 📥 Polling รับคำสั่ง
# ============================================================

last_update_id = 0

def poll_commands(watchlist_ref: list, alerted_ref: list):
    """รันใน thread แยก — ดึง message จาก Telegram ทุก 3 วินาที"""
    global last_update_id
    print("[Polling] เริ่ม polling commands...")

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            r   = requests.get(url, params={"offset": last_update_id + 1, "timeout": 10}, timeout=15)
            data = r.json()

            for update in data.get("result", []):
                last_update_id = update["update_id"]
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))

                # รับเฉพาะจาก chat ที่อนุญาต
                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                if text.startswith("/"):
                    print(f"[CMD] {text}")
                    watchlist_ref[0] = handle_command(text, watchlist_ref[0], alerted_ref[0])

        except Exception as e:
            print(f"[Polling] ERROR: {e}")

        time.sleep(3)

# ============================================================
# 🔍 Price Check Loop
# ============================================================

def is_market_open() -> bool:
    now = datetime.utcnow()
    if now.weekday() >= 5:
        return False
    h = now.hour + now.minute / 60
    return 14.5 <= h <= 21.0


def price_loop(watchlist_ref: list, alerted_ref: list):
    while True:
        watchlist = watchlist_ref[0]
        alerted   = alerted_ref[0]

        if watchlist:
            tickers = list(watchlist.keys())
            now_str = datetime.utcnow().strftime("%H:%M:%S UTC")
            print(f"\n[{now_str}] เช็คราคา {len(tickers)} ตัว...")

            try:
                data = yf.download(tickers, period="1d", interval="5m", progress=False, auto_adjust=True)
                if not data.empty:
                    prices = data["Close"].iloc[-1]
                    for ticker, support in watchlist.items():
                        try:
                            price = float(prices[ticker])
                            if price != price:
                                raise ValueError("NaN")
                            pct  = (price - support) / support * 100
                            near = pct <= THRESHOLD_PCT
                            icon = "⚠️ " if near else "✅"
                            print(f"  {icon} ${ticker:6s}  {price:8.2f}  แนวรับ={support:.2f}  ({pct:+.2f}%)")
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
    print("=" * 50)
    print("  📡 Stock Alert Bot v2 — Telegram Commands")
    print(f"  เช็คทุก {CHECK_INTERVAL}s | threshold ≤{THRESHOLD_PCT}%")
    print("=" * 50)

    wl = load_watchlist()
    al = {t: False for t in wl}

    # ใช้ list เพื่อให้ thread แชร์ข้อมูลกันได้
    watchlist_ref = [wl]
    alerted_ref   = [al]

    # Start polling thread
    t = threading.Thread(target=poll_commands, args=(watchlist_ref, alerted_ref), daemon=True)
    t.start()

    # แจ้งเตือนว่าเริ่มแล้ว
    send(
        f"✅ <b>Stock Alert Bot v2 เริ่มทำงานแล้ว!</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 ติดตาม <b>{len(wl)} หุ้น</b>\n"
        f"⏱ เช็คทุก <b>{CHECK_INTERVAL} วินาที</b>\n"
        f"🎯 แจ้งเมื่อห่างแนวรับ ≤ <b>{THRESHOLD_PCT}%</b>\n\n"
        f"พิมพ์ /help เพื่อดูคำสั่งทั้งหมด"
    )

    # Start price loop (main thread)
    price_loop(watchlist_ref, alerted_ref)
