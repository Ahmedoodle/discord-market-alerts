import os
import threading
import asyncio
import math
import re
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, date, timedelta
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
# 2. BROWSER SESSIONS
# -------------------------------------------------------------
http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9"
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

# --- MATHEMATICAL INDICATOR ENGINES ---
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
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calculate_macd(closes):
    if len(closes) < 35:
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
        return 1.0
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(1, len(closes))]
    return sum(trs[-period:]) / period

def calculate_historical_volatility(closes, window=30):
    if len(closes) < window + 1:
        return 0.25
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - window, len(closes))]
    mean_ret = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_ret) ** 2 for r in log_returns) / (len(log_returns) - 1)
    daily_vol = math.sqrt(variance)
    return daily_vol * math.sqrt(252)

def calculate_beta_vs_spy(closes, session_http):
    try:
        if len(closes) < 50:
            return None
        url_spy = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=1y"
        res_spy = session_http.get(url_spy, timeout=4)
        if res_spy.status_code == 200:
            spy_closes = [c for c in res_spy.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None]
            min_len = min(len(closes), len(spy_closes))
            if min_len >= 50:
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
        return f"**{rvol:.1f}x** &emsp;(`Avg: {avg_fmt}` • 🔥 Unusual Surge)"
    elif rvol >= 1.3:
        return f"**{rvol:.1f}x** &emsp;(`Avg: {avg_fmt}` • ⚡ Strong)"
    elif rvol < 0.6:
        return f"**{rvol:.1f}x** &emsp;(`Avg: {avg_fmt}` • 💤 Low)"
    else:
        return f"**{rvol:.1f}x** &emsp;(`Avg: {avg_fmt}` • 📊 Normal)"

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
    low_t, mean_t, high_t, rating = None, None, None, None
    try:
        fz_url = f"https://finviz.com/quote.ashx?t={ticker_symbol}&p=d"
        fz_res = cureq.get(fz_url, impersonate="chrome124", timeout=4)
        if fz_res.status_code == 200:
            m_tp = re.search(r'Target\s*Price</td>\s*<td[^>]*>(?:<b>)?([\d\.]+)', fz_res.text, re.IGNORECASE)
            m_rc = re.search(r'Recom</td>\s*<td[^>]*>(?:<b>)?([\d\.]+)', fz_res.text, re.IGNORECASE)
            if m_tp:
                mean_t = float(m_tp.group(1))
            if m_rc:
                score = float(m_rc.group(1))
                rating = "Strong Buy 🟢" if score <= 1.8 else ("Buy 🟢" if score <= 2.5 else ("Hold 🟡" if score <= 3.5 else "Sell 🔴"))
    except Exception:
        pass

    if mean_t and current_price > 0 and mean_t < (current_price * 10):
        upside = ((mean_t - current_price) / current_price) * 100
        up_tag = " 🔥" if upside >= 15 else (" 🟢" if upside > 0 else " 🔴")
        rating_part = f" | Rating: `{rating}`" if rating else ""
        return f"Mean: `${mean_t:.2f}` (**{upside:+.1f}% Upside{up_tag}**){rating_part}"

    return "N/A"

# -------------------------------------------------------------
# 3. ON-DEMAND TECHNICALS, FUNDAMENTALS & MULTI-MARKET DIVIDENDS
# -------------------------------------------------------------
def get_on_demand_data(ticker_symbol):
    ticker_symbol = ticker_symbol.upper().strip()
    is_canadian = ticker_symbol.endswith(".TO") or ticker_symbol.endswith(".V")

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?interval=1d&range=2y&events=div"
        res = http_session.get(url, timeout=5)
        
        if res.status_code != 200:
            return None, f"Could not fetch data for `{ticker_symbol}` (Status: {res.status_code})."

        data = res.json()
        result = data.get("chart", {}).get("result")
        if not result or len(result) == 0:
            return None, f"No market data found for `{ticker_symbol}`."

        chart_data = result[0]
        meta = chart_data.get("meta", {})
        indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]
        events = chart_data.get("events", {})
        dividends_dict = events.get("dividends", {})

        raw_closes = indicators.get("close", [])
        raw_volumes = indicators.get("volume", [])
        raw_highs = indicators.get("high", [])
        raw_lows = indicators.get("low", [])

        closes = [c for c in raw_closes if c is not None]
        volumes = [v for v in raw_volumes if v is not None]
        highs = [h for h in raw_highs if h is not None]
        lows = [l for l in raw_lows if l is not None]

        if len(closes) < 2:
            return None, f"Insufficient price history for `{ticker_symbol}`."

        current_price = meta.get("regularMarketPrice") or closes[-1]
        prev_close = meta.get("regularMarketPreviousClose") or meta.get("previousClose") or (closes[-2] if len(closes) >= 2 else current_price)
        change_pct = ((current_price - prev_close) / prev_close) * 100

        vol_today = volumes[-1] if volumes else 0
        v_today_fmt = format_large_number(vol_today).replace("$", "") + " shares" if vol_today >= 1000 else str(int(vol_today))

        avg_vol_20 = (sum(volumes[-21:-1]) / len(volumes[-21:-1])) if len(volumes) >= 20 and sum(volumes[-21:-1]) > 0 else None
        avg_vol_50 = (sum(volumes[-51:-1]) / len(volumes[-51:-1])) if len(volumes) >= 50 and sum(volumes[-51:-1]) > 0 else None
        avg_vol_90 = (sum(volumes[-91:-1]) / len(volumes[-91:-1])) if len(volumes) >= 90 and sum(volumes[-91:-1]) > 0 else None

        rvol_20 = (vol_today / avg_vol_20) if avg_vol_20 else None
        rvol_50 = (vol_today / avg_vol_50) if avg_vol_50 else None
        rvol_90 = (vol_today / avg_vol_90) if avg_vol_90 else None

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

        range_str = "N/A"
        high_52w = meta.get("fiftyTwoWeekHigh") or (max(highs) if highs else None)
        low_52w = meta.get("fiftyTwoWeekLow") or (min(lows) if lows else None)
        if high_52w and low_52w and high_52w > low_52w:
            dist_high = ((high_52w - current_price) / high_52w) * 100
            if dist_high <= 2.0:
                range_str = f"`${low_52w:.2f} - ${high_52w:.2f}` (🔥 {dist_high:.1f}% from 52W High!)"
            elif dist_high <= 5.0:
                range_str = f"`${low_52w:.2f} - ${high_52w:.2f}` (⚡ {dist_high:.1f}% from 52W High)"
            else:
                range_str = f"`${low_52w:.2f} - ${high_52w:.2f}` ({dist_high:.1f}% below 52W High)"

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

        trend_block = (
            f"• **50-Day SMA:** {sma_50_str}\n"
            f"• **200-Day SMA:** {sma_200_str}\n"
            f"• **Overall Verdict:** {verdict_str}"
        )

        macd_str = calculate_macd(closes)

        pivot_str = "N/A"
        if len(highs) >= 2 and len(lows) >= 2 and len(closes) >= 2:
            h_prev = highs[-2]
            l_prev = lows[-2]
            c_prev = closes[-2]
            p = (h_prev + l_prev + c_prev) / 3.0
            r1 = (2.0 * p) - l_prev
            s1 = (2.0 * p) - h_prev
            pivot_str = f"`Support (S1): ${s1:.2f}` | `Resistance (R1): ${r1:.2f}`"

        atr = calculate_atr(highs, lows, closes, 14)
        quote_type = meta.get("instrumentType", "EQUITY")
        dividend_block = None

        if quote_type == "CRYPTOCURRENCY" or "-USD" in ticker_symbol:
            profile_title = "🏢 Asset Class & Profile"
            profile_block = (
                f"• **Asset Class:** `Cryptocurrency (Decentralized Protocol)`\n"
                f"• **Network Utility:** `Digital Asset / Smart Contract Network`\n"
                f"• **Trading:** `24/7/365 Continuous Global Liquidity`"
            )
            catalysts_block, smart_money_block, health_block = None, None, None

        elif quote_type == "FUTURE" or "=F" in ticker_symbol:
            profile_title = "🏢 Asset Class & Profile"
            profile_block = (
                f"• **Asset Class:** `Commodity / Index Derivative Contract`\n"
                f"• **Contract Type:** `Standardized Delivery Futures`"
            )
            catalysts_block, smart_money_block, health_block = None, None, None

        else:
            is_etf = (quote_type == "ETF" or ticker_symbol in KNOWN_ETFS)
            profile_title = "🏢 Fund Profile & Structure" if is_etf else "🏢 Company Profile"
            
            sector, industry = None, None
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

            # Multi-Source Dividend Schedule
            try:
                ex_date_str = "N/A"
                pay_date_str = "N/A"
                payout_ratio = None
                trailing_div_rate = None
                trailing_div_yield = None

                # Query QuoteSummary with TLS Impersonation
                try:
                    region_param = "CA" if is_canadian else "US"
                    qs_url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker_symbol}?modules=calendarEvents,summaryDetail,defaultKeyStatistics&region={region_param}&lang=en-{region_param}"
                    qs_res = cureq.get(qs_url, impersonate="chrome124", timeout=4)
                    if qs_res.status_code == 200:
                        res_data = qs_res.json().get("quoteSummary", {}).get("result", [{}])[0]
                        cal_events = res_data.get("calendarEvents", {})
                        sum_detail = res_data.get("summaryDetail", {})

                        ex_obj = cal_events.get("exDividendDate", {}) or sum_detail.get("exDividendDate", {})
                        if isinstance(ex_obj, dict):
                            if ex_obj.get("fmt"):
                                ex_date_str = ex_obj.get("fmt")
                            elif ex_obj.get("raw"):
                                ex_date_str = datetime.fromtimestamp(ex_obj.get("raw"), tz=NY_TZ).strftime("%b %d, %Y")

                        pay_obj = cal_events.get("dividendDate", {}) or sum_detail.get("dividendDate", {})
                        if isinstance(pay_obj, dict):
                            if pay_obj.get("fmt"):
                                pay_date_str = pay_obj.get("fmt")
                            elif pay_obj.get("raw"):
                                pay_date_str = datetime.fromtimestamp(pay_obj.get("raw"), tz=NY_TZ).strftime("%b %d, %Y")

                        pr_obj = sum_detail.get("payoutRatio", {}) or res_data.get("defaultKeyStatistics", {}).get("payoutRatio", {})
                        if isinstance(pr_obj, dict) and pr_obj.get("raw") is not None:
                            payout_ratio = float(pr_obj.get("raw"))

                        rate_obj = sum_detail.get("dividendRate", {}) or sum_detail.get("trailingAnnualDividendRate", {})
                        if isinstance(rate_obj, dict) and rate_obj.get("raw") is not None:
                            trailing_div_rate = float(rate_obj.get("raw"))

                        yield_obj = sum_detail.get("dividendYield", {}) or sum_detail.get("trailingAnnualDividendYield", {})
                        if isinstance(yield_obj, dict) and yield_obj.get("raw") is not None:
                            trailing_div_yield = float(yield_obj.get("raw"))
                except Exception:
                    pass

                # Parse chart events
                recent_div_amounts = []
                one_year_ago_ts = int(time.time()) - (365 * 86400)
                divs_in_last_year = []

                if dividends_dict:
                    for ts_key, d_obj in sorted(dividends_dict.items(), key=lambda x: int(x[0])):
                        ts_val = int(ts_key)
                        amt = float(d_obj.get("amount", 0))
                        recent_div_amounts.append((ts_val, amt))
                        if ts_val >= one_year_ago_ts:
                            divs_in_last_year.append(amt)

                if ex_date_str == "N/A" and recent_div_amounts:
                    latest_ex_ts = recent_div_amounts[-1][0]
                    ex_date_str = datetime.fromtimestamp(latest_ex_ts, tz=NY_TZ).strftime("%b %d, %Y")

                num_divs = len(divs_in_last_year)
                if num_divs >= 10:
                    freq_str = "Monthly (12x per year)"
                    mult = 12
                elif num_divs in [3, 4, 5]:
                    freq_str = "Quarterly (4x per year)"
                    mult = 4
                elif num_divs == 2:
                    freq_str = "Semi-Annual (2x per year)"
                    mult = 2
                elif num_divs == 1:
                    freq_str = "Annual (1x per year)"
                    mult = 1
                else:
                    freq_str = "Quarterly (4x per year)"
                    mult = 4

                if pay_date_str == "N/A" and ex_date_str != "N/A":
                    try:
                        ex_parsed = datetime.strptime(ex_date_str, "%b %d, %Y")
                        est_pay = ex_parsed + timedelta(days=14 if "Monthly" in freq_str else 21)
                        pay_date_str = f"~{est_pay.strftime('%b %d, %Y')} (Est)"
                    except Exception:
                        pass

                last_payout = recent_div_amounts[-1][1] if recent_div_amounts else None
                annual_rate = trailing_div_rate or (last_payout * mult if last_payout else None)

                if (annual_rate and annual_rate > 0) or (trailing_div_yield and trailing_div_yield > 0) or last_payout:
                    calc_yield = ((annual_rate / current_price) * 100) if (annual_rate and current_price > 0) else ((trailing_div_yield * 100) if (trailing_div_yield and trailing_div_yield <= 1.0) else (trailing_div_yield or 0.0))
                    per_payout = last_payout if last_payout else (annual_rate / mult if annual_rate else (current_price * (calc_yield / 100) / mult))
                    annual_display = annual_rate if annual_rate else (per_payout * mult)

                    payout_ratio_str = ""
                    if payout_ratio is not None and payout_ratio > 0:
                        pr_pct = payout_ratio * 100 if payout_ratio <= 1.0 else payout_ratio
                        pr_tag = "🟢 (Highly Secure / Low Risk)" if pr_pct <= 50 else ("🟡 (Moderate Payout)" if pr_pct <= 75 else "⚠️ (High / Elevated Payout)")
                        payout_ratio_str = f"\n• **Sustainability:** Payout Ratio: `{pr_pct:.1f}% {pr_tag}`"

                    dividend_block = (
                        f"• **Yield & Payout:** `{calc_yield:.2f}%` • `${per_payout:.2f} / share` (`${annual_display:.2f} Annualized`)\n"
                        f"• **Frequency:** `{freq_str}`\n"
                        f"• **Key Dates:** Ex-Dividend: `{ex_date_str}` • Pay Date: `{pay_date_str}`"
                        f"{payout_ratio_str}"
                    )
                else:
                    dividend_block = "• **Status:** `No Regular Dividend (Zero Yield / Pure Growth Stock)`"

            except Exception:
                dividend_block = "• **Status:** `No Regular Dividend (Zero Yield / Pure Growth Stock)`"

            market_cap, shares, trailing_pe = None, None, None
            roe_str, margin_str, de_str, curr_ratio_str, fcf_str, quality_str, pfcf_str = "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", ""
            rev_growth_pct, net_inc_growth_pct = None, None
            earnings_date_str, prev_surprise_str, beta_str = "N/A", "", "N/A"

            try:
                t_obj = yf.Ticker(ticker_symbol)
                try:
                    shares = t_obj.fast_info.shares
                    market_cap = t_obj.fast_info.market_cap
                except Exception:
                    pass

                if not market_cap and shares and current_price:
                    market_cap = current_price * shares

                try:
                    ed_df = t_obj.earnings_dates
                    if ed_df is not None and not ed_df.empty:
                        future_rows = ed_df[ed_df['Reported EPS'].isna()] if 'Reported EPS' in ed_df.columns else pd.DataFrame()
                        if not future_rows.empty:
                            nxt_dt = future_rows.index[-1]
                            nxt_d = nxt_dt.date() if isinstance(nxt_dt, (datetime, pd.Timestamp)) else nxt_dt
                            days_left = (nxt_d - datetime.now().date()).days
                            earnings_date_str = f"`In {days_left} Days ({nxt_d.strftime('%b %d')})`" if days_left >= 0 else f"`{nxt_d.strftime('%b %d')}`"
                        
                        past_rows = ed_df[ed_df['Reported EPS'].notna()] if 'Reported EPS' in ed_df.columns else pd.DataFrame()
                        if not past_rows.empty and "Surprise(%)" in past_rows.columns:
                            raw_surp = float(past_rows["Surprise(%)"].iloc[0])
                            surp_val = raw_surp * 100 if abs(raw_surp) <= 1.0 else raw_surp
                            tag = "🎯" if surp_val >= 0 else "⚠️"
                            prev_surprise_str = f" | `Prev Beat: {surp_val:+.1f}% {tag}`"
                except Exception:
                    pass

                beta_val = calculate_beta_vs_spy(closes, http_session)
                if beta_val:
                    tag = " (High Volatility 🔥)" if beta_val >= 1.5 else (" (Moderate 📊)" if beta_val >= 0.8 else " (Defensive 🛡️)")
                    beta_str = f"`{beta_val:.2f}x`{tag}"

                q_inc = t_obj.quarterly_income_stmt
                ttm_net_inc, ttm_rev = None, None
                if q_inc is not None and not q_inc.empty:
                    rev_row = next((r for r in ["Total Revenue", "Operating Revenue", "Revenue"] if r in q_inc.index), None)
                    if rev_row:
                        rev_s = q_inc.loc[rev_row].dropna()
                        if len(rev_s) >= 5:
                            r0, r4 = float(rev_s.iloc[0]), float(rev_s.iloc[4])
                            if r4 > 0:
                                rev_growth_pct = ((r0 - r4) / r4) * 100
                        elif len(rev_s) >= 2:
                            r0, r4 = float(rev_s.iloc[0]), float(rev_s.iloc[-1])
                            if r4 > 0:
                                rev_growth_pct = ((r0 - r4) / r4) * 100
                        ttm_rev = float(rev_s.iloc[:4].sum()) if len(rev_s) >= 1 else None

                    inc_row = next((r for r in ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"] if r in q_inc.index), None)
                    if inc_row:
                        inc_s = q_inc.loc[inc_row].dropna()
                        if len(inc_s) >= 5:
                            i0, i4 = float(inc_s.iloc[0]), float(inc_s.iloc[4])
                            if i4 != 0:
                                net_inc_growth_pct = ((i0 - i4) / abs(i4)) * 100
                        elif len(inc_s) >= 2:
                            i0, i4 = float(inc_s.iloc[0]), float(inc_s.iloc[-1])
                            if i4 != 0:
                                net_inc_growth_pct = ((i0 - i4) / abs(i4)) * 100
                        ttm_net_inc = float(inc_s.iloc[:4].sum()) if len(inc_s) >= 1 else None

                q_bs = t_obj.quarterly_balance_sheet
                stockholders_equity, total_debt, current_assets, current_liab = None, None, None, None
                if q_bs is not None and not q_bs.empty:
                    eq_row = next((r for r in ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"] if r in q_bs.index), None)
                    if eq_row:
                        stockholders_equity = float(q_bs.loc[eq_row].dropna().iloc[0])

                    debt_row = next((r for r in ["Total Debt", "Long Term Debt And Capital Lease Obligation", "Total Non Current Liabilities Net Minority Interest"] if r in q_bs.index), None)
                    if debt_row:
                        total_debt = float(q_bs.loc[debt_row].dropna().iloc[0])

                    ca_row = next((r for r in ["Current Assets", "Total Current Assets"] if r in q_bs.index), None)
                    cl_row = next((r for r in ["Current Liabilities", "Total Current Liabilities"] if r in q_bs.index), None)
                    if ca_row and cl_row:
                        current_assets = float(q_bs.loc[ca_row].dropna().iloc[0])
                        current_liab = float(q_bs.loc[cl_row].dropna().iloc[0])

                q_cf = t_obj.quarterly_cash_flow
                ttm_fcf = None
                if q_cf is not None and not q_cf.empty:
                    ocf_row = next((r for r in ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"] if r in q_cf.index), None)
                    capex_row = next((r for r in ["Capital Expenditure", "Capital Expenditures"] if r in q_cf.index), None)
                    if ocf_row:
                        ocf_s = q_cf.loc[ocf_row].dropna()
                        ttm_ocf = float(ocf_s.iloc[:4].sum()) if len(ocf_s) >= 1 else 0
                        ttm_capex = abs(float(q_cf.loc[capex_row].dropna().iloc[:4].sum())) if capex_row else 0
                        ttm_fcf = ttm_ocf - ttm_capex

                if ttm_net_inc and stockholders_equity and stockholders_equity > 0:
                    roe_pct = (ttm_net_inc / stockholders_equity) * 100
                    roe_tag = " 💎" if roe_pct >= 20.0 else (" 🟢" if roe_pct >= 12.0 else "")
                    roe_str = f"`{roe_pct:.1f}%`{roe_tag}"

                if ttm_net_inc and ttm_rev and ttm_rev > 0:
                    margin_pct = (ttm_net_inc / ttm_rev) * 100
                    margin_tag = " 💎" if margin_pct >= 25.0 else (" 🟢" if margin_pct >= 10.0 else "")
                    margin_str = f"`{margin_pct:.1f}%`{margin_tag}"

                if total_debt is not None and stockholders_equity and stockholders_equity > 0:
                    de_ratio = total_debt / stockholders_equity
                    de_tag = " (Low Debt 🟢)" if de_ratio <= 0.6 else (" (Moderate 🟡)" if de_ratio <= 1.5 else " (High Debt ⚠️)")
                    de_str = f"`{de_ratio:.2f}x`{de_tag}"

                if current_assets and current_liab and current_liab > 0:
                    cr = current_assets / current_liab
                    cr_tag = " 🟢" if cr >= 1.5 else (" 🟡" if cr >= 1.0 else " ⚠️")
                    curr_ratio_str = f"`{cr:.2f}x`{cr_tag}"

                if ttm_fcf is not None:
                    fcf_fmt = format_large_number(ttm_fcf)
                    fcf_str = f"`{fcf_fmt}` (Yield: `{(ttm_fcf / market_cap) * 100:.1f}%`)" if (market_cap and market_cap > 0) else f"`{fcf_fmt}`"

                if ttm_fcf is not None and ttm_net_inc and ttm_net_inc > 0:
                    quality_ratio = ttm_fcf / ttm_net_inc
                    quality_str = f"`{quality_ratio:.2f}x` 🟢 (Real Cash Backing)" if quality_ratio >= 1.0 else (f"`{quality_ratio:.2f}x` 🟡 (Moderate Cash Conversion)" if quality_ratio >= 0.6 else f"`{quality_ratio:.2f}x` ⚠️ (Accrual / Paper Earnings)")

                if ttm_net_inc and ttm_net_inc > 0 and shares and shares > 0:
                    trailing_eps = ttm_net_inc / shares
                    pe_str = f"`{current_price / trailing_eps:.1f}x`" if trailing_eps > 0 else "`N/A (Pre-Profit)`"
                else:
                    pe_str = "`N/A`"

                if ttm_fcf and ttm_fcf > 0 and market_cap and market_cap > 0:
                    pfcf_str = f" | P/FCF: `{market_cap / ttm_fcf:.1f}x`"

            except Exception:
                pe_str = "`N/A`"

            targets_line_str = fetch_wallstreet_targets_tls(ticker_symbol, current_price)

            if is_etf:
                line_sector = f"• **Asset Class:** `Exchange-Traded Fund (ETF Basket)`\n• **Structure:** `Diversified Market Basket Holding`"
            elif sector and industry:
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

            profile_block = f"{line_sector}\n{line_cap}"
            catalysts_block = f"• **Next Earnings:** {earnings_date_str}{prev_surprise_str}\n• **Wall St. Targets:** {targets_line_str}"
            atr_fmt = f"±${atr:.2f} (±{(atr/current_price)*100:.1f}% swing)" if atr and current_price > 0 else "N/A"
            smart_money_block = f"• **Beta (Market Volatility):** {beta_str}\n• **Expected Daily Move (ATR):** `{atr_fmt}`"

            growth_parts = []
            if rev_growth_pct is not None:
                growth_parts.append(f"Revenue: `{rev_growth_pct:+.1f}%`")
            if net_inc_growth_pct is not None:
                growth_parts.append(f"Net Income: `{net_inc_growth_pct:+.1f}% 🚀`")
            line_growth = f"• **Growth (YoY):** {' | '.join(growth_parts)}" if growth_parts else ""

            health_elements = [
                f"• **Capital Efficiency:** ROE: {roe_str} | Net Margin: {margin_str}"
            ]
            if line_growth:
                health_elements.append(line_growth)
            health_elements.extend([
                f"• **Solvency & Liquidity:** Debt/Equity: {de_str} | Current Ratio: {curr_ratio_str}",
                f"• **Free Cash Flow:** {fcf_str}",
                f"• **Earnings Quality (FCF / Net Income):** {quality_str}",
                f"• **Valuation Multiples:** Trailing P/E: {pe_str}{pfcf_str}"
            ])

            health_block = "\n".join(health_elements)

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
            "catalysts_block": catalysts_block,
            "smart_money_block": smart_money_block,
            "profile_title": profile_title,
            "profile_block": profile_block,
            "health_block": health_block
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
    if data.get("health_block"):
        embed.add_field(name="📊 Balance Sheet & Cash Flow Health", value=data['health_block'], inline=False)

    embed.set_footer(text="Looney • On-Demand Market Terminal")
    return embed

# -------------------------------------------------------------
# 4. ROBUST INSTITUTIONAL ANALYST CONSENSUS (%TICKER)
# -------------------------------------------------------------
def fetch_analyst_consensus(ticker_symbol):
    sym = ticker_symbol.upper().strip()
    is_canadian = sym.endswith(".TO") or sym.endswith(".V")
    currency = "CAD" if is_canadian else "USD"

    try:
        t_obj = yf.Ticker(sym, session=http_session)

        # Step 1: Real-time price
        current_price = 0.0
        try:
            fi = t_obj.fast_info
            current_price = float(fi.last_price or 0)
        except Exception:
            pass

        if current_price == 0.0:
            try:
                hist = t_obj.history(period="2d")
                if not hist.empty and 'Close' in hist.columns:
                    current_price = float(hist['Close'].iloc[-1])
            except Exception:
                pass

        high_target = None
        mean_target = None
        low_target = None
        total_analysts = 0
        strong_buy, buy, hold, sell, strong_sell = 0, 0, 0, 0, 0
        consensus_score = 0.0

        # Step 2: Extract from yfinance analyst_price_targets (Crumb-managed)
        try:
            apt = t_obj.analyst_price_targets
            if apt and isinstance(apt, dict):
                h = apt.get("high")
                m = apt.get("mean") or apt.get("current")
                l = apt.get("low")
                if h and float(h) > 0 and (current_price == 0 or float(h) < current_price * 10):
                    high_target = float(h)
                if m and float(m) > 0 and (current_price == 0 or float(m) < current_price * 10):
                    mean_target = float(m)
                if l and float(l) > 0 and (current_price == 0 or float(l) < current_price * 10):
                    low_target = float(l)
        except Exception:
            pass

        # Step 3: Extract from yfinance recommendations
        try:
            rec_df = t_obj.recommendations
            if rec_df is not None and not rec_df.empty:
                row = rec_df.iloc[0]
                strong_buy = int(row.get("strongBuy", 0) or 0)
                buy = int(row.get("buy", 0) or 0)
                hold = int(row.get("hold", 0) or 0)
                sell = int(row.get("sell", 0) or 0)
                strong_sell = int(row.get("strongSell", 0) or 0)
                total_analysts = strong_buy + buy + hold + sell + strong_sell
        except Exception:
            pass

        # Step 4: Fallback to t_obj.info if targets or counts missing
        if not mean_target or total_analysts == 0:
            try:
                inf = t_obj.info or {}
                if not high_target and inf.get("targetHighPrice"):
                    h = float(inf["targetHighPrice"])
                    if current_price == 0 or h < current_price * 10:
                        high_target = h
                if not mean_target and inf.get("targetMeanPrice"):
                    m = float(inf["targetMeanPrice"])
                    if current_price == 0 or m < current_price * 10:
                        mean_target = m
                if not low_target and inf.get("targetLowPrice"):
                    l = float(inf["targetLowPrice"])
                    if current_price == 0 or l < current_price * 10:
                        low_target = l
                if total_analysts == 0 and inf.get("numberOfAnalystOpinions"):
                    total_analysts = int(inf["numberOfAnalystOpinions"])
                if consensus_score == 0.0 and inf.get("recommendationMean"):
                    consensus_score = float(inf["recommendationMean"])
            except Exception:
                pass

        # Step 5: Finviz TLS regex fallback for US stocks
        if not mean_target and not is_canadian:
            try:
                fz_res = cureq.get(f"https://finviz.com/quote.ashx?t={sym}&p=d", impersonate="chrome124", timeout=4)
                if fz_res.status_code == 200:
                    m_tp = re.search(r'Target\s*Price</td>\s*<td[^>]*>(?:<b>)?([\d\.]+)', fz_res.text, re.IGNORECASE)
                    m_rc = re.search(r'Recom</td>\s*<td[^>]*>(?:<b>)?([\d\.]+)', fz_res.text, re.IGNORECASE)
                    if m_tp:
                        val = float(m_tp.group(1))
                        if current_price == 0 or val < current_price * 10:
                            mean_target = val
                    if m_rc and consensus_score == 0.0:
                        consensus_score = float(m_rc.group(1))
            except Exception:
                pass

        if not mean_target and total_analysts == 0:
            return None, f"No active institutional analyst coverage found for `{sym}`."

        # Compute Consensus Score & Verdict
        if total_analysts > 0 and consensus_score == 0.0:
            consensus_score = ((strong_buy * 1.0) + (buy * 2.0) + (hold * 3.0) + (sell * 4.0) + (strong_sell * 5.0)) / total_analysts
        elif consensus_score == 0.0:
            consensus_score = 2.0

        if consensus_score <= 1.8:
            verdict = "Strong Buy 🟢"
            embed_color = 0x2ecc71
        elif consensus_score <= 2.5:
            verdict = "Moderate Buy 🟢"
            embed_color = 0x2ecc71
        elif consensus_score <= 3.5:
            verdict = "Hold / Neutral 🟡"
            embed_color = 0xf1c40f
        elif consensus_score <= 4.2:
            verdict = "Underperform / Sell 🔴"
            embed_color = 0xe74c3c
        else:
            verdict = "Strong Sell 🔴"
            embed_color = 0xe74c3c

        return {
            "ticker": sym,
            "current_price": current_price,
            "currency": currency,
            "high_target": high_target,
            "mean_target": mean_target,
            "low_target": low_target,
            "total_analysts": total_analysts,
            "strong_buy": strong_buy,
            "buy": buy,
            "hold": hold,
            "sell": sell,
            "strong_sell": strong_sell,
            "consensus_score": consensus_score,
            "verdict": verdict,
            "color": embed_color
        }, None

    except Exception as e:
        return None, str(e)

def create_analyst_embed(data):
    p = data["current_price"]
    curr = data["currency"]
    
    high_str = f"${data['high_target']:.2f} {curr}" if data["high_target"] else "N/A"
    if data["high_target"] and p > 0:
        up_high = ((data["high_target"] - p) / p) * 100
        tag = "🔺" if up_high >= 0 else "🔻"
        high_str += f" `({tag} {up_high:+.1f}%)`"

    mean_str = f"${data['mean_target']:.2f} {curr}" if data["mean_target"] else "N/A"
    if data["mean_target"] and p > 0:
        up_mean = ((data["mean_target"] - p) / p) * 100
        tag = "🔺" if up_mean >= 0 else "🔻"
        mean_str += f" `({tag} {up_mean:+.1f}%)`"

    low_str = f"${data['low_target']:.2f} {curr}" if data["low_target"] else "N/A"
    if data["low_target"] and p > 0:
        up_low = ((data["low_target"] - p) / p) * 100
        tag = "🔺" if up_low >= 0 else "🔻"
        low_str += f" `({tag} {up_low:+.1f}%)`"

    targets_text = (
        f"• 🟢 **Street High:** {high_str}\n"
        f"• 🎯 **Consensus Mean:** {mean_str}\n"
        f"• 🔴 **Street Low:** {low_str}"
    )

    tot = max(1, data["total_analysts"])
    sb_pct = (data["strong_buy"] / tot) * 100
    b_pct = (data["buy"] / tot) * 100
    h_pct = (data["hold"] / tot) * 100
    s_pct = (data["sell"] / tot) * 100
    ss_pct = (data["strong_sell"] / tot) * 100

    if data["total_analysts"] > 0 and (data["strong_buy"] + data["buy"] + data["hold"] + data["sell"] + data["strong_sell"]) > 0:
        breakdown_text = (
            f"• 🟢 **Strong Buy:** `{data['strong_buy']}` firms ({sb_pct:.1f}%)\n"
            f"• 🟢 **Moderate Buy:** `{data['buy']}` firms ({b_pct:.1f}%)\n"
            f"• 🟡 **Hold / Neutral:** `{data['hold']}` firms ({h_pct:.1f}%)\n"
            f"• 🔴 **Moderate Sell:** `{data['sell']}` firms ({s_pct:.1f}%)\n"
            f"• 🔴 **Strong Sell:** `{data['strong_sell']}` firms ({ss_pct:.1f}%)"
        )
        field_title = f"🗳️ Analyst Rating Breakdown ({data['total_analysts']} Total Votes)"
    else:
        breakdown_text = f"• **Consensus Sentiment:** `{data['verdict']}` (Institutional Survey)"
        field_title = "🗳️ Analyst Rating Breakdown"

    price_header = f"${p:.2f} {curr}" if p > 0 else "Live"
    embed = discord.Embed(
        title=f"🏛️ Institutional Analyst Consensus: {data['ticker']}",
        description=(
            f"**Current Price:** `{price_header}` | **Total Coverage:** `{data['total_analysts']} Wall/Bay Street Firms`\n"
            f"**Overall Consensus:** **{data['verdict']}** `(Score: {data['consensus_score']:.2f} / 5.0)`"
        ),
        color=data["color"]
    )

    embed.add_field(name="🎯 12-Month Price Targets", value=targets_text, inline=False)
    embed.add_field(name=field_title, value=breakdown_text, inline=False)

    if data["total_analysts"] > 0:
        bull_pct = ((data["strong_buy"] + data["buy"]) / tot) * 100
        summary_line = f"💡 **Institutional Takeaway:** `{bull_pct:.1f}%` of covering analysts are Bullish on **{data['ticker']}** with an average price target of `${data['mean_target']:.2f} {curr}`." if data["mean_target"] else f"💡 **Institutional Takeaway:** `{bull_pct:.1f}%` of covering analysts maintain a Buy rating."
    else:
        summary_line = f"💡 **Institutional Takeaway:** Consensus price target sits at `${data['mean_target']:.2f} {curr}`." if data["mean_target"] else f"💡 **Institutional Takeaway:** Institutional sentiment is {data['verdict']}."
    
    embed.add_field(name="📊 Summary Sentiment", value=summary_line, inline=False)
    embed.set_footer(text="Looney • Institutional Analyst & Price Target Terminal")
    return embed

# -------------------------------------------------------------
# 5. ON-DEMAND OPTIONS DEEP-DIVE ENGINE (#TICKER)
# -------------------------------------------------------------
def analyze_stock_options_setup(ticker_symbol):
    sym = ticker_symbol.upper().strip()
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1y"
        res = http_session.get(url, timeout=6)
        if res.status_code != 200:
            return None

        chart_data = res.json().get("chart", {}).get("result", [{}])[0]
        meta = chart_data.get("meta", {})
        indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]

        closes = [c for c in indicators.get("close", []) if c is not None]
        volumes = [v for v in indicators.get("volume", []) if v is not None]
        highs = [h for h in indicators.get("high", []) if h is not None]
        lows = [l for l in indicators.get("low", []) if l is not None]

        if len(closes) < 50:
            return None

        current_price = meta.get("regularMarketPrice") or closes[-1]
        prev_close = meta.get("regularMarketPreviousClose") or closes[-2]
        change_pct = ((current_price - prev_close) / prev_close) * 100

        sma_50 = sum(closes[-50:]) / 50
        sma_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else sma_50
        rsi_14 = calculate_rsi(closes, 14)
        macd_verdict = calculate_macd(closes)
        atr_14 = calculate_atr(highs, lows, closes, 14)

        vol_today = volumes[-1] if volumes else 0
        avg_vol_20 = (sum(volumes[-21:-1]) / 20) if len(volumes) >= 21 else vol_today
        rvol = (vol_today / avg_vol_20) if avg_vol_20 > 0 else 1.0

        h_prev, l_prev, c_prev = highs[-2], lows[-2], closes[-2]
        p = (h_prev + l_prev + c_prev) / 3.0
        r1 = (2.0 * p) - l_prev
        s1 = (2.0 * p) - h_prev

        hv_30 = calculate_historical_volatility(closes, 30)
        hv_90 = calculate_historical_volatility(closes, 90) if len(closes) >= 91 else hv_30
        iv_rank_est = max(5, min(95, int((hv_30 / (hv_90 * 1.3 if hv_90 > 0 else 1.0)) * 50)))

        bull_score, bear_score = 0, 0

        if current_price >= sma_50 and current_price >= sma_200:
            bull_score += 25
        elif current_price >= sma_50:
            bull_score += 15
        elif current_price < sma_50 and current_price < sma_200:
            bear_score += 25
        elif current_price < sma_50:
            bear_score += 15

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

        if final_score >= 80:
            badge = "🟢 HIGH CONVICTION"
            color = 0x2ecc71
        elif final_score >= 60:
            badge = "🟠 DEVELOPING / WATCHLIST"
            color = 0xe67e22
        else:
            badge = "🔴 LOW CONVICTION / AVOID"
            color = 0xe74c3c

        strike_step = 2.5 if current_price < 100 else (5.0 if current_price < 300 else 10.0)

        if is_bullish:
            if iv_rank_est < 40:
                strategy_name = "Long Call (Outright Bullish Momentum)"
                strike_short = round((current_price + (atr_14 * 0.5)) / strike_step) * strike_step
                prem_short = round(max(0.5, atr_14 * 0.9), 2)
                be_short = strike_short + prem_short

                strike_long = round((current_price - (atr_14 * 0.3)) / strike_step) * strike_step
                prem_long = round(max(1.0, atr_14 * 2.1), 2)
                be_long = strike_long + prem_long

                play_7_14 = f"Buy ${strike_short:.2f} Call @ ~${prem_short:.2f} | Break-Even: `${be_short:.2f}`"
                play_30_45 = f"Buy ${strike_long:.2f} Call @ ~${prem_long:.2f} | Break-Even: `${be_long:.2f}`"
                defensive_play = f"Bull Call Debit Spread: Buy ${strike_long:.2f} C / Sell ${strike_long + (strike_step*2):.2f} C (Debit: ~${prem_long*0.55:.2f})"
            else:
                strategy_name = "Bull Put Credit Spread (Neutral to Bullish Income)"
                sell_p_short = round((s1 - (atr_14 * 0.2)) / strike_step) * strike_step
                buy_p_short = sell_p_short - strike_step
                credit_short = round(strike_step * 0.28, 2)
                be_short = sell_p_short - credit_short

                sell_p_long = round((current_price * 0.95) / strike_step) * strike_step
                buy_p_long = sell_p_long - strike_step
                credit_long = round(strike_step * 0.33, 2)
                be_long = sell_p_long - credit_long

                play_7_14 = f"Sell ${sell_p_short:.2f} P / Buy ${buy_p_short:.2f} P | Credit: `${credit_short:.2f}` | Break-Even: `${be_short:.2f}`"
                play_30_45 = f"Sell ${sell_p_long:.2f} P / Buy ${buy_p_long:.2f} P | Credit: `${credit_long:.2f}` | Break-Even: `${be_long:.2f}`"
                defensive_play = f"Covered Call / Protective Married Put at ${s1:.2f} Support"
        else:
            if iv_rank_est < 40:
                strategy_name = "Bear Put Debit Spread (Moderately Bearish Momentum)"
                buy_p_short = round((current_price + (atr_14 * 0.2)) / strike_step) * strike_step
                sell_p_short = buy_p_short - strike_step
                debit_short = round(strike_step * 0.45, 2)
                be_short = buy_p_short - debit_short

                buy_p_long = round(current_price / strike_step) * strike_step
                sell_p_long = buy_p_long - (strike_step * 2)
                debit_long = round(strike_step * 0.90, 2)
                be_long = buy_p_long - debit_long

                play_7_14 = f"Buy ${buy_p_short:.2f} P / Sell ${sell_p_short:.2f} P | Debit: `${debit_short:.2f}` | Break-Even: `${be_short:.2f}`"
                play_30_45 = f"Buy ${buy_p_long:.2f} P / Sell ${sell_p_long:.2f} P | Debit: `${debit_long:.2f}` | Break-Even: `${be_long:.2f}`"
                defensive_play = f"Long Put: Buy 35-DTE ${buy_p_long:.2f} Put @ ~${debit_long*1.2:.2f} (Outright Bearish)"
            else:
                strategy_name = "Bear Call Credit Spread (Neutral to Bearish Resistance Play)"
                sell_c_short = round((r1 + (atr_14 * 0.2)) / strike_step) * strike_step
                buy_c_short = sell_c_short + strike_step
                credit_short = round(strike_step * 0.26, 2)
                be_short = sell_c_short + credit_short

                sell_c_long = round((current_price * 1.05) / strike_step) * strike_step
                buy_c_long = sell_c_long + strike_step
                credit_long = round(strike_step * 0.32, 2)
                be_long = sell_c_long + credit_long

                play_7_14 = f"Sell ${sell_c_short:.2f} C / Buy ${buy_c_short:.2f} C | Credit: `${credit_short:.2f}` | Break-Even: `${be_short:.2f}`"
                play_30_45 = f"Sell ${sell_c_long:.2f} C / Buy ${buy_c_long:.2f} C | Credit: `${credit_long:.2f}` | Break-Even: `${be_long:.2f}`"
                defensive_play = f"Iron Condor: Range-bound between ${s1:.2f} and ${r1:.2f}"

        return {
            "ticker": sym,
            "name": meta.get("shortName") or sym,
            "price": current_price,
            "change_pct": change_pct,
            "score": final_score,
            "badge": badge,
            "color": color,
            "is_bullish": is_bullish,
            "strategy_name": strategy_name,
            "iv_rank": iv_rank_est,
            "rsi_14": rsi_14,
            "rvol": rvol,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "macd_verdict": macd_verdict,
            "s1": s1,
            "r1": r1,
            "play_7_14": play_7_14,
            "play_30_45": play_30_45,
            "defensive_play": defensive_play
        }
    except Exception:
        return None

def create_deep_dive_options_embed(data):
    embed = discord.Embed(
        title=f"🎯 LOONEY OPTIONS INTELLIGENCE: {data['ticker']} [{data['badge']}]",
        description=f"**{data['ticker']}** is trading at **${data['price']:.2f}** ({data['change_pct']:+.2f}% today).\n**Quantitative Confidence Score:** `{data['score']} / 100`",
        color=data['color']
    )
    diag_text = (
        f"• **Trend Health:** Above 50D SMA (`${data['sma_50']:.2f}`) & 200D SMA (`${data['sma_200']:.2f}`)\n"
        f"• **Momentum:** RSI-14: `{data['rsi_14']:.1f}` | MACD: `{data['macd_verdict']}`\n"
        f"• **Volume & Volatility:** RVOL: `{data['rvol']:.1f}x` | IV Rank: `{data['iv_rank']}%` ({'Cheap / Buy Premium' if data['iv_rank'] < 40 else 'Expensive / Sell Premium'})\n"
        f"• **Key Levels:** Support (S1): `${data['s1']:.2f}` | Resistance (R1): `${data['r1']:.2f}`"
    )
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

    # TRIGGER 1: Institutional Analyst Consensus on `%TICKER` (e.g. %NVDA, %TD.TO, %MU)
    if content.startswith("%") and len(content) >= 2:
        raw_ticker = content[1:].split()[0].upper().replace("$", "")
        if len(raw_ticker) <= 12 and re.match(r'^[A-Z0-9=\-\.]+$', raw_ticker):
            async with message.channel.typing():
                data, err = await asyncio.to_thread(fetch_analyst_consensus, raw_ticker)
                if err:
                    await message.channel.send(f"❌ {err}")
                    return
                embed = create_analyst_embed(data)
                await message.channel.send(embed=embed)
                return

    # TRIGGER 2: Options Deep-Dive on `#TICKER` (e.g. #NVDA, #TSLA)
    if content.startswith("#") and len(content) >= 2:
        raw_ticker = content[1:].split()[0].upper().replace("$", "")
        if len(raw_ticker) <= 12 and re.match(r'^[A-Z0-9=\-\.]+$', raw_ticker):
            async with message.channel.typing():
                data = await asyncio.to_thread(analyze_stock_options_setup, raw_ticker)
                if not data:
                    await message.channel.send(f"❌ Could not compute options analytics for `{raw_ticker}`. Verify ticker symbol.")
                    return
                embed = create_deep_dive_options_embed(data)
                await message.channel.send(embed=embed)
                return

    # TRIGGER 3: Technicals Snapshot on `!TICKER` or `$TICKER` (e.g. !NVDA or $NVDA)
    if content.startswith("!") or content.startswith("$"):
        raw_cmd = content[1:].strip()
        first_word = raw_cmd.split()[0].lower() if raw_cmd else ""

        if first_word in ["price", "p", "four", "check", "opt", "options", "analyst", "ratings"]:
            await bot.process_commands(message)
            return

        potential_ticker = raw_cmd.split()[0].upper()
        if potential_ticker and len(potential_ticker) <= 12 and re.match(r'^[A-Z0-9=\-\.]+$', potential_ticker):
            async with message.channel.typing():
                data, err = await asyncio.to_thread(get_on_demand_data, potential_ticker)
                if err:
                    await message.channel.send(f"❌ {err}")
                    return
                embed = create_market_embed(data)
                await message.channel.send(embed=embed)
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

@bot.command(name="analyst", aliases=["ratings", "target"])
async def analyst_command(ctx, ticker: str):
    async with ctx.typing():
        data, err = await asyncio.to_thread(fetch_analyst_consensus, ticker)
        if err:
            await ctx.send(f"❌ {err}")
            return
        embed = create_analyst_embed(data)
        await ctx.send(embed=embed)

# -------------------------------------------------------------
# 7. ENTRYPOINT
# -------------------------------------------------------------
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not set.")
    else:
        bot.run(BOT_TOKEN)
