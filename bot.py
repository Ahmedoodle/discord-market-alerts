import os
import threading
import asyncio
import math
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd

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

def get_on_demand_data(ticker_symbol):
    """Direct Chart API + Pure Statement Engine with Exact Average Volumes."""
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
        atr_str = "N/A"
        atr = calculate_atr(highs, lows, closes, 14)
        if atr and current_price > 0:
            atr_pct = (atr / current_price) * 100
            atr_str = f"`±${atr:.2f}` (±{atr_pct:.1f}% typical daily swing)"

        # =================================================================
        # 2. PURE STATEMENT-BASED FUNDAMENTALS & BALANCE SHEET ENGINE
        # =================================================================
        quote_type = meta.get("instrumentType", "EQUITY")
        
        # 1. CRYPTO
        if quote_type == "CRYPTOCURRENCY" or "-USD" in ticker_symbol:
            fund_title = "🏢 Asset Class & Profile"
            t_obj = yf.Ticker(ticker_symbol)
            m_cap = getattr(t_obj.fast_info, "market_cap", None)
            cap_fmt = format_large_number(m_cap) if m_cap else "N/A"
            tier = "Mega-Cap 👑" if m_cap and m_cap >= 2e11 else ("Large-Cap 🏢" if m_cap and m_cap >= 1e10 else "Mid/Small-Cap 📈")
            profile_block = (
                f"• **Asset Class:** `Cryptocurrency (Decentralized Protocol)`\n"
                f"• **Market Cap:** `{cap_fmt}` ({tier})\n"
                f"• **Valuation:** `Digital Asset / Network Utility`"
            )

        # 2. ETFs
        elif quote_type == "ETF" or ticker_symbol in KNOWN_ETFS:
            fund_title = "🏢 Fund Profile & Structure"
            t_obj = yf.Ticker(ticker_symbol)
            m_cap = getattr(t_obj.fast_info, "market_cap", None)
            cap_fmt = format_large_number(m_cap) if m_cap else "N/A"
            profile_block = (
                f"• **Asset Class:** `Exchange-Traded Fund (ETF Basket)`\n"
                f"• **Total Net Assets:** `{cap_fmt}`\n"
                f"• **Strategy:** `Diversified Index / Holdings Basket`"
            )

        # 3. FUTURES
        elif quote_type == "FUTURE" or "=F" in ticker_symbol:
            fund_title = "🏢 Asset Class & Profile"
            profile_block = (
                f"• **Asset Class:** `Commodity / Index Derivative Contract`\n"
                f"• **Contract Type:** `Standardized Delivery Futures`"
            )

        # 4. EQUITIES / STOCKS (Computed directly from filed balance sheet & statements)
        else:
            fund_title = "🏢 Valuation, Earnings & Growth"
            t_obj = yf.Ticker(ticker_symbol)
            fi = t_obj.fast_info
            
            # Market Cap & Shares
            market_cap = getattr(fi, "market_cap", None)
            shares = getattr(fi, "shares", None)
            if not market_cap and shares and current_price:
                market_cap = current_price * shares

            # Sector / Industry from Search API
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

            # Direct Calculations from Filed Financial Statements
            trailing_pe = None
            rev_growth_pct = None
            net_inc_growth_pct = None
            profit_margin_pct = None

            try:
                q_inc = t_obj.quarterly_income_stmt
                if q_inc is not None and not q_inc.empty:
                    # Find Revenue Row
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
                    else:
                        ttm_rev = None

                    # Find Net Income Row
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

                        # Compute Real Trailing P/E from Balance Sheet Net Income!
                        if ttm_net_inc and ttm_net_inc > 0 and shares and shares > 0:
                            trailing_eps = ttm_net_inc / shares
                            if trailing_eps > 0:
                                trailing_pe = current_price / trailing_eps

                        # Compute Profit Margin
                        if ttm_net_inc is not None and ttm_rev and ttm_rev > 0:
                            profit_margin_pct = (ttm_net_inc / ttm_rev) * 100
            except Exception:
                pass

            # Construct Output Lines
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
            
            profile_block = "\n".join(elements)

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
            "atr_str": atr_str,
            "fund_title": fund_title,
            "profile_block": profile_block
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
    embed.add_field(name="⚡ Expected Daily Move", value=data['atr_str'], inline=False)
    if data.get("profile_block"):
        embed.add_field(name=data.get("fund_title", "🏢 Valuation, Earnings & Growth"), value=data['profile_block'], inline=False)

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
