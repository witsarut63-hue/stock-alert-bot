#!/usr/bin/env python3
"""
Stock Support Alert Bot v4
- แนวรับ 3 ไม้ (S1, S2, S3) ต่อหุ้น
- แจ้งเตือนทั้ง "ใกล้แนวรับ" และ "ทะลุแนวรับ"
- Watchlist เก็บใน Google Sheet
- รับคำสั่งผ่าน Telegram
"""

import os
import json
import time
import threading
import requests
from datetime import datetime, timezone

# ============================================================
# 🔧 Config
# ============================================================

TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
SHEET_ID          = os.environ.get("SHEET_ID", "")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")
FINNHUB_API_KEY   = os.environ.get("FINNHUB_API_KEY", "")

CHECK_INTERVAL    = int(os.environ.get("CHECK_INTERVAL", "300"))
THRESHOLD_PCT     = float(os.environ.get("THRESHOLD_PCT", "1.0"))

SHEET_RANGE       = "ชีต1!A:E"  # TICKER | S1 | S2 | S3 | NOTE

# ============================================================
# 📡 Status Tracking
# ============================================================

BOT_START_TIME = datetime.now(timezone.utc)
status = {
    "last_check": None,
    "last_ok_count": 0,
    "last_total": 0,
    "alert_today": 0,
    "data_ok": True,
    "sheet_ok": True,
    "last_alert_reset": datetime.now(timezone.utc).date(),
}

# ============================================================
# 📊 Default Watchlist (TICKER: [S1, S2, S3])
# ============================================================

DEFAULT_WATCHLIST = {
    "NVDA":  [194.0, None, None],
    "ARM":   [286.0, None, None],
    "MRVL":  [168.0, None, None],
    "INTC":  [111.0, None, None],
    "FORM":  [128.0, None, None],
    "WOLF":  [65.4,  None, None],
    "NVTS":  [25.8,  None, None],
    "ASTS":  [93.0,  None, None],
    "RKLB":  [119.0, None, None],
    "PL":    [39.0,  None, None],
    "SATL":  [9.5,   None, None],
    "COHR":  [366.0, None, None],
    "LITE":  [879.0, None, None],
    "AEHR":  [90.0,  None, None],
    "AAOI":  [174.5, None, None],
    "LWLG":  [12.7,  None, None],
    "POET":  [13.6,  None, None],
    "PLTR":  [120.0, None, None],
    "ONDS":  [9.0,   None, None],
    "OSS":   [15.6,  None, None],
    "SIMO":  [237.0, None, None],
    "SNDK":  [1355.0,None, None],
    "MRAM":  [29.0,  None, None],
    "IONQ":  [59.7,  None, None],
    "RGTI":  [26.4,  None, None],
    "QBTS":  [26.6,  None, None],
    "BE":    [274.0, None, None],
    "AMPX":  [15.3,  None, None],
}

# ============================================================
# 🔑 Google Sheets Auth
# ============================================================

_token_cache = {"token": "", "expires": 0}

def get_access_token() -> str:
    creds = json.loads(GOOGLE_CREDS_JSON)
    import base64
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend

    now = int(time.time())
    header  = base64.urlsafe_b64encode(json.dumps({"alg":"RS256","typ":"JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "iss": creds["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud": "https://oauth2.googleapis.com/token",
        "exp": now + 3600,
        "iat": now,
    }).encode()).rstrip(b"=")

    private_key = serialization.load_pem_private_key(
        creds["private_key"].encode(), password=None, backend=default_backend()
    )
    signing_input = header + b"." + payload
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")
    jwt_token = (signing_input + b"." + sig_b64).decode()

    r = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_token,
    }, timeout=10)
    token = r.json().get("access_token")
    status["sheet_ok"] = bool(token)
    return token


def sheets_token() -> str:
    if time.time() > _token_cache["expires"] - 60:
        _token_cache["token"]   = get_access_token()
        _token_cache["expires"] = time.time() + 3600
    return _token_cache["token"]

# ============================================================
# 📊 Google Sheet CRUD
# watchlist = {TICKER: [S1, S2, S3]}  (None = ไม่มีแนวรับ)
# ============================================================

def sheet_read() -> dict:
    try:
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{SHEET_RANGE}"
        r   = requests.get(url, headers={"Authorization": f"Bearer {sheets_token()}"}, timeout=10)
        rows = r.json().get("values", [])
        wl = {}
        for row in rows:
            if not row or row[0].strip().upper() in ("TICKER", ""):
                continue
            ticker = row[0].strip().upper().replace("$", "")
            levels = []
            for i in range(1, 4):
                try:
                    v = float(row[i]) if i < len(row) and row[i].strip() else None
                except (ValueError, IndexError):
                    v = None
                levels.append(v)
            wl[ticker] = levels

        if not wl:
            print("[Sheet] ว่าง → เขียน DEFAULT_WATCHLIST...")
            sheet_write(DEFAULT_WATCHLIST)
            return DEFAULT_WATCHLIST.copy()
        return wl
    except Exception as e:
        print(f"[Sheet] read ERROR: {e}")
        return DEFAULT_WATCHLIST.copy()


def sheet_write(watchlist: dict):
    try:
        token   = sheets_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Clear ก่อน
        requests.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{SHEET_RANGE}:clear",
            headers=headers, timeout=10
        )

        # เขียนใหม่
        values = [["TICKER", "S1", "S2", "S3"]]
        for ticker, levels in sorted(watchlist.items()):
            row = [ticker] + [str(v) if v is not None else "" for v in levels]
            values.append(row)

        r = requests.put(
            f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{SHEET_RANGE}?valueInputOption=RAW",
            headers=headers,
            json={"range": SHEET_RANGE, "majorDimension": "ROWS", "values": values},
            timeout=10
        )
        if r.status_code == 200:
            print(f"[Sheet] เขียน {len(watchlist)} รายการสำเร็จ")
        else:
            print(f"[Sheet] write WARNING: {r.status_code} {r.text}")
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


def get_price(ticker: str):
    """ดึงราคาปัจจุบันจาก Finnhub → คืน float หรือ None"""
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        data = r.json()
        price = data.get("c", 0)  # c = current price
        if price and price > 0:
            return float(price)
        return None
    except Exception as e:
        print(f"  [Finnhub] ${ticker} ERROR: {e}")
        return None


def thai_time_str() -> str:
    now = datetime.now(timezone.utc)
    th  = (now.hour + 7) % 24
    return f"{now.day:02d}/{now.month:02d}/{now.year} {th:02d}:{now.minute:02d} น."


def notify_near(ticker: str, price: float, support: float, level: int, pct: float):
    """แจ้งเตือน ใกล้แนวรับ"""
    send(
        f"🚨 <b>ใกล้แนวรับไม้ {level}!</b>\n"
        f"🕐 {thai_time_str()}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 <b>${ticker}</b>\n"
        f"💰 ราคาปัจจุบัน: <b>${price:.2f}</b>\n"
        f"🎯 แนวรับ S{level}: ${support:.2f}\n"
        f"📉 ห่างแนวรับอีก <b>{pct:.2f}%</b>"
    )
    print(f"🚨 ใกล้ S{level} ${ticker} ราคา={price:.2f} S{level}={support:.2f} ({pct:+.2f}%)")


def notify_break(ticker: str, price: float, support: float, level: int, pct: float):
    """แจ้งเตือน ทะลุแนวรับ"""
    is_last = level == 3
    extra   = "\n⚠️ <b>หมดแนวรับทั้ง 3 ไม้แล้ว!</b>" if is_last else ""
    send(
        f"🔴 <b>ทะลุแนวรับไม้ {level}!</b>\n"
        f"🕐 {thai_time_str()}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 <b>${ticker}</b>\n"
        f"💰 ราคาปัจจุบัน: <b>${price:.2f}</b>\n"
        f"🎯 แนวรับ S{level}: ${support:.2f}\n"
        f"📉 ต่ำกว่าแนวรับ <b>{abs(pct):.2f}%</b>{extra}"
    )
    print(f"🔴 ทะลุ S{level} ${ticker} ราคา={price:.2f} S{level}={support:.2f} ({pct:+.2f}%)")

# ============================================================
# 🤖 Commands
# ============================================================

HELP_TEXT = """
📖 <b>คำสั่งที่ใช้ได้</b>
━━━━━━━━━━━━━━━
➕ <b>เพิ่ม / แก้แนวรับ:</b>
<code>/add TICKER S1</code>
<code>/add TICKER S1 S2</code>
<code>/add TICKER S1 S2 S3</code>
เช่น: <code>/add NVDA 194 185 170</code>

🗑 <b>ลบหุ้น:</b>
<code>/remove TICKER</code>

📋 <b>ดูรายการทั้งหมด:</b>
<code>/list</code>

🔍 <b>เช็คราคาทันที:</b>
<code>/check</code>

📡 <b>เช็คสถานะ bot:</b>
<code>/status</code>

❓ <b>ดูคำสั่ง:</b>
<code>/help</code>
"""


def handle_command(text: str, watchlist: dict, alerted: dict) -> dict:
    parts = text.strip().split()
    cmd   = parts[0].lower()

    if cmd == "/help":
        send(HELP_TEXT)

    elif cmd == "/add":
        if len(parts) < 3:
            send("❌ ต้องใส่อย่างน้อย S1\nเช่น: <code>/add NVDA 194 185 170</code>")
        else:
            ticker = parts[1].upper().replace("$", "")
            try:
                levels = []
                for i in range(2, 5):
                    if i < len(parts) and parts[i]:
                        levels.append(float(parts[i]))
                    else:
                        levels.append(None)
                is_update = ticker in watchlist
                watchlist[ticker] = levels
                # reset alerted ทุก level
                for lvl in range(1, 4):
                    alerted[f"{ticker}_S{lvl}_near"]  = False
                    alerted[f"{ticker}_S{lvl}_break"] = False
                sheet_write(watchlist)
                action = "✏️ อัปเดต" if is_update else "✅ เพิ่ม"
                s_str  = " | ".join([f"S{i+1}=${v:.2f}" for i, v in enumerate(levels) if v is not None])
                send(f"{action} <b>${ticker}</b>\n{s_str}\nบันทึกลง Google Sheet แล้วครับ!")
            except ValueError:
                send("❌ ราคาต้องเป็นตัวเลข เช่น <code>/add NVDA 194 185 170</code>")

    elif cmd == "/remove":
        if len(parts) != 2:
            send("❌ รูปแบบผิด ใช้: <code>/remove TICKER</code>")
        else:
            ticker = parts[1].upper().replace("$", "")
            if ticker in watchlist:
                del watchlist[ticker]
                for lvl in range(1, 4):
                    alerted.pop(f"{ticker}_S{lvl}_near",  None)
                    alerted.pop(f"{ticker}_S{lvl}_break", None)
                sheet_write(watchlist)
                send(f"🗑 ลบ <b>${ticker}</b> ออกจาก Watchlist แล้วครับ!")
            else:
                send(f"⚠️ ไม่พบ <b>${ticker}</b> ใน Watchlist")

    elif cmd == "/list":
        if not watchlist:
            send("📋 Watchlist ว่างอยู่ครับ ใช้ /add เพื่อเพิ่มหุ้น")
        else:
            lines = [f"📋 <b>Watchlist ({len(watchlist)} ตัว)</b>", "━━━━━━━━━━━━━━━"]
            for t, levels in sorted(watchlist.items()):
                s_parts = [f"S{i+1}=${v:.2f}" for i, v in enumerate(levels) if v is not None]
                lines.append(f"📌 <b>${t}</b>  {' | '.join(s_parts)}")
            lines.append(f"\n🎯 แจ้งเมื่อห่าง ≤ {THRESHOLD_PCT}%")
            send("\n".join(lines))

    elif cmd == "/check":
        # /check → เช็คทั้งหมด
        # /check NVDA TSLA → เช็คเฉพาะที่ระบุ
        if len(parts) == 1:
            send("🔍 กำลังเช็คราคาทั้งหมด รอแป๊บนึงครับ...")
            check_and_report(watchlist)
        else:
            custom = [p.upper().replace("$","") for p in parts[1:]]
            send(f"🔍 กำลังเช็ค {', '.join(['$'+t for t in custom])} รอแป๊บนึงครับ...")
            check_and_report(watchlist, custom_tickers=custom)

    elif cmd == "/status":
        now    = datetime.now(timezone.utc)
        uptime = now - BOT_START_TIME
        hours, rem = divmod(int(uptime.total_seconds()), 3600)
        minutes = rem // 60

        if status["last_check"]:
            diff = int((now - status["last_check"]).total_seconds())
            last_str = f"{diff} วินาทีที่แล้ว" if diff < 60 else f"{diff//60} นาทีที่แล้ว"
        else:
            last_str = "ยังไม่ได้เช็ค"

        market_str = "🟢 เปิดอยู่" if is_market_open() else "🔴 ปิดอยู่"
        data_str   = "✅ OK" if status["data_ok"] else "❌ Error"
        sheet_str  = "✅ OK" if status["sheet_ok"]   else "❌ Error"

        send(
            f"📡 <b>Bot Status</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"✅ Bot Online\n"
            f"⏱ Uptime: {hours} ชั่วโมง {minutes} นาที\n"
            f"🕐 เวลาไทย: {thai_time_str()}\n\n"
            f"📊 <b>รอบล่าสุด</b>\n"
            f"🔄 เช็คล่าสุด: {last_str}\n"
            f"📈 ราคาที่ดึงได้: {status['last_ok_count']}/{status['last_total']} ตัว\n"
            f"🚨 แจ้งเตือนวันนี้: {status['alert_today']} ครั้ง\n\n"
            f"🌐 <b>API Status</b>\n"
            f"  Finnhub: {data_str}\n"
            f"  Google Sheet: {sheet_str}\n"
            f"  Telegram: ✅ OK\n\n"
            f"🕰 ตลาด US: {market_str}"
        )

    else:
        send(f"❓ ไม่รู้จักคำสั่ง <code>{cmd}</code>\nพิมพ์ /help เพื่อดูคำสั่งทั้งหมด")

    return watchlist


def check_and_report(watchlist: dict, custom_tickers: list = None):
    if not watchlist:
        send("📋 Watchlist ว่างอยู่ครับ")
        return
    # ถ้ามี custom_tickers ให้เช็คเฉพาะตัวที่ระบุ (รวมตัวที่ไม่อยู่ใน watchlist ด้วย)
    if custom_tickers:
        tickers = custom_tickers
    else:
        tickers = list(watchlist.keys())
    try:
        prices = {}
        for t in tickers:
            p = get_price(t)
            if p is not None:
                prices[t] = p
            time.sleep(1.1)
        if not prices:
            send("⚠️ ดึงข้อมูลไม่ได้ (เช็ค API key หรือชื่อหุ้น)")
            return
    except Exception as e:
        send(f"❌ Error: {e}")
        return

    lines = ["📊 <b>ราคาล่าสุด</b>", "━━━━━━━━━━━━━━━"]
    for ticker in sorted(tickers):
        try:
            price = prices.get(ticker, float("nan"))
            if price != price:
                raise ValueError("NaN")
            levels = watchlist.get(ticker, [None, None, None])
            valid  = [v for v in levels if v is not None]
            if not valid:
                lines.append(f"📌 <b>${ticker}</b>  ${price:.2f}  (ไม่มีแนวรับใน watchlist)")
            else:
                s_parts = []
                for i, v in enumerate(levels):
                    if v is None:
                        continue
                    pct  = (price - v) / v * 100
                    icon = "⚠️" if abs(pct) <= THRESHOLD_PCT else ("🔴" if pct < 0 else "✅")
                    s_parts.append(f"S{i+1}={icon}${v:.2f}({pct:+.1f}%)")
                lines.append(f"📌 <b>${ticker}</b>  ${price:.2f}\n    {' | '.join(s_parts)}")
        except Exception:
            lines.append(f"❓ ${ticker} — ไม่มีข้อมูล")
    send("\n".join(lines))

# ============================================================
# 📥 Polling
# ============================================================

last_update_id = 0

def poll_commands(watchlist_ref: list, alerted_ref: list):
    global last_update_id
    print("[Polling] เริ่มรับคำสั่ง...")
    while True:
        try:
            r = requests.get(
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

# ============================================================
# 🔍 Price Loop
# ============================================================

def is_market_open() -> bool:
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    h = now.hour + now.minute / 60
    return 14.5 <= h <= 21.0


def check_prices(watchlist: dict, alerted: dict):
    tickers = list(watchlist.keys())
    if not tickers:
        return

    try:
        status["last_check"] = datetime.now(timezone.utc)

        # reset daily counter
        today = datetime.now(timezone.utc).date()
        if today != status["last_alert_reset"]:
            status["alert_today"]      = 0
            status["last_alert_reset"] = today

        # ดึงราคาจาก Finnhub ทีละตัว (60 calls/นาที = 1 ตัว/วินาที)
        all_prices = {}
        for t in tickers:
            p = get_price(t)
            if p is not None:
                all_prices[t] = p
                print(f"  ✅ ${t} = ${p:.2f}")
            else:
                print(f"  ❌ ${t} ไม่มีข้อมูล")
            time.sleep(1.1)  # ปลอดภัยใต้ 60/นาที

        if not all_prices:
            print("  ⚠️ ไม่ได้ข้อมูลเลย")
            return

        prices = all_prices
        ok_count = 0
        status["last_total"] = len(tickers)

        for ticker, levels in watchlist.items():
            try:
                price = float(prices.get(ticker, float("nan")))
                if price != price:
                    raise ValueError("NaN")
                ok_count += 1

                for i, support in enumerate(levels):
                    if support is None:
                        continue
                    lvl      = i + 1
                    pct      = (price - support) / support * 100
                    key_near  = f"{ticker}_S{lvl}_near"
                    key_break = f"{ticker}_S{lvl}_break"

                    # ใกล้แนวรับ (0 ถึง THRESHOLD_PCT%)
                    if 0 <= pct <= THRESHOLD_PCT:
                        if not alerted.get(key_near, False):
                            notify_near(ticker, price, support, lvl, pct)
                            alerted[key_near] = True
                            status["alert_today"] += 1

                    # ทะลุแนวรับ (ต่ำกว่า 0)
                    elif pct < 0:
                        if not alerted.get(key_break, False):
                            notify_break(ticker, price, support, lvl, pct)
                            alerted[key_break] = True
                            status["alert_today"] += 1

                    # ราคาขึ้นพ้น 3% → reset
                    elif pct > 3.0:
                        alerted[key_near]  = False
                        alerted[key_break] = False

                    icon = "⚠️" if 0 <= pct <= THRESHOLD_PCT else ("🔴" if pct < 0 else "✅")
                    print(f"  {icon} ${ticker:6s} S{lvl}={support:.2f}  ราคา={price:.2f}  ({pct:+.2f}%)")

            except Exception:
                print(f"  ❓ ${ticker} — ข้ามไป")

        status["last_ok_count"] = ok_count
        status["data_ok"]   = True

    except Exception as e:
        status["data_ok"] = False
        print(f"  [data] ERROR: {e}")


def price_loop(watchlist_ref: list, alerted_ref: list):
    while True:
        watchlist_ref[0] = sheet_read()
        watchlist = watchlist_ref[0]
        alerted   = alerted_ref[0]

        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        print(f"\n[{now_str}] เช็ค {len(watchlist)} ตัว...")
        check_prices(watchlist, alerted)

        # สรุปเช้า 08:00 น. ไทย = 01:00 UTC
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour == 1 and now_utc.minute < 2:
            send(
                f"🌅 <b>สรุปเช้าวันนี้</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📊 ติดตาม {len(watchlist)} หุ้น\n"
                f"🚨 แจ้งเตือนเมื่อวาน: {status['alert_today']} ครั้ง\n"
                f"🕰 ตลาด US เปิด: 21:30 น. คืนนี้\n"
                f"💡 พิมพ์ /status เพื่อดูสถานะ"
            )

        sleep = CHECK_INTERVAL if is_market_open() else 600
        if not is_market_open():
            print("  💤 ตลาดปิด รอ 10 นาที")
        time.sleep(sleep)

# ============================================================
# 🚀 Main
# ============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("  📡 Stock Alert Bot v4 — 3 Support Levels")
    print(f"  เช็คทุก {CHECK_INTERVAL}s | threshold ≤{THRESHOLD_PCT}%")
    print("=" * 55)

    wl = sheet_read()
    al = {}
    watchlist_ref = [wl]
    alerted_ref   = [al]

    threading.Thread(target=poll_commands, args=(watchlist_ref, alerted_ref), daemon=True).start()

    send(
        f"✅ <b>Stock Alert Bot v4 เริ่มทำงานแล้ว!</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 โหลด <b>{len(wl)} หุ้น</b> จาก Google Sheet\n"
        f"🎯 แนวรับ 3 ไม้ต่อหุ้น (S1, S2, S3)\n"
        f"⏱ เช็คทุก <b>{CHECK_INTERVAL} วินาที</b>\n\n"
        f"พิมพ์ /help เพื่อดูคำสั่งทั้งหมด"
    )

    price_loop(watchlist_ref, alerted_ref)
