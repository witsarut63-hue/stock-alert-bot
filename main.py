#!/usr/bin/env python3
"""
Stock Support Level Alert Bot — Telegram Only
แจ้งเตือนเมื่อราคาหุ้นถึงแนวรับ → Telegram
"""

import os
import time
import requests
import yfinance as yf
from datetime import datetime

# ============================================================
# 🔧 Config จาก Environment Variables (ตั้งใน Railway Dashboard)
# ============================================================

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CHECK_INTERVAL   = int(os.environ.get("CHECK_INTERVAL", "120"))
THRESHOLD_PCT    = float(os.environ.get("THRESHOLD_PCT", "1.0"))

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
# 📬 ส่ง Telegram
# ============================================================

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] ❌ ไม่มี TOKEN หรือ CHAT_ID")
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
        if r.status_code == 200:
            print(f"[Telegram] ✅ ส่งสำเร็จ")
        else:
            print(f"[Telegram] ⚠️ status={r.status_code} {r.text}")
    except Exception as e:
        print(f"[Telegram] ERROR: {e}")


def notify(ticker: str, current: float, support: float, pct_diff: float):
    now = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    thai_time = datetime.utcnow().replace(hour=(datetime.utcnow().hour + 7) % 24)
    thai_str  = thai_time.strftime("%d/%m/%Y %H:%M น.")

    if pct_diff < 0:
        status_line = f"🔴 <b>ต่ำกว่าแนวรับแล้ว! {pct_diff:.2f}%</b>"
    else:
        status_line = f"📉 ห่างแนวรับอีก <b>{pct_diff:.2f}%</b>"

    msg = (
        f"🚨 <b>แนวรับใกล้แล้ว!</b>\n"
        f"🕐 {thai_str}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 <b>${ticker}</b>\n"
        f"💰 ราคาปัจจุบัน: <b>${current:.2f}</b>\n"
        f"🎯 แนวรับ: ${support:.2f}\n"
        f"{status_line}"
    )
    send_telegram(msg)
    print(f"\n🚨 แจ้งเตือน ${ticker} ราคา={current:.2f} แนวรับ={support:.2f} ห่าง={pct_diff:+.2f}%")

# ============================================================
# 🔍 เช็คราคา
# ============================================================

alerted: dict = {t: False for t in SUPPORT_LEVELS}


def is_market_open() -> bool:
    """ตลาด US เปิด Mon-Fri 09:30-16:00 ET = 14:30-21:00 UTC"""
    now = datetime.utcnow()
    if now.weekday() >= 5:
        return False
    hour = now.hour + now.minute / 60
    return 14.5 <= hour <= 21.0


def check_prices():
    tickers = list(SUPPORT_LEVELS.keys())
    now_str = datetime.utcnow().strftime("%H:%M:%S UTC")
    print(f"\n[{now_str}] เช็คราคา {len(tickers)} ตัว...")

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
            if price != price:
                raise ValueError("NaN")
        except Exception:
            print(f"  ⚠️  ${ticker:6s} — ไม่มีข้อมูล")
            continue

        pct_diff = (price - support) / support * 100
        near = pct_diff <= THRESHOLD_PCT

        icon = "⚠️ " if near else "✅"
        print(f"  {icon} ${ticker:6s}  ราคา={price:8.2f}  แนวรับ={support:7.2f}  ห่าง={pct_diff:+6.2f}%")

        if near and not alerted[ticker]:
            notify(ticker, price, support, pct_diff)
            alerted[ticker] = True
        elif pct_diff > 3.0:
            alerted[ticker] = False  # reset เมื่อราคาขึ้นพ้น 3%

# ============================================================
# 🚀 Main
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  📡 Stock Alert Bot — Telegram Only")
    print(f"  ติดตาม {len(SUPPORT_LEVELS)} หุ้น | เช็คทุก {CHECK_INTERVAL}s | threshold ≤{THRESHOLD_PCT}%")
    print("=" * 50)

    tickers_list = " ".join([f"${t}" for t in SUPPORT_LEVELS.keys()])
    start_msg = (
        f"✅ <b>Stock Alert Bot เริ่มทำงานแล้ว!</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 ติดตาม <b>{len(SUPPORT_LEVELS)} หุ้น</b>\n"
        f"⏱ เช็คทุก <b>{CHECK_INTERVAL} วินาที</b>\n"
        f"🎯 แจ้งเมื่อห่างแนวรับ ≤ <b>{THRESHOLD_PCT}%</b>\n\n"
        f"📌 {tickers_list}"
    )
    send_telegram(start_msg)

    while True:
        try:
            check_prices()
        except Exception as e:
            print(f"[MAIN LOOP ERROR] {e}")

        if is_market_open():
            time.sleep(CHECK_INTERVAL)
        else:
            print(f"  💤 ตลาดปิด — รอ 10 นาที")
            time.sleep(600)
