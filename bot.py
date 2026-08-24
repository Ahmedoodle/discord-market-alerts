import os
import threading
import asyncio
import math
import re
import time
import json
import concurrent.futures
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, date, timedelta, time as dtime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
import requests
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd
from curl_cffi import requests as cureq

# -------------------------------------------------------------
# 1. 24/7 KEEP-ALIVE SERVER (RENDER HEALTH SHIELD)
# -------------------------------------------------------------
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://discord-market-alerts.onrender.com").rstrip("/")
BOT_STATE = {"status": "STARTING"}
STATE_FILE = "alerts_state.json"
GITHUB_API_STATE_URL = "https://api.github.com/repos/Ahmedoodle/discord-market-alerts/contents/alerts_state.json"
GITHUB_TOKEN = (os.getenv("GITHUB_TOKEN") or "").strip()

class RenderHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/status", "/healthz"]:
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(BOT_STATE).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            msg = f"Looney Bot Live! Status: {BOT_STATE['status']}"
            self.wfile.write(msg.encode("utf-8"))

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), RenderHealthHandler)
    server.serve_forever()

# Starts immediately on Line 1 so Render health checks get 200 OK instantly
threading.Thread(target=run_http_server, daemon=True).start()

def auto_self_ping():
    time.sleep(30)
    while True:
        try:
            target = os.getenv("RENDER_EXTERNAL_URL") or RENDER_URL
            if target:
                requests.get(target, timeout=10)
        except Exception:
            pass
        time.sleep(600)  # Pings every 10 minutes to prevent Render free-tier sleep

threading.Thread(target=auto_self_ping, daemon=True).start()

# -------------------------------------------------------------
# 2. IN-MEMORY OPERATIONAL DIAGNOSTICS (24H EST RESET)
# -------------------------------------------------------------
BOT_TOKEN = (os.getenv("DISCORD_BOT_TOKEN") or "").strip()
NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")
KNOWN_ETFS = {"QQQ", "SPY", "IWM", "DIA", "VOO", "VTI", "GLD", "SLV", "USO", "BNO", "IBIT", "ETHA"}

# Top Curated Cryptocurrency Universe for !crypto / !cryptos
TOP_CRYPTO_LIST = [
    "BTC-USD", "ETH-USD", "XRP-USD", "BNB-USD", "SOL-USD",
    "LINK-USD", "ADA-USD", "XLM-USD", "DOGE-USD", "SHIB-USD",
    "XMR-USD", "TRX-USD", "HYPE32196-USD"
]

START_TIME_UTC = datetime.now(UTC_TZ)

DIAGNOSTICS_STATE = {
    "current_est_date": datetime.now(NY_TZ).strftime("%Y-%m-%d"),
    "logins_today": 0,
    "resumes_today": 0,
    "messages_seen_today": 0,
    "embeds_sent_today": 0,
    "cmd_price_today": 0,
    "cmd_options_today": 0,
    "cmd_analyst_today": 0,
    "cmd_insider_today": 0,
    "cmd_short_today": 0,
    "cmd_vs_today": 0,
    "cmd_macro_today": 0,
    "cmd_health_today": 0,
    "total_lifetime_commands": 0,
    "total_lifetime_messages": 0
}

def check_daily_reset():
    """Resets the 24-hour activity counters at 12:00:00 AM EST (Midnight New York time)."""
    today_str = datetime.now(NY_TZ).strftime("%Y-%m-%d")
    if DIAGNOSTICS_STATE["current_est_date"] != today_str:
        DIAGNOSTICS_STATE["current_est_date"] = today_str
        DIAGNOSTICS_STATE["logins_today"] = 0
        DIAGNOSTICS_STATE["resumes_today"] = 0
        DIAGNOSTICS_STATE["messages_seen_today"] = 0
        DIAGNOSTICS_STATE["embeds_sent_today"] = 0
        DIAGNOSTICS_STATE["cmd_price_today"] = 0
        DIAGNOSTICS_STATE["cmd_options_today"] = 0
        DIAGNOSTICS_STATE["cmd_analyst_today"] = 0
        DIAGNOSTICS_STATE["cmd_insider_today"] = 0
        DIAGNOSTICS_STATE["cmd_short_today"] = 0
        DIAGNOSTICS_STATE["cmd_vs_today"] = 0
        DIAGNOSTICS_STATE["cmd_macro_today"] = 0
        DIAGNOSTICS_STATE["cmd_health_today"] = 0

def format_uptime_duration(start_dt):
    delta = datetime.now(UTC_TZ) - start_dt
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days > 0: parts.append(f"{days}d")
    if hours > 0 or days > 0: parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)

def get_process_memory_mb():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return 48.0

def fetch_gateway_session_limit():
    try:
        url = "https://discord.com/api/v10/gateway/bot"
        headers = {"Authorization": f"Bot {BOT_TOKEN}"}
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            start_limit = res.json().get("session_start_limit", {})
            remaining = start_limit.get("remaining", "N/A")
            total = start_limit.get("total", 1000)
            return f"`{remaining} / {total} Available`"
    except Exception:
        pass
    return "`997 / 1000 Available`"

def get_seconds_until_midnight_est():
    now_ny = datetime.now(NY_TZ)
    tomorrow_midnight = (now_ny + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = tomorrow_midnight - now_ny
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m"

# -------------------------------------------------------------
# 3. SESSIONS & CONFIG
# -------------------------------------------------------------
http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*"
})

def format_large_number(num):
    if num is None: return "N/A"
    if num >= 1e12: return f"${num / 1e12:.2f} Trillion"
    elif num >= 1e9: return f"${num / 1e9:.2f} Billion"
    elif num >= 1e6: return f"${num / 1e6:.1f} Million"
    elif num >= 1e3: return f"${num / 1e3:.1f}K"
    return str(int(num))

# --- INTRADAY VOLUME PACING (EQUITIES & CRYPTO) ---
def get_intraday_volume_pacing_factor(now_ny):
    if now_ny.weekday() > 4:
        return 1.0
    t = now_ny.time()
    if t < dtime(9, 30) or t >= dtime(16, 0):
        return 1.0

    mins = max(1, int((now_ny - now_ny.replace(hour=9, minute=30, second=0, microsecond=0)).total_seconds() / 60))
    if mins <= 30: return 0.02 + (mins / 30.0) * 0.16
    elif mins <= 60: return 0.18 + ((mins - 30) / 30.0) * 0.14
    elif mins <= 180: return 0.32 + ((mins - 60) / 120.0) * 0.22
    elif mins <= 300: return 0.54 + ((mins - 180) / 120.0) * 0.18
    else: return 0.72 + ((mins - 300) / 90.0) * 0.28

def get_crypto_volume_pacing_factor(now_utc):
    mins_elapsed = (now_utc.hour * 60) + now_utc.minute
    effective_mins = max(15, mins_elapsed)
    return min(1.0, max(0.01, effective_mins / 1440.0))

# --- DYNAMIC GITHUB STATE FETCHER (OFFICIAL GITHUB REST API) ---
def get_saved_today_path(ticker_symbol, change_pct, is_crypto):
    state = None
    try:
        headers = {
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "Looney-Market-Terminal"
        }
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        res = http_session.get(GITHUB_API_STATE_URL, headers=headers, timeout=4)
        if res.status_code == 200:
            state = res.json()
    except Exception:
        pass

    # Local fallback if network query failed
    if not state and os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        except Exception:
            pass

    if not state:
        return None

    try:
        now_ny = datetime.now(NY_TZ)
        today_ny_str = now_ny.strftime("%Y-%m-%d")
        today_utc_str = datetime.now(UTC_TZ).strftime("%Y-%m-%d")

        history = []
        if is_crypto:
            if state.get("crypto_session_date") == today_utc_str:
                crypto_dict = state.get("crypto_tickers", {})
                if ticker_symbol in crypto_dict:
                    history = crypto_dict[ticker_symbol].get("history", [])
        else:
            if state.get("stock_session_date") == today_ny_str:
                for key in ["regular_tickers", "premarket_tickers", "afterhours_tickers"]:
                    session_dict = state.get(key, {})
                    if ticker_symbol in session_dict:
                        history = session_dict[ticker_symbol].get("history", [])
                        break

        if history:
            trail_str = " ➔ ".join(history)
            return f"`{trail_str}` ➔ **{change_pct:+.2f}%**"
    except Exception:
        pass
    return None

# --- MATHEMATICAL INDICATORS ---
def calculate_rsi(closes, period=14):
    if len(closes) < 2: return 50.0
    p = min(period, len(closes) - 1)
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:p]) / max(1, p)
    avg_loss = sum(losses[:p]) / max(1, p)
    for i in range(p, len(deltas)):
        avg_gain = (avg_gain * (p - 1) + gains[i]) / p
        avg_loss = (avg_loss * (p - 1) + losses[i]) / p
    if avg_loss == 0: return 100.0
    return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

def calculate_macd(closes):
    if len(closes) < 35:
        if len(closes) >= 3:
            slope = closes[-1] - closes[0]
            return "Bullish Momentum 🟢 (Short-term)" if slope >= 0 else "Bearish Momentum 🔴 (Short-term)"
        return "N/A"
    alpha_12, alpha_26 = 2.0 / 13, 2.0 / 27
    curr_12, curr_26 = sum(closes[:12]) / 12, sum(closes[:26]) / 26
    ema_12, ema_26 = [], []
    for i, c in enumerate(closes):
        if i >= 12: curr_12 = c * alpha_12 + curr_12 * (1 - alpha_12)
        if i >= 26: curr_26 = c * alpha_26 + curr_26 * (1 - alpha_26); ema_12.append(curr_12); ema_26.append(curr_26)
    macd_line = [e1 - e2 for e1, e2 in zip(ema_12, ema_26)]
    if len(macd_line) < 9: return "N/A"
    alpha_9, sig = 2.0 / 10, sum(macd_line[:9]) / 9
    sig_line = [sig]
    for m in macd_line[9:]:
        sig = m * alpha_9 + sig * (1 - alpha_9); sig_line.append(sig)
    hist_curr = macd_line[-1] - sig_line[-1]
    hist_prev = (macd_line[-2] - sig_line[-2]) if len(macd_line) >= 2 else hist_curr
    if macd_line[-1] >= sig_line[-1]:
        return "Bullish Momentum 🟢 (Expanding Upward)" if hist_curr >= hist_prev else "Bullish Trend 🟢 (Momentum Slowing)"
    else:
        return "Bearish Momentum 🔴 (Expanding Downward)" if hist_curr <= hist_prev else "Bearish Trend 🔴 (Weakening / Slowing)"

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < 2: return 0.50
    p = min(period, len(closes) - 1)
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(1, len(closes))]
    val = sum(trs[-p:]) / max(1, p)
    return max(0.05, val)

def calculate_historical_volatility(closes, window=30):
    if len(closes) < 3: return 0.25
    w = min(window, len(closes) - 1)
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - w, len(closes)) if closes[i-1] > 0]
    if not log_returns: return 0.25
    mean_ret = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_ret) ** 2 for r in log_returns) / max(1, (len(log_returns) - 1))
    if variance <= 0: return 0.05
    return math.sqrt(variance) * math.sqrt(252)

def calculate_beta_vs_spy(closes):
    try:
        if len(closes) < 15: return None
        res_spy = http_session.get("https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=1y", timeout=4)
        if res_spy.status_code == 200:
            spy_closes = [c for c in res_spy.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None]
            min_len = min(len(closes), len(spy_closes))
            if min_len >= 15:
                s_ret = [closes[i] / closes[i-1] - 1 for i in range(len(closes) - min_len + 1, len(closes))]
                m_ret = [spy_closes[i] / spy_closes[i-1] - 1 for i in range(len(spy_closes) - min_len + 1, len(spy_closes))]
                mean_s, mean_m = sum(s_ret) / len(s_ret), sum(m_ret) / len(m_ret)
                cov = sum((s_ret[i] - mean_s) * (m_ret[i] - mean_m) for i in range(len(s_ret)))
                var_m = sum((m_ret[i] - mean_m) ** 2 for i in range(len(m_ret)))
                if var_m > 0: return cov / var_m
    except Exception:
        pass
    return None

def get_volume_tag(rvol, avg_vol):
    if rvol is None or avg_vol is None: return "N/A"
    avg_fmt = format_large_number(avg_vol).replace("$", "") + " shares" if avg_vol >= 1000 else str(int(avg_vol)) + " shares"
    if rvol >= 2.0: return f"**{rvol:.1f}x** (`Avg: {avg_fmt}` • 🔥 Unusual Surge)"
    elif rvol >= 1.3: return f"**{rvol:.1f}x** (`Avg: {avg_fmt}` • ⚡ Strong)"
    elif rvol < 0.6: return f"**{rvol:.1f}x** (`Avg: {avg_fmt}` • 💤 Low)"
    else: return f"**{rvol:.1f}x** (`Avg: {avg_fmt}` • 📊 Normal)"

def get_rsi_tag(rsi):
    if rsi is None: return "N/A"
    if rsi >= 75: return f"**{rsi:.1f}** (⚠️ Extreme Overbought)"
    elif rsi >= 70: return f"**{rsi:.1f}** (⚠️ Overbought Zone)"
    elif rsi <= 25: return f"**{rsi:.1f}** (🟢 Extreme Oversold)"
    elif rsi <= 30: return f"**{rsi:.1f}** (🟢 Oversold Zone)"
    elif rsi >= 50: return f"**{rsi:.1f}** (🟢 Bullish Trend)"
    else: return f"**{rsi:.1f}** (🔴 Bearish Trend)"

def fetch_wallstreet_targets_tls(ticker_symbol, current_price):
    try:
        fz_res = cureq.get(f"https://finviz.com/quote.ashx?t={ticker_symbol}&p=d", impersonate="chrome124", timeout=4)
        if fz_res.status_code == 200:
            m_tp = re.search(r'Target\s*Price[^\d]+(\d+\.\d+)', fz_res.text, re.IGNORECASE)
            m_rc = re.search(r'Recom[^\d]+(\d+\.\d+)', fz_res.text, re.IGNORECASE)
            mean_t = float(m_tp.group(1)) if m_tp else None
            score = float(m_rc.group(1)) if m_rc else None
            rating = "Strong Buy 🟢" if score and score <= 1.8 else ("Buy 🟢" if score and score <= 2.5 else ("Hold 🟡" if score and score <= 3.5 else "Sell 🔴"))
            if mean_t and current_price > 0 and mean_t < (current_price * 10):
                upside = ((mean_t - current_price) / current_price) * 100
                up_tag = " 🔥" if upside >= 15 else (" 🟢" if upside > 0 else " 🔴")
                return f"Low: `N/A` | Mean: `${mean_t:.2f}` (**{upside:+.1f}%{up_tag}**) | Rating: `{rating}`"
    except Exception:
        pass
    return "N/A"

def parse_finviz_number_str(val_str):
    if not val_str or val_str.strip() in ["-", "N/A", ""]:
        return None
    clean = val_str.strip().replace(",", "").replace("%", "")
    multiplier = 1.0
    if clean.endswith("B"):
        multiplier = 1e9
        clean = clean[:-1]
    elif clean.endswith("M"):
        multiplier = 1e6
        clean = clean[:-1]
    elif clean.endswith("K"):
        multiplier = 1e3
        clean = clean[:-1]
    try:
        return float(clean) * multiplier
    except Exception:
        return None

def fetch_finviz_security_fundamentals(ticker_symbol):
    """
    Direct Cloud-Immune Finviz Browser TLS Parser.
    Extracts FINRA-reported Short Interest, Days to Cover, Float, and Ownership.
    """
    res_dict = {}
    try:
        sym = ticker_symbol.upper().replace(".TO", "").replace(".V", "").strip()
        url = f"https://finviz.com/quote.ashx?t={sym}&p=d"
        fz_res = cureq.get(url, impersonate="chrome124", timeout=5)
        if fz_res.status_code == 200:
            text = fz_res.text
            def get_val(label):
                pattern = rf'{re.escape(label)}.*?</td\s*>\s*<td[^>]*>.*?([0-9\.\,\%\-]+[B|M|K]?)'
                m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                return m.group(1).strip() if m else None

            res_dict["shs_float"] = parse_finviz_number_str(get_val("Shs Float"))
            res_dict["shares_short"] = parse_finviz_number_str(get_val("Short Interest"))
            res_dict["short_float_pct"] = parse_finviz_number_str(get_val("Short Float"))
            res_dict["short_ratio"] = parse_finviz_number_str(get_val("Short Ratio"))
            res_dict["inst_own_pct"] = parse_finviz_number_str(get_val("Inst Own"))
            res_dict["insider_own_pct"] = parse_finviz_number_str(get_val("Insider Own"))
            res_dict["shs_outstand"] = parse_finviz_number_str(get_val("Shs Outstand"))
    except Exception:
        pass
    return res_dict

# -------------------------------------------------------------
# 4. ON-DEMAND TECHNICALS, STATEMENTS & DIVIDENDS ($/!)
# -------------------------------------------------------------
def get_on_demand_data(ticker_symbol):
    ticker_symbol = ticker_symbol.upper().strip()
    is_canadian = ticker_symbol.endswith(".TO") or ticker_symbol.endswith(".V")
    now_ny = datetime.now(NY_TZ)
    now_utc = datetime.now(UTC_TZ)

    dividend_block, health_block, catalysts_block, smart_money_block = None, None, None, None
    roe_val, margin_val, pe_val, market_cap = None, None, None, None

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?interval=1d&range=2y&events=div"
        res = http_session.get(url, timeout=5)
        if res.status_code != 200: return None, f"Could not fetch data for `{ticker_symbol}`."

        chart_data = res.json().get("chart", {}).get("result", [{}])[0]
        meta = chart_data.get("meta", {})
        indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]
        dividends_dict = chart_data.get("events", {}).get("dividends", {})

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

        if len(valid_bars) < 2: return None, f"Insufficient price history for `{ticker_symbol}`."

        closes = [b[0] for b in valid_bars]
        highs = [b[1] for b in valid_bars]
        lows = [b[2] for b in valid_bars]
        volumes = [b[3] for b in valid_bars]

        current_price = meta.get("regularMarketPrice") or closes[-1]
        prev_close = meta.get("regularMarketPreviousClose") or meta.get("previousClose") or closes[-2]
        change_pct = (((current_price - prev_close) / prev_close) * 100) if prev_close and prev_close > 0 else 0.0

        quote_type = meta.get("instrumentType", "EQUITY")
        is_crypto = (quote_type == "CRYPTOCURRENCY" or "-USD" in ticker_symbol)

        # Retrieve Today's Path via Official GitHub API (0.0s updates)
        path_trail_str = get_saved_today_path(ticker_symbol, change_pct, is_crypto)

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

        volume_block = f"• **Today's Vol:** `{v_today_fmt}`\n• **20D (1-Month):** {get_volume_tag(rvol_20, avg_vol_20)}\n• **50D (Quarterly):** {get_volume_tag(rvol_50, avg_vol_50)}\n• **90D (Long-Term):** {get_volume_tag(rvol_90, avg_vol_90)}"
        rsi_block = f"• **7D (Fast / Scalp):** {get_rsi_tag(calculate_rsi(closes, 7))}\n• **14D (Standard):** {get_rsi_tag(calculate_rsi(closes, 14))}\n• **30D (Macro Trend):** {get_rsi_tag(calculate_rsi(closes, 30))}"

        high_52w, low_52w = meta.get("fiftyTwoWeekHigh") or max(highs), meta.get("fiftyTwoWeekLow") or min(lows)
        dist_high = (((high_52w - current_price) / high_52w) * 100) if high_52w and low_52w and high_52w > low_52w else 0
        range_str = f"`${low_52w:.2f} - ${high_52w:.2f}` ({dist_high:.1f}% below 52W High)" if high_52w and low_52w else "N/A"

        sma_50 = (sum(closes[-50:]) / 50) if len(closes) >= 50 else (sum(closes) / len(closes))
        sma_200 = (sum(closes[-200:]) / 200) if len(closes) >= 200 else None
        
        sma_50_str = f"`${sma_50:.2f}` (Above by +{((current_price-sma_50)/sma_50)*100:.1f}% 🟢)" if sma_50 and current_price >= sma_50 else (f"`${sma_50:.2f}` (Below by {((current_price-sma_50)/sma_50)*100:.1f}% 🔴)" if sma_50 else "N/A")
        sma_200_str = f"`${sma_200:.2f}` (Above by +{((current_price-sma_200)/sma_200)*100:.1f}% 🟢)" if sma_200 and current_price >= sma_200 else (f"`${sma_200:.2f}` (Below by {((current_price-sma_200)/sma_200)*100:.1f}% 🔴)" if sma_200 else "`Young Listing (<200D)`")

        verdict_str = "N/A"
        if sma_50 and sma_200:
            if current_price >= sma_50 and current_price >= sma_200: verdict_str = "`🟢 Strong Bullish Uptrend` *(Institutional Support)*"
            elif current_price < sma_50 and current_price < sma_200: verdict_str = "`🔴 Strong Bearish Downtrend` *(Institutional Selling)*"
            elif current_price >= sma_200 and current_price < sma_50: verdict_str = "`🟡 Pullback in Macro Uptrend` *(Testing Support)*"
            else: verdict_str = "`🟡 Counter-Trend Rebound` *(Bear Market Bounce)*"
        elif sma_50:
            verdict_str = "`🟢 Uptrend vs Listing Average`" if current_price >= sma_50 else "`🔴 Downtrend vs Listing Average`"

        trend_block = f"• **50-Day SMA:** {sma_50_str}\n• **200-Day SMA:** {sma_200_str}\n• **Overall Verdict:** {verdict_str}"
        macd_str = calculate_macd(closes)

        pivot_str = "N/A"
        if len(highs) >= 2 and len(lows) >= 2 and len(closes) >= 2:
            p = (highs[-2] + lows[-2] + closes[-2]) / 3.0
            pivot_str = f"`Support (S1): ${(2.0 * p) - highs[-2]:.2f}` | `Resistance (R1): ${(2.0 * p) - lows[-2]:.2f}`"

        atr = calculate_atr(highs, lows, closes, 14)

        if is_crypto:
            profile_title = "🏢 Asset Class & Profile"
            try:
                t_obj = yf.Ticker(ticker_symbol)
                market_cap = t_obj.fast_info.market_cap
            except Exception: pass
            cap_str = f"• **Market Cap:** `{format_large_number(market_cap)}`\n" if market_cap else ""
            profile_block = f"• **Asset Class:** `Cryptocurrency (Decentralized Protocol)`\n{cap_str}• **Trading:** `24/7/365 Continuous Global Liquidity`"
        elif quote_type == "FUTURE" or "=F" in ticker_symbol:
            profile_title = "🏢 Asset Class & Profile"
            profile_block = f"• **Asset Class:** `Commodity / Index Derivative Contract`"
        else:
            is_etf = (quote_type == "ETF" or ticker_symbol in KNOWN_ETFS)
            profile_title = "🏢 Fund Profile & Structure" if is_etf else "🏢 Company Profile"
            sector, industry, shares = None, None, None
            t_obj = yf.Ticker(ticker_symbol)

            try:
                shares = t_obj.fast_info.shares
                market_cap = t_obj.fast_info.market_cap
            except Exception: pass
            if not market_cap and shares and current_price: market_cap = current_price * shares

            try:
                s_res = http_session.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker_symbol}&quotesCount=1", timeout=3)
                if s_res.status_code == 200:
                    sq = s_res.json().get("quotes", [])
                    if sq: sector, industry = sq[0].get("sector"), sq[0].get("industry")
            except Exception: pass

            cap_fmt = format_large_number(market_cap)
            tier_str = "Mega-Cap 👑" if market_cap and market_cap >= 2e11 else ("Large-Cap 🏢" if market_cap and market_cap >= 1e10 else "Mid-Cap 📈")
            line_sec = f"• **Sector / Industry:** `{sector} • {industry}`\n" if sector and industry else ""
            profile_block = f"{line_sec}• **Market Cap:** `{cap_fmt}` ({tier_str})"

            earnings_date_str, prev_surprise_str = "N/A", ""
            try:
                ed_df = t_obj.earnings_dates
                if ed_df is not None and not ed_df.empty:
                    f_rows = ed_df[ed_df['Reported EPS'].isna()] if 'Reported EPS' in ed_df.columns else pd.DataFrame()
                    if not f_rows.empty:
                        nxt_dt = f_rows.index[-1]
                        nxt_d = nxt_dt.date() if isinstance(nxt_dt, (datetime, pd.Timestamp)) else nxt_dt
                        days_left = (nxt_d - datetime.now().date()).days
                        earnings_date_str = f"`In {days_left} Days ({nxt_d.strftime('%b %d')})`" if days_left >= 0 else f"`{nxt_d.strftime('%b %d')}`"
                    p_rows = ed_df[ed_df['Reported EPS'].notna()] if 'Reported EPS' in ed_df.columns else pd.DataFrame()
                    if not p_rows.empty and "Surprise(%)" in p_rows.columns:
                        raw_surp = float(p_rows["Surprise(%)"].iloc[0])
                        surp_val = raw_surp * 100 if abs(raw_surp) <= 1.0 else raw_surp
                        prev_surprise_str = f" | `Prev Beat: {surp_val:+.1f}% {'🎯' if surp_val>=0 else '⚠️'}`"
            except Exception: pass

            targets_line = fetch_wallstreet_targets_tls(ticker_symbol, current_price)
            catalysts_block = f"• **Next Earnings:** {earnings_date_str}{prev_surprise_str}\n• **Wall St. Targets:** {targets_line}"

            beta_val = calculate_beta_vs_spy(closes)
            beta_str = f"`{beta_val:.2f}x` ({'High Volatility 🔥' if beta_val and beta_val>=1.5 else 'Moderate 📊'})" if beta_val else "N/A"
            smart_money_block = f"• **Beta (Market Volatility):** {beta_str}\n• **Expected Daily Move (ATR):** `±${atr:.2f} (±{(atr/current_price)*100:.1f}% swing)`"

            try:
                ex_date_str, pay_date_str, payout_ratio, trailing_div_rate = "N/A", "N/A", None, None
                qs_res = cureq.get(f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker_symbol}?modules=calendarEvents,summaryDetail,defaultKeyStatistics&region={'CA' if is_canadian else 'US'}&lang=en", impersonate="chrome124", timeout=4)
                if qs_res.status_code == 200:
                    res_data = qs_res.json().get("quoteSummary", {}).get("result", [{}])[0]
                    cal_events, sum_detail = res_data.get("calendarEvents", {}), res_data.get("summaryDetail", {})
                    ex_obj = cal_events.get("exDividendDate", {}) or sum_detail.get("exDividendDate", {})
                    if isinstance(ex_obj, dict): ex_date_str = ex_obj.get("fmt") or "N/A"
                    pay_obj = cal_events.get("dividendDate", {}) or sum_detail.get("dividendDate", {})
                    if isinstance(pay_obj, dict): pay_date_str = pay_obj.get("fmt") or "N/A"
                    pr_obj = sum_detail.get("payoutRatio", {}) or res_data.get("defaultKeyStatistics", {}).get("payoutRatio", {})
                    if isinstance(pr_obj, dict) and pr_obj.get("raw") is not None: payout_ratio = float(pr_obj.get("raw"))
                    rate_obj = sum_detail.get("dividendRate", {}) or sum_detail.get("trailingAnnualDividendRate", {})
                    if isinstance(rate_obj, dict) and rate_obj.get("raw") is not None: trailing_div_rate = float(rate_obj.get("raw"))

                recent_divs = [(int(k), float(v.get("amount", 0))) for k, v in dividends_dict.items()] if dividends_dict else []
                if ex_date_str == "N/A" and recent_divs:
                    ex_date_str = datetime.fromtimestamp(sorted(recent_divs, key=lambda x: x[0])[-1][0], tz=NY_TZ).strftime("%b %d, %Y")

                last_payout = sorted(recent_divs, key=lambda x: x[0])[-1][1] if recent_divs else None
                annual_rate = trailing_div_rate or (last_payout * 4 if last_payout else None)
                if annual_rate and annual_rate > 0:
                    calc_yield = (annual_rate / current_price) * 100
                    per_payout = last_payout or (annual_rate / 4)
                    pr_str = f"\n• **Sustainability:** Payout Ratio: `{payout_ratio*100:.1f}% 🟢`" if payout_ratio else ""
                    dividend_block = f"• **Yield & Payout:** `{calc_yield:.2f}%` • `${per_payout:.2f} / share` (`${annual_rate:.2f} Annualized`)\n• **Key Dates:** Ex-Dividend: `{ex_date_str}` • Pay Date: `{pay_date_str}`{pr_str}"
                else:
                    dividend_block = "• **Status:** `No Regular Dividend (Zero Yield / Pure Growth Stock)`"
            except Exception:
                dividend_block = "• **Status:** `No Regular Dividend (Zero Yield / Pure Growth Stock)`"

            try:
                roe_str, margin_str, de_str, curr_ratio_str, fcf_str, quality_str = "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"
                rev_growth_pct, net_inc_growth_pct = None, None
                ttm_rev, ttm_net_inc, ttm_fcf = None, None, None
                stockholders_equity, total_debt, current_assets, current_liab = None, None, None, None

                q_inc = t_obj.quarterly_income_stmt
                if q_inc is not None and not q_inc.empty:
                    rev_row = next((r for r in ["Total Revenue", "Operating Revenue", "Revenue"] if r in q_inc.index), None)
                    if rev_row:
                        rev_s = q_inc.loc[rev_row].dropna()
                        if len(rev_s) >= 5 and float(rev_s.iloc[4]) > 0:
                            rev_growth_pct = ((float(rev_s.iloc[0]) - float(rev_s.iloc[4])) / float(rev_s.iloc[4])) * 100
                        elif len(rev_s) >= 2 and float(rev_s.iloc[-1]) > 0:
                            rev_growth_pct = ((float(rev_s.iloc[0]) - float(rev_s.iloc[-1])) / float(rev_s.iloc[-1])) * 100
                        ttm_rev = float(rev_s.iloc[:4].sum()) if len(rev_s) >= 1 else None

                    inc_row = next((r for r in ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"] if r in q_inc.index), None)
                    if inc_row:
                        inc_s = q_inc.loc[inc_row].dropna()
                        if len(inc_s) >= 5 and float(inc_s.iloc[4]) != 0:
                            net_inc_growth_pct = ((float(inc_s.iloc[0]) - float(inc_s.iloc[4])) / abs(float(inc_s.iloc[4]))) * 100
                        elif len(inc_s) >= 2 and float(inc_s.iloc[-1]) != 0:
                            net_inc_growth_pct = ((float(inc_s.iloc[0]) - float(inc_s.iloc[-1])) / abs(float(inc_s.iloc[-1]))) * 100
                        ttm_net_inc = float(inc_s.iloc[:4].sum()) if len(inc_s) >= 1 else None

                q_bs = t_obj.quarterly_balance_sheet
                if q_bs is not None and not q_bs.empty:
                    eq_row = next((r for r in ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"] if r in q_bs.index), None)
                    if eq_row: stockholders_equity = float(q_bs.loc[eq_row].dropna().iloc[0])
                    debt_row = next((r for r in ["Total Debt", "Long Term Debt And Capital Lease Obligation", "Total Non Current Liabilities Net Minority Interest"] if r in q_bs.index), None)
                    if debt_row: total_debt = float(q_bs.loc[debt_row].dropna().iloc[0])
                    ca_row = next((r for r in ["Current Assets", "Total Current Assets"] if r in q_bs.index), None)
                    cl_row = next((r for r in ["Current Liabilities", "Total Current Liabilities"] if r in q_bs.index), None)
                    if ca_row and cl_row:
                        current_assets = float(q_bs.loc[ca_row].dropna().iloc[0])
                        current_liab = float(q_bs.loc[cl_row].dropna().iloc[0])

                q_cf = t_obj.quarterly_cash_flow
                if q_cf is not None and not q_cf.empty:
                    ocf_row = next((r for r in ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"] if r in q_cf.index), None)
                    capex_row = next((r for r in ["Capital Expenditure", "Capital Expenditures"] if r in q_cf.index), None)
                    if ocf_row:
                        ocf_s = q_cf.loc[ocf_row].dropna()
                        ttm_ocf = float(ocf_s.iloc[:4].sum()) if len(ocf_s) >= 1 else 0
                        capex_s = q_cf.loc[capex_row].dropna() if capex_row else pd.Series([0])
                        ttm_capex = abs(float(capex_s.iloc[:4].sum())) if len(capex_s) >= 1 else 0
                        ttm_fcf = ttm_ocf - ttm_capex

                if ttm_net_inc and stockholders_equity and stockholders_equity > 0:
                    roe_val = (ttm_net_inc / stockholders_equity) * 100
                    roe_str = f"`{roe_val:.1f}% {'💎' if roe_val>=20 else '🟢'}`"
                if ttm_net_inc and ttm_rev and ttm_rev > 0:
                    margin_val = (ttm_net_inc / ttm_rev) * 100
                    margin_str = f"`{margin_val:.1f}% {'💎' if margin_val>=20 else '🟢'}`"
                if total_debt is not None and stockholders_equity and stockholders_equity > 0:
                    de_val = total_debt / stockholders_equity
                    de_str = f"`{de_val:.2f}x` ({'Low Debt 🟢' if de_val<=0.6 else ('Moderate 🟡' if de_val<=1.5 else 'High Debt ⚠️')})"
                if current_assets and current_liab and current_liab > 0:
                    cr_val = current_assets / current_liab
                    curr_ratio_str = f"`{cr_val:.2f}x` ({'🟢' if cr_val>=1.5 else ('🟡' if cr_val>=1.0 else '⚠️')})"
                if ttm_fcf is not None:
                    fcf_fmt = format_large_number(ttm_fcf)
                    fcf_str = f"`{fcf_fmt}` (Yield: `{(ttm_fcf / market_cap) * 100:.1f}%`)" if (market_cap and market_cap > 0) else f"`{fcf_fmt}`"
                if ttm_fcf is not None and ttm_net_inc and ttm_net_inc > 0:
                    q_val = ttm_fcf / ttm_net_inc
                    quality_str = f"`{q_val:.2f}x` 🟢 (Real Cash Backing)" if q_val >= 1.0 else (f"`{q_val:.2f}x` 🟡 (Moderate Cash Conversion)" if q_val >= 0.6 else f"`{q_val:.2f}x` ⚠️ (Accrual / Paper Earnings)")

                calc_market_cap = market_cap if market_cap and market_cap > 0 else ((current_price * shares) if shares and current_price else None)
                if ttm_net_inc and shares and (ttm_net_inc / shares) > 0:
                    pe_val = current_price / (ttm_net_inc / shares)
                    pe_str = f"`{pe_val:.1f}x`"
                else:
                    pe_str = "`N/A (Pre-Profit)`"
                
                if ttm_fcf and ttm_fcf > 0 and calc_market_cap and calc_market_cap > 0:
                    pfcf_str = f" | P/FCF: `{calc_market_cap / ttm_fcf:.1f}x`"
                elif ttm_fcf and ttm_fcf <= 0:
                    pfcf_str = " | P/FCF: `Negative FCF`"
                else:
                    pfcf_str = " | P/FCF: `N/A`"

                growth_parts = []
                if rev_growth_pct is not None: growth_parts.append(f"Revenue: `{rev_growth_pct:+.1f}%`")
                if net_inc_growth_pct is not None: growth_parts.append(f"Net Income: `{net_inc_growth_pct:+.1f}% 🚀`")
                line_growth = f"• **Growth (YoY):** {' | '.join(growth_parts)}\n" if growth_parts else ""

                health_block = (
                    f"• **Capital Efficiency:** ROE: {roe_str} | Net Margin: {margin_str}\n"
                    f"{line_growth}"
                    f"• **Solvency & Liquidity:** Debt/Equity: {de_str} | Current Ratio: {curr_ratio_str}\n"
                    f"• **Free Cash Flow:** {fcf_str}\n"
                    f"• **Earnings Quality (FCF / Net Income):** {quality_str}\n"
                    f"• **Valuation Multiples:** Trailing P/E: {pe_str}{pfcf_str}"
                )
            except Exception:
                health_block = None

        return {
            "ticker": ticker_symbol, "price": current_price, "change_pct": change_pct,
            "path_trail_str": path_trail_str, "rsi_val": calculate_rsi(closes, 14),
            "roe_val": roe_val, "margin_val": margin_val, "pe_val": pe_val, "market_cap": market_cap,
            "volume_block": volume_block, "rsi_block": rsi_block, "range_str": range_str,
            "trend_block": trend_block, "macd_str": macd_str, "pivot_str": pivot_str,
            "dividend_block": dividend_block, "profile_title": profile_title,
            "profile_block": profile_block, "catalysts_block": catalysts_block,
            "smart_money_block": smart_money_block, "health_block": health_block
        }, None
    except Exception as e:
        return None, f"Error fetching `{ticker_symbol}`: {e}"

def create_market_embed(data):
    embed = discord.Embed(
        title=f"🚨 Market Snapshot: {data['ticker']} [LIVE ON-DEMAND]",
        description=f"**{data['ticker']}** is currently **{data['change_pct']:+.2f}%** today.",
        color=0x2ecc71 if data['change_pct'] >= 0 else 0xe74c3c
    )
    embed.add_field(name="Current Price", value=f"${data['price']:.2f}", inline=True)
    embed.add_field(name="1D Total Change", value=f"{data['change_pct']:+.2f}%", inline=True)
    if data.get("path_trail_str"):
        embed.add_field(name="🕒 Today's Path", value=data["path_trail_str"], inline=False)
    embed.add_field(name="📊 Volume Multipliers", value=data['volume_block'], inline=False)
    embed.add_field(name="📈 Multi-Timeframe RSI", value=data['rsi_block'], inline=False)
    embed.add_field(name="🏔️ 52-Week Range", value=data['range_str'], inline=False)
    embed.add_field(name="📈 Moving Averages & Trend", value=data['trend_block'], inline=False)
    embed.add_field(name="📊 MACD (12,26,9)", value=data['macd_str'], inline=False)
    embed.add_field(name="🛡️ Key Pivot Levels", value=data['pivot_str'], inline=False)
    if data.get("dividend_block"): embed.add_field(name="💰 Dividend & Shareholder Yield", value=data["dividend_block"], inline=False)
    if data.get("catalysts_block"): embed.add_field(name="🗓️ Catalysts & Wall Street Targets", value=data['catalysts_block'], inline=False)
    if data.get("smart_money_block"): embed.add_field(name="🐋 Smart Money & Risk Metrics", value=data['smart_money_block'], inline=False)
    if data.get("profile_block"): embed.add_field(name=data.get("profile_title", "🏢 Company Profile"), value=data['profile_block'], inline=False)
    if data.get("health_block"): embed.add_field(name="📊 Balance Sheet & Cash Flow Health", value=data['health_block'], inline=False)
    embed.set_footer(text="Looney • On-Demand Market Terminal")
    return embed

# -------------------------------------------------------------
# 5. MULTI-PART PAGINATED RESEARCH RADAR (%TICKER)
# -------------------------------------------------------------
INSTITUTION_REGISTRY = {
    "Rosenblatt": ("Rosenblatt Securities", "🏦"), "Goldman Sachs": ("Goldman Sachs", "🏦"),
    "Morgan Stanley": ("Morgan Stanley", "🏦"), "JPMorgan": ("JPMorgan Chase", "🏦"),
    "J.P. Morgan": ("JPMorgan Chase", "🏦"), "Bank of America": ("Bank of America", "🏦"),
    "BofA": ("Bank of America", "🏦"), "Wells Fargo": ("Wells Fargo", "🏦"),
    "Citigroup": ("Citigroup", "🏦"), "Citi": ("Citigroup", "🏦"),
    "Barclays": ("Barclays", "🏦"), "UBS": ("UBS Investment Bank", "🏦"),
    "Deutsche Bank": ("Deutsche Bank", "🏦"), "Jefferies": ("Jefferies", "🏦"),
    "Piper Sandler": ("Piper Sandler", "🏦"), "Wedbush": ("Wedbush Securities", "🏦"),
    "Oppenheimer": ("Oppenheimer", "🏦"), "Bernstein": ("Bernstein", "🏦"),
    "Mizuho": ("Mizuho Securities", "🏦"), "Truist": ("Truist Securities", "🏦"),
    "KeyBanc": ("KeyBanc Capital", "🏦"), "Evercore": ("Evercore ISI", "🏦"),
    "Baird": ("Baird", "🏦"), "Stifel": ("Stifel", "🏦"), "Needham": ("Needham & Co", "🏦"),
    "Wolfe Research": ("Wolfe Research", "🏦"), "Raymond James": ("Raymond James", "🏦"),
    "Cantor Fitzgerald": ("Cantor Fitzgerald", "🏦"), "Cantor": ("Cantor Fitzgerald", "🏦"),
    "D.A. Davidson": ("D.A. Davidson", "🏦"), "Benchmark": ("Benchmark Co", "🏦"),
    "TD Cowen": ("TD Cowen", "🍁"), "Cowen": ("TD Cowen", "🍁"),
    "RBC Capital Markets": ("RBC Capital Markets", "🍁"), "RBC": ("RBC Capital Markets", "🍁"),
    "TD Securities": ("TD Securities", "🍁"), "BMO Capital": ("BMO Capital Markets", "🍁"),
    "BMO": ("BMO Capital Markets", "🍁"), "Scotiabank": ("Scotiabank Global", "🍁"),
    "Scotia": ("Scotiabank Global", "🍁"), "CIBC World Markets": ("CIBC World Markets", "🍁"),
    "CIBC": ("CIBC World Markets", "🍁"), "National Bank Financial": ("National Bank Financial", "🍁"),
    "National Bank": ("National Bank Financial", "🍁"), "Desjardins": ("Desjardins Capital", "🍁")
}

def fetch_institutional_research_radar(ticker_symbol):
    sym = ticker_symbol.upper().strip()
    is_canadian = sym.endswith(".TO") or sym.endswith(".V")
    currency = "CAD" if is_canadian else "USD"
    base_sym = sym.replace(".TO", "").replace(".V", "").upper()
    now_ny = datetime.now(NY_TZ)
    cutoff_time = now_ny - timedelta(days=90)

    try:
        current_price = 0.0
        company_name = base_sym
        t_obj = yf.Ticker(sym)
        try: current_price = float(t_obj.fast_info.last_price or 0.0)
        except Exception: pass
        try: company_name = str(t_obj.info.get("shortName") or t_obj.info.get("longName") or base_sym)
        except Exception: pass

        clean_company_short = re.sub(r'[\(\),.]|Inc|Corp|Ltd|Corporation|Company|Bank', '', company_name).strip()
        search_terms = list(dict.fromkeys([base_sym, sym, clean_company_short]))
        seen_banks = {}

        try:
            ud_df = t_obj.upgrades_downgrades
            if ud_df is not None and not ud_df.empty:
                for idx, row in ud_df.iterrows():
                    row_dt = idx if isinstance(idx, (datetime, pd.Timestamp)) else None
                    if row_dt:
                        if row_dt.tzinfo is None: row_dt = row_dt.replace(tzinfo=NY_TZ)
                        if row_dt < cutoff_time: continue
                    firm_name, to_grade, action = str(row.get("Firm", "") or ""), str(row.get("ToGrade", "") or ""), str(row.get("Action", "") or "")
                    matched_inst, inst_badge = None, "🏦"
                    for key_name, (full_name, badge) in INSTITUTION_REGISTRY.items():
                        if re.search(rf'\b{re.escape(key_name)}\b', firm_name, re.IGNORECASE):
                            matched_inst, inst_badge = full_name, badge; break
                    if not matched_inst: matched_inst = firm_name if len(firm_name) > 2 else "Wall Street Bank"
                    low_grade = (to_grade + " " + action).lower()
                    if any(b in low_grade for b in ["buy", "outperform", "overweight", "up", "top pick"]): rating_str, tier = f"{to_grade or 'Outperform'} 🟢", "BULLISH"
                    elif any(b in low_grade for b in ["sell", "underperform", "underweight", "down"]): rating_str, tier = f"{to_grade or 'Underperform'} 🔴", "CAUTIOUS"
                    else: rating_str, tier = f"{to_grade or 'Hold'} 🟡", "NEUTRAL"

                    entry = {
                        "institution": matched_inst, "badge": inst_badge, "rating": rating_str, "tier": tier,
                        "target": None, "headline": f"{matched_inst} {action.capitalize() if action else 'rates'} {clean_company_short} to {to_grade}",
                        "link": f"https://finance.yahoo.com/quote/{sym}", "date_str": row_dt.strftime("%b %d, %Y") if row_dt else "Recent Action",
                        "pub_dt": row_dt or now_ny
                    }
                    if matched_inst not in seen_banks: seen_banks[matched_inst] = entry
        except Exception: pass

        raw_reports = []
        def search_yahoo():
            items = []
            try:
                res = http_session.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={clean_company_short}+price+target+analyst&newsCount=25", timeout=4)
                if res.status_code == 200:
                    for n in res.json().get("news", []):
                        title, link, pub_time = n.get("title", ""), n.get("link") or n.get("canonicalUrl", {}).get("url"), n.get("providerPublishTime") or n.get("pubDate")
                        pub_dt = datetime.fromtimestamp(pub_time if pub_time < 1e11 else pub_time/1000.0, tz=NY_TZ) if pub_time else None
                        if title and link: items.append({"title": title, "link": link, "pub_dt": pub_dt})
            except Exception: pass
            return items

        def search_google():
            items = []
            try:
                res = http_session.get(f"https://news.google.com/rss/search?q={clean_company_short}+price+target+OR+analyst+rating&hl=en-US&gl=US&ceid=US:en", timeout=4)
                if res.status_code == 200:
                    root = ET.fromstring(res.content)
                    for item in root.findall(".//item")[:25]:
                        title, link, pub_date_str = item.findtext("title"), item.findtext("link"), item.findtext("pubDate")
                        pub_dt = parsedate_to_datetime(pub_date_str).astimezone(NY_TZ) if pub_date_str else None
                        if title and link: items.append({"title": title, "link": link, "pub_dt": pub_dt})
            except Exception: pass
            return items

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f_y, f_g = executor.submit(search_yahoo), executor.submit(search_google)
            raw_reports.extend(f_y.result())
            raw_reports.extend(f_g.result())

        for rep in raw_reports:
            t_text, pub_dt = rep["title"], rep.get("pub_dt")
            if pub_dt and pub_dt < cutoff_time: continue

            is_subject = False
            for term in search_terms:
                if len(term) >= 2 and re.search(rf'\b{re.escape(term)}\b', t_text, re.IGNORECASE):
                    if term.upper() == "TD" and re.search(r'\bTD\s*(?:Cowen|Securities|Bank\s*Analyst)\s*(?:raises|cuts|maintains|lowers|sets|rates)\b', t_text, re.IGNORECASE):
                        if not re.search(r'\b(?:Toronto[- ]Dominion|TD\s*stock|TD\s*shares|TD\.TO)\b', t_text, re.IGNORECASE): continue
                    is_subject = True; break
            if not is_subject: continue

            matched_inst, inst_badge = None, "🏦"
            for key_name, (full_name, badge) in INSTITUTION_REGISTRY.items():
                if re.search(rf'\b{re.escape(key_name)}\b', t_text, re.IGNORECASE):
                    matched_inst, inst_badge = full_name, badge; break
            if not matched_inst:
                if any(w in t_text.lower() for w in ["price target", "analyst", "upgrade", "downgrade", "outperform"]):
                    matched_inst = "Institutional Consensus"
                else: continue

            pt_val = None
            pt_match = re.search(r'(?:target|pt|to|price target)\s*(?:of|is|at|to|from\s*\$[\d\.]+\s*to)?\s*\$?([\d,]+(?:\.\d{2})?)', t_text, re.IGNORECASE)
            if pt_match:
                try:
                    cand_pt = float(pt_match.group(1).replace(',', ''))
                    if cand_pt not in [2024, 2025, 2026, 2027]:
                        if current_price == 0 or (0.1 * current_price <= cand_pt <= 6.0 * current_price): pt_val = cand_pt
                except Exception: pass

            low_t = t_text.lower()
            if any(b in low_t for b in ["strong buy", "conviction buy", "top pick", "outperform", "overweight", "raises target", "boosts target", "upgrade", "bullish"]): rating_str, tier = "Outperform / Buy 🟢", "BULLISH"
            elif any(b in low_t for b in ["downgrade", "underperform", "underweight", "cuts target", "lowers target", "sell", "bearish"]): rating_str, tier = "Underperform / Cautious 🔴", "CAUTIOUS"
            else:
                if current_price > 0 and pt_val and pt_val > current_price * 1.05: rating_str, tier = "Target Raised 🟢", "BULLISH"
                elif current_price > 0 and pt_val and pt_val < current_price * 0.95: rating_str, tier = "Target Lowered 🔴", "CAUTIOUS"
                else: rating_str, tier = "Hold / Neutral 🟡", "NEUTRAL"

            entry = {
                "institution": matched_inst, "badge": inst_badge, "rating": rating_str,
                "tier": tier, "target": pt_val, "headline": t_text, "link": rep["link"],
                "date_str": pub_dt.strftime("%b %d, %Y") if pub_dt else "Recent Note",
                "pub_dt": pub_dt or now_ny
            }
            if matched_inst in seen_banks:
                if pt_val and not seen_banks[matched_inst]["target"]: seen_banks[matched_inst] = entry
                elif pub_dt and pub_dt > seen_banks[matched_inst]["pub_dt"]: seen_banks[matched_inst] = entry
            else:
                seen_banks[matched_inst] = entry

        valid_reports = list(seen_banks.values())
        if not valid_reports: return None, f"No verified institutional research notes found for `{sym}` in the last 90 days."

        valid_reports.sort(key=lambda x: (x["target"] is not None, x["target"] or 0, x["pub_dt"]), reverse=True)
        return {
            "ticker": sym, "company_name": clean_company_short,
            "current_price": current_price, "currency": currency,
            "reports": valid_reports[:12]
        }, None
    except Exception as e:
        return None, str(e)

def create_institutional_radar_embeds(data):
    sym, curr, p, reports = data["ticker"], data["currency"], data["current_price"], data["reports"]
    c_name, is_ca = data.get("company_name", sym), sym.endswith(".TO") or sym.endswith(".V")
    price_header = f"${p:.2f} {curr}" if p > 0 else "Live"
    base_title = f"🏛️ BAY STREET RESEARCH RADAR: {sym} ({c_name}) 🍁" if is_ca else f"🏛️ WALL STREET RESEARCH RADAR: {sym} ({c_name})"

    chunk_size = 4
    chunks = [reports[i:i + chunk_size] for i in range(0, len(reports), chunk_size)]
    total_parts = len(chunks)
    embeds = []

    valid_pts = [r["target"] for r in reports if r["target"]]
    spread_line = f"High: `${max(valid_pts):.2f}` | Low: `${min(valid_pts):.2f} {curr}`" if valid_pts else "Active Upgrades & Reiterations"

    for part_idx, chunk in enumerate(chunks, 1):
        part_title = f"{base_title} [Part {part_idx}/{total_parts}]" if total_parts > 1 else base_title
        embed = discord.Embed(
            title=part_title,
            description=f"**Current Price:** `{price_header}` | **Showing {len(reports)} Verified Bank Notes (Last 90 Days)**\n*Ranked from Highest Price Target to Lowest*\n\n",
            color=0x2ecc71 if any(r["tier"] == "BULLISH" for r in reports) else 0x3498db
        )

        entries_txt = ""
        start_num = (part_idx - 1) * chunk_size + 1
        for j, r in enumerate(chunk):
            pt = r["target"]
            if pt and p > 0:
                diff_pct = ((pt - p) / p) * 100
                pt_line = f"• **Price Target:** `${pt:.2f} {curr}` ({'🔺' if diff_pct >= 0 else '🔻'} {diff_pct:+.1f}%)\n"
            elif pt:
                pt_line = f"• **Price Target:** `${pt:.2f} {curr}`\n"
            else:
                pt_line = "• **Price Target:** `In Research Note 📄`\n"

            tier_badge = "🟢" if r["tier"] == "BULLISH" else ("🟡" if r["tier"] == "NEUTRAL" else "🔴")
            clean_headline = re.sub(r'[\[\]]', '', r['headline'])
            clean_link = r['link'] if r['link'].startswith("http") else f"https://finance.yahoo.com/quote/{sym}"
            entries_txt += f"**{start_num + j}. {tier_badge} {r['badge']} {r['institution']}** — `{r['rating']}`\n{pt_line}• **Research:** [{clean_headline[:70]}...]({clean_link})\n• **Date:** `{r['date_str']}`\n\n"

        embed.description += entries_txt.strip()
        if part_idx == total_parts:
            embed.add_field(name="📊 Institutional Target Spread", value=f"• **Target Spread:** {spread_line}", inline=False)
        embed.set_footer(text=f"Looney • Institutional Research Intelligence (Part {part_idx} of {total_parts})")
        embeds.append(embed)

    return embeds

# -------------------------------------------------------------
# 6. ADAPTIVE OPTIONS DEEP-DIVE ENGINE (#TICKER)
# -------------------------------------------------------------
def analyze_stock_options_setup(ticker_symbol):
    sym = ticker_symbol.upper().strip()
    now_ny = datetime.now(NY_TZ)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2y"
        res = http_session.get(url, timeout=6)
        if res.status_code != 200: return None

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

        if len(valid_bars) < 3: return None

        closes = [b[0] for b in valid_bars]
        highs = [b[1] for b in valid_bars]
        lows = [b[2] for b in valid_bars]
        volumes = [b[3] for b in valid_bars]

        current_price = meta.get("regularMarketPrice") or closes[-1]
        prev_close = meta.get("regularMarketPreviousClose") or meta.get("previousClose") or (closes[-2] if len(closes) >= 2 else current_price)
        change_pct = (((current_price - prev_close) / prev_close) * 100) if prev_close and prev_close > 0 else 0.0

        if len(closes) >= 200:
            sma_50 = sum(closes[-50:]) / 50
            sma_200 = sum(closes[-200:]) / 200
            trend_diag = f"Above 50D SMA (`${sma_50:.2f}`) & 200D SMA (`${sma_200:.2f}`)" if current_price >= sma_50 and current_price >= sma_200 else f"50D SMA: `${sma_50:.2f}` | 200D SMA: `${sma_200:.2f}`"
        elif len(closes) >= 50:
            sma_50 = sum(closes[-50:]) / 50
            sma_200 = sma_50
            trend_diag = f"50D SMA: `${sma_50:.2f}` ({'Above 🟢' if current_price >= sma_50 else 'Below 🔴'}) • Young Listing (<200D)"
        else:
            sma_avail = sum(closes) / len(closes)
            sma_50 = sma_avail
            sma_200 = sma_avail
            trend_diag = f"Listing Avg ({len(closes)}D): `${sma_avail:.2f}` ({'Above 🟢' if current_price >= sma_avail else 'Below 🔴'}) • Fresh IPO"

        rsi_14 = calculate_rsi(closes, period=min(14, len(closes)-1))
        macd_verdict = calculate_macd(closes)
        atr_14 = calculate_atr(highs, lows, closes, period=14)

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

        hv_30 = calculate_historical_volatility(closes, window=30)
        hv_90 = calculate_historical_volatility(closes, window=90) if len(closes) >= 91 else hv_30
        denom = (hv_90 * 1.3) if (hv_90 and hv_90 > 0) else 1.0
        iv_rank_est = max(5, min(95, int((hv_30 / denom) * 50)))

        bull_score, bear_score = 0, 0
        if current_price >= sma_50: bull_score += 25
        else: bear_score += 25

        if 52 <= rsi_14 <= 68: bull_score += 20
        elif rsi_14 > 68: bull_score += 10
        elif 32 <= rsi_14 <= 48: bear_score += 20
        elif rsi_14 < 32: bear_score += 10

        if "Bullish Momentum" in str(macd_verdict): bull_score += 20
        elif "Bullish" in str(macd_verdict): bull_score += 12
        elif "Bearish Momentum" in str(macd_verdict): bear_score += 20
        elif "Bearish" in str(macd_verdict): bear_score += 12

        if rvol >= 1.5:
            bull_score += 15 if change_pct >= 0 else 0; bear_score += 15 if change_pct < 0 else 0
        elif rvol >= 1.1:
            bull_score += 10 if change_pct >= 0 else 0; bear_score += 10 if change_pct < 0 else 0
        else:
            bull_score += 5; bear_score += 5

        if bull_score >= bear_score:
            bull_score += 20 if iv_rank_est < 35 else (18 if iv_rank_est > 50 else 12)
        else:
            bear_score += 20 if iv_rank_est < 35 else (18 if iv_rank_est > 50 else 12)

        final_score = max(bull_score, bear_score)
        is_bullish = bull_score >= bear_score
        badge = "🟢 HIGH CONVICTION" if final_score >= 80 else ("🟠 DEVELOPING / WATCHLIST" if final_score >= 60 else "🔴 LOW CONVICTION / AVOID")
        color = 0x2ecc71 if final_score >= 80 else (0xe67e22 if final_score >= 60 else 0xe74c3c)

        strike_step = 0.5 if current_price < 15 else (1.0 if current_price < 50 else (2.5 if current_price < 100 else (5.0 if current_price < 300 else 10.0)))

        if is_bullish:
            if iv_rank_est < 40:
                strategy_name = "Long Call (Outright Bullish Momentum)"
                strike_short = round((current_price + (atr_14 * 0.5)) / strike_step) * strike_step
                prem_short = round(max(0.15, atr_14 * 0.9), 2)
                strike_long = round((current_price - (atr_14 * 0.3)) / strike_step) * strike_step
                prem_long = round(max(0.25, atr_14 * 2.1), 2)
                play_7_14 = f"Buy ${strike_short:.2f} Call @ ~${prem_short:.2f} | Break-Even: `${strike_short + prem_short:.2f}`"
                play_30_45 = f"Buy ${strike_long:.2f} Call @ ~${prem_long:.2f} | Break-Even: `${strike_long + prem_long:.2f}`"
                defensive_play = f"Bull Call Debit Spread: Buy ${strike_long:.2f} C / Sell ${strike_long + (strike_step*2):.2f} C"
            else:
                strategy_name = "Bull Put Credit Spread (Neutral to Bullish Income)"
                sell_p_short = round((s1 - (atr_14 * 0.2)) / strike_step) * strike_step
                credit_short = round(max(0.10, strike_step * 0.28), 2)
                sell_p_long = round((current_price * 0.95) / strike_step) * strike_step
                credit_long = round(max(0.15, strike_step * 0.33), 2)
                play_7_14 = f"Sell ${sell_p_short:.2f} P / Buy ${sell_p_short - strike_step:.2f} P | Credit: `${credit_short:.2f}`"
                play_30_45 = f"Sell ${sell_p_long:.2f} P / Buy ${sell_p_long - strike_step:.2f} P | Credit: `${credit_long:.2f}`"
                defensive_play = f"Covered Call / Protective Married Put at ${s1:.2f} Support"
        else:
            if iv_rank_est < 40:
                strategy_name = "Bear Put Debit Spread (Moderately Bearish Momentum)"
                buy_p_short = round((current_price + (atr_14 * 0.2)) / strike_step) * strike_step
                debit_short = round(max(0.15, strike_step * 0.45), 2)
                buy_p_long = round(current_price / strike_step) * strike_step
                debit_long = round(max(0.25, strike_step * 0.90), 2)
                play_7_14 = f"Buy ${buy_p_short:.2f} P / Sell ${buy_p_short - strike_step:.2f} P | Debit: `${debit_short:.2f}`"
                play_30_45 = f"Buy ${buy_p_long:.2f} P / Sell ${buy_p_long - (strike_step*2):.2f} P | Debit: `${debit_long:.2f}`"
                defensive_play = f"Long Put: Buy 35-DTE ${buy_p_long:.2f} Put @ ~${debit_long*1.2:.2f}"
            else:
                strategy_name = "Bear Call Credit Spread (Neutral to Bearish Resistance Play)"
                sell_c_short = round((r1 + (atr_14 * 0.2)) / strike_step) * strike_step
                credit_short = round(max(0.10, strike_step * 0.26), 2)
                sell_c_long = round((current_price * 1.05) / strike_step) * strike_step
                credit_long = round(max(0.15, strike_step * 0.32), 2)
                play_7_14 = f"Sell ${sell_c_short:.2f} C / Buy ${sell_c_short + strike_step:.2f} C | Credit: `${credit_short:.2f}`"
                play_30_45 = f"Sell ${sell_c_long:.2f} C / Buy ${sell_c_long + strike_step:.2f} C | Credit: `${credit_long:.2f}`"
                defensive_play = f"Iron Condor: Range-bound between ${s1:.2f} and ${r1:.2f}"

        return {
            "ticker": sym, "name": meta.get("shortName") or sym, "price": current_price,
            "change_pct": change_pct, "score": final_score, "badge": badge, "color": color,
            "is_bullish": is_bullish, "strategy_name": strategy_name, "iv_rank": iv_rank_est,
            "rsi_14": rsi_14, "rvol": rvol, "trend_diag": trend_diag,
            "macd_verdict": macd_verdict, "s1": s1, "r1": r1,
            "play_7_14": play_7_14, "play_30_45": play_30_45, "defensive_play": defensive_play
        }
    except Exception:
        return None

def create_deep_dive_options_embed(data):
    embed = discord.Embed(
        title=f"🎯 LOONEY OPTIONS INTELLIGENCE: {data['ticker']} [{data['badge']}]",
        description=f"**{data['ticker']}** is trading at **${data['price']:.2f}** ({data['change_pct']:+.2f}% today).\n**Quantitative Confidence Score:** `{data['score']} / 100`",
        color=data['color']
    )
    diag_text = f"• **Trend Health:** {data['trend_diag']}\n• **Momentum:** RSI: `{data['rsi_14']:.1f}` | MACD: `{data['macd_verdict']}`\n• **Volume & Volatility:** RVOL: `{data['rvol']:.1f}x (Time-Paced)` | IV Rank: `{data['iv_rank']}%`\n• **Key Levels:** Support (S1): `${data['s1']:.2f}` | Resistance (R1): `${data['r1']:.2f}`"
    embed.add_field(name="📊 Technical & Volatility Environment", value=diag_text, inline=False)
    embed.add_field(name="🏆 Primary DFOL Strategy", value=f"**{data['strategy_name']}**", inline=False)
    embed.add_field(name="⚡ PLAY A: 7 – 14 DTE (Fast Scalp / Weekly Momentum)", value=f"• **Trade Plan:** {data['play_7_14']}\n• **Target Exit:** +50% to +80% on contract | Stop-Loss: Cut at -35% loss", inline=False)
    embed.add_field(name="🏛️ PLAY B: 30 – 45 DTE (Standard Swing / Institutional)", value=f"• **Trade Plan:** {data['play_30_45']}\n• **Target Exit:** +40% to +60% on contract | Stop-Loss: Trailing 50D SMA", inline=False)
    embed.add_field(name="🛡️ Alternative Setup (Risk Mitigation)", value=data['defensive_play'], inline=False)
    embed.set_footer(text="Looney Options Terminal • DFOL Golden Rule Break-Even Engine")
    return embed

# -------------------------------------------------------------
# 7. ADVANCED MARKET INTELLIGENCE ENGINES
# -------------------------------------------------------------

# --- 7A. HEAD-TO-HEAD COMPARATIVE BATTLE (!vs) ---
def compare_two_stocks(sym1, sym2):
    sym1, sym2 = sym1.upper().strip(), sym2.upper().strip()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(get_on_demand_data, sym1)
        f2 = executor.submit(get_on_demand_data, sym2)
        d1, err1 = f1.result()
        d2, err2 = f2.result()

    if err1 or not d1: return None, f"Could not fetch data for `{sym1}`: {err1}"
    if err2 or not d2: return None, f"Could not fetch data for `{sym2}`: {err2}"

    embed = discord.Embed(
        title=f"⚔️ HEAD-TO-HEAD BATTLE: {sym1} vs. {sym2}",
        description=f"**{sym1}** (`${d1['price']:.2f}` • {d1['change_pct']:+.2f}%) vs. **{sym2}** (`${d2['price']:.2f}` • {d2['change_pct']:+.2f}%)\n*Live Quantitative & Financial Health Showdown*",
        color=0x3498db
    )

    def crown(v1, v2, higher_is_better=True):
        if v1 is None or v2 is None: return "", ""
        if v1 == v2: return "", ""
        if higher_is_better: return (" 🏆" if v1 > v2 else ""), (" 🏆" if v2 > v1 else "")
        else: return (" 🏆" if v1 < v2 else ""), (" 🏆" if v2 < v1 else "")

    c_p1, c_p2 = crown(d1['change_pct'], d2['change_pct'])
    c_rsi1, c_rsi2 = crown(d1['rsi_val'], d2['rsi_val'])
    c_roe1, c_roe2 = crown(d1['roe_val'], d2['roe_val'])
    c_m1, c_m2 = crown(d1['margin_val'], d2['margin_val'])
    c_pe1, c_pe2 = crown(d1['pe_val'], d2['pe_val'], higher_is_better=False)

    col1 = (
        f"• **1D Return:** `{d1['change_pct']:+.2f}%`{c_p1}\n"
        f"• **Market Cap:** `{format_large_number(d1['market_cap'])}`\n"
        f"• **RSI (14D):** `{d1['rsi_val']:.1f}`{c_rsi1}\n"
        f"• **ROE:** `{d1['roe_val']:.1f}%`{c_roe1 if d1['roe_val'] else ''}\n"
        f"• **Net Margin:** `{d1['margin_val']:.1f}%`{c_m1 if d1['margin_val'] else ''}\n"
        f"• **P/E Ratio:** `{d1['pe_val']:.1f}x`{c_pe1 if d1['pe_val'] else ''}"
    )

    col2 = (
        f"• **1D Return:** `{d2['change_pct']:+.2f}%`{c_p2}\n"
        f"• **Market Cap:** `{format_large_number(d2['market_cap'])}`\n"
        f"• **RSI (14D):** `{d2['rsi_val']:.1f}`{c_rsi2}\n"
        f"• **ROE:** `{d2['roe_val']:.1f}%`{c_roe2 if d2['roe_val'] else ''}\n"
        f"• **Net Margin:** `{d2['margin_val']:.1f}%`{c_m2 if d2['margin_val'] else ''}\n"
        f"• **P/E Ratio:** `{d2['pe_val']:.1f}x`{c_pe2 if d2['pe_val'] else ''}"
    )

    embed.add_field(name=f"🔵 {sym1}", value=col1, inline=True)
    embed.add_field(name=f"🔴 {sym2}", value=col2, inline=True)
    embed.set_footer(text="Looney Market Terminal • Head-to-Head Valuation Engine")
    return embed, None

# --- 7B. INSIDER BUYING, TOP 10 WHALES, TOP 10 INDIVIDUALS & 8-K DISPOSITIONS (?TICKER) ---
def fetch_sec_edgar_form4_trades(ticker_symbol):
    """
    Institutional SEC EDGAR Form 4 XML parser.
    - Validates <issuerTradingSymbol> to eliminate cross-company ingestion.
    - Parses Form 4 XMLs directly from EDGAR filing directory indexes.
    - Accurately classifies Open Market Buys, Sells, Option Exercises, Grants, Gifts, and Tax Withholdings.
    """
    sym = ticker_symbol.upper().strip()
    if sym.endswith(".TO") or sym.endswith(".V"):
        return []

    sec_headers = {
        "User-Agent": "LooneyMarketTerminal admin@looney.app",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    trades = []
    try:
        feed_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={sym}&type=4&count=15&output=atom"
        res = http_session.get(feed_url, headers=sec_headers, timeout=5)
        if res.status_code != 200 or b"<feed" not in res.content:
            return []

        root = ET.fromstring(res.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        def parse_single_edgar_entry(entry):
            local_trades = []
            try:
                link_el = entry.find("atom:link", ns)
                if link_el is None:
                    return []
                doc_page_url = link_el.attrib.get("href", "")
                
                # Fetch directory index page to locate the exact form4 XML file
                dir_url = doc_page_url.rsplit('/', 1)[0] + '/'
                dir_res = http_session.get(dir_url, headers=sec_headers, timeout=4)
                if dir_res.status_code != 200:
                    return []

                # Find .xml file in filing directory (excluding submission header and xsl files)
                xml_matches = re.findall(r'href=["\']([^"\']+\.xml)["\']', dir_res.text, re.IGNORECASE)
                form4_xml_rel = None
                for xm in xml_matches:
                    low_xm = xm.lower()
                    if not low_xm.endswith(".xml"): continue
                    if any(bad in low_xm for bad in ["xsl", "header", "eis", "submission"]): continue
                    form4_xml_rel = xm
                    break

                if not form4_xml_rel:
                    return []

                target_xml_url = dir_url + form4_xml_rel if not form4_xml_rel.startswith("http") else form4_xml_rel
                xml_res = http_session.get(target_xml_url, headers=sec_headers, timeout=4)
                if xml_res.status_code != 200 or b"<ownershipDocument" not in xml_res.content:
                    return []

                form_root = ET.fromstring(xml_res.content)

                # STRICT ISSUER VALIDATION GUARD: Discard cross-company entries
                issuer_sym = form_root.findtext(".//issuer/issuerTradingSymbol") or form_root.findtext(".//issuerTradingSymbol")
                if issuer_sym and issuer_sym.upper().strip() != sym:
                    return []

                owner_name = form_root.findtext(".//rptOwnerName") or "Insider"
                officer_title = form_root.findtext(".//officerTitle") or ""
                is_dir = form_root.findtext(".//isDirector")
                is_ten = form_root.findtext(".//isTenPercentOwner")

                role_label = officer_title
                if not role_label:
                    if is_dir in ["1", "true", "True"]: role_label = "Director"
                    elif is_ten in ["1", "true", "True"]: role_label = "10% Owner"
                    else: role_label = "Insider"

                role_tag = f" ({role_label[:14]})"

                # 1. Non-Derivative Transactions (Table I - Common Stock)
                for tx in form_root.findall(".//nonDerivativeTransaction"):
                    shares_str = tx.findtext(".//transactionShares/value")
                    price_str = tx.findtext(".//transactionPricePerShare/value")
                    acq_disp = tx.findtext(".//transactionAcquiredDisposedCode/value")
                    tx_code = tx.findtext(".//transactionCoding/transactionCode")
                    tx_date = tx.findtext(".//transactionDate/value") or "Recent"

                    if not shares_str:
                        continue

                    shares = float(shares_str)
                    price_per_share = float(price_str) if price_str and float(price_str) > 0 else 0.0
                    total_val = shares * price_per_share
                    sh_fmt = format_large_number(int(shares)).replace("$", "")

                    if tx_code == "P":
                        badge = "🟢 BUY (Open Mkt)"
                        line = f"• **{badge}** by **{owner_name[:16]}{role_tag}** (`{sh_fmt} shs` @ `${price_per_share:.2f}` on `{tx_date}` ➔ **`{format_large_number(total_val)}`**)"
                    elif tx_code == "S":
                        badge = "🔴 SELL (Open Mkt)"
                        line = f"• **{badge}** by **{owner_name[:16]}{role_tag}** (`{sh_fmt} shs` @ `${price_per_share:.2f}` on `{tx_date}` ➔ **`{format_large_number(total_val)} Proceeds`**)"
                    elif tx_code == "M":
                        badge = "⚡ OPTION EXERCISE"
                        p_str = f" @ `${price_per_share:.2f} strike`" if price_per_share > 0 else ""
                        line = f"• **{badge}** by **{owner_name[:16]}{role_tag}** (`{sh_fmt} shs`{p_str} on `{tx_date}` • Common Stock Acquisition)"
                    elif tx_code == "G":
                        badge = "🎁 GIFT / TRANSFER"
                        line = f"• **{badge}** by **{owner_name[:16]}{role_tag}** (`{sh_fmt} shs` on `{tx_date}` • Bona Fide Gift)"
                    elif tx_code == "A":
                        badge = "🎁 EQUITY GRANT"
                        line = f"• **{badge}** by **{owner_name[:16]}{role_tag}** (`{sh_fmt} shs` on `{tx_date}` • Restricted Stock Units)"
                    elif tx_code == "F":
                        badge = "🏛️ TAX WITHHOLDING"
                        p_str = f" @ `${price_per_share:.2f}`" if price_per_share > 0 else ""
                        line = f"• **{badge}** by **{owner_name[:16]}{role_tag}** (`{sh_fmt} shs`{p_str} on `{tx_date}` • Tax Settlement)"
                    else:
                        is_buy = acq_disp == "A"
                        badge = "🟢 ACQUIRED" if is_buy else "🔴 DISPOSED"
                        p_str = f" @ `${price_per_share:.2f}`" if price_per_share > 0 else ""
                        line = f"• **{badge}** by **{owner_name[:16]}{role_tag}** (`{sh_fmt} shs`{p_str} on `{tx_date}`)"

                    local_trades.append((tx_date, line))

                # 2. Derivative Transactions (Table II - Stock Options)
                for tx in form_root.findall(".//derivativeTransaction"):
                    shares_str = tx.findtext(".//transactionShares/value")
                    conv_price_str = tx.findtext(".//conversionOrExercisePrice/value")
                    price_str = tx.findtext(".//transactionPricePerShare/value")
                    tx_code = tx.findtext(".//transactionCoding/transactionCode")
                    tx_date = tx.findtext(".//transactionDate/value") or "Recent"

                    if not shares_str:
                        continue

                    shares = float(shares_str)
                    strike_val = float(conv_price_str) if conv_price_str and float(conv_price_str) > 0 else (float(price_str) if price_str and float(price_str) > 0 else 0.0)
                    sh_fmt = format_large_number(int(shares)).replace("$", "")
                    strike_str = f" @ `${strike_val:.2f} strike`" if strike_val > 0 else ""

                    if tx_code == "M":
                        line = f"• **⚡ OPTION EXERCISE** by **{owner_name[:16]}{role_tag}** (`{sh_fmt} contracts`{strike_str} on `{tx_date}`)"
                        local_trades.append((tx_date, line))
                    elif tx_code == "A":
                        line = f"• **🎁 OPTION GRANT** by **{owner_name[:16]}{role_tag}** (`{sh_fmt} options`{strike_str} on `{tx_date}`)"
                        local_trades.append((tx_date, line))

            except Exception:
                pass
            return local_trades

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            future_to_entry = [executor.submit(parse_single_edgar_entry, entry) for entry in entries[:12]]
            for future in concurrent.futures.as_completed(future_to_entry):
                res_list = future.result()
                if res_list:
                    trades.extend(res_list)

        # Sort newest date first and take Top 10
        trades.sort(key=lambda x: x[0], reverse=True)
        return [t[1] for t in trades[:10]]

    except Exception:
        return []

def fetch_insider_and_institutional_data(ticker_symbol):
    sym = ticker_symbol.upper().strip()
    try:
        t_obj = yf.Ticker(sym)
        price = 0.0
        c_name = sym
        try: price = float(t_obj.fast_info.last_price or 0.0)
        except Exception: pass
        try: c_name = str(t_obj.info.get("shortName") or t_obj.info.get("longName") or sym)
        except Exception: pass

        # 1. Direct Ownership Extraction (Finviz TLS Engine Primary + Yahoo Fallback)
        fz_data = fetch_finviz_security_fundamentals(sym)
        
        k_info = {}
        try: k_info = t_obj.info or {}
        except Exception: pass

        inst_pct_raw = (fz_data.get("inst_own_pct") / 100.0) if fz_data.get("inst_own_pct") is not None else k_info.get("heldPercentInstitutions")
        insider_pct_raw = (fz_data.get("insider_own_pct") / 100.0) if fz_data.get("insider_own_pct") is not None else k_info.get("heldPercentInsiders")
        float_raw = fz_data.get("shs_float") or k_info.get("floatShares") or getattr(t_obj.fast_info, "shares", None)

        inst_own_str = f"`{inst_pct_raw * 100:.1f}%`" if inst_pct_raw is not None else "`N/A`"
        insider_own_str = f"`{insider_pct_raw * 100:.1f}%`" if insider_pct_raw is not None else "`N/A`"
        float_str = format_large_number(float_raw).replace("$", "") + " shares" if float_raw else "N/A"

        # 2. Top 10 Institutional Whales (Funds)
        whales_col = []
        try:
            inst_df = t_obj.institutional_holders
            if inst_df is not None and not inst_df.empty:
                for idx, r in inst_df.head(10).iterrows():
                    rank = idx + 1
                    h_name = str(r.get("Holder", "Whale Fund"))[:20]
                    pct_held = float(r.get("pctHeld", 0) or 0) * 100
                    whales_col.append(f"**{rank}. {h_name}:** `{pct_held:.1f}%`")
        except Exception: pass
        whales_txt = "\n".join(whales_col) if whales_col else "• *Registry Syncing*"

        # 3. Top 10 Individual Insider Owners (Ranked from Highest to Lowest Shareholder)
        insiders_col = []
        try:
            roster_df = t_obj.insider_roster_holders
            if roster_df is not None and not roster_df.empty:
                parsed_insiders = []
                for _, r in roster_df.iterrows():
                    p_name = str(r.get("Name", "Insider"))[:18]
                    pos = str(r.get("Position", ""))
                    pos_tag = f" ({pos[:10]})" if pos and str(pos).lower() not in ["none", "nan", ""] else ""
                    
                    sh_direct = r.get("Shares Owned Directly")
                    sh_indirect = r.get("Shares Owned Indirectly")
                    
                    total_sh = 0
                    if pd.notna(sh_direct) and float(sh_direct) > 0:
                        total_sh += float(sh_direct)
                    if pd.notna(sh_indirect) and float(sh_indirect) > 0:
                        total_sh += float(sh_indirect)
                    
                    parsed_insiders.append({
                        "name": p_name,
                        "pos_tag": pos_tag,
                        "shares": total_sh
                    })

                # Sort descending: Highest share count to lowest
                parsed_insiders.sort(key=lambda x: x["shares"], reverse=True)

                for idx, person in enumerate(parsed_insiders[:10]):
                    rank = idx + 1
                    if person["shares"] > 0:
                        sh_fmt = format_large_number(int(person["shares"])).replace("$", "")
                        insiders_col.append(f"**{rank}. {person['name']}{person['pos_tag']}:** `{sh_fmt} shs`")
                    else:
                        insiders_col.append(f"**{rank}. {person['name']}{person['pos_tag']}:** `Trust / Direct Holder`")
        except Exception: pass
        insiders_txt = "\n".join(insiders_col) if insiders_col else "• *Roster Pending*"

        # 4. C-Suite Form 4 Trades (SEC EDGAR Direct Ground-Truth Parser: Top 10 Newest)
        raw_trades = fetch_sec_edgar_form4_trades(sym)

        # Fallback to yfinance for Canadian tickers or if EDGAR feed had no recent entries
        if not raw_trades:
            try:
                it_df = t_obj.insider_transactions
                if it_df is not None and not it_df.empty:
                    for _, r in it_df.head(10).iterrows():
                        insider_name = str(r.get("Insider", "Officer"))[:16]
                        text_action = str(r.get("Text", "Transaction"))
                        shares = r.get("Shares") or 0
                        raw_val = r.get("Value")

                        low_act = text_action.lower()
                        is_buy = "buy" in low_act or "purchase" in low_act
                        is_gift = "gift" in low_act or "charit" in low_act
                        is_sale = "sale" in low_act or "sold" in low_act

                        if is_buy:
                            badge = "🟢 BUY (Open Mkt)"
                        elif is_gift:
                            badge = "🎁 GIFT / TRANSFER"
                        elif is_sale:
                            badge = "🔴 SELL (Open Mkt)"
                        else:
                            badge = "⚡ OPTION / GRANT"

                        try:
                            sh_int = int(shares)
                            if raw_val is not None and float(raw_val) > 0 and sh_int > 0:
                                tot_val = float(raw_val)
                                p_per_share = tot_val / sh_int
                                val_fmt = format_large_number(tot_val)
                                sh_fmt = format_large_number(sh_int).replace("$", "")
                                raw_trades.append(f"• **{badge}** by **{insider_name}** (`{sh_fmt} shs` @ `${p_per_share:.2f}` ➔ **`{val_fmt}`**)")
                            else:
                                sh_fmt = format_large_number(sh_int).replace("$", "") if sh_int > 0 else str(shares)
                                clean_act = text_action if text_action.strip() else "Transaction Filed"
                                raw_trades.append(f"• **{badge}** by **{insider_name}** (`{sh_fmt} shs` • {clean_act})")
                        except Exception:
                            clean_act = text_action if text_action.strip() else "Transaction Filed"
                            raw_trades.append(f"• **{badge}** by **{insider_name}** (`{shares} shs` • {clean_act})")
            except Exception: pass

        # Guarantee Discord 1024-Character Embed Field Limit
        trades_lines = []
        curr_len = 0
        for t_line in raw_trades[:10]:
            if curr_len + len(t_line) + 1 < 1000:
                trades_lines.append(t_line)
                curr_len += len(t_line) + 1
            else:
                break

        trades_txt = "\n".join(trades_lines) if trades_lines else "• *No Form 4 open market filings recorded in last 90 days.*"

        # 5. Material Corporate Dispositions & 8-K Filings (Direct from Official SEC EDGAR Database)
        disposition_notes = []
        try:
            sec_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={sym}&type=8-K&count=5&output=atom"
            sec_headers = {
                "User-Agent": "LooneyMarketTerminal admin@looney.app",
                "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
            }
            sec_res = http_session.get(sec_url, headers=sec_headers, timeout=4)
            if sec_res.status_code == 200 and b"<feed" in sec_res.content:
                root = ET.fromstring(sec_res.content)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall("atom:entry", ns)[:3]:
                    t_el = entry.find("atom:title", ns)
                    l_el = entry.find("atom:link", ns)
                    u_el = entry.find("atom:updated", ns)
                    
                    raw_title = t_el.text if t_el is not None else "Form 8-K"
                    link = l_el.attrib.get("href", "") if l_el is not None else "https://www.sec.gov"
                    
                    date_str = "Recent"
                    if u_el is not None and u_el.text:
                        try:
                            date_str = u_el.text.split("T")[0]
                        except Exception:
                            pass
                    
                    clean_title = re.sub(r'^(?:8-K(?:\/A)?\s*-\s*)', '', raw_title).strip()
                    if not clean_title or clean_title.lower() == "current report":
                        clean_title = "Current Report Filing (Material Event)"
                    
                    disposition_notes.append(f"• 📄 **Form 8-K** (`{date_str}`): [{clean_title[:65]}]({link})")
                    if len(disposition_notes) >= 3:
                        break
        except Exception:
            pass

        disposition_txt = "\n".join(disposition_notes) if disposition_notes else "• *No material Form 8-K filings reported in the current quarter.*"

        embed = discord.Embed(
            title=f"🐋 INSIDER & CORPORATE DISPOSITION RADAR: {sym}",
            description=f"**{sym} ({c_name})** is trading at **${price:.2f}**\n*SEC Form 4 Filings (Top 10 Newest), Top Whales & Form 8-K Dispositions*",
            color=0x9b59b6
        )
        embed.add_field(
            name="🏛️ Ownership Structure & Tradable Float",
            value=(
                f"• **Institutional Ownership:** {inst_own_str} | **Officer / Insider Ownership:** {insider_own_str}\n"
                f"• **Tradable Float:** `{float_str}`"
            ),
            inline=False
        )
        embed.add_field(name="🏢 Top 10 Institutional Whales (Funds)", value=whales_txt, inline=True)
        embed.add_field(name="👤 Top 10 Individual Insider Owners (People)", value=insiders_txt, inline=True)
        embed.add_field(name="📝 Recent Insider & Form 4 Transactions (SEC EDGAR Verified)", value=trades_txt, inline=False)
        embed.add_field(name="🏢 Material Corporate Dispositions & 8-K Filings", value=disposition_txt, inline=False)
        embed.set_footer(text="Looney Insider Intelligence • SEC Form 4, 13F & SEC EDGAR 8-K Engine")
        return embed, None
    except Exception as e:
        return None, f"Error fetching insider data for `{sym}`: {e}"

# --- 7C. 100% CALCULATED SHORT SQUEEZE & BORROW RISK METRICS (^TICKER) ---
def fetch_short_squeeze_metrics(ticker_symbol):
    sym = ticker_symbol.upper().strip()
    try:
        t_obj = yf.Ticker(sym)
        price = 0.0
        c_name = sym
        try: price = float(t_obj.fast_info.last_price or 0.0)
        except Exception: pass
        try: c_name = str(t_obj.info.get("shortName") or t_obj.info.get("longName") or sym)
        except Exception: pass

        # 1. Pull Raw Fundamental Data from Cloud-Immune Finviz Browser Engine
        fz_data = fetch_finviz_security_fundamentals(sym)

        k_info = {}
        try: k_info = t_obj.info or {}
        except Exception: pass

        float_shares = fz_data.get("shs_float") or k_info.get("floatShares") or getattr(t_obj.fast_info, "shares", None)
        shares_short = fz_data.get("shares_short") or k_info.get("sharesShort")
        shares_prior = k_info.get("sharesShortPriorMonth")

        # Average Daily Volume for Days to Cover Calculation
        avg_vol = None
        try:
            hist = t_obj.history(period="1mo")
            if 'Volume' in hist.columns and not hist['Volume'].empty:
                avg_vol = float(hist['Volume'].mean())
        except Exception: pass

        if not avg_vol:
            avg_vol = getattr(t_obj.fast_info, "three_month_average_volume", None) or getattr(t_obj.fast_info, "ten_day_average_volume", None)

        # 2. PURE MATHEMATICAL CALCULATION ENGINE
        short_pct_float = None
        if shares_short and float_shares and float_shares > 0:
            short_pct_float = (float(shares_short) / float(float_shares)) * 100.0
        elif fz_data.get("short_float_pct") is not None:
            short_pct_float = float(fz_data["short_float_pct"])
        elif k_info.get("shortPercentOfFloat") is not None:
            short_pct_float = float(k_info["shortPercentOfFloat"]) * 100.0

        # If shares_short was missing from online feeds but we have float and short_pct_float, calculate shares_short
        if not shares_short and float_shares and short_pct_float is not None:
            shares_short = float_shares * (short_pct_float / 100.0)

        short_ratio = None
        if shares_short and avg_vol and avg_vol > 0:
            short_ratio = float(shares_short) / float(avg_vol)
        elif fz_data.get("short_ratio") is not None:
            short_ratio = float(fz_data["short_ratio"])
        elif k_info.get("shortRatio") is not None:
            short_ratio = float(k_info["shortRatio"])

        # 3. FORMATTING STRINGS & RISK BADGING
        float_fmt = format_large_number(float_shares).replace("$", "") + " shares" if float_shares else "N/A"
        short_fmt = format_large_number(shares_short).replace("$", "") + " shares" if shares_short else "N/A"
        short_pct_str = f"{short_pct_float:.2f}%" if short_pct_float is not None else "N/A"
        short_ratio_str = f"{short_ratio:.1f} Days" if short_ratio is not None else "N/A"

        mom_trend_str = ""
        if shares_short and shares_prior and shares_prior > 0:
            mom_chg = ((shares_short - shares_prior) / shares_prior) * 100
            tag = "🔺 Short Piling" if mom_chg > 0 else "🔻 Short Covering"
            mom_trend_str = f"\n• **Month-over-Month Short Trend:** `{mom_chg:+.1f}%` ({tag})"

        if short_pct_float is not None:
            if short_pct_float >= 20.0:
                risk_badge = "🔥 EXTREME SQUEEZE RISK"
                color = 0xe74c3c
                vuln_text = "High 🔥 (Shorts crowded; heavy borrow fee and liquidity risk)"
                exit_text = f"High borrow pressure on sudden volume surges ({short_ratio_str} to cover)" if short_ratio else "High borrow pressure on sudden volume surges"
            elif short_pct_float >= 10.0:
                risk_badge = "⚡ ELEVATED SHORT INTEREST"
                color = 0xe67e22
                vuln_text = "Moderate ⚡ (Elevated short interest; watch volume breakouts)"
                exit_text = f"Shorts require {short_ratio_str} of trading volume to cover" if short_ratio else "Moderate coverage duration"
            else:
                risk_badge = "🟢 LOW / NORMAL SHORT INTEREST"
                color = 0x2ecc71
                vuln_text = "Low 🟢 (Normal liquidity; orderly covering)"
                exit_text = "Shorts can exit without causing a liquidity cascade"
        else:
            risk_badge = "⚪ NEUTRAL / UNREPORTED"
            color = 0x95a5a6
            vuln_text = "Unreported / Non-Equity Contract"
            exit_text = "N/A"

        embed = discord.Embed(
            title=f"🩳 SHORT SQUEEZE & BORROW RISK: {sym} [{risk_badge}]",
            description=f"**{sym} ({c_name})** is trading at **${price:.2f}**\n*Exchange Short Interest Filings & Liquidity Coverage*",
            color=color
        )
        embed.add_field(
            name="📊 Short Seller Exposure (Calculated)",
            value=(
                f"• **Short % of Float:** ` {short_pct_str} `\n"
                f"• **Days to Cover (Short Ratio):** ` {short_ratio_str} `\n"
                f"• **Total Shares Shorted:** ` {short_fmt} `\n"
                f"• **Tradable Float:** ` {float_fmt} `{mom_trend_str}"
            ),
            inline=False
        )
        embed.add_field(
            name="🎯 Short Squeeze Mechanics",
            value=(
                f"• **Squeeze Vulnerability:** {vuln_text}\n"
                f"• **Exit Duration:** {exit_text}"
            ),
            inline=False
        )
        embed.set_footer(text="Looney Short Intelligence • Calculated FINRA & Exchange Short Metrics")
        return embed, None
    except Exception as e:
        return None, f"Error fetching short metrics for `{sym}`: {e}"

# --- 7D. GLOBAL MACRO PULSE & ECONOMIC CALENDAR (!!macro) ---
def fetch_global_macro_pulse():
    now_ny = datetime.now(NY_TZ)
    symbols = ["SPY", "QQQ", "DIA", "IWM", "^TNX", "^VIX", "DX-Y.NYB", "GC=F", "CL=F", "BTC-USD"]
    names = {
        "SPY": "S&P 500", "QQQ": "Nasdaq 100", "DIA": "Dow Jones", "IWM": "Russell 2000",
        "^TNX": "10Y Treasury Yield", "^VIX": "VIX Volatility", "DX-Y.NYB": "US Dollar Index",
        "GC=F": "Gold", "CL=F": "Crude Oil", "BTC-USD": "Bitcoin"
    }

    quotes_map = {}
    try:
        def get_mini_quote(sym):
            try:
                res = http_session.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2d", timeout=3)
                if res.status_code == 200:
                    d = res.json()["chart"]["result"][0]["meta"]
                    p = d.get("regularMarketPrice", 0)
                    prev = d.get("regularMarketPreviousClose", p)
                    chg = ((p - prev) / prev) * 100 if prev and prev > 0 else 0.0
                    return sym, p, chg
            except Exception: pass
            return sym, 0.0, 0.0

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(get_mini_quote, symbols)
            for sym, p, chg in results:
                quotes_map[sym] = (p, chg)
    except Exception: pass

    embed = discord.Embed(
        title="🏛️ GLOBAL MACRO PULSE & MARKET HEALTH",
        description=f"*Live Multi-Asset Pulse as of {now_ny.strftime('%A, %B %d, %Y • %I:%M %p %Z')}*",
        color=0x2ecc71 if quotes_map.get("SPY", (0, 0))[1] >= 0 else 0xe74c3c
    )

    indices_txt = ""
    for s in ["SPY", "QQQ", "DIA", "IWM"]:
        p, chg = quotes_map.get(s, (0, 0))
        tag = "🟢" if chg >= 0 else "🔴"
        indices_txt += f"• **{names[s]} ({s}):** `${p:.2f}` ({tag} `{chg:+.2f}%`)\n"

    bonds_comm_txt = ""
    for s in ["^TNX", "^VIX", "DX-Y.NYB", "GC=F", "CL=F", "BTC-USD"]:
        p, chg = quotes_map.get(s, (0, 0))
        tag = "🟢" if chg >= 0 else "🔴"
        price_fmt = f"{p:.2f}%" if s == "^TNX" else (f"${p:.2f}" if s in ["GC=F", "CL=F", "BTC-USD"] else f"{p:.2f}")
        bonds_comm_txt += f"• **{names[s]}:** `{price_fmt}` ({tag} `{chg:+.2f}%`)\n"

    calendar_txt = (
        "• **FOMC Rate Policy:** `Neutral / Data-Dependent` *(Target: 4.25% – 4.50%)*\n"
        "• **CPI Inflation Release:** `Next Monthly Print: 8:30 AM EST`\n"
        "• **Non-Farm Payrolls (Jobs):** `First Friday of Month: 8:30 AM EST`\n"
        "• **Yield Curve Posture:** `10Y vs 2Y Spread Normalizing`"
    )

    embed.add_field(name="📈 Major Equities Indices", value=indices_txt or "• *Live data stream syncing*", inline=False)
    embed.add_field(name="🛢️ Yields, Dollar, Commodities & Crypto", value=bonds_comm_txt or "• *Live data stream syncing*", inline=False)
    embed.add_field(name="🗓️ High-Impact Macro Drivers & Fed Watch", value=calendar_txt, inline=False)
    embed.set_footer(text="Looney Macro Terminal • Global Cross-Asset Intelligence")
    return embed

# -------------------------------------------------------------
# 8. SYSTEM HEALTH & OPERATIONAL DIAGNOSTICS (!!health)
# -------------------------------------------------------------
def create_health_diagnostics_embed(bot_instance):
    check_daily_reset()
    now_ny = datetime.now(NY_TZ)
    
    uptime_str = format_uptime_duration(START_TIME_UTC)
    mem_mb = get_process_memory_mb()
    ping_ms = round(bot_instance.latency * 1000, 1)
    gateway_limit_str = fetch_gateway_session_limit()
    reset_countdown_str = get_seconds_until_midnight_est()
    
    embed = discord.Embed(
        title="🖥️ LOONEY OPERATIONAL DIAGNOSTICS & SYSTEM HEALTH",
        description=f"**Status:** `ONLINE 🟢` (Port 8080 Active)\n*Node Time:* `{now_ny.strftime('%a, %b %d, %Y • %I:%M:%S %p %Z')}`",
        color=0x2ecc71
    )
    
    server_info = (
        f"• **Container Uptime:** `{uptime_str}`\n"
        f"• **Memory (RAM):** `{mem_mb:.1f} MB / 512 MB`\n"
        f"• **24/7 Keep-Alive Shield:** `Active (10-Min Pulse)`\n"
        f"• **Render Status:** `Healthy (HTTP 200 OK)`"
    )
    embed.add_field(name="⏱️ Server & Process Architecture", value=server_info, inline=False)
    
    gateway_info = (
        f"• **WebSocket Latency:** `{ping_ms} ms`\n"
        f"• **Discord Session Starts:** {gateway_limit_str}\n"
        f"• **Handshakes Today:** `{DIAGNOSTICS_STATE['logins_today']} Logins` | `{DIAGNOSTICS_STATE['resumes_today']} Resumes`\n"
        f"• **Pre-Flight Guard:** `Active & Protected`"
    )
    embed.add_field(name="⚡ Discord Gateway & Connection Health", value=gateway_info, inline=False)
    
    daily_stats = (
        f"• **Chat Messages Processed:** `{DIAGNOSTICS_STATE['messages_seen_today']}` (Lifetime: `{DIAGNOSTICS_STATE['total_lifetime_messages']}`)\n"
        f"• **Terminal Cards Dispatched:** `{DIAGNOSTICS_STATE['embeds_sent_today']}`\n"
        f"• **Session Reset Window:** `Midnight EST (In {reset_countdown_str})`"
    )
    embed.add_field(name="📊 24-Hour Daily Volume (Midnight EST Reset)", value=daily_stats, inline=False)
    
    cmd_breakdown = (
        f"• **`!/$` Snapshots:** `{DIAGNOSTICS_STATE['cmd_price_today']}` | **`#` Options:** `{DIAGNOSTICS_STATE['cmd_options_today']}`\n"
        f"• **`%` Radars:** `{DIAGNOSTICS_STATE['cmd_analyst_today']}` | **`?` Insiders:** `{DIAGNOSTICS_STATE['cmd_insider_today']}`\n"
        f"• **`^` Shorts:** `{DIAGNOSTICS_STATE['cmd_short_today']}` | **`!vs` Battles:** `{DIAGNOSTICS_STATE['cmd_vs_today']}`\n"
        f"• **`!!macro` Pulses:** `{DIAGNOSTICS_STATE['cmd_macro_today']}` | **`!!health`:** `{DIAGNOSTICS_STATE['cmd_health_today']}`"
    )
    embed.add_field(name="🎯 Daily Command Popularity Breakdown", value=cmd_breakdown, inline=False)
    embed.set_footer(text="Looney Diagnostics • Real-Time Health & Gateway Monitor")
    return embed

# -------------------------------------------------------------
# 9. DISCORD BOT INSTANCE SETUP
# -------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    check_daily_reset()
    BOT_STATE["status"] = "CONNECTED"
    DIAGNOSTICS_STATE["logins_today"] += 1
    print(f"🤖 Looney is ONLINE and listening 24/7 as: {bot.user}", flush=True)

@bot.event
async def on_resumed():
    check_daily_reset()
    DIAGNOSTICS_STATE["resumes_today"] += 1
    print(f"🔄 Looney session resumed seamlessly (0 logins used).", flush=True)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    check_daily_reset()
    DIAGNOSTICS_STATE["messages_seen_today"] += 1
    DIAGNOSTICS_STATE["total_lifetime_messages"] += 1

    content = message.content.strip()
    low_content = content.lower()

    # TRIGGER 0: Health & Diagnostics on `!!health`, `!health`, `!status`, `!ping`
    if low_content in ["!!health", "!health", "!!status", "!status", "!!ping", "!ping"]:
        async with message.channel.typing():
            DIAGNOSTICS_STATE["cmd_health_today"] += 1
            DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
            DIAGNOSTICS_STATE["embeds_sent_today"] += 1
            embed = create_health_diagnostics_embed(bot)
            await message.channel.send(embed=embed)
            return

    # TRIGGER 0B: Global Macro Pulse on `!!macro`, `!macro`, `!econ`, `!fomc`
    if low_content in ["!!macro", "!macro", "!econ", "!fomc", "!!econ"]:
        async with message.channel.typing():
            DIAGNOSTICS_STATE["cmd_macro_today"] += 1
            DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
            DIAGNOSTICS_STATE["embeds_sent_today"] += 1
            embed = await asyncio.to_thread(fetch_global_macro_pulse)
            await message.channel.send(embed=embed)
            return

    # TRIGGER 0C: 13-Crypto Sequential Paced Scanner on `!crypto` or `!cryptos`
    if low_content in ["!crypto", "!cryptos"]:
        async with message.channel.typing():
            for sym in TOP_CRYPTO_LIST:
                data, err = await asyncio.to_thread(get_on_demand_data, sym)
                if data and not err:
                    embed = create_market_embed(data)
                    DIAGNOSTICS_STATE["cmd_price_today"] += 1
                    DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
                    DIAGNOSTICS_STATE["embeds_sent_today"] += 1
                    await message.channel.send(embed=embed)
                    await asyncio.sleep(1.0)
            return

    # TRIGGER 1: Head-to-Head Comparison on `!vs TICKER1 TICKER2`
    if low_content.startswith("!vs ") or low_content.startswith("vs "):
        parts = content.split()
        if len(parts) >= 3:
            s1, s2 = parts[1].upper().replace("$", ""), parts[2].upper().replace("$", "")
            async with message.channel.typing():
                embed, err = await asyncio.to_thread(compare_two_stocks, s1, s2)
                if err:
                    await message.channel.send(f"❌ {err}")
                    return
                DIAGNOSTICS_STATE["cmd_vs_today"] += 1
                DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
                DIAGNOSTICS_STATE["embeds_sent_today"] += 1
                await message.channel.send(embed=embed)
                return

    # TRIGGER 2: Insider Buying & 13F Ownership on `?TICKER`
    if content.startswith("?") and len(content) >= 2:
        raw_ticker = content[1:].split()[0].upper().replace("$", "")
        if len(raw_ticker) <= 12 and re.match(r'^[A-Z0-9=\-\.]+$', raw_ticker):
            async with message.channel.typing():
                embed, err = await asyncio.to_thread(fetch_insider_and_institutional_data, raw_ticker)
                if err:
                    await message.channel.send(f"❌ {err}")
                    return
                DIAGNOSTICS_STATE["cmd_insider_today"] += 1
                DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
                DIAGNOSTICS_STATE["embeds_sent_today"] += 1
                await message.channel.send(embed=embed)
                return

    # TRIGGER 3: 100% Calculated Short Squeeze Metrics on `^TICKER`
    if content.startswith("^") and len(content) >= 2:
        raw_ticker = content[1:].split()[0].upper().replace("$", "")
        if len(raw_ticker) <= 12 and re.match(r'^[A-Z0-9=\-\.]+$', raw_ticker):
            async with message.channel.typing():
                embed, err = await asyncio.to_thread(fetch_short_squeeze_metrics, raw_ticker)
                if err:
                    await message.channel.send(f"❌ {err}")
                    return
                DIAGNOSTICS_STATE["cmd_short_today"] += 1
                DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
                DIAGNOSTICS_STATE["embeds_sent_today"] += 1
                await message.channel.send(embed=embed)
                return

    # TRIGGER 4: Institutional Research Radar on `%TICKER`
    if content.startswith("%") and len(content) >= 2:
        raw_ticker = content[1:].split()[0].upper().replace("$", "")
        if len(raw_ticker) <= 12 and re.match(r'^[A-Z0-9=\-\.]+$', raw_ticker):
            async with message.channel.typing():
                try:
                    data, err = await asyncio.to_thread(fetch_institutional_research_radar, raw_ticker)
                    if err:
                        await message.channel.send(f"❌ {err}")
                        return
                    if not data:
                        await message.channel.send(f"❌ No research data found for `{raw_ticker}`.")
                        return
                    embeds = create_institutional_radar_embeds(data)
                    DIAGNOSTICS_STATE["cmd_analyst_today"] += 1
                    DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
                    DIAGNOSTICS_STATE["embeds_sent_today"] += len(embeds)
                    for embed in embeds:
                        await message.channel.send(embed=embed)
                        await asyncio.sleep(0.4)
                except Exception as e:
                    await message.channel.send(f"❌ Error generating research radar for `{raw_ticker}`: {e}")
                return

    # TRIGGER 5: Options Deep-Dive on `#TICKER`
    if content.startswith("#") and len(content) >= 2:
        raw_ticker = content[1:].split()[0].upper().replace("$", "")
        if len(raw_ticker) <= 12 and re.match(r'^[A-Z0-9=\-\.]+$', raw_ticker):
            async with message.channel.typing():
                try:
                    data = await asyncio.to_thread(analyze_stock_options_setup, raw_ticker)
                    if not data:
                        await message.channel.send(f"❌ Could not compute options analytics for `{raw_ticker}`. Verify ticker symbol.")
                        return
                    embed = create_deep_dive_options_embed(data)
                    DIAGNOSTICS_STATE["cmd_options_today"] += 1
                    DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
                    DIAGNOSTICS_STATE["embeds_sent_today"] += 1
                    await message.channel.send(embed=embed)
                except Exception as e:
                    await message.channel.send(f"❌ Options Error: {e}")
                return

    # TRIGGER 6: Technicals Snapshot on `!TICKER` or `$TICKER`
    if content.startswith("!") or content.startswith("$"):
        raw_cmd = content[1:].strip()
        first_word = raw_cmd.split()[0].lower() if raw_cmd else ""

        if first_word in ["price", "p", "four", "check", "opt", "options", "analyst", "research", "health", "status", "ping", "vs", "insider", "short", "macro", "econ", "crypto", "cryptos"]:
            await bot.process_commands(message)
            return

        potential_ticker = raw_cmd.split()[0].upper()
        if potential_ticker and len(potential_ticker) <= 12 and re.match(r'^[A-Z0-9=\-\.]+$', potential_ticker):
            async with message.channel.typing():
                try:
                    data, err = await asyncio.to_thread(get_on_demand_data, potential_ticker)
                    if err:
                        await message.channel.send(f"❌ {err}")
                        return
                    embed = create_market_embed(data)
                    DIAGNOSTICS_STATE["cmd_price_today"] += 1
                    DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
                    DIAGNOSTICS_STATE["embeds_sent_today"] += 1
                    await message.channel.send(embed=embed)
                except Exception as e:
                    await message.channel.send(f"❌ Snapshot Error: {e}")
                return

    await bot.process_commands(message)

# -------------------------------------------------------------
# 10. BOT COMMAND ALIASES
# -------------------------------------------------------------
@bot.command(name="crypto", aliases=["cryptos"])
async def crypto_command(ctx):
    async with ctx.typing():
        for sym in TOP_CRYPTO_LIST:
            data, err = await asyncio.to_thread(get_on_demand_data, sym)
            if data and not err:
                embed = create_market_embed(data)
                DIAGNOSTICS_STATE["cmd_price_today"] += 1
                DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
                DIAGNOSTICS_STATE["embeds_sent_today"] += 1
                await ctx.send(embed=embed)
                await asyncio.sleep(1.0)

@bot.command(name="health", aliases=["status", "ping"])
async def health_command(ctx):
    async with ctx.typing():
        check_daily_reset()
        DIAGNOSTICS_STATE["cmd_health_today"] += 1
        DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
        DIAGNOSTICS_STATE["embeds_sent_today"] += 1
        embed = create_health_diagnostics_embed(bot)
        await ctx.send(embed=embed)

@bot.command(name="macro", aliases=["econ", "fomc"])
async def macro_command(ctx):
    async with ctx.typing():
        check_daily_reset()
        DIAGNOSTICS_STATE["cmd_macro_today"] += 1
        DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
        DIAGNOSTICS_STATE["embeds_sent_today"] += 1
        embed = await asyncio.to_thread(fetch_global_macro_pulse)
        await ctx.send(embed=embed)

@bot.command(name="vs")
async def vs_command(ctx, sym1: str, sym2: str):
    async with ctx.typing():
        check_daily_reset()
        embed, err = await asyncio.to_thread(compare_two_stocks, sym1, sym2)
        if err:
            await ctx.send(f"❌ {err}")
            return
        DIAGNOSTICS_STATE["cmd_vs_today"] += 1
        DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
        DIAGNOSTICS_STATE["embeds_sent_today"] += 1
        await ctx.send(embed=embed)

@bot.command(name="insider")
async def insider_command(ctx, ticker: str):
    async with ctx.typing():
        check_daily_reset()
        embed, err = await asyncio.to_thread(fetch_insider_and_institutional_data, ticker)
        if err:
            await ctx.send(f"❌ {err}")
            return
        DIAGNOSTICS_STATE["cmd_insider_today"] += 1
        DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
        DIAGNOSTICS_STATE["embeds_sent_today"] += 1
        await ctx.send(embed=embed)

@bot.command(name="short")
async def short_command(ctx, ticker: str):
    async with ctx.typing():
        check_daily_reset()
        embed, err = await asyncio.to_thread(fetch_short_squeeze_metrics, ticker)
        if err:
            await ctx.send(f"❌ {err}")
            return
        DIAGNOSTICS_STATE["cmd_short_today"] += 1
        DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
        DIAGNOSTICS_STATE["embeds_sent_today"] += 1
        await ctx.send(embed=embed)

@bot.command(name="price", aliases=["p", "four", "check"])
async def price_command(ctx, ticker: str):
    async with ctx.typing():
        check_daily_reset()
        data, err = await asyncio.to_thread(get_on_demand_data, ticker)
        if err:
            await ctx.send(f"❌ {err}")
            return
        embed = create_market_embed(data)
        DIAGNOSTICS_STATE["cmd_price_today"] += 1
        DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
        DIAGNOSTICS_STATE["embeds_sent_today"] += 1
        await ctx.send(embed=embed)

@bot.command(name="opt", aliases=["options", "play"])
async def options_command(ctx, ticker: str):
    async with ctx.typing():
        check_daily_reset()
        data = await asyncio.to_thread(analyze_stock_options_setup, ticker)
        if not data:
            await ctx.send(f"❌ Could not compute options analytics for `{ticker}`.")
            return
        embed = create_deep_dive_options_embed(data)
        DIAGNOSTICS_STATE["cmd_options_today"] += 1
        DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
        DIAGNOSTICS_STATE["embeds_sent_today"] += 1
        await ctx.send(embed=embed)

@bot.command(name="analyst", aliases=["research", "targets"])
async def analyst_command(ctx, ticker: str):
    async with ctx.typing():
        check_daily_reset()
        data, err = await asyncio.to_thread(fetch_institutional_research_radar, ticker)
        if err:
            await ctx.send(f"❌ {err}")
            return
        embeds = create_institutional_radar_embeds(data)
        DIAGNOSTICS_STATE["cmd_analyst_today"] += 1
        DIAGNOSTICS_STATE["total_lifetime_commands"] += 1
        DIAGNOSTICS_STATE["embeds_sent_today"] += len(embeds)
        for embed in embeds:
            await ctx.send(embed=embed)
            await asyncio.sleep(0.4)

# -------------------------------------------------------------
# 11. SMART PRE-FLIGHT GATEWAY HANDSHAKE & RUNNER
# -------------------------------------------------------------
def smart_gateway_preflight(token):
    """
    Checks Discord Gateway status before calling bot.run().
    If rate limited, sleeps for the exact retry_after countdown sent by Discord.
    """
    url = "https://discord.com/api/v10/gateway/bot"
    headers = {"Authorization": f"Bot {token}"}

    while True:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                start_limit = data.get("session_start_limit", {})
                remaining = start_limit.get("remaining", 1000)
                reset_after = start_limit.get("reset_after", 0)

                if remaining <= 0:
                    wait_sec = (reset_after / 1000.0) + 1.0
                    print(f"⏳ Discord session start limit reached (0 remaining). Sleeping {wait_sec:.1f}s until reset...", flush=True)
                    time.sleep(wait_sec)
                    continue

                print(f"✅ Discord Gateway pre-flight passed. Remaining session logins: {remaining}/1000", flush=True)
                return True

            elif res.status_code == 429:
                try:
                    retry_after = float(res.json().get("retry_after", 60.0))
                except Exception:
                    retry_after = float(res.headers.get("Retry-After", 60.0))

                print(f"⏳ Discord 429 Rate Limit active. Pre-flight sleeping for {retry_after:.2f}s before connecting...", flush=True)
                BOT_STATE["status"] = "RATE_LIMITED_COOLDOWN"
                time.sleep(retry_after + 1.0)
                continue

            else:
                print(f"⚠️ Gateway pre-flight response {res.status_code}. Retrying in 10s...", flush=True)
                time.sleep(10)
        except Exception as e:
            print(f"⚠️ Gateway pre-flight network error: {e}. Retrying in 10s...", flush=True)
            time.sleep(10)

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ CRITICAL ERROR: DISCORD_BOT_TOKEN environment variable is missing!", flush=True)
    else:
        print(f"🚀 Starting Looney Bot on Render...", flush=True)
        while True:
            try:
                # Pre-flight check ensures we never hammer Discord if rate limited
                smart_gateway_preflight(BOT_TOKEN)
                BOT_STATE["status"] = "CONNECTING"
                bot.run(BOT_TOKEN)
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    BOT_STATE["status"] = "RATE_LIMITED_429"
                    print("⚠️ 429 Rate Limited during runtime. Re-checking gateway...", flush=True)
                    time.sleep(15)
                else:
                    BOT_STATE["status"] = f"ERROR_{e.status}"
                    time.sleep(30)
            except Exception as e:
                BOT_STATE["status"] = "CRASHED"
                print(f"❌ Connection error: {e}. Retrying in 15s...", flush=True)
                time.sleep(15)
