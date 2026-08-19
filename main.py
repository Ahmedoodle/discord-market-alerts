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
import pandas as pd

# Environment Variables (Securely pulled from GitHub Secrets)
DISCORD_NEWS_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_PRICE_WEBHOOK_URL = os.getenv(
    "DISCORD_PRICE_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1539395404502671440/HCuVM2hd2t7OV8r1DaLk46iTNz3xgD1Li_Mdt05RAU7m3W2ZTYLIaYKrQyMti81axOxV"
)

# Bot Branding & Unified Avatar (Rocket Image across both channels)
BOT_NAME = "Looney"
BOT_AVATAR_URL = "https://cdn.discordapp.com/attachments/1536082016184045750/1539077205437714442/IMG_6630.jpg?ex=6a8500d8&is=6a83af58&hm=f46d7b936827c9651de6bafe607af3e23c40009ee9799431f622886c85c78013&"

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
# 1. BULLETPROOF NYSE & TSX MARKET HOLIDAY & EARLY CLOSE ENGINE
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

    # 2. MLK Day (US: 3rd Mon in Jan, 1998+)
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
    all_us = {}
    all_ca = {}
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
    black_friday = us_thanks + timedelta(days=1)
    if target_date == black_friday:
        return True, "Black Friday (1:00 PM Close)"

    if target_date.month == 12 and target_date.day == 24 and target_date.weekday() < 5:
        return True, "Christmas Eve (1:00 PM Close)"

    return False, None

# ====================================================================
# 2. SESSION TIMING & DYNAMIC CLASSIFIER
# ====================================================================
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
                    print(f"📅 New Stock Calendar Day ({today_ny_str}). Resetting daily stock memory slots.")

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
# 4. INSTITUTIONAL TECHNICAL INDICATOR & STATEMENT ENGINE
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
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calculate_macd(closes):
    if len(closes) < 35:
        return "N/A"
    
    alpha_12 = 2.0 / (12 + 1)
    alpha_26 = 2.0 / (26 + 1)
    curr_12 = sum(closes[:12]) / 12
    curr_26 = sum(closes[:26]) / 26
    ema_12_full = []
    ema_26_full = []

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

    alpha_9 = 2.0 / (9 + 1)
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
        if hist_curr >= hist_prev:
            return "Bullish Momentum 🟢 (Signal Expanding Upward)"
        else:
            return "Bullish Trend 🟢 (Momentum Slowing)"
    else:
        if hist_curr <= hist_prev:
            return "Bearish Momentum 🔴 (Expanding Downward)"
        else:
            return "Bearish Trend 🔴 (Weakening / Slowing)"

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        c_prev = closes[i - 1]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    return sum(trs[-period:]) / period

def get_volume_tag(rvol):
    if rvol is None:
        return "N/A"
    if rvol >= 2.0:
        return f"**{rvol:.1f}x** (🔥 Unusual Surge)"
    elif rvol >= 1.3:
        return f"**{rvol:.1f}x** (⚡ Strong)"
    elif rvol < 0.6:
        return f"**{rvol:.1f}x** (💤 Low)"
    else:
        return f"**{rvol:.1f}x** (📊 Normal)"

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

def get_technical_and_fundamental_metrics(ticker_symbol, current_price, http_session):
    """Calculates all 8 institutional indicators & statement-based fundamentals directly."""
    metrics = {}
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?interval=1d&range=1y"
        res = http_session.get(url, timeout=5)
        if res.status_code != 200:
            return metrics

        data = res.json()
        result = data.get("chart", {}).get("result")
        if not result:
            return metrics

        chart_data = result[0]
        meta = chart_data.get("meta", {})
        indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]

        closes = [c for c in indicators.get("close", []) if c is not None]
        volumes = [v for v in indicators.get("volume", []) if v is not None]
        highs = [h for h in indicators.get("high", []) if h is not None]
        lows = [l for l in indicators.get("low", []) if l is not None]

        if len(closes) < 2:
            return metrics

        # 1. Volume Multipliers (20D, 50D, 90D)
        vol_today = volumes[-1] if volumes else 0
        v_fmt = format_large_number(vol_today).replace("$", "") + " shares" if vol_today >= 1000 else str(int(vol_today))
        rvol_20 = (vol_today / (sum(volumes[-21:-1]) / len(volumes[-21:-1]))) if len(volumes) >= 20 and sum(volumes[-21:-1]) > 0 else None
        rvol_50 = (vol_today / (sum(volumes[-51:-1]) / len(volumes[-51:-1]))) if len(volumes) >= 50 and sum(volumes[-51:-1]) > 0 else None
        rvol_90 = (vol_today / (sum(volumes[-91:-1]) / len(volumes[-91:-1]))) if len(volumes) >= 90 and sum(volumes[-91:-1]) > 0 else None

        metrics["volume_block"] = (
            f"• **Today's Vol:** `{v_fmt}`\n"
            f"• **20D (1-Month):** {get_volume_tag(rvol_20)}\n"
            f"• **50D (Quarterly):** {get_volume_tag(rvol_50)}\n"
            f"• **90D (Long-Term):** {get_volume_tag(rvol_90)}"
        )

        # 2. Multi-Timeframe RSI (7D, 14D, 30D)
        rsi_7 = calculate_rsi(closes, 7)
        rsi_14 = calculate_rsi(closes, 14)
        rsi_30 = calculate_rsi(closes, 30)

        metrics["rsi_block"] = (
            f"• **7D (Fast / Scalp):** {get_rsi_tag(rsi_7)}\n"
            f"• **14D (Standard):** {get_rsi_tag(rsi_14)}\n"
            f"• **30D (Macro Trend):** {get_rsi_tag(rsi_30)}"
        )

        # 3. 52-Week Range in Dollars
        high_52w = meta.get("fiftyTwoWeekHigh") or (max(highs) if highs else None)
        low_52w = meta.get("fiftyTwoWeekLow") or (min(lows) if lows else None)
        if high_52w and low_52w and high_52w > low_52w:
            dist_high = ((high_52w - current_price) / high_52w) * 100
            if dist_high <= 2.0:
                metrics["range_str"] = f"`${low_52w:.2f} - ${high_52w:.2f}` (🔥 {dist_high:.1f}% from 52W High!)"
            elif dist_high <= 5.0:
                range_str = f"`${low_52w:.2f} - ${high_52w:.2f}` (⚡ {dist_high:.1f}% from 52W High)"
                metrics["range_str"] = range_str
            else:
                metrics["range_str"] = f"`${low_52w:.2f} - ${high_52w:.2f}` ({dist_high:.1f}% below 52W High)"

        # 4. Moving Averages & Trend
        sma_50 = (sum(closes[-50:]) / 50) if len(closes) >= 50 else None
        sma_200 = (sum(closes[-200:]) / 200) if len(closes) >= 200 else None

        sma_50_str = f"`${sma_50:.2f}` (Above by +{((current_price-sma_50)/sma_50)*100:.1f}% 🟢)" if sma_50 and current_price >= sma_50 else (f"`${sma_50:.2f}` (Below by {((current_price-sma_50)/sma_50)*100:.1f}% 🔴)" if sma_50 else "N/A")
        sma_200_str = f"`${sma_200:.2f}` (Above by +{((current_price-sma_200)/sma_200)*100:.1f}% 🟢)" if sma_200 and current_price >= sma_200 else (f"`${sma_200:.2f}` (Below by {((current_price-sma_200)/sma_200)*100:.1f}% 🔴)" if sma_200 else "N/A")

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
            verdict_str = "`🟢 Short-Term Uptrend`" if current_price >= sma_50 else "`🔴 Short-Term Downtrend`"

        metrics["trend_block"] = (
            f"• **50-Day SMA:** {sma_50_str}\n"
            f"• **200-Day SMA:** {sma_200_str}\n"
            f"• **Overall Verdict:** {verdict_str}"
        )

        # 5. MACD (12, 26, 9)
        metrics["macd_str"] = calculate_macd(closes)

        # 6. Pivot Levels (S1 & R1)
        if len(highs) >= 2 and len(lows) >= 2 and len(closes) >= 2:
            h_prev, l_prev, c_prev = highs[-2], lows[-2], closes[-2]
            p = (h_prev + l_prev + c_prev) / 3.0
            r1 = (2.0 * p) - l_prev
            s1 = (2.0 * p) - h_prev
            metrics["pivot_str"] = f"`Support (S1): ${s1:.2f}` | `Resistance (R1): ${r1:.2f}`"

        # 7. 14D ATR
        atr = calculate_atr(highs, lows, closes, 14)
        if atr and current_price > 0:
            metrics["atr_str"] = f"`±${atr:.2f}` (±{(atr/current_price)*100:.1f}% typical daily swing)"

        # =================================================================
        # 8. DIRECT FINANCIAL STATEMENT & FUNDAMENTAL ENGINE
        # =================================================================
        quote_type = meta.get("instrumentType", "EQUITY")
        
        if quote_type == "CRYPTOCURRENCY" or "USD" in ticker_symbol:
            metrics["fund_title"] = "🏢 Asset Class & Profile"
            t_obj = yf.Ticker(ticker_symbol)
            m_cap = getattr(t_obj.fast_info, "market_cap", None)
            cap_fmt = format_large_number(m_cap) if m_cap else "N/A"
            tier = "Mega-Cap 👑" if m_cap and m_cap >= 2e11 else ("Large-Cap 🏢" if m_cap and m_cap >= 1e10 else "Mid/Small-Cap 📈")
            metrics["profile_block"] = (
                f"• **Asset Class:** `Cryptocurrency (Decentralized Protocol)`\n"
                f"• **Market Cap:** `{cap_fmt}` ({tier})\n"
                f"• **Valuation:** `Digital Asset / Network Utility`"
            )
        elif quote_type == "ETF":
            metrics["fund_title"] = "🏢 Fund Profile & Structure"
            t_obj = yf.Ticker(ticker_symbol)
            m_cap = getattr(t_obj.fast_info, "market_cap", None)
            cap_fmt = format_large_number(m_cap) if m_cap else "N/A"
            metrics["profile_block"] = (
                f"• **Asset Class:** `Exchange-Traded Fund (ETF Basket)`\n"
                f"• **Total Net Assets:** `{cap_fmt}`\n"
                f"• **Strategy:** `Diversified Index / Holdings Basket`"
            )
        elif quote_type == "FUTURE" or "=F" in ticker_symbol:
            metrics["fund_title"] = "🏢 Asset Class & Profile"
            metrics["profile_block"] = (
                f"• **Asset Class:** `Commodity / Index Derivative Contract`\n"
                f"• **Contract Type:** `Standardized Delivery Futures`"
            )
        else:
            # Equities / Stocks — Computed directly from Balance Sheet Statements
            metrics["fund_title"] = "🏢 Valuation, Earnings & Growth"
            t_obj = yf.Ticker(ticker_symbol)
            fi = t_obj.fast_info
            
            # Market Cap
            market_cap = getattr(fi, "market_cap", None)
            shares = getattr(fi, "shares", None)
            if not market_cap and shares and current_price:
                market_cap = current_price * shares

            # Sector & Industry
            sector = None
            industry = None
            try:
                s_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker_symbol}&quotesCount=1&newsCount=0"
                s_res = http_session.get(s_url, timeout=3)
                if s_res.status_code == 200:
                    sq = s_res.json().get("quotes", [])
                    if sq:
                        sector = sq[0].get("sector")
                        industry = sq[0].get("industry")
            except Exception:
                pass

            # Statement Calculations
            trailing_pe = None
            rev_growth_pct = None
            net_inc_growth_pct = None
            profit_margin_pct = None

            try:
                q_inc = t_obj.quarterly_income_stmt
                if q_inc is not None and not q_inc.empty:
                    if "Total Revenue" in q_inc.index:
                        rev_s = q_inc.loc["Total Revenue"].dropna()
                        if len(rev_s) >= 4:
                            r0 = rev_s.iloc[0]
                            r4 = rev_s.iloc[3] if len(rev_s) >= 4 else rev_s.iloc[-1]
                            if r4 > 0:
                                rev_growth_pct = ((r0 - r4) / r4) * 100
                            ttm_rev = rev_s.iloc[:4].sum()
                        else:
                            ttm_rev = rev_s.sum()
                    else:
                        ttm_rev = None

                    if "Net Income" in q_inc.index:
                        inc_s = q_inc.loc["Net Income"].dropna()
                        if len(inc_s) >= 4:
                            i0 = inc_s.iloc[0]
                            i4 = inc_s.iloc[3] if len(inc_s) >= 4 else inc_s.iloc[-1]
                            if i4 != 0:
                                net_inc_growth_pct = ((i0 - i4) / abs(i4)) * 100
                            ttm_net_inc = inc_s.iloc[:4].sum()
                        else:
                            ttm_net_inc = inc_s.sum()

                        if ttm_net_inc > 0 and shares and shares > 0:
                            trailing_eps = ttm_net_inc / shares
                            if trailing_eps > 0:
                                trailing_pe = current_price / trailing_eps

                        if ttm_net_inc is not None and ttm_rev and ttm_rev > 0:
                            profit_margin_pct = (ttm_net_inc / ttm_rev) * 100
            except Exception:
                pass

            if sector and industry:
                line_sector = f"• **Sector / Industry:** `{sector} • {industry}`"
            elif sector:
                line_sector = f"• **Sector:** `{sector}`"
            else:
                line_sector = f"• **Asset Class:** `Equities / Common Stock`"

            if market_cap and market_cap > 0:
                cap_fmt = format_large_number(market_cap)
                tier = "Mega-Cap 👑" if market_cap >= 2e11 else ("Large-Cap 🏢" if market_cap >= 1e10 else ("Mid-Cap 📈" if market_cap >= 2e9 else "Small-Cap 🌱"))
                line_cap = f"• **Market Cap:** `{cap_fmt}` ({tier})"
            else:
                line_cap = "• **Market Cap:** `N/A`"

            if trailing_pe and trailing_pe > 0:
                line_val = f"• **Valuation:** Trailing P/E: `{trailing_pe:.1f}x`"
            else:
                line_val = f"• **Valuation:** `High-Growth / Reinvestment Phase`"

            growth_parts = []
            if rev_growth_pct is not None:
                growth_parts.append(f"Revenue: `{rev_growth_pct:+.1f}%`")
            if net_inc_growth_pct is not None:
                growth_parts.append(f"Net Income: `{net_inc_growth_pct:+.1f}% 🚀`")

            line_growth = f"• **Growth (YoY):** {' | '.join(growth_parts)}" if growth_parts else ""

            if profit_margin_pct is not None:
                tag = " (High Margin 💎)" if profit_margin_pct >= 20.0 else (" (Healthy 🟢)" if profit_margin_pct >= 10.0 else "")
                line_margin = f"• **Profit Margin:** `{profit_margin_pct:.1f}%`{tag}"
            else:
                line_margin = ""

            elements = [line_sector, line_cap, line_val]
            if line_growth:
                elements.append(line_growth)
            if line_margin:
                elements.append(line_margin)
            
            metrics["profile_block"] = "\n".join(elements)

    except Exception:
        pass

    return metrics

# ====================================================================
# 5. DISCORD WEBHOOK DISPATCHERS
# ====================================================================
def send_discord_price_alert(ticker, current_price, change_pct, session_badge, step_change=None, history_trail=None, metrics=None):
    if not DISCORD_PRICE_WEBHOOK_URL:
        print(f"Skipping price alert for {ticker}: DISCORD_PRICE_WEBHOOK_URL not configured.")
        return

    title_text = f"🚨 Market Alert: {ticker} {session_badge}"
    desc_text = f"**{ticker}** moved **{change_pct:+.2f}%** today!"
    if step_change is not None:
        desc_text = f"**{ticker}** moved **{step_change:+.2f}%** since last alert! (Total {session_badge}: **{change_pct:+.2f}%**)"

    # 1. Price & % Change
    fields = [
        {"name": "Current Price", "value": f"${current_price:.2f}", "inline": True},
        {"name": f"{session_badge} Change", "value": f"{change_pct:+.2f}%", "inline": True}
    ]

    # 2. Today's Path (Positioned immediately below Price & Change!)
    if history_trail and len(history_trail) > 0:
        trail_str = " ➔ ".join(history_trail)
        fields.append({
            "name": f"🕒 Today's {session_badge} Path",
            "value": f"`{trail_str}` ➔ **{change_pct:+.2f}%**",
            "inline": False
        })

    # 3. Attach Full Institutional Indicators
    if metrics:
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
        if metrics.get("atr_str"):
            fields.append({"name": "⚡ Expected Daily Move", "value": metrics["atr_str"], "inline": False})
        if metrics.get("profile_block"):
            fields.append({"name": metrics.get("fund_title", "🏢 Valuation, Earnings & Growth"), "value": metrics["profile_block"], "inline": False})

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
        "avatar_url": BOT_AVATAR_URL,
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
    try:
        res = requests.post(DISCORD_NEWS_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"Error sending news alert: {e}")

# ====================================================================
# 6. DATA EXTRACTION ENGINE (3-Layer Bulletproof Fallback)
# ====================================================================
def get_extended_stock_data(ticker_symbol, session_type, session_http):
    current_price = None
    baseline_price = None

    try:
        ticker = yf.Ticker(ticker_symbol, session=session_http)
        
        # Layer 1: fast_info
        try:
            fi = ticker.fast_info
            current_price = float(fi.last_price) if fi.last_price is not None else None
            baseline_price = float(fi.previous_close) if fi.previous_close is not None else None
        except Exception:
            pass

        # Layer 2: Realtime history fallback
        if current_price is None or baseline_price is None:
            try:
                hist = ticker.history(period="2d")
                if 'Close' in hist.columns and len(hist['Close']) >= 2:
                    baseline_price = float(hist['Close'].iloc[-2])
                    current_price = float(hist['Close'].iloc[-1])
                elif 'Close' in hist.columns and len(hist['Close']) == 1:
                    current_price = float(hist['Close'].iloc[-1])
            except Exception:
                pass

        # Layer 3: After-Hours Baseline
        if session_type == "AFTER_HOURS" and current_price is not None:
            try:
                hist = ticker.history(period="2d")
                if 'Close' in hist.columns and len(hist['Close']) >= 1:
                    baseline_price = float(hist['Close'].iloc[-1])
            except Exception:
                pass

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
# 7. MAIN EXECUTION CONTROLLER
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
    # 3. SCAN PRICES (With Institutional Indicators)
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

                should_alert = False
                step_change_pct = None
                history_trail = []

                # Case 1: Already alerted in this session -> Step check
                if ticker_symbol in tracked_dict:
                    item_data = tracked_dict[ticker_symbol]
                    last_alert_price = item_data["last_price"]
                    history_trail = list(item_data.get("history", []))

                    step_change_pct = ((current_price - last_alert_price) / last_alert_price) * 100

                    if abs(step_change_pct) >= req_threshold:
                        should_alert = True
                        print(f"🔥 {ticker_symbol:10s} {badge} | STEP TRIGGER | Price: ${current_price:10.2f} | Step: {step_change_pct:+6.2f}%")
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
                        should_alert = True
                        print(f"🚨 {ticker_symbol:10s} {badge} | INITIAL TRIGGER | Price: ${current_price:10.2f} | Change: {change_pct:+6.2f}%")
                        tracked_dict[ticker_symbol] = {
                            "last_price": current_price,
                            "history": [f"{change_pct:+.2f}%"]
                        }
                        history_trail = []
                    else:
                        print(f"✅ {ticker_symbol:10s} {badge} | Price: ${current_price:10.2f} | Change: {change_pct:+6.2f}%")

                if should_alert:
                    # Calculate live institutional indicators & balance sheet metrics on demand
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
                history_trail=alert["history_trail"],
                metrics=alert["metrics"]
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
