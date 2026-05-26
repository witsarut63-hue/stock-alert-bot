#!/usr/bin/env python3
"""
Stock Support Level Alert Bot — Railway Cloud
แจ้งเตือนเมื่อราคาหุ้นถึงแนวรับ → Line Notify + Telegram
"""

import os
import time
import requests
import yfinance as yf
from datetime import datetime

# ============================================================
# 🔧 Config จาก Environment Variables (ตั้งใน Railway Dashboard)
# ============================================================

LINE_TOKEN      = os.environ.get("LINE_TOKEN", "")
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CHECK_INTERVAL  = int(os.environ.get("CHECK_INTERVAL", "120"))  # วินาที (default 2 นาที)
THRESHOLD_PCT   = float(os.environ.get("THRESHOLD_PCT", "1.0")) # แจ้งเมื่อห่างแนวรับ ≤ 1%

# ============================================================
# 📊 แนวรับทั้งหมดจากรูป
# ============================================================

SUPPORT_LEVELS = {
    # SEMICONDUCTORS
    "NVDA":  194.0,
    "ARM":   286.0,
    "MRVL":  168.0,
    "INTC":  111.0,
    "FORM":  128.0,
    "WOLF":  65.4,
    "NVTS":  25.8,

    # SPACE TECHNOLOGY
    "ASTS":  93.0,
    "RKLB":  119.0,
    "PL":    39.0,
    "SATL":  9.5,

    # PHOTONICS
    "COHR":  366.0,
    "LITE":  879.0,
    "AEHR":  90.0,
    "AAOI":  174.5,
    "LWLG":  12.7,
    "POET":  13.6,

    # DRONE & DEFENSE
    "PLTR":  120.0,
    "ONDS":  9.0,
    "OSS":   15.6,

    # MEMORY
    "SIMO":  237.0,
    "SNDK":  1355.0,
    "MRAM":  29.0,

    # QUANTUM COMPUTING
    "IONQ":  59.7,
    "RGTI":  26.4,
    "QBTS":  26.6,

    # ENERGY
    "BE":    274.0,
    "AMPX":  15.3,
}

# ============================================================
# 📬 ส่งแจ้งเตือน
# ============================================================

def send_line(message: str):
    if not LINE_TOKEN:
        print("[Line] ไม่มี TOKEN ข้ามไป")
        return
    try:
        r = requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            data={"message": message},
            timeout=10,
        )
        print(f"[Line] sent → status={r.status_code}")
    except Exception as e:
        print(f"[Line] ERROR: {e}")


def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] ไม่มี TOKEN/CHAT_ID ข้ามไป")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        print(f"[Telegram] sent → status={r.status_code}")
    except Exception as e:
        print(f"[Telegram] ERROR: {e}")


def notify_all(ticker: str, current: float, support: float, pct_diff: float):
    now = datetime.now().strftime("%d/%m/%Y %H:%M UTC")

    direction = "🔴 ต่ำกว่าแนวรับ!" if pct_diff < 0 else f"📉 ห่างแนวรับ {pct_diff:.2f}%"

    msg = (
        f"\n🚨 <b>แนวรับใกล้แล้ว!</b> [{now}]\n"
        f"📌 <b>${ticker}</b>\n"
        f"💰 ราคาปัจจุบัน: <b>${current:.2f}</b>\n"
        f"🎯 แนวรับ: ${support:.2f}\n"
        f"{direction}"
    )

    # Line ไม่รอง HTML ให้แปลงเป็น plain text
    msg_plain = msg.replace("<b>", "").replace("</b>", "")

    send_line(msg_plain)
    send_telegram(msg)
    print(f"\n{'='*45}")
    print(msg_plain)
    print('='*45)

# ============================================================
# 🔍 ดึงราคาและเช็ค
# ============================================================

# เก็บสถานะว่าแจ้งไปแล้วหรือยัง (reset เมื่อราคาขึ้นพ้นแนวรับ)
alerted: dict[str, bool] = {t: False for t in SUPPORT_LEVELS}


def is_market_open() -> bool:
    """เช็คว่าตลาด US เปิดอยู่ไหม (Mon-Fri 09:30-16:00 ET ≈ 14:30-21:00 UTC)"""
    now = datetime.utcnow()
    if now.weekday() >= 5:  # เสาร์-อาทิตย์
        return False
    hour = now.hour + now.minute / 60
    return 14.5 <= hour <= 21.0


def check_prices():
    tickers = list(SUPPORT_LEVELS.keys())
    print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')} UTC] เช็คราคา {len(tickers)} ตัว...")

    try:
        data = yf.download(
            tickers,
            period="1d",
            interval="5m",
            progress=False,
            auto_adjust=True,
        )
        if data.empty:
            print("  ⚠️ ไม่ได้ข้อมูล (อาจนอกเวลาตลาด)")
            return

        prices = data["Close"].iloc[-1]
    except Exception as e:
        print(f"  [yfinance] ERROR: {e}")
        return

    for ticker, support in SUPPORT_LEVELS.items():
        try:
            price = float(prices[ticker])
            if price != price:  # NaN check
                raise ValueError("NaN")
        except Exception:
            print(f"  ⚠️ ${ticker:6s} — ไม่มีข้อมูล")
            continue

        pct_diff = (price - support) / support * 100

        # แจ้งเมื่อราคาอยู่ภายใน THRESHOLD_PCT% ของแนวรับ (หรือต่ำกว่า)
        near_support = pct_diff <= THRESHOLD_PCT

        status = "⚠️ ใกล้แนวรับ!" if near_support else "✅"
        print(f"  {status} ${ticker:6s}  ราคา={price:8.2f}  แนวรับ={support:7.2f}  ห่าง={pct_diff:+6.2f}%")

        if near_support and not alerted[ticker]:
            notify_all(ticker, price, support, pct_diff)
            alerted[ticker] = True
        elif pct_diff > 3.0:
            alerted[ticker] = False  # reset เมื่อราคาขึ้นไปพ้นแล้ว

# ============================================================
# 🚀 Main Loop
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  📡 Stock Support Alert Bot — Railway")
    print(f"  เช็คทุก {CHECK_INTERVAL}s  |  threshold ≤{THRESHOLD_PCT}%")
    print(f"  หุ้นที่ติดตาม: {len(SUPPORT_LEVELS)} ตัว")
    print("=" * 50)

    # แจ้งเตือนว่าบอท start แล้ว
    start_msg = (
        f"\n✅ Stock Alert Bot เริ่มทำงานแล้ว!\n"
        f"📊 ติดตาม {len(SUPPORT_LEVELS)} หุ้น\n"
        f"⏱ เช็คทุก {CHECK_INTERVAL} วินาที\n"
        f"🎯 แจ้งเมื่อห่างแนวรับ ≤ {THRESHOLD_PCT}%"
    )
    send_line(start_msg)
    send_telegram(start_msg)

    while True:
        try:
            check_prices()
        except Exception as e:
            print(f"[MAIN LOOP ERROR] {e}")

        sleep_time = CHECK_INTERVAL if is_market_open() else 600  # นอกเวลาเช็คทุก 10 นาที
        if not is_market_open():
            print(f"  💤 ตลาดปิด รอ 10 นาที...")
        time.sleep(sleep_time)
