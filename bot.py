import os
import threading
import asyncio
import math
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, date, timedelta
import requests
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd
from curl_cffi import requests as cureq

# -------------------------------------------------------------
# 1. KEEP-ALIVE SERVER (For Render Free Tier)
# -------------------------------------------------------------
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Looney On-Demand Discord Bot is Live 24/7!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# -------------------------------------------------------------
# 2. BROWSER SESSION
# -------------------------------------------------------------
http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9"
})

# -------------------------------------------------------------
# 3. DISCORD BOT CLIENT
# -------------------------------------------------------------
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

KNOWN_ETFS = {"QQQ", "SPY", "IWM", "DIA", "VOO", "VTI", "GLD", "SLV", "USO", "BNO", "IBIT", "ETHA", "SPCX"}

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

def calculate_beta_vs_spy(closes, http_session):
    try:
        if len(closes) < 50:
            return None
        url_spy = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=1y"
        res_spy = http_session.get(url_spy, timeout=4)
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
    """Pulls Wall Street Targets using TLS Chrome Impersonation."""
    low_t = None
    mean_t = None
    high_t = None
    rating = None

    # Source 1: Finviz via Chrome TLS
    try:
        fz_url = f"https://finviz.com/quote.ashx?t={ticker_symbol}&p=d"
        fz_res = cureq.get(fz_url, impersonate="chrome124", timeout=4)
        if fz_res.status_code == 200:
            text = fz_res.text
            tp_match = re.search(r'Target\s*Price[^\d]+([\d,.]+)', text, re.IGNORECASE)
            rec_match = re.search(r'Recom[^\d]+([\d,.]+)', text, re.IGNORECASE)
            
            if tp_match:
                mean_t = float(tp_match.group(1).replace(',', ''))
            if rec_match:
                score = float(rec_match.group(1))
                rating = "Strong Buy 🟢" if score <= 1.8 else ("Buy 🟢" if score <= 2.5 else ("Hold 🟡" if score <= 3.5 else "Sell 🔴"))
    except Exception:
        pass

    # Source 2: TipRanks via Chrome TLS
    if not mean_t:
        try:
            tr_url = f"https://market.tipranks.com/api/stocks/getData/?name={ticker_symbol}"
            tr_res = cureq.get(tr_url, impersonate="chrome124", timeout=4)
            if tr_res.status_code == 200:
                tr_data = tr_res.json()
                pt = tr_data.get("ptConsensus", {})
                if pt:
                    low_t = pt.get("low")
                    mean_t = pt.get("priceTarget")
                    high_t = pt.get("high")
                c_rating = tr_data.get("consensuses", {}).get("consensusRating")
                if c_rating:
                    rating = c_rating.title() + " 🟢"
        except Exception:
            pass

    # Source 3: CNN Forecast via Chrome TLS
    if not mean_t:
        try:
            cnn_url = f"https://money.cnn.com/quote/forecast/forecast.html?symb={ticker_symbol}"
            cnn_res = cureq.get(cnn_url, impersonate="chrome124", timeout=4)
            if cnn_res.status_code == 200:
                m = re.search(r'median target of\s*([\d,.]+)', cnn_res.text, re.IGNORECASE)
                h = re.search(r'high estimate of\s*([\d,.]+)', cnn_res.text, re.IGNORECASE)
                l = re.search(r'low estimate of\s*([\d,.]+)', cnn_res.text, re.IGNORECASE)
                if m:
                    mean_t = float(m.group(1).replace(',', ''))
                if h:
                    high_t = float(h.group(1).replace(',', ''))
                if l:
                    low_t = float(l.group(1).replace(',', ''))
        except Exception:
            pass

    # Format Output String
    if mean_t and current_price > 0:
        upside = ((mean_t - current_price) / current_price) * 100
        up_tag = " 🔥" if upside >= 15 else (" 🟢" if upside > 0 else " 🔴")
        rating_part = f" | Rating: `{rating}`" if rating else ""
        if low_t and high_t:
            return f"Low: `${low_t:.2f}` | Mean: `${mean_t:.2f}` (**{upside:+.1f}%{up_tag}**) | High: `${high_t:.2f}`{rating_part}"
        else:
            return f"Mean: `${mean_t:.2f}` (**{upside:+.1f}% Upside{up_tag}**){rating_part}"

    return "N/A"

def get_on_demand_data(ticker_symbol):
    """Direct Chart API + Full Statement & YoY Growth Engine."""
    ticker_symbol = ticker_symbol.upper().strip()
    try:
        # 1. Pull Chart Data (Price, History Arrays, Range)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?interval=1d&range=1y"
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

        # Price & 1D Change
        current_price = meta.get("regularMarketPrice") or closes[-1]
        prev_close = meta.get("regularMarketPreviousClose") or meta.get("previousClose") or (closes[-2] if len(closes) >= 2 else current_price)
        change_pct = ((current_price - prev_close) / prev_close) * 100

        # Volume Multipliers with Exact Historical Average Numbers
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

        # Multi-Timeframe RSI (7D, 14D, 30D)
        rsi_7 = calculate_rsi(closes, 7)
        rsi_14 = calculate_rsi(closes, 14)
        rsi_30 = calculate_rsi(closes, 30)

        rsi_block = (
            f"• **7D (Fast / Scalp):** {get_rsi_tag(rsi_7)}\n"
            f"• **14D (Standard):** {get_rsi_tag(rsi_14)}\n"
            f"• **30D (Macro Trend):** {get_rsi_tag(rsi_30)}"
        )

        # 52-Week Range in Dollars
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

        # 50D & 200D SMA Trend Health
        sma_50_str = "N/A"
        sma_200_str = "N/A"
        verdict_str = "N/A"

        sma_50 = (sum(closes[-50:]) / 50) if len(closes) >= 50 else None
        sma_200 = (sum(closes[-200:]) / 200) if len(closes) >= 200 else None

        if sma_50:
            pct_50 = ((current_price - sma_50) / sma_50) * 100
            sma_50_str = f"`${sma_50:.2f}` (Above by +{pct_50:.1f}% 🟢)" if pct_50 >= 0 else f"`${sma_50:.2f}` (Below by {pct_50:.1f}% 🔴)"

        if sma_200:
            pct_200 = ((current_price - sma_200) / sma_200) * 100
            sma_200_str = f"`${sma_200:.2f}` (Above by +{pct_200:.1f}% 🟢)" if pct_200 >= 0 else f"`${sma_200:.2f}` (Below by {pct_200:.1f}% 🔴)"

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

        # MACD (12, 26, 9)
        macd_str = calculate_macd(closes)

        # Daily Pivot Levels (Support S1 & Resistance R1)
        pivot_str = "N/A"
        if len(highs) >= 2 and len(lows) >= 2 and len(closes) >= 2:
            h_prev = highs[-2]
            l_prev = lows[-2]
            c_prev = closes[-2]
            p = (h_prev + l_prev + c_prev) / 3.0
            r1 = (2.0 * p) - l_prev
            s1 = (2.0 * p) - h_prev
            pivot_str = f"`Support (S1): ${s1:.2f}` | `Resistance (R1): ${r1:.2f}`"

        # Expected Daily Move (14D ATR)
        atr = calculate_atr(highs, lows, closes, 14)

        # =================================================================
        # 2. ASSET CLASSIFICATION & INSTITUTIONAL HEALTH ENGINE
        # =================================================================
        quote_type = meta.get("instrumentType", "EQUITY")
        
        # 1. CRYPTO
        if quote_type == "CRYPTOCURRENCY" or "-USD" in ticker_symbol:
            profile_title = "🏢 Asset Class & Profile"
            profile_block = (
                f"• **Asset Class:** `Cryptocurrency (Decentralized Protocol)`\n"
                f"• **Network Utility:** `Digital Asset / Smart Contract Network`\n"
                f"• **Trading:** `24/7/365 Continuous Global Liquidity`"
            )
            catalysts_block = None
            smart_money_block = None
            health_block = None

        # 2. ETFs
        elif quote_type == "ETF" or ticker_symbol in KNOWN_ETFS:
            profile_title = "🏢 Fund Profile & Structure"
            profile_block = (
                f"• **Asset Class:** `Exchange-Traded Fund (ETF Basket)`\n"
                f"• **Structure:** `Diversified Market Basket Holding`\n"
                f"• **Type:** `Open-End Fund Vehicle`"
            )
            catalysts_block = None
            smart_money_block = None
            health_block = None

        # 3. FUTURES
        elif quote_type == "FUTURE" or "=F" in ticker_symbol:
            profile_title = "🏢 Asset Class & Profile"
            profile_block = (
                f"• **Asset Class:** `Commodity / Index Derivative Contract`\n"
                f"• **Contract Type:** `Standardized Delivery Futures`"
            )
            catalysts_block = None
            smart_money_block = None
            health_block = None

        # 4. EQUITIES / STOCKS (Full Institutional Audit with YoY Growth)
        else:
            profile_title = "🏢 Company Profile"
            
            # Step A: Sector & Industry
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

            # Step B: Financial Statement & Catalysts Extraction
            market_cap = None
            shares = None
            trailing_pe = None
            roe_str = "N/A"
            margin_str = "N/A"
            de_str = "N/A"
            curr_ratio_str = "N/A"
            fcf_str = "N/A"
            quality_str = "N/A"
            pfcf_str = ""
            rev_growth_pct = None
            net_inc_growth_pct = None

            earnings_date_str = "N/A"
            prev_surprise_str = ""
            beta_str = "N/A"

            try:
                t_obj = yf.Ticker(ticker_symbol)
                
                # Fast info for shares & cap
                try:
                    shares = t_obj.fast_info.shares
                    market_cap = t_obj.fast_info.market_cap
                except Exception:
                    pass

                if not market_cap and shares and current_price:
                    market_cap = current_price * shares

                # 1. Earnings Timing
                try:
                    ed_df = t_obj.earnings_dates
                    if ed_df is not None and not ed_df.empty:
                        future_rows = ed_df[ed_df['Reported EPS'].isna()] if 'Reported EPS' in ed_df.columns else pd.DataFrame()
                        if not future_rows.empty:
                            nxt_dt = future_rows.index[-1]
                            nxt_d = nxt_dt.date() if isinstance(nxt_dt, (datetime, pd.Timestamp)) else nxt_dt
                            days_left = (nxt_d - datetime.now().date()).days
                            if days_left >= 0:
                                earnings_date_str = f"`In {days_left} Days ({nxt_d.strftime('%b %d')})`"
                            else:
                                earnings_date_str = f"`{nxt_d.strftime('%b %d')}`"
                        
                        past_rows = ed_df[ed_df['Reported EPS'].notna()] if 'Reported EPS' in ed_df.columns else pd.DataFrame()
                        if not past_rows.empty and "Surprise(%)" in past_rows.columns:
                            raw_surp = float(past_rows["Surprise(%)"].iloc[0])
                            surp_val = raw_surp * 100 if abs(raw_surp) <= 1.0 else raw_surp
                            tag = "🎯" if surp_val >= 0 else "⚠️"
                            prev_surprise_str = f" | `Prev Beat: {surp_val:+.1f}% {tag}`"
                except Exception:
                    pass

                if earnings_date_str == "N/A":
                    try:
                        cal = t_obj.calendar
                        if cal is not None:
                            ed_val = cal.get("Earnings Date") if isinstance(cal, dict) else (cal.loc["Earnings Date"].values if hasattr(cal, "loc") and "Earnings Date" in cal.index else None)
                            if ed_val is not None and len(ed_val) > 0:
                                target_ed = ed_val[0]
                                ed_d = target_ed.date() if isinstance(target_ed, (datetime, pd.Timestamp)) else target_ed
                                days_left = (ed_d - datetime.now().date()).days
                                if days_left >= 0:
                                    earnings_date_str = f"`In {days_left} Days ({ed_d.strftime('%b %d')})`"
                    except Exception:
                        pass

                # 2. Beta calculation vs SPY
                beta_val = calculate_beta_vs_spy(closes, http_session)
                if beta_val:
                    tag = " (High Volatility 🔥)" if beta_val >= 1.5 else (" (Moderate 📊)" if beta_val >= 0.8 else " (Defensive 🛡️)")
                    beta_str = f"`{beta_val:.2f}x`{tag}"

                # 3. Financial Statements Calculations (Income, Balance Sheet, Cash Flow)
                q_inc = t_obj.quarterly_income_stmt
                ttm_net_inc = None
                ttm_rev = None
                if q_inc is not None and not q_inc.empty:
                    # Net Income Row
                    inc_row = next((r for r in ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"] if r in q_inc.index), None)
                    if inc_row:
                        inc_s = q_inc.loc[inc_row].dropna()
                        if len(inc_s) >= 4:
                            i0 = float(inc_s.iloc[0])
                            i4 = float(inc_s.iloc[3]) if len(inc_s) >= 4 else float(inc_s.iloc[-1])
                            if i4 != 0:
                                net_inc_growth_pct = ((i0 - i4) / abs(i4)) * 100
                            ttm_net_inc = float(inc_s.iloc[:4].sum())
                        else:
                            ttm_net_inc = float(inc_s.sum())

                    # Revenue Row
                    rev_row = next((r for r in ["Total Revenue", "Operating Revenue", "Revenue"] if r in q_inc.index), None)
                    if rev_row:
                        rev_s = q_inc.loc[rev_row].dropna()
                        if len(rev_s) >= 4:
                            r0 = float(rev_s.iloc[0])
                            r4 = float(rev_s.iloc[3]) if len(rev_s) >= 4 else float(rev_s.iloc[-1])
                            if r4 > 0:
                                rev_growth_pct = ((r0 - r4) / r4) * 100
                            ttm_rev = float(rev_s.iloc[:4].sum())
                        else:
                            ttm_rev = float(rev_s.sum())

                # Balance Sheet
                q_bs = t_obj.quarterly_balance_sheet
                stockholders_equity = None
                total_debt = None
                current_assets = None
                current_liab = None
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

                # Cash Flow (FCF)
                q_cf = t_obj.quarterly_cash_flow
                ttm_fcf = None
                if q_cf is not None and not q_cf.empty:
                    ocf_row = next((r for r in ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"] if r in q_cf.index), None)
                    capex_row = next((r for r in ["Capital Expenditure", "Capital Expenditures"] if r in q_cf.index), None)
                    if ocf_row:
                        ocf_s = q_cf.loc[ocf_row].dropna()
                        ttm_ocf = float(ocf_s.iloc[:4].sum()) if len(ocf_s) >= 1 else 0
                        ttm_capex = 0
                        if capex_row:
                            capex_s = q_cf.loc[capex_row].dropna()
                            ttm_capex = abs(float(capex_s.iloc[:4].sum())) if len(capex_s) >= 1 else 0
                        ttm_fcf = ttm_ocf - ttm_capex

                # 4. Compute Health Metrics
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
                    if market_cap and market_cap > 0:
                        fcf_yield = (ttm_fcf / market_cap) * 100
                        fcf_str = f"`{fcf_fmt}` (Yield: `{fcf_yield:.1f}%`)"
                    else:
                        fcf_str = f"`{fcf_fmt}`"

                if ttm_fcf is not None and ttm_net_inc and ttm_net_inc > 0:
                    quality_ratio = ttm_fcf / ttm_net_inc
                    if quality_ratio >= 1.0:
                        quality_str = f"`{quality_ratio:.2f}x` 🟢 (Real Cash Backing)"
                    elif quality_ratio >= 0.6:
                        quality_str = f"`{quality_ratio:.2f}x` 🟡 (Moderate Cash Conversion)"
                    else:
                        quality_str = f"`{quality_ratio:.2f}x` ⚠️ (Accrual / Paper Earnings)"

                if ttm_net_inc and ttm_net_inc > 0 and shares and shares > 0:
                    trailing_eps = ttm_net_inc / shares
                    if trailing_eps > 0:
                        trailing_pe = current_price / trailing_eps
                        pe_str = f"`{trailing_pe:.1f}x`"
                    else:
                        pe_str = "`N/A (Pre-Profit)`"
                else:
                    pe_str = "`N/A (Pre-Profit)`"

                if ttm_fcf and ttm_fcf > 0 and market_cap and market_cap > 0:
                    pfcf_str = f" | P/FCF: `{market_cap / ttm_fcf:.1f}x`"

            except Exception:
                pe_str = "`N/A`"

            # 4. Multi-Source Wall Street Price Targets
            targets_line_str = fetch_wallstreet_targets_tls(ticker_symbol, current_price)

            # Construct Blocks
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

            profile_block = f"{line_sector}\n{line_cap}"

            catalysts_block = (
                f"• **Next Earnings:** {earnings_date_str}{prev_surprise_str}\n"
                f"• **Wall St. Targets:** {targets_line_str}"
            )

            atr_fmt = f"±${atr:.2f} (±{(atr/current_price)*100:.1f}% swing)" if atr and current_price > 0 else "N/A"
            smart_money_block = (
                f"• **Beta (Market Volatility):** {beta_str}\n"
                f"• **Expected Daily Move (ATR):** `{atr_fmt}`"
            )

            # Line 2 in Health: YoY Growth
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

@bot.event
async def on_ready():
    print(f"🤖 Looney is ONLINE and listening in Discord as: {bot.user}")

# -------------------------------------------------------------
# 4. INSTANT AUTO-TRIGGER (Non-Blocking Async Execution)
# -------------------------------------------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()

    if content.startswith("!") or content.startswith("$"):
        raw_cmd = content[1:].strip()
        first_word = raw_cmd.split()[0].lower() if raw_cmd else ""

        if first_word in ["price", "p", "four", "check"]:
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

# Standard Fallback Commands
@bot.command(name="price", aliases=["p", "four", "check"])
async def price_command(ctx, ticker: str):
    async with ctx.typing():
        data, err = await asyncio.to_thread(get_on_demand_data, ticker)
        if err:
            await ctx.send(f"❌ {err}")
            return
        embed = create_market_embed(data)
        await ctx.send(embed=embed)

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not set.")
    else:
        bot.run(BOT_TOKEN)
