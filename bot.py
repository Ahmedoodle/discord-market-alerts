import os
import threading
import asyncio
import math
import re
import time
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
# 1. 24/7 KEEP-ALIVE SERVER WITH SELF-PINGER (FOR RENDER)
# -------------------------------------------------------------
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Looney On-Demand Discord Bot is Live 24/7!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

def auto_self_ping():
    time.sleep(30)
    while True:
        try:
            render_url = os.getenv("RENDER_EXTERNAL_URL", "https://discord-market-alerts.onrender.com")
            requests.get(render_url, timeout=10)
        except Exception:
            pass
        time.sleep(600)

threading.Thread(target=auto_self_ping, daemon=True).start()

# -------------------------------------------------------------
# 2. BROWSER SESSIONS & CONFIG
# -------------------------------------------------------------
http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9"
})

nasdaq_session = requests.Session()
nasdaq_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/"
})

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
NY_TZ = ZoneInfo("America/New_York")
KNOWN_ETFS = {"QQQ", "SPY", "IWM", "DIA", "VOO", "VTI", "GLD", "SLV", "USO", "BNO", "IBIT", "ETHA", "SPCX"}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

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

# --- INSTITUTIONAL U-CURVE VOLUME PACING ENGINE ---
def get_intraday_volume_pacing_factor(now_ny):
    if now_ny.weekday() > 4:
        return 1.0
    t = now_ny.time()
    if t < dtime(9, 30):
        return 0.05
    if t >= dtime(16, 0):
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

# --- MATHEMATICAL INDICATORS ---
def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
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
    return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

def calculate_macd(closes):
    if len(closes) < 35:
        return "N/A"
    alpha_12, alpha_26 = 2.0 / 13, 2.0 / 27
    curr_12, curr_26 = sum(closes[:12]) / 12, sum(closes[:26]) / 26
    ema_12_full, ema_26_full = [], []
    for i, c in enumerate(closes):
        if i >= 12: curr_12 = c * alpha_12 + curr_12 * (1 - alpha_12)
        if i >= 26: curr_26 = c * alpha_26 + curr_26 * (1 - alpha_26); ema_12_full.append(curr_12); ema_26_full.append(curr_26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema_12_full, ema_26_full)]
    if len(macd_line) < 9: return "N/A"
    alpha_9, sig = 2.0 / 10, sum(macd_line[:9]) / 9
    sig_line = [sig]
    for m in macd_line[9:]:
        sig = m * alpha_9 + sig * (1 - alpha_9); sig_line.append(sig)
    curr_macd, curr_sig = macd_line[-1], sig_line[-1]
    hist_curr = curr_macd - curr_sig
    hist_prev = (macd_line[-2] - sig_line[-2]) if len(macd_line) >= 2 else hist_curr
    if curr_macd >= curr_sig:
        return "Bullish Momentum 🟢 (Expanding Upward)" if hist_curr >= hist_prev else "Bullish Trend 🟢 (Momentum Slowing)"
    else:
        return "Bearish Momentum 🔴 (Expanding Downward)" if hist_curr <= hist_prev else "Bearish Trend 🔴 (Weakening / Slowing)"

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1: return 1.0
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(1, len(closes))]
    return sum(trs[-period:]) / period

def calculate_historical_volatility(closes, window=30):
    if len(closes) < window + 1: return 0.25
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - window, len(closes))]
    mean_ret = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_ret) ** 2 for r in log_returns) / (len(log_returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)

def calculate_beta_vs_spy(closes):
    try:
        if len(closes) < 50: return None
        url_spy = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=1y"
        res_spy = http_session.get(url_spy, timeout=4)
        if res_spy.status_code == 200:
            spy_closes = [c for c in res_spy.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None]
            min_len = min(len(closes), len(spy_closes))
            if min_len >= 50:
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
    if rvol >= 2.0: return f"**{rvol:.1f}x** &emsp;(`Avg: {avg_fmt}` • 🔥 Unusual Surge)"
    elif rvol >= 1.3: return f"**{rvol:.1f}x** &emsp;(`Avg: {avg_fmt}` • ⚡ Strong)"
    elif rvol < 0.6: return f"**{rvol:.1f}x** &emsp;(`Avg: {avg_fmt}` • 💤 Low)"
    else: return f"**{rvol:.1f}x** &emsp;(`Avg: {avg_fmt}` • 📊 Normal)"

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

# -------------------------------------------------------------
# 3. ON-DEMAND TECHNICALS, FUNDAMENTALS & MULTI-MARKET DIVIDENDS
# -------------------------------------------------------------
def get_on_demand_data(ticker_symbol):
    ticker_symbol = ticker_symbol.upper().strip()
    is_canadian = ticker_symbol.endswith(".TO") or ticker_symbol.endswith(".V")
    now_ny = datetime.now(NY_TZ)

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?interval=1d&range=2y&events=div"
        res = http_session.get(url, timeout=5)
        if res.status_code != 200:
            return None, f"Could not fetch data for `{ticker_symbol}` (Status: {res.status_code})."

        chart_data = res.json().get("chart", {}).get("result", [{}])[0]
        meta = chart_data.get("meta", {})
        indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]
        dividends_dict = chart_data.get("events", {}).get("dividends", {})

        closes = [c for c in indicators.get("close", []) if c is not None]
        volumes = [v for v in indicators.get("volume", []) if v is not None]
        highs = [h for h in indicators.get("high", []) if h is not None]
        lows = [l for l in indicators.get("low", []) if l is not None]

        if len(closes) < 2:
            return None, f"Insufficient price history for `{ticker_symbol}`."

        current_price = meta.get("regularMarketPrice") or closes[-1]
        prev_close = meta.get("regularMarketPreviousClose") or meta.get("previousClose") or (closes[-2] if len(closes) >= 2 else current_price)
        change_pct = ((current_price - prev_close) / prev_close) * 100

        # Time-Paced RVOL
        vol_today = volumes[-1] if volumes else 0
        v_today_fmt = format_large_number(vol_today).replace("$", "") + " shares" if vol_today >= 1000 else str(int(vol_today))
        avg_vol_20 = (sum(volumes[-21:-1]) / len(volumes[-21:-1])) if len(volumes) >= 20 and sum(volumes[-21:-1]) > 0 else None
        avg_vol_50 = (sum(volumes[-51:-1]) / len(volumes[-51:-1])) if len(volumes) >= 50 and sum(volumes[-51:-1]) > 0 else None
        avg_vol_90 = (sum(volumes[-91:-1]) / len(volumes[-91:-1])) if len(volumes) >= 90 and sum(volumes[-91:-1]) > 0 else None

        pacing_factor = get_intraday_volume_pacing_factor(now_ny)
        exp_vol_20 = (avg_vol_20 * pacing_factor) if avg_vol_20 else None
        exp_vol_50 = (avg_vol_50 * pacing_factor) if avg_vol_50 else None
        exp_vol_90 = (avg_vol_90 * pacing_factor) if avg_vol_90 else None

        rvol_20 = (vol_today / exp_vol_20) if exp_vol_20 and exp_vol_20 > 0 else None
        rvol_50 = (vol_today / exp_vol_50) if exp_vol_50 and exp_vol_50 > 0 else None
        rvol_90 = (vol_today / exp_vol_90) if exp_vol_90 and exp_vol_90 > 0 else None

        volume_block = (
            f"• **Today's Vol:** `{v_today_fmt}`\n"
            f"• **20D (1-Month):** {get_volume_tag(rvol_20, avg_vol_20)}\n"
            f"• **50D (Quarterly):** {get_volume_tag(rvol_50, avg_vol_50)}\n"
            f"• **90D (Long-Term):** {get_volume_tag(rvol_90, avg_vol_90)}"
        )

        rsi_7 = calculate_rsi(closes, 7)
        rsi_14 = calculate_rsi(closes, 14)
        rsi_30 = calculate_rsi(closes, 30)

        rsi_block = (
            f"• **7D (Fast / Scalp):** {get_rsi_tag(rsi_7)}\n"
            f"• **14D (Standard):** {get_rsi_tag(rsi_14)}\n"
            f"• **30D (Macro Trend):** {get_rsi_tag(rsi_30)}"
        )

        high_52w = meta.get("fiftyTwoWeekHigh") or (max(highs) if highs else None)
        low_52w = meta.get("fiftyTwoWeekLow") or (min(lows) if lows else None)
        dist_high = (((high_52w - current_price) / high_52w) * 100) if high_52w and low_52w and high_52w > low_52w else 0
        range_str = f"`${low_52w:.2f} - ${high_52w:.2f}` ({dist_high:.1f}% below 52W High)" if high_52w and low_52w else "N/A"

        sma_50 = (sum(closes[-50:]) / 50) if len(closes) >= 50 else None
        sma_200 = (sum(closes[-200:]) / 200) if len(closes) >= 200 else None
        sma_50_str = f"`${sma_50:.2f}` (Above by +{((current_price-sma_50)/sma_50)*100:.1f}% 🟢)" if sma_50 and current_price >= sma_50 else (f"`${sma_50:.2f}` (Below by {((current_price-sma_50)/sma_50)*100:.1f}% 🔴)" if sma_50 else "N/A")
        sma_200_str = f"`${sma_200:.2f}` (Above by +{((current_price-sma_200)/sma_200)*100:.1f}% 🟢)" if sma_200 and current_price >= sma_200 else (f"`${sma_200:.2f}` (Below by {((current_price-sma_200)/sma_200)*100:.1f}% 🔴)" if sma_200 else "N/A")

        verdict_str = "N/A"
        if sma_50 and sma_200:
            if current_price >= sma_50 and current_price >= sma_200: verdict_str = "`🟢 Strong Bullish Uptrend` *(Institutional Support)*"
            elif current_price < sma_50 and current_price < sma_200: verdict_str = "`🔴 Strong Bearish Downtrend` *(Institutional Selling)*"
            elif current_price >= sma_200 and current_price < sma_50: verdict_str = "`🟡 Pullback in Macro Uptrend` *(Testing Support)*"
            else: verdict_str = "`🟡 Counter-Trend Rebound` *(Bear Market Bounce)*"
        elif sma_50:
            verdict_str = "`🟢 Short-Term Uptrend`" if current_price >= sma_50 else "`🔴 Short-Term Downtrend`"

        trend_block = f"• **50-Day SMA:** {sma_50_str}\n• **200-Day SMA:** {sma_200_str}\n• **Overall Verdict:** {verdict_str}"
        macd_str = calculate_macd(closes)

        pivot_str = "N/A"
        if len(highs) >= 2 and len(lows) >= 2 and len(closes) >= 2:
            p = (highs[-2] + lows[-2] + closes[-2]) / 3.0
            pivot_str = f"`Support (S1): ${(2.0 * p) - highs[-2]:.2f}` | `Resistance (R1): ${(2.0 * p) - lows[-2]:.2f}`"

        atr = calculate_atr(highs, lows, closes, 14)
        quote_type = meta.get("instrumentType", "EQUITY")
        dividend_block = None

        if quote_type == "CRYPTOCURRENCY" or "-USD" in ticker_symbol:
            profile_title = "🏢 Asset Class & Profile"
            profile_block = f"• **Asset Class:** `Cryptocurrency (Decentralized Protocol)`\n• **Trading:** `24/7/365 Continuous Global Liquidity`"
            catalysts_block, smart_money_block = None, None
        elif quote_type == "FUTURE" or "=F" in ticker_symbol:
            profile_title = "🏢 Asset Class & Profile"
            profile_block = f"• **Asset Class:** `Commodity / Index Derivative Contract`"
            catalysts_block, smart_money_block = None, None
        else:
            is_etf = (quote_type == "ETF" or ticker_symbol in KNOWN_ETFS)
            profile_title = "🏢 Fund Profile & Structure" if is_etf else "🏢 Company Profile"
            market_cap = None
            try:
                t_obj = yf.Ticker(ticker_symbol)
                market_cap = t_obj.fast_info.market_cap
            except Exception:
                pass

            profile_block = f"• **Market Cap:** `{format_large_number(market_cap)}`"
            catalysts_block = f"• **Wall St. Targets:** {fetch_wallstreet_targets_tls(ticker_symbol, current_price)}"
            beta_val = calculate_beta_vs_spy(closes)
            beta_str = f"`{beta_val:.2f}x`" if beta_val else "N/A"
            smart_money_block = f"• **Beta (Market Volatility):** {beta_str}\n• **Expected Daily Move (ATR):** `±${atr:.2f} (±{(atr/current_price)*100:.1f}% swing)`"

            # Multi-Source Dividend Schedule
            try:
                ex_date_str, pay_date_str = "N/A", "N/A"
                payout_ratio, trailing_div_rate, trailing_div_yield = None, None, None
                qs_url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker_symbol}?modules=calendarEvents,summaryDetail,defaultKeyStatistics&region={'CA' if is_canadian else 'US'}&lang=en"
                qs_res = cureq.get(qs_url, impersonate="chrome124", timeout=4)
                if qs_res.status_code == 200:
                    res_data = qs_res.json().get("quoteSummary", {}).get("result", [{}])[0]
                    cal_events = res_data.get("calendarEvents", {})
                    sum_detail = res_data.get("summaryDetail", {})
                    ex_obj = cal_events.get("exDividendDate", {}) or sum_detail.get("exDividendDate", {})
                    if isinstance(ex_obj, dict):
                        ex_date_str = ex_obj.get("fmt") or (datetime.fromtimestamp(ex_obj.get("raw"), tz=NY_TZ).strftime("%b %d, %Y") if ex_obj.get("raw") else "N/A")
                    pay_obj = cal_events.get("dividendDate", {}) or sum_detail.get("dividendDate", {})
                    if isinstance(pay_obj, dict):
                        pay_date_str = pay_obj.get("fmt") or (datetime.fromtimestamp(pay_obj.get("raw"), tz=NY_TZ).strftime("%b %d, %Y") if pay_obj.get("raw") else "N/A")
                    pr_obj = sum_detail.get("payoutRatio", {}) or res_data.get("defaultKeyStatistics", {}).get("payoutRatio", {})
                    if isinstance(pr_obj, dict) and pr_obj.get("raw") is not None: payout_ratio = float(pr_obj.get("raw"))
                    rate_obj = sum_detail.get("dividendRate", {}) or sum_detail.get("trailingAnnualDividendRate", {})
                    if isinstance(rate_obj, dict) and rate_obj.get("raw") is not None: trailing_div_rate = float(rate_obj.get("raw"))
                    yield_obj = sum_detail.get("dividendYield", {}) or sum_detail.get("trailingAnnualDividendYield", {})
                    if isinstance(yield_obj, dict) and yield_obj.get("raw") is not None: trailing_div_yield = float(yield_obj.get("raw"))

                # Chart event fallback
                recent_divs = []
                if dividends_dict:
                    for ts_key, d_obj in sorted(dividends_dict.items(), key=lambda x: int(x[0])):
                        recent_divs.append((int(ts_key), float(d_obj.get("amount", 0))))
                if ex_date_str == "N/A" and recent_divs:
                    ex_date_str = datetime.fromtimestamp(recent_divs[-1][0], tz=NY_TZ).strftime("%b %d, %Y")

                last_payout = recent_divs[-1][1] if recent_divs else None
                annual_rate = trailing_div_rate or (last_payout * 4 if last_payout else None)
                if (annual_rate and annual_rate > 0) or (trailing_div_yield and trailing_div_yield > 0) or last_payout:
                    calc_yield = ((annual_rate / current_price) * 100) if (annual_rate and current_price > 0) else ((trailing_div_yield * 100) if trailing_div_yield and trailing_div_yield <= 1.0 else (trailing_div_yield or 0.0))
                    per_payout = last_payout if last_payout else (annual_rate / 4 if annual_rate else (current_price * (calc_yield / 100) / 4))
                    pr_str = f"\n• **Sustainability:** Payout Ratio: `{payout_ratio*100:.1f}%`" if payout_ratio else ""
                    dividend_block = f"• **Yield & Payout:** `{calc_yield:.2f}%` • `${per_payout:.2f} / share` (`${annual_rate or (per_payout*4):.2f} Annualized`)\n• **Key Dates:** Ex-Dividend: `{ex_date_str}` • Pay Date: `{pay_date_str}`{pr_str}"
                else:
                    dividend_block = "• **Status:** `No Regular Dividend (Zero Yield / Pure Growth Stock)`"
            except Exception:
                dividend_block = "• **Status:** `No Regular Dividend (Zero Yield / Pure Growth Stock)`"

        return {
            "ticker": ticker_symbol,
            "price": current_price,
            "change_pct": change_pct,
            "volume_block": volume_block,
            "rsi_block": rsi_block,
            "range_str": range_str,
            "trend_block": trend_block,
            "macd_str": macd_str,
            "pivot_str": pivot_str,
            "dividend_block": dividend_block,
            "profile_title": profile_title,
            "profile_block": profile_block,
            "catalysts_block": catalysts_block,
            "smart_money_block": smart_money_block
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
    embed.add_field(name="📊 Volume Multipliers", value=data['volume_block'], inline=False)
    embed.add_field(name="📈 Multi-Timeframe RSI", value=data['rsi_block'], inline=False)
    embed.add_field(name="🏔️ 52-Week Range", value=data['range_str'], inline=False)
    embed.add_field(name="📈 Moving Averages & Trend", value=data['trend_block'], inline=False)
    embed.add_field(name="📊 MACD (12,26,9)", value=data['macd_str'], inline=False)
    embed.add_field(name="🛡️ Key Pivot Levels", value=data['pivot_str'], inline=False)
    if data.get("dividend_block"):
        embed.add_field(name="💰 Dividend & Shareholder Yield", value=data["dividend_block"], inline=False)
    if data.get("catalysts_block"):
        embed.add_field(name="🗓️ Catalysts & Wall Street Targets", value=data['catalysts_block'], inline=False)
    if data.get("smart_money_block"):
        embed.add_field(name="🐋 Smart Money & Risk Metrics", value=data['smart_money_block'], inline=False)
    if data.get("profile_block"):
        embed.add_field(name=data.get("profile_title", "🏢 Company Profile"), value=data['profile_block'], inline=False)
    embed.set_footer(text="Looney • On-Demand Market Terminal")
    return embed

# -------------------------------------------------------------
# 4. SMART DISAMBIGUATING INSTITUTIONAL RESEARCH RADAR (%TICKER)
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
    "RBC Capital": ("RBC Capital Markets", "🍁"), "RBC": ("RBC Capital Markets", "🍁"),
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
        try:
            current_price = float(t_obj.fast_info.last_price or 0.0)
            company_name = str(t_obj.fast_info.name or base_sym)
        except Exception:
            pass

        clean_company_short = re.sub(r'[\(\),.]|Inc|Corp|Ltd|Corporation|Company|Bank', '', company_name).strip()
        search_terms = list(dict.fromkeys([base_sym, sym, clean_company_short]))
        seen_banks = {}

        # 1. Structured Upgrades/Downgrades Feed
        try:
            ud_df = t_obj.upgrades_downgrades
            if ud_df is not None and not ud_df.empty:
                for idx, row in ud_df.iterrows():
                    row_dt = idx if isinstance(idx, (datetime, pd.Timestamp)) else None
                    if row_dt:
                        if row_dt.tzinfo is None: row_dt = row_dt.replace(tzinfo=NY_TZ)
                        if row_dt < cutoff_time: continue
                    firm_name = str(row.get("Firm", "") or "")
                    to_grade = str(row.get("ToGrade", "") or "")
                    action = str(row.get("Action", "") or "")

                    matched_inst, inst_badge = None, "🏦"
                    for key_name, (full_name, badge) in INSTITUTION_REGISTRY.items():
                        if re.search(rf'\b{re.escape(key_name)}\b', firm_name, re.IGNORECASE):
                            matched_inst, inst_badge = full_name, badge; break

                    if not matched_inst: matched_inst = firm_name if len(firm_name) > 2 else "Wall Street Bank"
                    low_grade = (to_grade + " " + action).lower()
                    if any(b in low_grade for b in ["buy", "outperform", "overweight", "up", "top pick", "positive"]):
                        rating_str, tier = f"{to_grade or 'Outperform'} 🟢", "BULLISH"
                    elif any(b in low_grade for b in ["sell", "underperform", "underweight", "down", "negative"]):
                        rating_str, tier = f"{to_grade or 'Underperform'} 🔴", "CAUTIOUS"
                    else:
                        rating_str, tier = f"{to_grade or 'Hold'} 🟡", "NEUTRAL"

                    entry = {
                        "institution": matched_inst, "badge": inst_badge, "rating": rating_str,
                        "tier": tier, "target": None,
                        "headline": f"{matched_inst} {action.capitalize() if action else 'rates'} {clean_company_short} to {to_grade}",
                        "link": f"https://finance.yahoo.com/quote/{sym}",
                        "date_str": row_dt.strftime("%b %d, %Y") if row_dt else "Recent Action",
                        "pub_dt": row_dt or now_ny
                    }
                    if matched_inst not in seen_banks: seen_banks[matched_inst] = entry
        except Exception:
            pass

        # 2. Deep Web Search with Subject Disambiguation
        raw_reports = []
        def search_yahoo():
            items = []
            try:
                ts_ms = int(time.time() * 1000)
                url = f"https://query2.finance.yahoo.com/v1/finance/search?q={clean_company_short}+price+target+analyst&newsCount=25&_={ts_ms}"
                res = http_session.get(url, timeout=4)
                if res.status_code == 200:
                    for n in res.json().get("news", []):
                        title = n.get("title", "")
                        link = n.get("link") or n.get("canonicalUrl", {}).get("url")
                        pub_time = n.get("providerPublishTime") or n.get("pubDate")
                        pub_dt = datetime.fromtimestamp(pub_time if pub_time < 1e11 else pub_time/1000.0, tz=NY_TZ) if pub_time else None
                        if title and link: items.append({"title": title, "link": link, "pub_dt": pub_dt})
            except Exception:
                pass
            return items

        def search_google_rss():
            items = []
            try:
                g_url = f"https://news.google.com/rss/search?q={clean_company_short}+price+target+OR+analyst+rating&hl=en-US&gl=US&ceid=US:en"
                res = http_session.get(g_url, timeout=4)
                if res.status_code == 200:
                    root = ET.fromstring(res.content)
                    for item in root.findall(".//item")[:25]:
                        title = item.findtext("title")
                        link = item.findtext("link")
                        pub_date_str = item.findtext("pubDate")
                        pub_dt = parsedate_to_datetime(pub_date_str).astimezone(NY_TZ) if pub_date_str else None
                        if title and link: items.append({"title": title, "link": link, "pub_dt": pub_dt})
            except Exception:
                pass
            return items

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f_y, f_g = executor.submit(search_yahoo), executor.submit(search_google_rss)
            raw_reports.extend(f_y.result())
            raw_reports.extend(f_g.result())

        for rep in raw_reports:
            t_text, pub_dt = rep["title"], rep.get("pub_dt")
            if pub_dt and pub_dt < cutoff_time: continue

            is_subject = False
            for term in search_terms:
                if len(term) >= 2 and re.search(rf'\b{re.escape(term)}\b', t_text, re.IGNORECASE):
                    if term.upper() == "TD" and re.search(r'\bTD\s*(?:Cowen|Securities|Bank\s*Analyst)\s*(?:raises|cuts|maintains|lowers|sets|rates)\b', t_text, re.IGNORECASE):
                        if not re.search(r'\b(?:Toronto[- ]Dominion|TD\s*stock|TD\s*shares|TD\.TO)\b', t_text, re.IGNORECASE):
                            continue
                    is_subject = True
                    break
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
                        if current_price == 0 or (0.1 * current_price <= cand_pt <= 6.0 * current_price):
                            pt_val = cand_pt
                except Exception:
                    pass

            low_t = t_text.lower()
            if any(b in low_t for b in ["strong buy", "conviction buy", "top pick", "outperform", "overweight", "raises target", "boosts target", "upgrade", "bullish"]):
                rating_str, tier = "Outperform / Buy 🟢", "BULLISH"
            elif any(b in low_t for b in ["downgrade", "underperform", "underweight", "cuts target", "lowers target", "sell", "bearish"]):
                rating_str, tier = "Underperform / Cautious 🔴", "CAUTIOUS"
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
        if not valid_reports:
            return None, f"No verified institutional research notes found for `{sym}` in the last 90 days."

        valid_reports.sort(key=lambda x: (x["target"] is not None, x["target"] or 0, x["pub_dt"]), reverse=True)
        return {
            "ticker": sym, "company_name": clean_company_short,
            "current_price": current_price, "currency": currency,
            "reports": valid_reports[:10]
        }, None

    except Exception as e:
        return None, str(e)

def create_institutional_radar_embed(data):
    sym = data["ticker"]
    curr = data["currency"]
    p = data["current_price"]
    reports = data["reports"]
    c_name = data.get("company_name", sym)
    is_ca = sym.endswith(".TO") or sym.endswith(".V")

    price_header = f"${p:.2f} {curr}" if p > 0 else "Live"
    radar_title = f"🏛️ BAY STREET RESEARCH RADAR: {sym} ({c_name}) 🍁" if is_ca else f"🏛️ WALL STREET RESEARCH RADAR: {sym} ({c_name})"

    embed = discord.Embed(
        title=radar_title,
        description=f"**Current Price:** `{price_header}` | **Showing {len(reports)} Verified Bank Actions (Last 90 Days)**\n*Ranked from Highest Price Target to Lowest*",
        color=0x2ecc71 if any(r["tier"] == "BULLISH" for r in reports) else 0x3498db
    )

    entries_txt = ""
    bull_cnt, neut_cnt, caut_cnt = 0, 0, 0
    valid_pts = []

    for i, r in enumerate(reports, 1):
        pt = r["target"]
        if pt and p > 0:
            diff_pct = ((pt - p) / p) * 100
            pt_line = f"• **Price Target:** `${pt:.2f} {curr}` ({'🔺' if diff_pct >= 0 else '🔻'} {diff_pct:+.1f}%)\n"
            valid_pts.append(pt)
        elif pt:
            pt_line = f"• **Price Target:** `${pt:.2f} {curr}`\n"
            valid_pts.append(pt)
        else:
            pt_line = "• **Price Target:** `In Research Note 📄`\n"

        if r["tier"] == "BULLISH": tier_badge, bull_cnt = "🟢", bull_cnt + 1
        elif r["tier"] == "NEUTRAL": tier_badge, neut_cnt = "🟡", neut_cnt + 1
        else: tier_badge, caut_cnt = "🔴", caut_cnt + 1

        clean_headline = re.sub(r'[\[\]]', '', r['headline'])
        clean_link = r['link'] if r['link'].startswith("http") else f"https://finance.yahoo.com/quote/{sym}"

        entries_txt += f"**{i}. {tier_badge} {r['badge']} {r['institution']}** — `{r['rating']}`\n{pt_line}• **Research:** [{clean_headline[:75]}...]({clean_link})\n• **Date:** `{r['date_str']}`\n\n"

    embed.add_field(name="🎯 Institutional Targets & Rating Actions", value=entries_txt.strip()[:4000], inline=False)
    spread_line = f"High: `${max(valid_pts):.2f}` | Low: `${min(valid_pts):.2f} {curr}`" if valid_pts else "Active Upgrades & Reiterations"
    embed.add_field(name="📊 Institutional Consensus Overview", value=f"• **Distribution:** `{bull_cnt} Buy / Outperform` • `{neut_cnt} Hold` • `{caut_cnt} Cautious`\n• **Target Spread:** {spread_line}", inline=False)
    embed.set_footer(text="Looney • Wall Street & Bay Street Research Intelligence (90-Day Freshness)")
    return embed

# -------------------------------------------------------------
# 5. ON-DEMAND OPTIONS DEEP-DIVE ENGINE (#TICKER)
# -------------------------------------------------------------
def analyze_stock_options_setup(ticker_symbol):
    sym = ticker_symbol.upper().strip()
    now_ny = datetime.now(NY_TZ)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1y"
        res = http_session.get(url, timeout=6)
        if res.status_code != 200: return None

        chart_data = res.json().get("chart", {}).get("result", [{}])[0]
        meta = chart_data.get("meta", {})
        indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]

        closes = [c for c in indicators.get("close", []) if c is not None]
        volumes = [v for v in indicators.get("volume", []) if v is not None]
        highs = [h for h in indicators.get("high", []) if h is not None]
        lows = [l for l in indicators.get("low", []) if l is not None]

        if len(closes) < 50: return None

        current_price = meta.get("regularMarketPrice") or closes[-1]
        prev_close = meta.get("regularMarketPreviousClose") or closes[-2]
        change_pct = ((current_price - prev_close) / prev_close) * 100

        sma_50 = sum(closes[-50:]) / 50
        sma_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else sma_50
        rsi_14 = calculate_rsi(closes, 14)
        macd_verdict = calculate_macd(closes)
        atr_14 = calculate_atr(highs, lows, closes, 14)

        # Time-Weighted Paced RVOL
        vol_today = volumes[-1] if volumes else 0
        avg_vol_20 = (sum(volumes[-21:-1]) / 20) if len(volumes) >= 21 else vol_today
        pacing_factor = get_intraday_volume_pacing_factor(now_ny)
        expected_vol_so_far = avg_vol_20 * pacing_factor
        rvol = (vol_today / expected_vol_so_far) if expected_vol_so_far > 0 else 1.0

        h_prev, l_prev, c_prev = highs[-2], lows[-2], closes[-2]
        p = (h_prev + l_prev + c_prev) / 3.0
        r1, s1 = (2.0 * p) - l_prev, (2.0 * p) - h_prev

        hv_30 = calculate_historical_volatility(closes, 30)
        hv_90 = calculate_historical_volatility(closes, 90) if len(closes) >= 91 else hv_30
        iv_rank_est = max(5, min(95, int((hv_30 / (hv_90 * 1.3 if hv_90 > 0 else 1.0)) * 50)))

        bull_score, bear_score = 0, 0
        if current_price >= sma_50 and current_price >= sma_200: bull_score += 25
        elif current_price >= sma_50: bull_score += 15
        elif current_price < sma_50 and current_price < sma_200: bear_score += 25
        elif current_price < sma_50: bear_score += 15

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

        strike_step = 2.5 if current_price < 100 else (5.0 if current_price < 300 else 10.0)

        if is_bullish:
            if iv_rank_est < 40:
                strategy_name = "Long Call (Outright Bullish Momentum)"
                strike_short = round((current_price + (atr_14 * 0.5)) / strike_step) * strike_step
                prem_short = round(max(0.5, atr_14 * 0.9), 2)
                strike_long = round((current_price - (atr_14 * 0.3)) / strike_step) * strike_step
                prem_long = round(max(1.0, atr_14 * 2.1), 2)
                play_7_14 = f"Buy ${strike_short:.2f} Call @ ~${prem_short:.2f} | Break-Even: `${strike_short + prem_short:.2f}`"
                play_30_45 = f"Buy ${strike_long:.2f} Call @ ~${prem_long:.2f} | Break-Even: `${strike_long + prem_long:.2f}`"
                defensive_play = f"Bull Call Debit Spread: Buy ${strike_long:.2f} C / Sell ${strike_long + (strike_step*2):.2f} C"
            else:
                strategy_name = "Bull Put Credit Spread (Neutral to Bullish Income)"
                sell_p_short = round((s1 - (atr_14 * 0.2)) / strike_step) * strike_step
                credit_short = round(strike_step * 0.28, 2)
                sell_p_long = round((current_price * 0.95) / strike_step) * strike_step
                credit_long = round(strike_step * 0.33, 2)
                play_7_14 = f"Sell ${sell_p_short:.2f} P / Buy ${sell_p_short - strike_step:.2f} P | Credit: `${credit_short:.2f}`"
                play_30_45 = f"Sell ${sell_p_long:.2f} P / Buy ${sell_p_long - strike_step:.2f} P | Credit: `${credit_long:.2f}`"
                defensive_play = f"Covered Call / Protective Married Put at ${s1:.2f} Support"
        else:
            if iv_rank_est < 40:
                strategy_name = "Bear Put Debit Spread (Moderately Bearish Momentum)"
                buy_p_short = round((current_price + (atr_14 * 0.2)) / strike_step) * strike_step
                debit_short = round(strike_step * 0.45, 2)
                buy_p_long = round(current_price / strike_step) * strike_step
                debit_long = round(strike_step * 0.90, 2)
                play_7_14 = f"Buy ${buy_p_short:.2f} P / Sell ${buy_p_short - strike_step:.2f} P | Debit: `${debit_short:.2f}`"
                play_30_45 = f"Buy ${buy_p_long:.2f} P / Sell ${buy_p_long - (strike_step*2):.2f} P | Debit: `${debit_long:.2f}`"
                defensive_play = f"Long Put: Buy 35-DTE ${buy_p_long:.2f} Put @ ~${debit_long*1.2:.2f}"
            else:
                strategy_name = "Bear Call Credit Spread (Neutral to Bearish Resistance Play)"
                sell_c_short = round((r1 + (atr_14 * 0.2)) / strike_step) * strike_step
                credit_short = round(strike_step * 0.26, 2)
                sell_c_long = round((current_price * 1.05) / strike_step) * strike_step
                credit_long = round(strike_step * 0.32, 2)
                play_7_14 = f"Sell ${sell_c_short:.2f} C / Buy ${sell_c_short + strike_step:.2f} C | Credit: `${credit_short:.2f}`"
                play_30_45 = f"Sell ${sell_c_long:.2f} C / Buy ${sell_c_long + strike_step:.2f} C | Credit: `${credit_long:.2f}`"
                defensive_play = f"Iron Condor: Range-bound between ${s1:.2f} and ${r1:.2f}"

        return {
            "ticker": sym, "name": meta.get("shortName") or sym, "price": current_price,
            "change_pct": change_pct, "score": final_score, "badge": badge, "color": color,
            "is_bullish": is_bullish, "strategy_name": strategy_name, "iv_rank": iv_rank_est,
            "rsi_14": rsi_14, "rvol": rvol, "sma_50": sma_50, "sma_200": sma_200,
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
    diag_text = f"• **Trend Health:** Above 50D SMA (`${data['sma_50']:.2f}`) & 200D SMA (`${data['sma_200']:.2f}`)\n• **Momentum:** RSI-14: `{data['rsi_14']:.1f}` | MACD: `{data['macd_verdict']}`\n• **Volume & Volatility:** RVOL: `{data['rvol']:.1f}x (Time-Paced)` | IV Rank: `{data['iv_rank']}%`\n• **Key Levels:** Support (S1): `${data['s1']:.2f}` | Resistance (R1): `${data['r1']:.2f}`"
    embed.add_field(name="📊 Technical & Volatility Environment", value=diag_text, inline=False)
    embed.add_field(name="🏆 Primary DFOL Strategy", value=f"**{data['strategy_name']}**", inline=False)
    embed.add_field(name="⚡ PLAY A: 7 – 14 DTE (Fast Scalp / Weekly Momentum)", value=f"• **Trade Plan:** {data['play_7_14']}\n• **Target Exit:** +50% to +80% on contract | Stop-Loss: Cut at -35% loss", inline=False)
    embed.add_field(name="🏛️ PLAY B: 30 – 45 DTE (Standard Swing / Institutional)", value=f"• **Trade Plan:** {data['play_30_45']}\n• **Target Exit:** +40% to +60% on contract | Stop-Loss: Trailing 50D SMA", inline=False)
    embed.add_field(name="🛡️ Alternative Setup (Risk Mitigation)", value=data['defensive_play'], inline=False)
    embed.set_footer(text="Looney Options Terminal • DFOL Golden Rule Break-Even Engine")
    return embed

# -------------------------------------------------------------
# 6. UNIFIED DISCORD BOT EVENT HANDLERS
# -------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"🤖 Looney is ONLINE and listening 24/7 as: {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()

    # TRIGGER 1: Institutional Research Radar on `%TICKER` (e.g. %NVDA, %TD.TO, %MU)
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
                    embed = create_institutional_radar_embed(data)
                    await message.channel.send(embed=embed)
                except Exception as e:
                    await message.channel.send(f"❌ Error generating research radar for `{raw_ticker}`: {e}")
                return

    # TRIGGER 2: Options Deep-Dive on `#TICKER` (e.g. #NVDA, #TSLA)
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
                    await message.channel.send(embed=embed)
                except Exception as e:
                    await message.channel.send(f"❌ Options Error: {e}")
                return

    # TRIGGER 3: Technicals Snapshot on `!TICKER` or `$TICKER` (e.g. !NVDA or $NVDA)
    if content.startswith("!") or content.startswith("$"):
        raw_cmd = content[1:].strip()
        first_word = raw_cmd.split()[0].lower() if raw_cmd else ""

        if first_word in ["price", "p", "four", "check", "opt", "options", "analyst", "research"]:
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
                    await message.channel.send(embed=embed)
                except Exception as e:
                    await message.channel.send(f"❌ Snapshot Error: {e}")
                return

    await bot.process_commands(message)

# Fallback Commands
@bot.command(name="price", aliases=["p", "four", "check"])
async def price_command(ctx, ticker: str):
    async with ctx.typing():
        data, err = await asyncio.to_thread(get_on_demand_data, ticker)
        if err:
            await ctx.send(f"❌ {err}")
            return
        embed = create_market_embed(data)
        await ctx.send(embed=embed)

@bot.command(name="opt", aliases=["options", "play"])
async def options_command(ctx, ticker: str):
    async with ctx.typing():
        data = await asyncio.to_thread(analyze_stock_options_setup, ticker)
        if not data:
            await ctx.send(f"❌ Could not compute options analytics for `{ticker}`.")
            return
        embed = create_deep_dive_options_embed(data)
        await ctx.send(embed=embed)

@bot.command(name="analyst", aliases=["research", "targets"])
async def analyst_command(ctx, ticker: str):
    async with ctx.typing():
        data, err = await asyncio.to_thread(fetch_institutional_research_radar, ticker)
        if err:
            await ctx.send(f"❌ {err}")
            return
        embed = create_institutional_radar_embed(data)
        await ctx.send(embed=embed)

# -------------------------------------------------------------
# 7. ENTRYPOINT
# -------------------------------------------------------------
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not set.")
    else:
        bot.run(BOT_TOKEN)
