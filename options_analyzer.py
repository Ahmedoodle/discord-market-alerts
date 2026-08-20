import os
import threading
import asyncio
import math
import re
import time
import concurrent.futures
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import requests
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd

# -------------------------------------------------------------
# 1. CONFIGURATION, WEBHOOK & BRANDING
# -------------------------------------------------------------
DISCORD_OPTIONS_WEBHOOK_URL = os.getenv(
    "DISCORD_OPTIONS_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1540116236073959555/Cd3S1gwzHZjh2te36-2h8iI7lzL2mUkTiCPS5ueZ1YdsEByp0QjcX-3lwWa892bjOA1g"
)
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
BOT_NAME = "Looney Options Intelligence"
BOT_AVATAR_URL = "https://cdn.discordapp.com/attachments/1536082016184045750/1539077205437714442/IMG_6630.jpg?ex=6a8500d8&is=6a83af58&hm=f46d7b936827c9651de6bafe607af3e23c40009ee9799431f622886c85c78013&"

NY_TZ = ZoneInfo("America/New_York")

# Full Nasdaq 100 Universe
NASDAQ_100 = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST",
    "ASML", "PEP", "NFLX", "AZN", "LIN", "AMD", "TMUS", "ADBE", "CSCO", "QCOM",
    "TXN", "AMAT", "INTU", "ISRG", "CMCSA", "HON", "AMGN", "BKNG", "VRTX", "SBUX",
    "PANW", "MDLZ", "GILD", "LRCX", "REGN", "ADP", "MU", "MELI", "KLAC", "SNPS",
    "CDNS", "PYPL", "CRWD", "ABNB", "MAR", "CSX", "CTAS", "ORLY", "NXPI", "PCAR",
    "WBD", "MRVL", "ROP", "MCHP", "FTNT", "DXCM", "KDP", "MNST", "LULU", "ADI",
    "KHC", "PAYX", "ROST", "IDXX", "ODFL", "EXC", "CHTR", "AEP", "FAST", "BIIB",
    "CPRT", "GEHC", "TEAM", "VRSK", "EA", "BKR", "CTSH", "DDOG", "ZS", "ANSS",
    "CSGP", "ON", "MRNA", "ILMN", "DLTR", "WDAY", "CEG", "SMCI", "DASH", "MSTR",
    "ARM", "TTD", "RBLX", "PLTR", "IREN", "RKLB", "SHOP.TO", "INTC", "IBM"
]

http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*"
})

# -------------------------------------------------------------
# 2. 24/7 KEEP-ALIVE SERVER WITH SELF-PINGER
# -------------------------------------------------------------
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Looney Options Analyzer is Live 24/7!")

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
# 3. MATHEMATICAL INDICATORS & VOLATILITY ENGINE
# -------------------------------------------------------------
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
        return 0, 0, "Neutral"
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
        return 0, 0, "Neutral"

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
        status = "Bullish Expanding 🟢" if hist_curr >= hist_prev else "Bullish Slowing 🟡"
    else:
        status = "Bearish Expanding 🔴" if hist_curr <= hist_prev else "Bearish Slowing 🟡"

    return curr_macd, curr_sig, status

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
    annualized_vol = daily_vol * math.sqrt(252)
    return annualized_vol

# -------------------------------------------------------------
# 4. QUANT SCORING & DFOL OPTIONS STRATEGY ENGINE
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

        # Technical Indicators
        sma_50 = sum(closes[-50:]) / 50
        sma_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else sma_50
        rsi_7 = calculate_rsi(closes, 7)
        rsi_14 = calculate_rsi(closes, 14)
        _, _, macd_verdict = calculate_macd(closes)
        atr_14 = calculate_atr(highs, lows, closes, 14)

        # Volume Multipliers
        vol_today = volumes[-1] if volumes else 0
        avg_vol_20 = (sum(volumes[-21:-1]) / 20) if len(volumes) >= 21 else vol_today
        rvol = (vol_today / avg_vol_20) if avg_vol_20 > 0 else 1.0

        # Support / Resistance Pivots
        h_prev, l_prev, c_prev = highs[-2], lows[-2], closes[-2]
        p = (h_prev + l_prev + c_prev) / 3.0
        r1 = (2.0 * p) - l_prev
        s1 = (2.0 * p) - h_prev

        # Volatility & IV Approximation
        hv_30 = calculate_historical_volatility(closes, 30)
        hv_90 = calculate_historical_volatility(closes, 90) if len(closes) >= 91 else hv_30
        iv_rank_est = max(5, min(95, int((hv_30 / (hv_90 * 1.3 if hv_90 > 0 else 1.0)) * 50)))

        # -------------------------------------------------------------
        # QUANT CONFIDENCE SCORING ALGORITHM (0 - 100)
        # -------------------------------------------------------------
        bull_score = 0
        bear_score = 0

        # Trend Scoring (25 pts)
        if current_price >= sma_50 and current_price >= sma_200:
            bull_score += 25
        elif current_price >= sma_50:
            bull_score += 15
        elif current_price < sma_50 and current_price < sma_200:
            bear_score += 25
        elif current_price < sma_50:
            bear_score += 15

        # RSI Momentum Sweet Spot (20 pts)
        if 52 <= rsi_14 <= 68:
            bull_score += 20
        elif rsi_14 > 68:
            bull_score += 10  # Overbought extension
        elif 32 <= rsi_14 <= 48:
            bear_score += 20
        elif rsi_14 < 32:
            bear_score += 10  # Oversold extension

        # MACD Alignment (20 pts)
        if "Bullish Expanding" in macd_verdict:
            bull_score += 20
        elif "Bullish" in macd_verdict:
            bull_score += 12
        elif "Bearish Expanding" in macd_verdict:
            bear_score += 20
        elif "Bearish" in macd_verdict:
            bear_score += 12

        # Volume Conviction (15 pts)
        if rvol >= 1.5:
            bull_score += 15 if change_pct >= 0 else 0
            bear_score += 15 if change_pct < 0 else 0
        elif rvol >= 1.1:
            bull_score += 10 if change_pct >= 0 else 0
            bear_score += 10 if change_pct < 0 else 0
        else:
            bull_score += 5
            bear_score += 5

        # Volatility Match (20 pts - DFOL Rule)
        # Selling options in High IV, Buying options in Low IV
        if bull_score >= bear_score:
            if iv_rank_est < 35:
                bull_score += 20  # Low IV: Perfect for Long Calls / Debit Spreads
            elif iv_rank_est > 50:
                bull_score += 18  # High IV: Perfect for Bull Put Credit Spreads
            else:
                bull_score += 12
        else:
            if iv_rank_est < 35:
                bear_score += 20  # Low IV: Perfect for Long Puts / Debit Spreads
            elif iv_rank_est > 50:
                bear_score += 18  # High IV: Perfect for Bear Call Credit Spreads
            else:
                bear_score += 12

        final_score = max(bull_score, bear_score)
        is_bullish = bull_score >= bear_score

        # Badge Tier
        if final_score >= 80:
            badge = "🟢 HIGH CONVICTION"
            color = 0x2ecc71  # Green
        elif final_score >= 60:
            badge = "🟠 DEVELOPING / WATCHLIST"
            color = 0xe67e22  # Orange
        else:
            badge = "🔴 LOW CONVICTION / AVOID"
            color = 0xe74c3c  # Red

        # -------------------------------------------------------------
        # DFOL STRATEGY DECISION & EXACT STRIKE CALCULATIONS
        # -------------------------------------------------------------
        strike_step = 2.5 if current_price < 100 else (5.0 if current_price < 300 else 10.0)
        
        # Exact Strikes & Break-Evens
        if is_bullish:
            if iv_rank_est < 40:
                strategy_name = "Long Call (Outright Bullish Momentum)"
                strategy_type = "LONG_CALL"
                
                # 7-14 DTE (Fast Scalp)
                strike_short = round((current_price + (atr_14 * 0.5)) / strike_step) * strike_step
                prem_short = round(max(0.5, atr_14 * 0.9), 2)
                be_short = strike_short + prem_short  # Golden Rule: Add Net Debit

                # 30-45 DTE (Standard Swing)
                strike_long = round((current_price - (atr_14 * 0.3)) / strike_step) * strike_step  # Slightly ITM
                prem_long = round(max(1.0, atr_14 * 2.1), 2)
                be_long = strike_long + prem_long
                
                play_7_14 = f"Buy ${strike_short:.2f} Call @ ~${prem_short:.2f} | Break-Even: `${be_short:.2f}`"
                play_30_45 = f"Buy ${strike_long:.2f} Call @ ~${prem_long:.2f} | Break-Even: `${be_long:.2f}`"
                defensive_play = f"Bull Call Debit Spread: Buy ${strike_long:.2f} C / Sell ${strike_long + (strike_step*2):.2f} C (Debit: ~${prem_long*0.55:.2f})"

            else:
                strategy_name = "Bull Put Credit Spread (Neutral to Bullish Income)"
                strategy_type = "BULL_PUT_SPREAD"
                
                # 7-14 DTE
                sell_p_short = round((s1 - (atr_14 * 0.2)) / strike_step) * strike_step
                buy_p_short = sell_p_short - strike_step
                credit_short = round(strike_step * 0.28, 2)
                be_short = sell_p_short - credit_short  # Golden Rule: RRR Subtract Credit

                # 30-45 DTE
                sell_p_long = round((current_price * 0.95) / strike_step) * strike_step
                buy_p_long = sell_p_long - strike_step
                credit_long = round(strike_step * 0.33, 2)
                be_long = sell_p_long - credit_long

                play_7_14 = f"Sell ${sell_p_short:.2f} P / Buy ${buy_p_short:.2f} P | Credit: `${credit_short:.2f}` | Break-Even: `${be_short:.2f}`"
                play_30_45 = f"Sell ${sell_p_long:.2f} P / Buy ${buy_p_long:.2f} P | Credit: `${credit_long:.2f}` | Break-Even: `${be_long:.2f}`"
                defensive_play = f"Covered Call / Protective Married Put (Income buffer at ${s1:.2f} Support)"

        else:
            if iv_rank_est < 40:
                strategy_name = "Bear Put Debit Spread (Moderately Bearish Momentum)"
                strategy_type = "BEAR_PUT_SPREAD"
                
                # 7-14 DTE
                buy_p_short = round((current_price + (atr_14 * 0.2)) / strike_step) * strike_step
                sell_p_short = buy_p_short - strike_step
                debit_short = round(strike_step * 0.45, 2)
                be_short = buy_p_short - debit_short  # Golden Rule: Bear means subtract debit

                # 30-45 DTE
                buy_p_long = round((current_price) / strike_step) * strike_step
                sell_p_long = buy_p_long - (strike_step * 2)
                debit_long = round(strike_step * 0.90, 2)
                be_long = buy_p_long - debit_long

                play_7_14 = f"Buy ${buy_p_short:.2f} P / Sell ${sell_p_short:.2f} P | Debit: `${debit_short:.2f}` | Break-Even: `${be_short:.2f}`"
                play_30_45 = f"Buy ${buy_p_long:.2f} P / Sell ${sell_p_long:.2f} P | Debit: `${debit_long:.2f}` | Break-Even: `${be_long:.2f}`"
                defensive_play = f"Long Put: Buy 35-DTE ${buy_p_long:.2f} Put @ ~${debit_long*1.2:.2f} (Outright Bearish)"

            else:
                strategy_name = "Bear Call Credit Spread (Neutral to Bearish Resistance Play)"
                strategy_type = "BEAR_CALL_SPREAD"
                
                # 7-14 DTE
                sell_c_short = round((r1 + (atr_14 * 0.2)) / strike_step) * strike_step
                buy_c_short = sell_c_short + strike_step
                credit_short = round(strike_step * 0.26, 2)
                be_short = sell_c_short + credit_short  # Golden Rule: RRR Add Credit

                # 30-45 DTE
                sell_c_long = round((current_price * 1.05) / strike_step) * strike_step
                buy_c_long = sell_c_long + strike_step
                credit_long = round(strike_step * 0.32, 2)
                be_long = sell_c_long + credit_long

                play_7_14 = f"Sell ${sell_c_short:.2f} C / Buy ${buy_c_short:.2f} C | Credit: `${credit_short:.2f}` | Break-Even: `${be_short:.2f}`"
                play_30_45 = f"Sell ${sell_c_long:.2f} C / Buy ${buy_c_long:.2f} C | Credit: `${credit_long:.2f}` | Break-Even: `${be_long:.2f}`"
                defensive_play = f"Iron Condor: Harvest high IV premium between ${s1:.2f} and ${r1:.2f}"

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
            "strategy_type": strategy_type,
            "iv_rank": iv_rank_est,
            "rsi_14": rsi_14,
            "rvol": rvol,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "macd_verdict": macd_verdict,
            "atr": atr_14,
            "s1": s1,
            "r1": r1,
            "play_7_14": play_7_14,
            "play_30_45": play_30_45,
            "defensive_play": defensive_play
        }
    except Exception as e:
        return None

# -------------------------------------------------------------
# 5. 30-MINUTE AUTOMATIC TOP 10 SCANNER
# -------------------------------------------------------------
def run_top10_options_radar():
    now_ny = datetime.now(NY_TZ)
    time_str = now_ny.strftime("%I:%M %p %Z")
    logging_header = f"Starting 30-Minute Nasdaq 100 Options Scan at {time_str}..."
    print(f"\n[SCANNER] {logging_header}")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(analyze_stock_options_setup, sym): sym for sym in NASDAQ_100}
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                results.append(res)

    # Sort descending by Confidence Score
    results.sort(key=lambda x: x["score"], reverse=True)
    top_10 = results[:10]

    if not top_10:
        print("[SCANNER] No results generated.")
        return

    # Build Top 10 Discord Embed
    embed_desc = ""
    for i, item in enumerate(top_10, 1):
        direction_tag = "🟢 (Bullish)" if item["is_bullish"] else "🔴 (Bearish)"
        embed_desc += (
            f"**{i}. {item['ticker']} — ${item['price']:.2f}** | **Score: {item['score']}%** {direction_tag}\n"
            f"• **Strategy:** `{item['strategy_name']}` (IV Rank: `{item['iv_rank']}%`)\n"
            f"• ⚡ **7–14 DTE:** {item['play_7_14']}\n"
            f"• 🏛️ **30–45 DTE:** {item['play_30_45']}\n"
            f"• **Catalyst:** RSI: `{item['rsi_14']:.1f}` • RVOL: `{item['rvol']:.1f}x` • MACD: `{item['macd_verdict']}`\n\n"
        )

    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_AVATAR_URL,
        "embeds": [{
            "title": f"🚨 NASDAQ 100 OPTIONS RADAR [TOP 10 QUANTITATIVE PICKS]",
            "description": f"*Live Quantitative Ranking across 100 Nasdaq Securities as of {time_str}.*\n\n{embed_desc}",
            "color": 3066993,  # Green
            "footer": {"text": "Looney Options Intelligence • Type '#TICKER' in chat for deep-dive Greeks & exit targets"}
        }]
    }

    try:
        res = requests.post(DISCORD_OPTIONS_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        print(f"[SCANNER] Top 10 Options Radar successfully dispatched to Discord at {time_str}!")
    except Exception as e:
        print(f"[SCANNER ERROR] Failed to dispatch webhook: {e}")

# Background Scheduler Loop: Runs automatically every 30 minutes
def background_30min_radar_loop():
    time.sleep(10)  # Wait for boot
    while True:
        try:
            now = datetime.now(NY_TZ)
            # Active during Market Sessions (Monday-Friday 9:00 AM - 4:30 PM EST)
            if now.weekday() <= 4 and (9 <= now.hour <= 16):
                run_top10_options_radar()
            else:
                # Off-hours test / maintenance ping
                print(f"[RADAR IDLE] Market closed ({now.strftime('%I:%M %p %Z')}). Next scan in 30 minutes.")
        except Exception as e:
            print(f"[LOOP ERROR] {e}")
        time.sleep(1800)  # 30 Minutes

threading.Thread(target=background_30min_radar_loop, daemon=True).start()

# -------------------------------------------------------------
# 6. ON-DEMAND DEEP-DIVE DISCORD BOT CLIENT (`#TICKER`)
# -------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def create_deep_dive_options_embed(data):
    embed = discord.Embed(
        title=f"🎯 LOONEY OPTIONS INTELLIGENCE: {data['ticker']} [{data['badge']}]",
        description=f"**{data['ticker']}** is trading at **${data['price']:.2f}** ({data['change_pct']:+.2f}% today).\n**Quantitative Confidence Score:** `{data['score']} / 100`",
        color=data['color']
    )

    # 1. Technical & Volatility Diagnostics
    diag_text = (
        f"• **Trend Health:** Above 50D SMA (`${data['sma_50']:.2f}`) & 200D SMA (`${data['sma_200']:.2f}`)\n"
        f"• **Momentum:** RSI-14: `{data['rsi_14']:.1f}` | MACD: `{data['macd_verdict']}`\n"
        f"• **Volume & Volatility:** RVOL: `{data['rvol']:.1f}x` | IV Rank: `{data['iv_rank']}%` ({'Cheap / Buy Premium' if data['iv_rank'] < 40 else 'Expensive / Sell Premium'})\n"
        f"• **Key Levels:** Support (S1): `${data['s1']:.2f}` | Resistance (R1): `${data['r1']:.2f}`"
    )
    embed.add_field(name="📊 Technical & Volatility Environment", value=diag_text, inline=False)

    # 2. Strategy Recommendation
    embed.add_field(name="🏆 Primary DFOL Strategy", value=f"**{data['strategy_name']}**", inline=False)

    # 3. Dual Timeframe Plays
    embed.add_field(name="⚡ PLAY A: 7 – 14 DTE (Fast Scalp / Weekly Momentum)", value=f"• **Trade Plan:** {data['play_7_14']}\n• **Target Exit:** +50% to +80% on contract | Stop-Loss: Cut at -35% loss", inline=False)
    embed.add_field(name="🏛️ PLAY B: 30 – 45 DTE (Standard Swing / Institutional)", value=f"• **Trade Plan:** {data['play_30_45']}\n• **Target Exit:** +40% to +60% on contract | Stop-Loss: Trailing 50D SMA", inline=False)

    # 4. Alternative / Defensive Setup
    embed.add_field(name="🛡️ Alternative Setup (Risk Mitigation)", value=data['defensive_play'], inline=False)

    embed.set_footer(text="Looney Options Terminal • DFOL Golden Rule Break-Even Engine")
    return embed

@bot.event
async def on_ready():
    print(f"🤖 Looney Options Bot is ONLINE as: {bot.user}")

# Instant Trigger on `#TICKER`
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()

    # Case 1: Triggered via `#TICKER` (e.g. #NVDA, #TSLA)
    if content.startswith("#") and len(content) >= 2:
        raw_ticker = content[1:].split()[0].upper().replace("$", "")
        if len(raw_ticker) <= 10 and re.match(r'^[A-Z0-9=\-\.]+$', raw_ticker):
            async with message.channel.typing():
                data = await asyncio.to_thread(analyze_stock_options_setup, raw_ticker)
                if not data:
                    await message.channel.send(f"❌ Could not compute options analytics for `{raw_ticker}`. Verify ticker symbol.")
                    return
                embed = create_deep_dive_options_embed(data)
                await message.channel.send(embed=embed)
                return

    # Case 2: Standard Command Prefix Fallback (`!opt TICKER`)
    await bot.process_commands(message)

@bot.command(name="opt", aliases=["options", "play"])
async def options_command(ctx, ticker: str):
    async with ctx.typing():
        data = await asyncio.to_thread(analyze_stock_options_setup, ticker)
        if not data:
            await ctx.send(f"❌ Could not compute options analytics for `{ticker}`.")
            return
        embed = create_deep_dive_options_embed(data)
        await ctx.send(embed=embed)

# -------------------------------------------------------------
# 7. MAIN ENTRYPOINT
# -------------------------------------------------------------
if __name__ == "__main__":
    print("Launching Looney Options Intelligence System...")
    
    # Run immediate initial scan on startup
    threading.Thread(target=run_top10_options_radar, daemon=True).start()

    if BOT_TOKEN:
        bot.run(BOT_TOKEN)
    else:
        print("⚠️ DISCORD_BOT_TOKEN not provided. Bot running in Webhook-only Mode.")
        while True:
            time.sleep(1)
