import os
import time
import json
import re
import concurrent.futures
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, date, time as dtime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
import requests
import yfinance as yf

# Environment Variables (Securely pulled from GitHub Secrets)
DISCORD_NEWS_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_PRICE_WEBHOOK_URL = os.getenv("DISCORD_PRICE_WEBHOOK_URL")

# Bot Branding & Avatars
BOT_NAME = "Looney"
BOT_PRICE_AVATAR_URL = "https://cdn.discordapp.com/attachments/1536082016184045750/1539150514313498634/IMG_6633.png?ex=6a85451e&is=6a83f39e&hm=c973d5a79654c66b306b4d8296fdc5b1b8ca8ce0c97e3f7693c111809acf5cb1&"
BOT_NEWS_AVATAR_URL = "https://cdn.discordapp.com/attachments/1536082016184045750/1539077205437714442/IMG_6630.jpg?ex=6a8500d8&is=6a83af58&hm=f46d7b936827c9651de6bafe607af3e23c40009ee9799431f622886c85c78013&"

STATE_FILE = "alerts_state.json"
NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

MAX_NEWS_AGE_MINUTES = 45

# Watchlists
CRYPTO_WATCHLIST = [
    "BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD", "LINK-USD"
]

STOCK_ETF_WATCHLIST = [
    "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "NQ=F", "ES=F", "YM=F", "RTY=F",
    "USO", "BNO", "GLD", "SLV", "IBIT", "ETHA", "MSTR", "IREN",
    "BLSH", "NVDA", "AMD", "MU", "SNDK", "INTC", "AVGO", "ASML",
    "CBRS", "SKHY", "IBM", "TSLA", "SPCX", "RKLB", "PLTR", "META",
    "NBIS", "ORCL", "RBLX"
]

ALL_TICKERS = CRYPTO_WATCHLIST + STOCK_ETF_WATCHLIST

# ====================================================================
# 1. NYSE & TSX MARKET HOLIDAY & EARLY CLOSE ENGINE
# ====================================================================
def calculate_easter(year):
    """Calculates Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)

def _get_year_holidays(year):
    """Generates precise NYSE (US) and TSX (Canada) full-day holiday schedules."""
    us_hols = {}
    ca_hols = {}

    easter = calculate_easter(year)
    good_friday = easter - timedelta(days=2)

    # 1. New Year's Day (Jan 1)
    ny_day = date(year, 1, 1)
    if ny_day.weekday() == 6:
        us_hols[date(year, 1, 2)] = "New Year's Day"
        ca_hols[date(year, 1, 2)] = "New Year's Day"
    elif ny_day.weekday() == 5:
        ca_hols[date(year, 1, 3)] = "New Year's Day"
    else:
        us_hols[ny_day] = "New Year's Day"
        ca_hols[ny_day] = "New Year's Day"

    # 2. MLK Day (US: 3rd Monday in Jan, 1998+)
    if year >= 1998:
        mlk = date(year, 1, 1) + timedelta(days=(0 - date(year, 1, 1).weekday() + 7) % 7 + 14)
        us_hols[mlk] = "Martin Luther King Jr. Day"

    # 3. Presidents' Day (US: 3rd Mon in Feb) / Family Day (TSX: 2008+)
    pres = date(year, 2, 1) + timedelta(days=(0 - date(year, 2, 1).weekday() + 7) % 7 + 14)
    us_hols[pres] = "Presidents' Day"
    if year >= 2008:
        ca_hols[pres] = "Family Day"

    # 4. Good Friday
    us_hols[good_friday] = "Good Friday"
    ca_hols[good_friday] = "Good Friday"

    # 5. Victoria Day (Canada: Monday before May 25)
    may_24 = date(year, 5, 24)
    vic = may_24 - timedelta(days=(may_24.weekday() - 0) % 7)
    ca_hols[vic] = "Victoria Day"

    # 6. Memorial Day (US: Last Monday in May)
    may_31 = date(year, 5, 31)
    mem = may_31 - timedelta(days=(may_31.weekday() - 0) % 7)
    us_hols[mem] = "Memorial Day"

    # 7. Juneteenth (US: June 19, 2022+)
    if year >= 2022:
        june_19 = date(year, 6, 19)
        if june_19.weekday() == 6:
            us_hols[date(year, 6, 20)] = "Juneteenth"
        elif june_19.weekday() == 5:
            us_hols[date(year, 6, 18)] = "Juneteenth"
        else:
            us_hols[june_19] = "Juneteenth"

    # 8. Canada Day (Canada: July 1)
    cad = date(year, 7, 1)
    if cad.weekday() == 6:
        ca_hols[date(year, 7, 2)] = "Canada Day"
    elif cad.weekday() == 5:
        ca_hols[date(year, 7, 3)] = "Canada Day"
    else:
        ca_hols[cad] = "Canada Day"

    # 9. Independence Day (US: July 4)
    july_4 = date(year, 7, 4)
    if july_4.weekday() == 6:
        us_hols[date(year, 7, 5)] = "Independence Day"
    elif july_4.weekday() == 5:
        us_hols[date(year, 7, 3)] = "Independence Day"
    else:
        us_hols[july_4] = "Independence Day"

    # 10. Civic Holiday (Canada: 1st Monday in Aug)
    civic = date(year, 8, 1) + timedelta(days=(0 - date(year, 8, 1).weekday() + 7) % 7)
    ca_hols[civic] = "Civic Holiday"

    # 11. Labor Day (US & Canada: 1st Monday in Sept)
    labor = date(year, 9, 1) + timedelta(days=(0 - date(year, 9, 1).weekday() + 7) % 7)
    us_hols[labor] = "Labor Day"
    ca_hols[labor] = "Labour Day"

    # 12. Thanksgiving (Canada: 2nd Monday in Oct)
    ca_thanks = date(year, 10, 1) + timedelta(days=(0 - date(year, 10, 1).weekday() + 7) % 7 + 7)
    ca_hols[ca_thanks] = "Thanksgiving (Canada)"

    # 13. Thanksgiving (US: 4th Thursday in Nov)
    us_thanks = date(year, 11, 1) + timedelta(days=(3 - date(year, 11, 1).weekday() + 7) % 7 + 21)
    us_hols[us_thanks] = "Thanksgiving Day"

    # 14 & 15. Christmas & Boxing Day
    xmas = date(year, 12, 25)
    boxing = date(year, 12, 26)

    if xmas.weekday() == 6:
        us_hols[date(year, 12, 26)] = "Christmas Day"
    elif xmas.weekday() == 5:
        us_hols[date(year, 12, 24)] = "Christmas Day"
    else:
        us_hols[xmas] = "Christmas Day"

    if xmas.weekday() == 4:
        ca_hols[date(year, 12, 25)] = "Christmas Day"
        ca_hols[date(year, 12, 28)] = "Boxing Day"
    elif xmas.weekday() == 5:
        ca_hols[date(year, 12, 27)] = "Christmas Day"
        ca_hols[date(year, 12, 28)] = "Boxing Day"
    elif xmas.weekday() == 6:
        ca_hols[date(year, 12, 26)] = "Christmas Day"
        ca_hols[date(year, 12, 27)] = "Boxing Day"
    else:
        ca_hols[xmas] = "Christmas Day"
        if boxing.weekday() == 6:
            ca_hols[date(year, 12, 27)] = "Boxing Day"
        else:
            ca_hols[boxing] = "Boxing Day"

    return us_hols, ca_hols

def check_market_holiday(target_date):
    """Checks full-day closures across a multi-year window."""
    all_us = {}
    all_ca = {}
    for y in [target_date.year - 1, target_date.year, target_date.year + 1]:
        u, c = _get_year_holidays(y)
        all_us.update(u)
        all_ca.update(c)
    return all_us.get(target_date), all_ca.get(target_date)

def check_early_close(target_date):
    """
    Detects 1:00 PM EST Early Market Close Days:
    1. July 3rd (Day before July 4, if July 4 is Tue-Fri)
    2. Black Friday (Day after Thanksgiving)
    3. Christmas Eve (Dec 24, if on Monday-Friday)
    """
    year = target_date.year

    # 1. July 3rd
    if target_date.month == 7 and target_date.day == 3 and target_date.weekday() < 5:
        july_4 = date(year, 7, 4)
        if july_4.weekday() in (1, 2, 3, 4):  # Tue, Wed, Thu, Fri
            return True, "Independence Day Eve (1:00 PM Close)"

    # 2. Black Friday
    us_thanks = date(year, 11, 1) + timedelta(days=(3 - date(year, 11, 1).weekday() + 7) % 7 + 21)
    black_friday = us_thanks + timedelta(days=1)
    if target_date == black_friday:
        return True, "Black Friday (1:00 PM Close)"

    # 3. Christmas Eve
    if target_date.month == 12 and target_date.day == 24 and target_date.weekday() < 5:
        return True, "Christmas Eve (1:00 PM Close)"

    return False, None

# ====================================================================
# 2. SESSION TIMING & DYNAMIC EARLY-CLOSE CLASSIFIER
# ====================================================================
def get_current_session_info(now_ny, is_early_close):
    """
    Dynamically adjusts Regular and After-Hours cutoffs on Early Close Days:
    - Normal Day: Regular (9:30 AM - 4:00 PM), After-Hours (4:00 PM - 8:00 PM)
    - Early Close: Regular (9:30 AM - 1:00 PM), After-Hours (1:00 PM - 5:00 PM)
    """
    if now_ny.weekday() > 4:
        return "CLOSED", 0.0, "[CLOSED]"

    t = now_ny.time()
    reg_close = dtime(13, 0) if is_early_close else dtime(16, 0)
    ah_end = dtime(17, 0) if is_early_close else dtime(20, 0)

    if dtime(4, 0) <= t < dtime(9, 30):
        return "PRE_MARKET", 1.0, "[PRE-MARKET]"
    elif dtime(9, 30) <= t < reg_close:
        return "REGULAR", 2.0, "[REGULAR]"
    elif reg_close <= t <= ah_end:
        return "AFTER_HOURS", 1.0, "[AFTER-HOURS]"
    else:
        return "CLOSED", 0.0, "[CLOSED]"

def normalize_title(title_text):
    if not title_text:
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', title_text).lower()

# ====================================================================
# 3. STATE MEMORY & PERSISTENCE
# ====================================================================
def load_alert_state():
    now_ny = datetime.now(NY_TZ)
    today_ny_str = now_ny.strftime("%Y-%m-%d")
    today_utc_str = datetime.now(UTC_TZ).strftime("%Y-%m-%d")

    state = {
        "stock_session_date": today_ny_str,
        "crypto_session_date": today_utc_str,
        "premarket_tickers": {},
        "regular_tickers": {},
        "afterhours_tickers": {},
        "crypto_tickers": {},
        "holiday_announced_date": None,
        "seen_news_fingerprints": []
    }

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                
                if saved.get("stock_session_date") == today_ny_str:
                    state["premarket_tickers"] = saved.get("premarket_tickers", {})
                    state["regular_tickers"] = saved.get("regular_tickers", {})
                    state["afterhours_tickers"] = saved.get("afterhours_tickers", {})
                    state["holiday_announced_date"] = saved.get("holiday_announced_date")
                else:
                    print(f"📅 New Stock Calendar Day ({today_ny_str}). Resetting stock memory slots.")

                if saved.get("crypto_session_date") == today_utc_str:
                    state["crypto_tickers"] = saved.get("crypto_tickers", {})
                else:
                    print(f"🪙 New Crypto 24h Session ({today_utc_str}). Resetting crypto memory.")
                
                state["seen_news_fingerprints"] = saved.get("seen_news_fingerprints") or saved.get("seen_news_links", [])
        except Exception as e:
            print(f"Error loading state file: {e}")

    return state

def save_alert_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        total_p = (len(state["premarket_tickers"]) + len(state["regular_tickers"]) + 
                   len(state["afterhours_tickers"]) + len(state["crypto_tickers"]))
        print(f"State saved ({total_p} active price benchmarks, {len(state['seen_news_fingerprints'])} news fingerprints).")
    except Exception as e:
        print(f"Error saving state file: {e}")

# ====================================================================
# 4. DISCORD WEBHOOK DISPATCHERS
# ====================================================================
def send_discord_price_alert(ticker, current_price, change_pct, session_badge, step_change=None, history_trail=None, benchmark_desc="today"):
    if not DISCORD_PRICE_WEBHOOK_URL:
        print(f"Skipping price alert for {ticker}: DISCORD_PRICE_WEBHOOK_URL not configured.")
        return

    title_text = f"🚨 Market Alert: {ticker} {session_badge}"
    desc_text = f"**{ticker}** moved **{change_pct:+.2f}%** {benchmark_desc}!"
    if step_change is not None:
        desc_text = f"**{ticker}** moved **{step_change:+.2f}%** since last alert! (Total {session_badge}: **{change_pct:+.2f}%**)"

    fields = [
        {"name": "Current Price", "value": f"${current_price:.2f}", "inline": True},
        {"name": f"{session_badge} Change", "value": f"{change_pct:+.2f}%", "inline": True}
    ]

    if history_trail and len(history_trail) > 0:
        trail_str = " ➔ ".join(history_trail)
        fields.append({
            "name": f"🕒 Today's {session_badge} Path",
            "value": f"`{trail_str}` ➔ **{change_pct:+.2f}%**",
            "inline": False
        })

    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_PRICE_AVATAR_URL,
        "embeds": [{
            "title": title_text,
            "description": desc_text,
            "color": 15158332 if change_pct < 0 else 3066993,
            "fields": fields,
            "footer": {"text": f"{BOT_NAME} • 24/7 Price Action Channel"}
        }]
    }
    try:
        res = requests.post(DISCORD_PRICE_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"Error sending price alert for {ticker}: {e}")

def send_discord_holiday_announcement(us_name, ca_name):
    if not DISCORD_PRICE_WEBHOOK_URL:
        return

    if us_name and ca_name:
        headline = f"US & Canadian Stock Markets are CLOSED today for {us_name} / {ca_name}!"
    elif us_name:
        headline = f"US Stock Markets (NYSE / NASDAQ) are CLOSED today for {us_name}!"
    else:
        headline = f"Canadian Stock Market (TSX) is CLOSED today for {ca_name}!"

    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_PRICE_AVATAR_URL,
        "embeds": [{
            "title": "🏛️ Market Notice: Exchange Holiday",
            "description": f"**{headline}**\n\n• 📈 **Stocks & ETFs:** Paused for the holiday session.\n• 🪙 **Crypto Watcher:** Active 24/7.\n• 📰 **Breaking News:** Active 24/7.",
            "color": 15844367,
            "footer": {"text": f"{BOT_NAME} • Market Holiday Engine"}
        }]
    }
    try:
        res = requests.post(DISCORD_PRICE_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        print(f"📢 Holiday announcement sent to Discord: {headline}")
    except Exception as e:
        print(f"Error sending holiday announcement: {e}")

def send_discord_news_alert(article):
    if not DISCORD_NEWS_WEBHOOK_URL:
        return

    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_NEWS_AVATAR_URL,
        "embeds": [{
            "title": f"📰 Breaking News: {article['ticker']}",
            "description": f"**[{article['title']}]({article['link']})**",
            "color": 3447003,
            "fields": [
                {"name": "Publisher", "value": article["publisher"], "inline": True},
                {"name": "Published (ET)", "value": article["time_str"], "inline": True}
            ],
            "footer": {"text": f"{BOT_NAME} • 24/7 Breaking News Channel"}
        }]
    }
    try:
        res = requests.post(DISCORD_NEWS_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"Error sending news alert: {e}")

# ====================================================================
# 5. DATA EXTRACTION ENGINE (Extended Hours & Realtime Live)
# ====================================================================
def get_extended_stock_data(ticker_symbol, session_type, session_http):
    current_price = None
    baseline_price = None

    try:
        ticker = yf.Ticker(ticker_symbol, session=session_http)
        fi = ticker.fast_info

        if session_type == "CRYPTO":
            current_price = fi.last_price
            baseline_price = fi.previous_close

        elif session_type in ("PRE_MARKET", "REGULAR"):
            current_price = fi.last_price
            baseline_price = fi.previous_close

        elif session_type == "AFTER_HOURS":
            # Compare live after-hours price against the regular closing price (1 PM on early close, 4 PM normal)
            current_price = fi.last_price
            try:
                hist = ticker.history(period="2d")
                if 'Close' in hist.columns and len(hist['Close']) >= 1:
                    baseline_price = float(hist['Close'].iloc[-1])
            except Exception:
                pass
            
            if baseline_price is None:
                baseline_price = fi.previous_close

    except Exception:
        pass

    return current_price, baseline_price

# --- NEWS FETCHING WITH TIME PARSING ---
def fetch_ticker_news_search(symbol, session):
    news_items = []
    try:
        ts_ms = int(time.time() * 1000)
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={symbol}&newsCount=3&listsCount=0&_={ts_ms}"
        res = session.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("news", [])[:3]:
                content = item.get("content") if isinstance(item.get("content"), dict) else {}
                title = item.get("title") or content.get("title")
                link = item.get("link") or content.get("canonicalUrl", {}).get("url")
                provider = item.get("publisher") or content.get("provider", {}).get("displayName") or "Yahoo Finance"
                raw_time = item.get("providerPublishTime") or content.get("pubDate") or item.get("pubDate")

                pub_dt = None
                time_str = "N/A"
                if isinstance(raw_time, (int, float)):
                    if raw_time > 1e11:
                        raw_time = raw_time / 1000.0
                    pub_dt = datetime.fromtimestamp(raw_time, tz=NY_TZ)
                    time_str = pub_dt.strftime("%a %I:%M %p")
                elif isinstance(raw_time, str):
                    try:
                        pub_dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00")).astimezone(NY_TZ)
                        time_str = pub_dt.strftime("%a %I:%M %p")
                    except Exception:
                        pass

                if title and link and pub_dt:
                    news_items.append({
                        "ticker": symbol,
                        "title": title.strip(),
                        "link": link.strip(),
                        "publisher": provider,
                        "pub_dt": pub_dt,
                        "time_str": time_str
                    })
    except Exception:
        pass
    return news_items

def fetch_ticker_news_rss(symbol, session):
    news_items = []
    try:
        ts = int(time.time())
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&_={ts}"
        res = session.get(url, timeout=5)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:3]:
                title = item.findtext("title")
                link = item.findtext("link")
                pub_date_str = item.findtext("pubDate")

                pub_dt = None
                time_str = "N/A"
                if pub_date_str:
                    try:
                        pub_dt = parsedate_to_datetime(pub_date_str).astimezone(NY_TZ)
                        time_str = pub_dt.strftime("%a %I:%M %p")
                    except Exception:
                        pass

                if title and link and pub_dt:
                    news_items.append({
                        "ticker": symbol,
                        "title": title.strip(),
                        "link": link.strip(),
                        "publisher": "Yahoo Wire",
                        "pub_dt": pub_dt,
                        "time_str": time_str
                    })
    except Exception:
        pass
    return news_items

# ====================================================================
# 6. MAIN EXECUTION CONTROLLER
# ====================================================================
def check_market():
    now_ny = datetime.now(NY_TZ)
    today_ny_date = now_ny.date()
    today_ny_str = now_ny.strftime("%Y-%m-%d")

    # 1. FULL-DAY HOLIDAY & EARLY-CLOSE CHECKS
    us_hol, ca_hol = check_market_holiday(today_ny_date)
    is_stock_holiday = bool(us_hol)
    is_early_close, early_close_reason = check_early_close(today_ny_date)

    state = load_alert_state()

    # Announce full holiday on morning's first run
    if is_stock_holiday and state.get("holiday_announced_date") != today_ny_str:
        send_discord_holiday_announcement(us_hol, ca_hol)
        state["holiday_announced_date"] = today_ny_str

    # 2. 9:30 AM OPENING PAUSE
    if not is_stock_holiday and now_ny.weekday() <= 4 and dtime(9, 30) <= now_ny.time() < dtime(9, 32):
        target_time = now_ny.replace(hour=9, minute=32, second=0, microsecond=0)
        sleep_seconds = max(0, (target_time - now_ny).total_seconds())
        if sleep_seconds > 0:
            print(f"⏳ Market opening bell ({now_ny.strftime('%I:%M:%S %p')}). Waiting {int(sleep_seconds)}s until 9:32 AM for opening cross...")
            time.sleep(sleep_seconds)
            now_ny = datetime.now(NY_TZ)

    session_type, threshold_pct, session_badge = get_current_session_info(now_ny, is_early_close)
    now_ny_str = now_ny.strftime("%Y-%m-%d %I:%M %p %Z")

    print(f"Current Time (NY): {now_ny_str}")
    if is_stock_holiday:
        print(f"US Stock Market Status: 🏛️ CLOSED for Holiday ({us_hol}) - Crypto & News Active\n")
    elif is_early_close:
        print(f"US Stock Market Session: {session_badge} ⚠️ EARLY CLOSE DAY: {early_close_reason} (Threshold: ±{threshold_pct}%)\n")
    else:
        print(f"US Stock Market Session: {session_badge} (Threshold: ±{threshold_pct}%)\n")

    session_http = requests.Session()
    session_http.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    # ==========================================
    # 3. SCAN PRICES
    # ==========================================
    price_alerts_to_send = []
    active_watchlist = [(c, "CRYPTO", 2.0, "[CRYPTO]") for c in CRYPTO_WATCHLIST]
    
    if not is_stock_holiday and session_type != "CLOSED":
        for s in STOCK_ETF_WATCHLIST:
            active_watchlist.append((s, session_type, threshold_pct, session_badge))

    for ticker_symbol, s_type, req_threshold, badge in active_watchlist:
        try:
            current_price, baseline_price = get_extended_stock_data(ticker_symbol, s_type, session_http)

            if current_price is not None and baseline_price is not None and baseline_price > 0:
                change_pct = ((current_price - baseline_price) / baseline_price) * 100

                if s_type == "CRYPTO":
                    tracked_dict = state["crypto_tickers"]
                elif s_type == "PRE_MARKET":
                    tracked_dict = state["premarket_tickers"]
                elif s_type == "REGULAR":
                    tracked_dict = state["regular_tickers"]
                elif s_type == "AFTER_HOURS":
                    tracked_dict = state["afterhours_tickers"]
                else:
                    tracked_dict = {}

                # Case 1: Already alerted in this session -> Step check
                if ticker_symbol in tracked_dict:
                    item_data = tracked_dict[ticker_symbol]
                    last_alert_price = item_data["last_price"]
                    history_trail = item_data.get("history", [])

                    step_change_pct = ((current_price - last_alert_price) / last_alert_price) * 100

                    if abs(step_change_pct) >= req_threshold:
                        print(f"🔥 {ticker_symbol:10s} {badge} | STEP TRIGGER | Price: ${current_price:10.2f} | Step: {step_change_pct:+6.2f}%")
                        price_alerts_to_send.append({
                            "ticker": ticker_symbol,
                            "price": current_price,
                            "change_pct": change_pct,
                            "badge": badge,
                            "step_change": step_change_pct,
                            "history_trail": list(history_trail)
                        })
                        history_trail.append(f"{change_pct:+.2f}%")
                        tracked_dict[ticker_symbol] = {
                            "last_price": current_price,
                            "history": history_trail
                        }
                    else:
                        print(f"⏭️ {ticker_symbol:10s} {badge} | Price: ${current_price:10.2f} | Step: {step_change_pct:+6.2f}% (Below {req_threshold}%)")

                # Case 2: Initial alert for this session -> Threshold check
                else:
                    if abs(change_pct) >= req_threshold:
                        print(f"🚨 {ticker_symbol:10s} {badge} | INITIAL TRIGGER | Price: ${current_price:10.2f} | Change: {change_pct:+6.2f}%")
                        price_alerts_to_send.append({
                            "ticker": ticker_symbol,
                            "price": current_price,
                            "change_pct": change_pct,
                            "badge": badge,
                            "step_change": None,
                            "history_trail": []
                        })
                        tracked_dict[ticker_symbol] = {
                            "last_price": current_price,
                            "history": [f"{change_pct:+.2f}%"]
                        }
                    else:
                        print(f"✅ {ticker_symbol:10s} {badge} | Price: ${current_price:10.2f} | Change: {change_pct:+6.2f}%")
            else:
                print(f"⚠️ {ticker_symbol:10s} {badge} | SKIPPED: Insufficient realtime price data")
        except Exception as e:
            print(f"❌ Error checking {ticker_symbol}: {e}")
        time.sleep(0.12)

    # ==========================================
    # 4. SCAN BREAKING NEWS
    # ==========================================
    print("\nScanning breaking news across all tickers...")
    cutoff_time = now_ny - timedelta(minutes=MAX_NEWS_AGE_MINUTES)
    seen_fingerprints_set = set(state.get("seen_news_fingerprints", []))
    raw_news = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures_search = [executor.submit(fetch_ticker_news_search, sym, session_http) for sym in ALL_TICKERS]
        futures_rss = [executor.submit(fetch_ticker_news_rss, sym, session_http) for sym in ALL_TICKERS]

        for f in concurrent.futures.as_completed(futures_search + futures_rss):
            raw_news.extend(f.result())

    new_articles = []
    for item in raw_news:
        link = item["link"]
        pub_dt = item.get("pub_dt")
        title = item.get("title", "")

        date_stamp = pub_dt.strftime("%Y-%m-%d") if pub_dt else "nodate"
        norm_title = normalize_title(title)

        title_date_key = f"title_{norm_title}_{date_stamp}"
        link_key = f"link_{link}"

        if link_key in seen_fingerprints_set or (norm_title and title_date_key in seen_fingerprints_set):
            continue

        seen_fingerprints_set.add(link_key)
        seen_fingerprints_set.add(title_date_key)
        state["seen_news_fingerprints"].append(link_key)
        state["seen_news_fingerprints"].append(title_date_key)

        if pub_dt and pub_dt >= cutoff_time:
            new_articles.append(item)

    # ==========================================
    # 5. DISPATCH DISCORD ALERTS (0.5s Spacing)
    # ==========================================
    price_alerts_to_send.sort(key=lambda x: x["change_pct"], reverse=True)
    if price_alerts_to_send:
        print(f"\nSending {len(price_alerts_to_send)} price alert(s) to PRICE CHANNEL...")
        for alert in price_alerts_to_send:
            send_discord_price_alert(
                ticker=alert["ticker"],
                current_price=alert["price"],
                change_pct=alert["change_pct"],
                session_badge=alert["badge"],
                step_change=alert["step_change"],
                history_trail=alert["history_trail"]
            )
            time.sleep(0.5)

    if new_articles:
        print(f"\nSending ALL {len(new_articles)} fresh headline alert(s) to NEWS CHANNEL...")
        for article in new_articles:
            send_discord_news_alert(article)
            time.sleep(0.5)

    # ==========================================
    # 6. PERSIST STATE
    # ==========================================
    save_alert_state(state)
    print(f"\n=======================================================")
    print(f"Check Complete. Price Alerts Sent: {len(price_alerts_to_send)} | Fresh News Sent: {len(new_articles)}")

if __name__ == "__main__":
    check_market()
