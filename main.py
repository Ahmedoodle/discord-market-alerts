import os
import time
import json
import re
import math
import concurrent.futures
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, date, time as dtime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import yfinance as yf
import pandas as pd
from curl_cffi import requests as cureq

# ====================================================================
# ENVIRONMENT VARIABLES & WEBHOOKS (SANITIZED & FALLBACK RESILIENT)
# ====================================================================
def _clean_url(url_val):
    if not url_val:
        return None
    cleaned = str(url_val).strip().strip('"').strip("'")
    return cleaned if cleaned.startswith("http") else None

DISCORD_NEWS_WEBHOOK_URL = _clean_url(os.getenv("DISCORD_WEBHOOK_URL"))

DISCORD_PRICE_WEBHOOK_URL = (
    _clean_url(os.getenv("DISCORD_PRICE_WEBHOOK_URL"))
    or "https://discord.com/api/webhooks/1539395404502671440/HCuVM2hd2t7OV8r1DaLk46iTNz3xgD1Li_Mdt05RAU7m3W2ZTYLIaYKrQyMti81axOxV"
)

DISCORD_OPTIONS_WEBHOOK_URL = (
    _clean_url(os.getenv("DISCORD_OPTIONS_WEBHOOK_URL"))
    or "https://discord.com/api/webhooks/1540124383618666507/8OZ0nG5SznAaguH8-bd4V6-CN1VMqNKCXEfXhjIZrjxIZhyFudPs8UFZinkxqp6qdI6a"
)

BOT_NAME = "Looney"
BOT_AVATAR_URL = "https://cdn.discordapp.com/attachments/1536082016184045750/1539077205437714442/IMG_6630.jpg?ex=6a8500d8&is=6a83af58&hm=f46d7b936827c9651de6bafe607af3e23c40009ee9799431f622886c85c78013&"

STATE_FILE = "alerts_state.json"
NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

MAX_NEWS_AGE_MINUTES = 45

# ====================================================================
# WATCHLISTS & MARKET UNIVERSE CONFIGURATION
# ====================================================================
CRYPTO_WATCHLIST = [
    "BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD", "LINK-USD"
]

STOCK_ETF_WATCHLIST = [
    # --- Commodity & Index Futures (9) ---
    "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "NQ=F", "ES=F", "YM=F", "RTY=F",

    # --- Core Index, Commodity & Crypto ETFs (12) ---
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "GLD", "SLV", "USO", "BNO", "IBIT", "ETHA",

    # --- S&P 500 (SPY) Top 100 & Mega-Caps ---
    "MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "BRK-B", "LLY", "AVGO",
    "TSLA", "JPM", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST",
    "ABBV", "MRK", "NFLX", "BAC", "CRM", "CVX", "WMT", "AMD", "PEP", "KO",
    "LIN", "TMO", "ACN", "ADBE", "MCD", "DIS", "CSCO", "QCOM", "ORCL", "GE",
    "WFC", "INTU", "CAT", "IBM", "TXN", "AMAT", "VZ", "NOW", "DHR", "CMCSA",
    "PM", "ISRG", "COP", "AMGN", "UNP", "LOW", "NEE", "HON", "BKNG", "GS",
    "RTX", "SPGI", "T", "BLK", "ELV", "SYK", "PLTR", "MDLZ", "TJX", "BSX",
    "PGR", "DE", "VRTX", "SBUX", "AXP", "MMC", "BA", "PANW", "LRCX", "ETN",
    "ADP", "MU", "REGN", "LMT", "CB", "GILD", "ADI", "MDT", "CI", "SCHW",
    "CVS", "KLAC", "FI", "SNPS", "CDNS", "MO", "CRWD", "ICE", "ABNB", "WM",

    # --- Nasdaq 100 Additions & High-Beta Growth ---
    "TMUS", "MELI", "PYPL", "MAR", "CSX", "CTAS", "ORLY", "NXPI", "PCAR", "WBD",
    "MRVL", "ROP", "MCHP", "FTNT", "DXCM", "KDP", "MNST", "LULU", "KHC", "PAYX",
    "ROST", "IDXX", "ODFL", "EXC", "CHTR", "AEP", "FAST", "BIIB", "CPRT", "GEHC",
    "TEAM", "VRSK", "EA", "BKR", "CTSH", "DDOG", "ZS", "ANSS", "CSGP", "ON",
    "MRNA", "ILMN", "DLTR", "WDAY", "CEG", "SMCI", "DASH", "ARM", "TTD", "RBLX",

    # --- Custom Watchlist, High-Beta & Crypto Miners ---
    "MSTR", "IREN", "BLSH", "SNDK", "INTC", "ASML", "CBRS", "SKHY", "SPCX", "RKLB", "NBIS",

    # --- S&P/TSX 60 Canadian Leaders (60) ---
    "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "NA.TO", "MFC.TO", "SLF.TO", "POW.TO", "IFC.TO", "IGM.TO",
    "ENB.TO", "CNQ.TO", "SU.TO", "TRP.TO", "CVE.TO", "IMO.TO", "TOU.TO", "ARX.TO", "PPL.TO", "KEY.TO", "MEG.TO",
    "ABX.TO", "AEM.TO", "FNV.TO", "WPM.TO", "NTR.TO", "TECK-B.TO", "FM.TO", "K.TO", "CCO.TO", "IVN.TO", "WDO.TO", "LUN.TO",
    "SHOP.TO", "CSU.TO", "TRI.TO", "OTEX.TO", "GIB-A.TO", "LSPD.TO",
    "CNR.TO", "CP.TO", "WCN.TO", "TFII.TO", "CAE.TO", "STN.TO", "ATS.TO", "TIH.TO",
    "ATD.TO", "L.TO", "DOL.TO", "MG.TO", "MRU.TO", "QSR.TO",
    "BCE.TO", "T.TO", "RCI-B.TO", "BIP-UN.TO", "BEP-UN.TO", "FTS.TO"
]

ALL_TICKERS = CRYPTO_WATCHLIST + STOCK_ETF_WATCHLIST
KNOWN_ETFS = {"QQQ", "SPY", "IWM", "DIA", "VOO", "VTI", "GLD", "SLV", "USO", "BNO", "IBIT", "ETHA"}

# Full Options Radar Universe (All Stocks & ETFs, excluding Futures)
OPTIONS_RADAR_UNIVERSE = [sym for sym in STOCK_ETF_WATCHLIST if not sym.endswith("=F")]

# ====================================================================
# 0. SMART RATE-LIMIT COMPLIANT & 404-RESILIENT DISPATCHER
# ====================================================================
def safe_post_webhook(url, payload, max_retries=3, fallback_url=None):
    if not url:
        if fallback_url:
            url = fallback_url
        else:
            return False

    for attempt in range(max_retries):
        try:
            res = requests.post(url, json=payload, timeout=12)
            if res.status_code == 200 or res.status_code == 204:
                return True
            if res.status_code == 429:
                try:
                    retry_after = float(res.json().get("retry_after", 2.0))
                except Exception:
                    retry_after = float(res.headers.get("Retry-After", 2.0))
                print(f"⚠️ Discord Webhook 429 Rate Limit. Pausing for {retry_after:.2f}s before retry...")
                time.sleep(retry_after + 0.3)
                continue
            if res.status_code == 404:
                print(f"⚠️ Webhook returned 404 Not Found (Invalid or deleted Webhook URL: {url[:35]}...).")
                if fallback_url and url != fallback_url:
                    print(f"🔄 Routing to Fallback Webhook: {fallback_url[:35]}...")
                    return safe_post_webhook(fallback_url, payload, max_retries=2, fallback_url=None)
                return False
            res.raise_for_status()
            return True
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ Failed to deliver webhook: {e}")
            time.sleep(1.0)
    return False

def create_resilient_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=25, pool_maxsize=25)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    })
    return session

# ====================================================================
# 1. INSTITUTIONAL VOLUME PACING ENGINES (EQUITIES & CRYPTO)
# ====================================================================
def get_intraday_volume_pacing_factor(now_ny):
    if now_ny.weekday() > 4:
        return 1.0

    t = now_ny.time()
    if t < dtime(9, 30) or t >= dtime(16, 0):
        return 1.0

    minutes_elapsed = max(1, int((now_ny - now_ny.replace(hour=9, minute=30, second=0, microsecond=0)).total_seconds() / 60))

    if minutes_elapsed <= 30:
        return 0.02 + (minutes_elapsed / 30.0) * 0.16
    elif minutes_elapsed <= 60:
        return 0.18 + ((minutes_elapsed - 30) / 30.0) * 0.14
    elif minutes_elapsed <= 180:
        return 0.32 + ((minutes_elapsed - 60) / 120.0) * 0.22
    elif minutes_elapsed <= 300:
        return 0.54 + ((minutes_elapsed - 180) / 120.0) * 0.18
    else:
        return 0.72 + ((minutes_elapsed - 300) / 90.0) * 0.28

def get_crypto_volume_pacing_factor(now_utc):
    mins_elapsed = (now_utc.hour * 60) + now_utc.minute
    effective_mins = max(15, mins_elapsed)
    return min(1.0, max(0.01, effective_mins / 1440.0))

# ====================================================================
# 2. HOLIDAY & EARLY CLOSE ENGINE
# ====================================================================
def calculate_easter(year):
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
    us_hols = {}
    ca_hols = {}
    easter = calculate_easter(year)
    good_friday = easter - timedelta(days=2)

    ny_day = date(year, 1, 1)
    if ny_day.weekday() == 6:
        us_hols[date(year, 1, 2)] = "New Year's Day"
        ca_hols[date(year, 1, 2)] = "New Year's Day"
    elif ny_day.weekday() == 5:
        ca_hols[date(year, 1, 3)] = "New Year's Day"
    else:
        us_hols[ny_day] = "New Year's Day"
        ca_hols[ny_day] = "New Year's Day"

    if year >= 1998:
        mlk = date(year, 1, 1) + timedelta(days=(0 - date(year, 1, 1).weekday() + 7) % 7 + 14)
        us_hols[mlk] = "Martin Luther King Jr. Day"

    pres = date(year, 2, 1) + timedelta(days=(0 - date(year, 2, 1).weekday() + 7) % 7 + 14)
    us_hols[pres] = "Presidents' Day"
    if year >= 2008:
        ca_hols[pres] = "Family Day"

    us_hols[good_friday] = "Good Friday"
    ca_hols[good_friday] = "Good Friday"

    may_24 = date(year, 5, 24)
    vic = may_24 - timedelta(days=(may_24.weekday() - 0) % 7)
    ca_hols[vic] = "Victoria Day"

    may_31 = date(year, 5, 31)
    mem = may_31 - timedelta(days=(may_31.weekday() - 0) % 7)
    us_hols[mem] = "Memorial Day"

    if year >= 2022:
        june_19 = date(year, 6, 19)
        if june_19.weekday() == 6:
            us_hols[date(year, 6, 20)] = "Juneteenth"
        elif june_19.weekday() == 5:
            us_hols[date(year, 6, 18)] = "Juneteenth"
        else:
            us_hols[june_19] = "Juneteenth"

    cad = date(year, 7, 1)
    if cad.weekday() == 6:
        ca_hols[date(year, 7, 2)] = "Canada Day"
    elif cad.weekday() == 5:
        ca_hols[date(year, 7, 3)] = "Canada Day"
    else:
        ca_hols[cad] = "Canada Day"

    july_4 = date(year, 7, 4)
    if july_4.weekday() == 6:
        us_hols[date(year, 7, 5)] = "Independence Day"
    elif july_4.weekday() == 5:
        us_hols[date(year, 7, 3)] = "Independence Day"
    else:
        us_hols[july_4] = "Independence Day"

    civic = date(year, 8, 1) + timedelta(days=(0 - date(year, 8, 1).weekday() + 7) % 7)
    ca_hols[civic] = "Civic Holiday"

    labor = date(year, 9, 1) + timedelta(days=(0 - date(year, 9, 1).weekday() + 7) % 7)
    us_hols[labor] = "Labor Day"
    ca_hols[labor] = "Labour Day"

    ca_thanks = date(year, 10, 1) + timedelta(days=(0 - date(year, 10, 1).weekday() + 7) % 7 + 7)
    ca_hols[ca_thanks] = "Thanksgiving (Canada)"

    us_thanks = date(year, 11, 1) + timedelta(days=(3 - date(year, 11, 1).weekday() + 7) % 7 + 21)
    us_hols[us_thanks] = "Thanksgiving Day"

    xmas = date(year, 12, 25)
    boxing = date(year, 12, 26)
    if xmas.weekday() == 6:
        us_hols[date(year, 12, 26)] = "Christmas Day"
        ca_hols[date(year, 12, 26)] = "Christmas Day"
        ca_hols[date(year, 12, 27)] = "Boxing Day"
    elif xmas.weekday() == 5:
        us_hols[date(year, 12, 24)] = "Christmas Day"
        ca_hols[date(year, 12, 27)] = "Christmas Day"
        ca_hols[date(year, 12, 28)] = "Boxing Day"
    else:
        us_hols[xmas] = "Christmas Day"
        ca_hols[xmas] = "Christmas Day"
        ca_hols[boxing] = "Boxing Day"

    return us_hols, ca_hols

def check_market_holiday(target_date):
    all_us, all_ca = {}, {}
    for y in [target_date.year - 1, target_date.year, target_date.year + 1]:
        u, c = _get_year_holidays(y)
        all_us.update(u)
        all_ca.update(c)
    return all_us.get(target_date), all_ca.get(target_date)

def check_early_close(target_date):
    year = target_date.year
    if target_date.month == 7 and target_date.day == 3 and target_date.weekday() < 5:
        july_4 = date(year, 7, 4)
        if july_4.weekday() in (1, 2, 3, 4):
            return True, "Independence Day Eve (1:00 PM Close)"
    us_thanks = date(year, 11, 1) + timedelta(days=(3 - date(year, 11, 1).weekday() + 7) % 7 + 21)
    if target_date == us_thanks + timedelta(days=1):
        return True, "Black Friday (1:00 PM Close)"
    if target_date.month == 12 and target_date.day == 24 and target_date.weekday() < 5:
        return True, "Christmas Eve (1:00 PM Close)"
    return False, None

def get_current_session_info(now_ny, is_early_close):
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
    return re.sub(r'[^a-zA-Z0-9]', '', title_text or '').lower()

# ====================================================================
# 3. STATE MEMORY WITH DAILY & LIFETIME METRICS
# ====================================================================
DEFAULT_METRICS = {
    "news_dispatches": 0,
    "price_fires": 0,
    "earnings_cards": 0,
    "options_radars": 0,
    "options_setups": 0
}

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
        "seen_news_fingerprints": [],
        "stats_today": dict(DEFAULT_METRICS),
        "stats_lifetime": dict(DEFAULT_METRICS)
    }

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                
                # Lifetime stats ALWAYS accumulate and never reset
                if isinstance(saved.get("stats_lifetime"), dict):
                    for k in DEFAULT_METRICS:
                        state["stats_lifetime"][k] = int(saved["stats_lifetime"].get(k, 0))

                # Today stats persist during the same day, auto-reset on a new day
                if saved.get("stock_session_date") == today_ny_str:
                    state["premarket_tickers"] = saved.get("premarket_tickers", {})
                    state["regular_tickers"] = saved.get("regular_tickers", {})
                    state["afterhours_tickers"] = saved.get("afterhours_tickers", {})
                    state["holiday_announced_date"] = saved.get("holiday_announced_date")
                    if isinstance(saved.get("stats_today"), dict):
                        for k in DEFAULT_METRICS:
                            state["stats_today"][k] = int(saved["stats_today"].get(k, 0))

                if saved.get("crypto_session_date") == today_utc_str:
                    state["crypto_tickers"] = saved.get("crypto_tickers", {})
                state["seen_news_fingerprints"] = saved.get("seen_news_fingerprints") or []
                if "persistent_analytics" in saved:
                    state["persistent_analytics"] = saved["persistent_analytics"]
        except Exception:
            pass
    return state

def save_alert_state(state):
    try:
        # Non-destructive merge: read latest disk state first so other processes are never overwritten
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    disk_saved = json.load(f)
                    if isinstance(disk_saved.get("persistent_analytics"), dict):
                        state["persistent_analytics"] = disk_saved["persistent_analytics"]
                    if isinstance(disk_saved.get("stats_today"), dict):
                        state["stats_today"]["earnings_cards"] = max(
                            state["stats_today"].get("earnings_cards", 0),
                            int(disk_saved["stats_today"].get("earnings_cards", 0))
                        )
                    if isinstance(disk_saved.get("stats_lifetime"), dict):
                        state["stats_lifetime"]["earnings_cards"] = max(
                            state["stats_lifetime"].get("earnings_cards", 0),
                            int(disk_saved["stats_lifetime"].get("earnings_cards", 0))
                        )
            except Exception:
                pass

        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

# ====================================================================
# 4. MATH & INDICATORS
# ====================================================================
def format_large_number(num):
    if num is None:
        return "N/A"
    if num >= 1e12:
        return f"${num / 1e12:.2f} Trillion"
    elif num >= 1e9:
        return f"${num / 1e9:.2f} Billion"
    elif num >= 1e6:
        return f"${num / 1e6:.1f} Million"
    elif num >= 1e3:
        return f"${num / 1e3:.1f}K"
    return str(int(num))

def calculate_rsi(closes, period=14):
    if len(closes) < 2:
        return 50.0
    p = min(period, len(closes) - 1)
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

    avg_gain = sum(gains[:p]) / max(1, p)
    avg_loss = sum(losses[:p]) / max(1, p)

    for i in range(p, len(deltas)):
        avg_gain = (avg_gain * (p - 1) + gains[i]) / p
        avg_loss = (avg_loss * (p - 1) + losses[i]) / p

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calculate_macd(closes):
    if len(closes) < 35:
        if len(closes) >= 3:
            slope = closes[-1] - closes[0]
            return "Bullish Momentum 🟢 (Short-term)" if slope >= 0 else "Bearish Momentum 🔴 (Short-term)"
        return "N/A"
    alpha_12 = 2.0 / 13
    alpha_26 = 2.0 / 27
    curr_12 = sum(closes[:12]) / 12
    curr_26 = sum(closes[:26]) / 26
    ema_12_full, ema_26_full = [], []

    for i, c in enumerate(closes):
        if i >= 12:
            curr_12 = c * alpha_12 + curr_12 * (1 - alpha_12)
        if i >= 26:
            curr_26 = c * alpha_26 + curr_26 * (1 - alpha_26)
            ema_12_full.append(curr_12)
            ema_26_full.append(curr_26)

    macd_line = [e12 - e26 for e12, e26 in zip(ema_12_full, ema_26_full)]
    if len(macd_line) < 9:
        return "N/A"

    alpha_9 = 2.0 / 10
    sig = sum(macd_line[:9]) / 9
    sig_line = [sig]
    for m in macd_line[9:]:
        sig = m * alpha_9 + sig * (1 - alpha_9)
        sig_line.append(sig)

    curr_macd = macd_line[-1]
    curr_sig = sig_line[-1]
    hist_curr = curr_macd - curr_sig
    hist_prev = (macd_line[-2] - sig_line[-2]) if len(macd_line) >= 2 else hist_curr

    if curr_macd >= curr_sig:
        return "Bullish Momentum 🟢 (Signal Expanding Upward)" if hist_curr >= hist_prev else "Bullish Trend 🟢 (Momentum Slowing)"
    else:
        return "Bearish Momentum 🔴 (Expanding Downward)" if hist_curr <= hist_prev else "Bearish Trend 🔴 (Weakening / Slowing)"

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < 2:
        return 0.50
    p = min(period, len(closes) - 1)
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(1, len(closes))]
    val = sum(trs[-p:]) / max(1, p)
    return max(0.05, val)

def calculate_historical_volatility(closes, window=30):
    if len(closes) < 3:
        return 0.25
    w = min(window, len(closes) - 1)
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - w, len(closes)) if closes[i-1] > 0]
    if not log_returns:
        return 0.25
    mean_ret = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_ret) ** 2 for r in log_returns) / max(1, (len(log_returns) - 1))
    if variance <= 0:
        return 0.05
    daily_vol = math.sqrt(variance)
    return daily_vol * math.sqrt(252)

def calculate_beta_vs_spy(closes, http_session):
    try:
        if len(closes) < 15:
            return None
        url_spy = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=1y"
        res_spy = http_session.get(url_spy, timeout=4)
        if res_spy.status_code == 200:
            spy_closes = [c for c in res_spy.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None]
            min_len = min(len(closes), len(spy_closes))
            if min_len >= 15:
                s_ret = [closes[i] / closes[i-1] - 1 for i in range(len(closes) - min_len + 1, len(closes))]
                m_ret = [spy_closes[i] / spy_closes[i-1] - 1 for i in range(len(spy_closes) - min_len + 1, len(spy_closes))]
                mean_s = sum(s_ret) / len(s_ret)
                mean_m = sum(m_ret) / len(m_ret)
                cov = sum((s_ret[i] - mean_s) * (m_ret[i] - mean_m) for i in range(len(s_ret)))
                var_m = sum((m_ret[i] - mean_m) ** 2 for i in range(len(m_ret)))
                if var_m > 0:
                    return cov / var_m
    except Exception:
        pass
    return None

def get_volume_tag(rvol, avg_vol):
    if rvol is None or avg_vol is None:
        return "N/A"
    avg_fmt = format_large_number(avg_vol).replace("$", "") + " shares" if avg_vol >= 1000 else str(int(avg_vol)) + " shares"
    if rvol >= 2.0:
        return f"**{rvol:.1f}x** (`Avg: {avg_fmt}` • 🔥 Unusual Surge)"
    elif rvol >= 1.3:
        return f"**{rvol:.1f}x** (`Avg: {avg_fmt}` • ⚡ Strong)"
    elif rvol < 0.6:
        return f"**{rvol:.1f}x** (`Avg: {avg_fmt}` • 💤 Low)"
    else:
        return f"**{rvol:.1f}x** (`Avg: {avg_fmt}` • 📊 Normal)"

def get_rsi_tag(rsi):
    if rsi is None:
        return "N/A"
    if rsi >= 75:
        return f"**{rsi:.1f}** (⚠️ Extreme Overbought)"
    elif rsi >= 70:
        return f"**{rsi:.1f}** (⚠️ Overbought Zone)"
    elif rsi <= 25:
        return f"**{rsi:.1f}** (🟢 Extreme Oversold)"
    elif rsi <= 30:
        return f"**{rsi:.1f}** (🟢 Oversold Zone)"
    elif rsi >= 50:
        return f"**{rsi:.1f}** (🟢 Bullish Trend)"
    else:
        return f"**{rsi:.1f}** (🔴 Bearish Trend)"

def fetch_wallstreet_targets_tls(ticker_symbol, current_price):
    try:
        fz_url = f"https://finviz.com/quote.ashx?t={ticker_symbol}&p=d"
        fz_res = cureq.get(fz_url, impersonate="chrome124", timeout=4)
        if fz_res.status_code == 200:
            m_tp = re.search(r'Target\s*Price[^\d]+(\d+\.\d+)', fz_res.text, re.IGNORECASE)
            m_rc = re.search(r'Recom[^\d]+(\d+\.\d+)', fz_res.text, re.IGNORECASE)
            mean_t = float(m_tp.group(1)) if m_tp else None
            score = float(m_rc.group(1)) if m_rc else None
            rating = "Strong Buy 🟢" if score and score <= 1.8 else ("Buy 🟢" if score and score <= 2.5 else ("Hold 🟡" if score and score <= 3.5 else "Sell 🔴"))
            if mean_t and current_price > 0 and mean_t < (current_price * 10):
                upside = ((mean_t - current_price) / current_price) * 100
                up_tag = " 🔥" if upside >= 15 else (" 🟢" if upside > 0 else " 🔴")
                rating_part = f" | Rating: `{rating}`" if rating else ""
                return f"Mean: `${mean_t:.2f}` (**{upside:+.1f}% Upside{up_tag}**){rating_part}"
    except Exception:
        pass
    return "N/A"

# ====================================================================
# 5. TECHNICALS & FUNDAMENTALS (RETURNS DICT ONLY)
# ====================================================================
def get_technical_and_fundamental_metrics(ticker_symbol, current_price, http_session):
    metrics = {}
    now_ny = datetime.now(NY_TZ)
    now_utc = datetime.now(UTC_TZ)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?interval=1d&range=2y"
        res = http_session.get(url, timeout=5)
        if res.status_code != 200:
            return metrics

        chart_data = res.json().get("chart", {}).get("result", [{}])[0]
        meta = chart_data.get("meta", {})
        indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]

        raw_c = indicators.get("close", []) or []
        raw_v = indicators.get("volume", []) or []
        raw_h = indicators.get("high", []) or []
        raw_l = indicators.get("low", []) or []

        valid_bars = []
        for i in range(min(len(raw_c), len(raw_h), len(raw_l))):
            c, h, l = raw_c[i], raw_h[i], raw_l[i]
            v = raw_v[i] if i < len(raw_v) and raw_v[i] is not None else 0
            if c is not None and h is not None and l is not None and c > 0:
                valid_bars.append((float(c), float(h), float(l), float(v)))

        if len(valid_bars) < 2:
            return metrics

        closes = [b[0] for b in valid_bars]
        highs = [b[1] for b in valid_bars]
        lows = [b[2] for b in valid_bars]
        volumes = [b[3] for b in valid_bars]

        quote_type = meta.get("instrumentType", "EQUITY")
        is_crypto = (quote_type == "CRYPTOCURRENCY" or "-USD" in ticker_symbol)

        vol_today = volumes[-1] if volumes else 0
        v_today_fmt = format_large_number(vol_today).replace("$", "") + " shares" if vol_today >= 1000 else str(int(vol_today))

        avg_vol_20 = (sum(volumes[-21:-1]) / len(volumes[-21:-1])) if len(volumes) >= 20 and sum(volumes[-21:-1]) > 0 else None
        avg_vol_50 = (sum(volumes[-51:-1]) / len(volumes[-51:-1])) if len(volumes) >= 50 and sum(volumes[-51:-1]) > 0 else None
        avg_vol_90 = (sum(volumes[-91:-1]) / len(volumes[-91:-1])) if len(volumes) >= 90 and sum(volumes[-91:-1]) > 0 else None

        pacing_factor = get_crypto_volume_pacing_factor(now_utc) if is_crypto else get_intraday_volume_pacing_factor(now_ny)
        exp_vol_20 = (avg_vol_20 * pacing_factor) if avg_vol_20 else None
        exp_vol_50 = (avg_vol_50 * pacing_factor) if avg_vol_50 else None
        exp_vol_90 = (avg_vol_90 * pacing_factor) if avg_vol_90 else None

        rvol_20 = (vol_today / exp_vol_20) if exp_vol_20 and exp_vol_20 > 0 else None
        rvol_50 = (vol_today / exp_vol_50) if exp_vol_50 and exp_vol_50 > 0 else None
        rvol_90 = (vol_today / exp_vol_90) if exp_vol_90 and exp_vol_90 > 0 else None

        metrics["volume_block"] = (
            f"• **Today's Vol:** `{v_today_fmt}`\n"
            f"• **20D (1-Month):** {get_volume_tag(rvol_20, avg_vol_20)}\n"
            f"• **50D (Quarterly):** {get_volume_tag(rvol_50, avg_vol_50)}\n"
            f"• **90D (Long-Term):** {get_volume_tag(rvol_90, avg_vol_90)}"
        )

        rsi_7 = calculate_rsi(closes, 7)
        rsi_14 = calculate_rsi(closes, 14)
        rsi_30 = calculate_rsi(closes, 30)

        metrics["rsi_block"] = (
            f"• **7D (Fast / Scalp):** {get_rsi_tag(rsi_7)}\n"
            f"• **14D (Standard):** {get_rsi_tag(rsi_14)}\n"
            f"• **30D (Macro Trend):** {get_rsi_tag(rsi_30)}"
        )

        high_52w = meta.get("fiftyTwoWeekHigh") or (max(highs) if highs else None)
        low_52w = meta.get("fiftyTwoWeekLow") or (min(lows) if lows else None)
        if high_52w and low_52w and high_52w > low_52w:
            dist_high = ((high_52w - current_price) / high_52w) * 100
            metrics["range_str"] = f"`${low_52w:.2f} - ${high_52w:.2f}` ({dist_high:.1f}% below 52W High)"

        sma_50 = (sum(closes[-50:]) / 50) if len(closes) >= 50 else (sum(closes) / len(closes))
        sma_200 = (sum(closes[-200:]) / 200) if len(closes) >= 200 else None

        sma_50_str = f"`${sma_50:.2f}` (Above by +{((current_price-sma_50)/sma_50)*100:.1f}% 🟢)" if sma_50 and current_price >= sma_50 else (f"`${sma_50:.2f}` (Below by {((current_price-sma_50)/sma_50)*100:.1f}% 🔴)" if sma_50 else "N/A")
        sma_200_str = f"`${sma_200:.2f}` (Above by +{((current_price-sma_200)/sma_200)*100:.1f}% 🟢)" if sma_200 and current_price >= sma_200 else (f"`${sma_200:.2f}` (Below by {((current_price-sma_200)/sma_200)*100:.1f}% 🔴)" if sma_200 else "`Young Listing (<200D)`")

        verdict_str = "N/A"
        if sma_50 and sma_200:
            if current_price >= sma_50 and current_price >= sma_200:
                verdict_str = "`🟢 Strong Bullish Uptrend` *(Institutional Support)*"
            elif current_price < sma_50 and current_price < sma_200:
                verdict_str = "`🔴 Strong Bearish Downtrend` *(Institutional Selling)*"
            elif current_price >= sma_200 and current_price < sma_50:
                verdict_str = "`🟡 Pullback in Macro Uptrend` *(Testing Support)*"
            else:
                verdict_str = "`🟡 Counter-Trend Rebound` *(Bear Market Bounce)*"
        elif sma_50:
            verdict_str = "`🟢 Uptrend vs Listing Average`" if current_price >= sma_50 else "`🔴 Downtrend vs Listing Average`"

        metrics["trend_block"] = (
            f"• **50-Day SMA:** {sma_50_str}\n"
            f"• **200-Day SMA:** {sma_200_str}\n"
            f"• **Overall Verdict:** {verdict_str}"
        )

        metrics["macd_str"] = calculate_macd(closes)

        if len(highs) >= 2 and len(lows) >= 2 and len(closes) >= 2:
            h_prev, l_prev, c_prev = highs[-2], lows[-2], closes[-2]
            p = (h_prev + l_prev + c_prev) / 3.0
            r1 = (2.0 * p) - l_prev
            s1 = (2.0 * p) - h_prev
            metrics["pivot_str"] = f"`Support (S1): ${s1:.2f}` | `Resistance (R1): ${r1:.2f}`"

        atr = calculate_atr(highs, lows, closes, 14)

        if is_crypto:
            metrics["profile_title"] = "🏢 Asset Class & Profile"
            metrics["profile_block"] = (
                f"• **Asset Class:** `Cryptocurrency (Decentralized Protocol)`\n"
                f"• **Trading:** `24/7/365 Continuous Global Liquidity`"
            )
        elif quote_type == "FUTURE" or "=F" in ticker_symbol:
            metrics["profile_title"] = "🏢 Asset Class & Profile"
            metrics["profile_block"] = f"• **Asset Class:** `Commodity / Index Derivative Contract`"
        else:
            market_cap = None
            try:
                t_obj = yf.Ticker(ticker_symbol)
                market_cap = t_obj.fast_info.market_cap
            except Exception:
                pass

            metrics["profile_title"] = "🏢 Company Profile"
            cap_fmt = format_large_number(market_cap)
            metrics["profile_block"] = f"• **Market Cap:** `{cap_fmt}`"
            metrics["catalysts_block"] = f"• **Wall St. Targets:** {fetch_wallstreet_targets_tls(ticker_symbol, current_price)}"
            atr_fmt = f"±${atr:.2f} (±{(atr/current_price)*100:.1f}% swing)" if atr and current_price > 0 else "N/A"
            beta_val = calculate_beta_vs_spy(closes, http_session)
            beta_str = f"`{beta_val:.2f}x`" if beta_val else "N/A"
            metrics["smart_money_block"] = f"• **Beta (Market Volatility):** {beta_str}\n• **Expected Daily Move (ATR):** `{atr_fmt}`"

        return metrics
    except Exception:
        return metrics

# ====================================================================
# 6. DISCORD WEBHOOK DISPATCHERS
# ====================================================================
def send_discord_price_alert(ticker, current_price, change_pct, session_badge, step_change=None, history_trail=None, metrics=None):
    if isinstance(metrics, tuple):
        metrics = metrics[0] if len(metrics) > 0 else {}
    if not isinstance(metrics, dict):
        metrics = {}

    title_text = f"🚨 Market Alert: {ticker} {session_badge}"
    desc_text = f"**{ticker}** moved **{change_pct:+.2f}%** today!"
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

    if metrics.get("volume_block"):
        fields.append({"name": "📊 Volume Multipliers", "value": metrics["volume_block"], "inline": False})
    if metrics.get("rsi_block"):
        fields.append({"name": "📈 Multi-Timeframe RSI", "value": metrics["rsi_block"], "inline": False})
    if metrics.get("range_str"):
        fields.append({"name": "🏔️ 52-Week Range", "value": metrics["range_str"], "inline": False})
    if metrics.get("trend_block"):
        fields.append({"name": "📈 Moving Averages & Trend", "value": metrics["trend_block"], "inline": False})
    if metrics.get("macd_str"):
        fields.append({"name": "📊 MACD (12,26,9)", "value": metrics["macd_str"], "inline": False})
    if metrics.get("pivot_str"):
        fields.append({"name": "🛡️ Key Pivot Levels", "value": metrics["pivot_str"], "inline": False})
    if metrics.get("catalysts_block"):
        fields.append({"name": "🗓️ Catalysts & Wall Street Targets", "value": metrics["catalysts_block"], "inline": False})
    if metrics.get("smart_money_block"):
        fields.append({"name": "🐋 Smart Money & Risk Metrics", "value": metrics["smart_money_block"], "inline": False})
    if metrics.get("profile_block"):
        fields.append({"name": metrics.get("profile_title", "🏢 Company Profile"), "value": metrics["profile_block"], "inline": False})

    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_AVATAR_URL,
        "embeds": [{
            "title": title_text,
            "description": desc_text,
            "color": 15158332 if change_pct < 0 else 3066993,
            "fields": fields,
            "footer": {"text": f"{BOT_NAME} • 24/7 Price Action Channel"}
        }]
    }
    safe_post_webhook(DISCORD_PRICE_WEBHOOK_URL, payload)

def send_discord_holiday_announcement(us_name, ca_name):
    headline = f"US & Canadian Stock Markets are CLOSED today for {us_name} / {ca_name}!" if us_name and ca_name else (f"US Stock Markets (NYSE / NASDAQ) are CLOSED today for {us_name}!" if us_name else f"Canadian Stock Market (TSX) is CLOSED today for {ca_name}!")
    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_AVATAR_URL,
        "embeds": [{
            "title": "🏛️ Market Notice: Exchange Holiday",
            "description": f"**{headline}**\n\n• 📈 **Stocks & ETFs:** Paused for the holiday session.\n• 🪙 **Crypto Watcher:** Active 24/7.\n• 📰 **Breaking News:** Active 24/7.",
            "color": 15844367,
            "footer": {"text": f"{BOT_NAME} • Market Holiday Engine"}
        }]
    }
    safe_post_webhook(DISCORD_PRICE_WEBHOOK_URL, payload)

def send_discord_news_alert(article):
    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_AVATAR_URL,
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
    safe_post_webhook(DISCORD_NEWS_WEBHOOK_URL, payload, fallback_url=DISCORD_PRICE_WEBHOOK_URL)

# ====================================================================
# 7. 30-MINUTE OPTIONS STRATEGY RADAR (TOP 100 PAGINATED)
# ====================================================================
def analyze_stock_options_setup(ticker_symbol, session_http):
    sym = ticker_symbol.upper().strip()
    now_ny = datetime.now(NY_TZ)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2y"
        res = session_http.get(url, timeout=7)
        if res.status_code != 200:
            return None

        chart_data = res.json().get("chart", {}).get("result", [{}])[0]
        meta = chart_data.get("meta", {})
        indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]

        raw_c = indicators.get("close", []) or []
        raw_v = indicators.get("volume", []) or []
        raw_h = indicators.get("high", []) or []
        raw_l = indicators.get("low", []) or []

        valid_bars = []
        for i in range(min(len(raw_c), len(raw_h), len(raw_l))):
            c, h, l = raw_c[i], raw_h[i], raw_l[i]
            v = raw_v[i] if i < len(raw_v) and raw_v[i] is not None else 0
            if c is not None and h is not None and l is not None and c > 0:
                valid_bars.append((float(c), float(h), float(l), float(v)))

        # Adaptive minimum data floor (allows fresh IPOs / SPACs from 3 days onward)
        if len(valid_bars) < 3:
            return None

        closes = [b[0] for b in valid_bars]
        highs = [b[1] for b in valid_bars]
        lows = [b[2] for b in valid_bars]
        volumes = [b[3] for b in valid_bars]

        current_price = meta.get("regularMarketPrice") or closes[-1]
        prev_close = meta.get("regularMarketPreviousClose") or meta.get("previousClose") or (closes[-2] if len(closes) >= 2 else current_price)
        change_pct = (((current_price - prev_close) / prev_close) * 100) if prev_close and prev_close > 0 else 0.0

        sma_50 = (sum(closes[-50:]) / 50) if len(closes) >= 50 else (sum(closes) / len(closes))
        sma_200 = (sum(closes[-200:]) / 200) if len(closes) >= 200 else sma_50
        rsi_14 = calculate_rsi(closes, period=min(14, len(closes)-1))
        macd_verdict = calculate_macd(closes)
        atr_14 = calculate_atr(highs, lows, closes, 14)

        vol_today = volumes[-1] if volumes else 0
        hist_vols = volumes[:-1]
        avg_vol = (sum(hist_vols) / len(hist_vols)) if hist_vols and sum(hist_vols) > 0 else (vol_today or 1.0)
        pacing_factor = get_intraday_volume_pacing_factor(now_ny)
        expected_vol = avg_vol * pacing_factor
        rvol = (vol_today / expected_vol) if expected_vol > 0 else 1.0

        h_prev = highs[-2] if len(highs) >= 2 else highs[-1]
        l_prev = lows[-2] if len(lows) >= 2 else lows[-1]
        c_prev = closes[-2] if len(closes) >= 2 else closes[-1]
        p = (h_prev + l_prev + c_prev) / 3.0
        r1 = (2.0 * p) - l_prev
        s1 = (2.0 * p) - h_prev

        hv_30 = calculate_historical_volatility(closes, 30)
        hv_90 = calculate_historical_volatility(closes, 90) if len(closes) >= 91 else hv_30
        denom = (hv_90 * 1.3) if (hv_90 and hv_90 > 0) else 1.0
        iv_rank_est = max(5, min(95, int((hv_30 / denom) * 50)))

        bull_score, bear_score = 0, 0

        if current_price >= sma_50:
            bull_score += 25
        else:
            bear_score += 25

        if 52 <= rsi_14 <= 68:
            bull_score += 20
        elif rsi_14 > 68:
            bull_score += 10
        elif 32 <= rsi_14 <= 48:
            bear_score += 20
        elif rsi_14 < 32:
            bear_score += 10

        if "Bullish Momentum" in str(macd_verdict):
            bull_score += 20
        elif "Bullish" in str(macd_verdict):
            bull_score += 12
        elif "Bearish Momentum" in str(macd_verdict):
            bear_score += 20
        elif "Bearish" in str(macd_verdict):
            bear_score += 12

        if rvol >= 1.5:
            bull_score += 15 if change_pct >= 0 else 0
            bear_score += 15 if change_pct < 0 else 0
        elif rvol >= 1.1:
            bull_score += 10 if change_pct >= 0 else 0
            bear_score += 10 if change_pct < 0 else 0
        else:
            bull_score += 5
            bear_score += 5

        if bull_score >= bear_score:
            bull_score += 20 if iv_rank_est < 35 else (18 if iv_rank_est > 50 else 12)
        else:
            bear_score += 20 if iv_rank_est < 35 else (18 if iv_rank_est > 50 else 12)

        final_score = max(bull_score, bear_score)
        is_bullish = bull_score >= bear_score

        strike_step = 0.5 if current_price < 15 else (1.0 if current_price < 50 else (2.5 if current_price < 100 else (5.0 if current_price < 300 else 10.0)))

        if is_bullish:
            if iv_rank_est < 40:
                strategy_name = "Long Call (Outright Bullish Momentum)"
                strike_short = round((current_price + (atr_14 * 0.5)) / strike_step) * strike_step
                prem_short = round(max(0.15, atr_14 * 0.9), 2)
                be_short = strike_short + prem_short

                strike_long = round((current_price - (atr_14 * 0.3)) / strike_step) * strike_step
                prem_long = round(max(0.25, atr_14 * 2.1), 2)
                be_long = strike_long + prem_long

                play_7_14 = f"Buy ${strike_short:.2f} C @ ~${prem_short:.2f} | B/E: `${be_short:.2f}`"
                play_30_45 = f"Buy ${strike_long:.2f} C @ ~${prem_long:.2f} | B/E: `${be_long:.2f}`"
            else:
                strategy_name = "Bull Put Credit Spread (Support Income)"
                sell_p_short = round((s1 - (atr_14 * 0.2)) / strike_step) * strike_step
                buy_p_short = sell_p_short - strike_step
                credit_short = round(max(0.10, strike_step * 0.28), 2)

                sell_p_long = round((current_price * 0.95) / strike_step) * strike_step
                buy_p_long = sell_p_long - strike_step
                credit_long = round(max(0.15, strike_step * 0.33), 2)

                play_7_14 = f"Sell ${sell_p_short:.2f} P / Buy ${buy_p_short:.2f} P | Credit: `${credit_short:.2f}`"
                play_30_45 = f"Sell ${sell_p_long:.2f} P / Buy ${buy_p_long:.2f} P | Credit: `${credit_long:.2f}`"
        else:
            if iv_rank_est < 40:
                strategy_name = "Bear Put Debit Spread (Downside Momentum)"
                buy_p_short = round((current_price + (atr_14 * 0.2)) / strike_step) * strike_step
                sell_p_short = buy_p_short - strike_step
                debit_short = round(max(0.15, strike_step * 0.45), 2)

                buy_p_long = round(current_price / strike_step) * strike_step
                sell_p_long = buy_p_long - (strike_step * 2)
                debit_long = round(max(0.25, strike_step * 0.90), 2)

                play_7_14 = f"Buy ${buy_p_short:.2f} P / Sell ${buy_p_short - strike_step:.2f} P | Debit: `${debit_short:.2f}`"
                play_30_45 = f"Buy ${buy_p_long:.2f} P / Sell ${buy_p_long - (strike_step*2):.2f} P | Debit: `${debit_long:.2f}`"
            else:
                strategy_name = "Bear Call Credit Spread (Resistance Rejection)"
                sell_c_short = round((r1 + (atr_14 * 0.2)) / strike_step) * strike_step
                buy_c_short = sell_c_short + strike_step
                credit_short = round(max(0.10, strike_step * 0.26), 2)

                sell_c_long = round((current_price * 1.05) / strike_step) * strike_step
                buy_c_long = sell_c_long + strike_step
                credit_long = round(max(0.15, strike_step * 0.32), 2)

                play_7_14 = f"Sell ${sell_c_short:.2f} C / Buy ${sell_c_short + strike_step:.2f} C | Credit: `${credit_short:.2f}`"
                play_30_45 = f"Sell ${sell_c_long:.2f} C / Buy ${sell_c_long + strike_step:.2f} C | Credit: `${credit_long:.2f}`"

        return {
            "ticker": sym,
            "price": current_price,
            "score": final_score,
            "is_bullish": is_bullish,
            "strategy_name": strategy_name,
            "iv_rank": iv_rank_est,
            "rsi_14": rsi_14,
            "rvol": rvol,
            "play_7_14": play_7_14,
            "play_30_45": play_30_45
        }
    except Exception:
        return None

def dispatch_top100_options_radar(session_http, state):
    webhook_url = DISCORD_OPTIONS_WEBHOOK_URL or DISCORD_PRICE_WEBHOOK_URL
    if not webhook_url:
        print("⚠️ No valid options or price webhook configured. Skipping options radar.")
        return

    now_ny = datetime.now(NY_TZ)
    time_str = now_ny.strftime("%I:%M %p %Z")
    print(f"\nScanning {len(OPTIONS_RADAR_UNIVERSE)} Securities for Top 100 Options Radar ({time_str})...")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(analyze_stock_options_setup, sym, session_http): sym for sym in OPTIONS_RADAR_UNIVERSE}
        for f in concurrent.futures.as_completed(futures):
            try:
                res = f.result()
                if res:
                    results.append(res)
            except Exception:
                pass

    results.sort(key=lambda x: x["score"], reverse=True)
    top_100 = results[:100]

    if not top_100:
        print("⚠️ No options radar data generated (upstream API returned no valid bars).")
        return

    # Increment setup statistics
    state["stats_today"]["options_setups"] += len(top_100)
    state["stats_lifetime"]["options_setups"] += len(top_100)

    chunk_size = 10
    chunks = [top_100[i:i + chunk_size] for i in range(0, len(top_100), chunk_size)]
    total_parts = len(chunks)
    dispatched_any = False

    for part_idx, chunk in enumerate(chunks, 1):
        start_num = (part_idx - 1) * chunk_size + 1
        embed_desc = ""
        for j, item in enumerate(chunk):
            direction_tag = "🟢 (Bullish)" if item["is_bullish"] else "🔴 (Bearish)"
            embed_desc += (
                f"**{start_num + j}. {item['ticker']} — ${item['price']:.2f}** | **Score: {item['score']}%** {direction_tag}\n"
                f"• **Strategy:** `{item['strategy_name']}` (IV Rank: `{item['iv_rank']}%`)\n"
                f"• ⚡ **7–14 DTE:** {item['play_7_14']}\n"
                f"• 🏛️ **30–45 DTE:** {item['play_30_45']}\n"
                f"• **Catalyst:** RSI: `{item['rsi_14']:.1f}` • RVOL: `{item['rvol']:.1f}x (Time-Paced)`\n\n"
            )

        title = f"🚨 MARKET OPTIONS RADAR [TOP 100 PICKS • PART {part_idx}/{total_parts}]" if total_parts > 1 else "🚨 MARKET OPTIONS RADAR [TOP QUANTITATIVE PICKS]"
        description_header = f"*Live Quantitative Ranking across {len(OPTIONS_RADAR_UNIVERSE)} Market Securities as of {time_str}.*\n*Showing Top Picks {start_num} to {start_num + len(chunk) - 1} of {len(top_100)} total.*\n\n"

        payload = {
            "username": BOT_NAME,
            "avatar_url": BOT_AVATAR_URL,
            "embeds": [{
                "title": title,
                "description": f"{description_header}{embed_desc}"[:4000],
                "color": 3066993,
                "footer": {"text": f"Looney Options Intelligence • Part {part_idx} of {total_parts} • Type '#TICKER' in chat for deep-dive Greeks"}
            }]
        }
        success = safe_post_webhook(webhook_url, payload, fallback_url=DISCORD_PRICE_WEBHOOK_URL)
        if success:
            dispatched_any = True
            print(f"Top 100 Options Radar Part {part_idx}/{total_parts} successfully posted at {time_str}!")
        time.sleep(1.2)

    if dispatched_any:
        state["stats_today"]["options_radars"] += 1
        state["stats_lifetime"]["options_radars"] += 1

# ====================================================================
# 8. DATA EXTRACTION ENGINE (Exact Pure Extended Hours Calculations)
# ====================================================================
def get_extended_stock_data(ticker_symbol, session_type, session_http):
    current_price = None
    baseline_price = None
    now_ny = datetime.now(NY_TZ)

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?interval=1m&range=2d&includePrePost=true"
        res = session_http.get(url, timeout=5)
        if res.status_code == 200:
            result = res.json().get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            indicators = result.get("indicators", {}).get("quote", [{}])[0]
            timestamps = result.get("timestamp", []) or []
            raw_closes = indicators.get("close", []) or []

            # Pair timestamps with valid price closes
            valid_trades = []
            for i in range(min(len(timestamps), len(raw_closes))):
                c = raw_closes[i]
                t = timestamps[i]
                if c is not None and c > 0 and t is not None:
                    valid_trades.append((int(t), float(c)))

            reg_market_close = meta.get("regularMarketPrice")  # Official regular close
            prev_day_close = meta.get("chartPreviousClose") or meta.get("previousClose") or meta.get("regularMarketPreviousClose")
            
            is_future = ticker_symbol.endswith("=F")

            if is_future:
                curr = meta.get("regularMarketPrice") or (valid_trades[-1][1] if valid_trades else None)
                base = prev_day_close or meta.get("chartPreviousClose")
                if curr is not None and base is not None and float(base) > 0:
                    current_price = float(curr)
                    baseline_price = float(base)

            elif session_type == "PRE_MARKET":
                # Only consider 1-minute bars executed TODAY since 4:00 AM EST
                today_4am_ts = int(now_ny.replace(hour=4, minute=0, second=0, microsecond=0).timestamp())
                morning_trades = [price for (ts, price) in valid_trades if ts >= today_4am_ts]

                pre_price = meta.get("preMarketPrice") or (morning_trades[-1] if morning_trades else None)
                base_ref = prev_day_close or reg_market_close

                if pre_price is not None and base_ref is not None and float(base_ref) > 0 and (morning_trades or meta.get("preMarketPrice")):
                    current_price = float(pre_price)
                    baseline_price = float(base_ref)
                else:
                    # No active morning pre-market trades yet today -> perfectly neutral (0.00% change, zero false alerts)
                    ref_p = float(base_ref) if base_ref else None
                    current_price = ref_p
                    baseline_price = ref_p

            elif session_type == "AFTER_HOURS":
                # Only consider 1-minute bars executed TODAY since 4:00 PM EST
                today_4pm_ts = int(now_ny.replace(hour=16, minute=0, second=0, microsecond=0).timestamp())
                evening_trades = [price for (ts, price) in valid_trades if ts >= today_4pm_ts]

                post_price = meta.get("postMarketPrice") or (evening_trades[-1] if evening_trades else None)
                base_ref = reg_market_close or prev_day_close

                if post_price is not None and base_ref is not None and float(base_ref) > 0 and (evening_trades or meta.get("postMarketPrice")):
                    current_price = float(post_price)
                    baseline_price = float(base_ref)
                else:
                    # No active evening after-hours trades -> perfectly neutral (0.00% change, zero false alerts)
                    ref_p = float(base_ref) if base_ref else None
                    current_price = ref_p
                    baseline_price = ref_p

            else:  # REGULAR / CRYPTO
                curr = meta.get("regularMarketPrice") or (valid_trades[-1][1] if valid_trades else None)
                base = prev_day_close or meta.get("chartPreviousClose")
                if curr is not None and base is not None and float(base) > 0:
                    current_price = float(curr)
                    baseline_price = float(base)
    except Exception:
        pass

    # Resilient fallback if chart API was unreachable
    if current_price is None or baseline_price is None:
        try:
            ticker = yf.Ticker(ticker_symbol, session=session_http)
            fi = ticker.fast_info
            if session_type in ["AFTER_HOURS", "PRE_MARKET"]:
                current_price = float(fi.last_price) if fi.last_price is not None else None
                baseline_price = float(fi.last_price) if fi.last_price is not None else None
            else:
                current_price = float(fi.last_price) if fi.last_price is not None else None
                baseline_price = float(fi.previous_close) if fi.previous_close is not None else None
        except Exception:
            pass

    return current_price, baseline_price

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
# 9. MAIN EXECUTION CONTROLLER
# ====================================================================
def check_market():
    now_ny = datetime.now(NY_TZ)
    today_ny_date = now_ny.date()
    today_ny_str = now_ny.strftime("%Y-%m-%d")

    us_hol, ca_hol = check_market_holiday(today_ny_date)
    is_stock_holiday = bool(us_hol)
    is_early_close, early_close_reason = check_early_close(today_ny_date)

    state = load_alert_state()

    if is_stock_holiday and state.get("holiday_announced_date") != today_ny_str:
        send_discord_holiday_announcement(us_hol, ca_hol)
        state["holiday_announced_date"] = today_ny_str

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

    session_http = create_resilient_session()

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

                should_alert = False
                step_change_pct = None
                history_trail = []

                if ticker_symbol in tracked_dict:
                    item_data = tracked_dict[ticker_symbol]
                    last_alert_price = item_data["last_price"]
                    history_trail = list(item_data.get("history", []))
                    step_change_pct = ((current_price - last_alert_price) / last_alert_price) * 100

                    if abs(step_change_pct) >= req_threshold:
                        should_alert = True
                        print(f"🔥 {ticker_symbol} {badge} | STEP TRIGGER | Price: ${current_price:.2f} | Step: {step_change_pct:+.2f}%")
                        history_trail.append(f"{change_pct:+.2f}%")
                        tracked_dict[ticker_symbol] = {
                            "last_price": current_price,
                            "history": history_trail
                        }
                    else:
                        print(f"⏭️ {ticker_symbol} {badge} | Price: ${current_price:.2f} | Step: {step_change_pct:+.2f}% (Below {req_threshold}%)")
                else:
                    if abs(change_pct) >= req_threshold:
                        should_alert = True
                        print(f"🚨 {ticker_symbol} {badge} | INITIAL TRIGGER | Price: ${current_price:.2f} | Change: {change_pct:+.2f}%")
                        tracked_dict[ticker_symbol] = {
                            "last_price": current_price,
                            "history": [f"{change_pct:+.2f}%"]
                        }
                        history_trail = []
                    else:
                        print(f"✅ {ticker_symbol} {badge} | Price: ${current_price:.2f} | Change: {change_pct:+.2f}%")

                if should_alert:
                    metrics = get_technical_and_fundamental_metrics(ticker_symbol, current_price, session_http)
                    price_alerts_to_send.append({
                        "ticker": ticker_symbol,
                        "price": current_price,
                        "change_pct": change_pct,
                        "badge": badge,
                        "step_change": step_change_pct,
                        "history_trail": history_trail[:-1] if step_change_pct is not None else [],
                        "metrics": metrics
                    })

            else:
                print(f"⚠️ {ticker_symbol} {badge} | SKIPPED: Insufficient realtime price data")
        except Exception as e:
            print(f"❌ Error checking {ticker_symbol}: {e}")
        time.sleep(0.08)

    print("\nScanning breaking news across all tickers...")
    cutoff_time = now_ny - timedelta(minutes=MAX_NEWS_AGE_MINUTES)
    seen_fingerprints_set = set(state.get("seen_news_fingerprints", []))
    raw_news = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
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
                history_trail=alert["history_trail"],
                metrics=alert["metrics"]
            )
            # Increment price fire metrics
            state["stats_today"]["price_fires"] += 1
            state["stats_lifetime"]["price_fires"] += 1
            time.sleep(1.0)

    if new_articles:
        print(f"\nSending ALL {len(new_articles)} fresh headline alert(s) to NEWS CHANNEL...")
        for article in new_articles:
            send_discord_news_alert(article)
            # Increment news dispatch metrics
            state["stats_today"]["news_dispatches"] += 1
            state["stats_lifetime"]["news_dispatches"] += 1
            time.sleep(1.0)

    # Re-evaluate live time right before running options check
    now_ny_options = datetime.now(NY_TZ)
    reg_close_time = dtime(13, 0) if is_early_close else dtime(16, 0)
    is_options_market_open = (
        not is_stock_holiday and
        now_ny_options.weekday() <= 4 and
        dtime(9, 32) <= now_ny_options.time() <= reg_close_time
    )

    if is_options_market_open:
        dispatch_top100_options_radar(session_http, state)
    elif is_stock_holiday:
        print("⏭️ Skipping options radar: US Stock Market is CLOSED for Holiday.")
    elif now_ny_options.weekday() > 4:
        print("⏭️ Skipping options radar: Weekend (Market Closed).")
    else:
        close_str = "1:00 PM" if is_early_close else "4:00 PM"
        print(f"⏭️ Skipping options radar: Outside live options market hours ({now_ny_options.strftime('%I:%M %p %Z')}). Active Mon-Fri 9:32 AM - {close_str} EST.")

    save_alert_state(state)
    print(f"\n=======================================================")
    print(f"Check Complete. Price Alerts: {len(price_alerts_to_send)} | Fresh News: {len(new_articles)}")

if __name__ == "__main__":
    check_market()
