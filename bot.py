import os
import threading
import math
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import discord
from discord.ext import commands

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

def format_large_number(num):
    if num is None:
        return "N/A"
    if num >= 1e9:
        return f"{num / 1e9:.2f}B"
    elif num >= 1e6:
        return f"{num / 1e6:.1f}M"
    elif num >= 1e3:
        return f"{num / 1e3:.1f}K"
    return str(int(num))

def calculate_rsi_from_closes(closes, period=14):
    """Calculates Wilder's 14-period RSI directly from closing price list."""
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

def get_on_demand_data(ticker_symbol):
    """Direct Yahoo Chart Engine — Accurately pulls 1-Day change & Dollar 52W Range."""
    ticker_symbol = ticker_symbol.upper().strip()
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?interval=1d&range=1y"
        res = http_session.get(url, timeout=6)
        
        if res.status_code != 200:
            return None, f"Could not fetch data for `{ticker_symbol}` (Status: {res.status_code})."

        data = res.json()
        result = data.get("chart", {}).get("result")
        if not result or len(result) == 0:
            return None, f"No market data returned for `{ticker_symbol}`."

        chart_data = result[0]
        meta = chart_data.get("meta", {})
        indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]

        raw_closes = indicators.get("close", [])
        raw_volumes = indicators.get("volume", [])
        raw_highs = indicators.get("high", [])
        raw_lows = indicators.get("low", [])

        # Filter out null values
        closes = [c for c in raw_closes if c is not None]
        volumes = [v for v in raw_volumes if v is not None]
        highs = [h for h in raw_highs if h is not None]
        lows = [l for l in raw_lows if l is not None]

        if len(closes) < 2:
            return None, f"Insufficient price history for `{ticker_symbol}`."

        # 1. True 1-Day Price & Previous Day Close
        current_price = meta.get("regularMarketPrice") or closes[-1]
        prev_close = meta.get("regularMarketPreviousClose") or meta.get("previousClose") or (closes[-2] if len(closes) >= 2 else current_price)
        change_pct = ((current_price - prev_close) / prev_close) * 100

        # 2. 20-Day RVOL
        vol_str = "N/A"
        if len(volumes) >= 20:
            avg_vol_20 = sum(volumes[-21:-1]) / len(volumes[-21:-1])
            vol_today = volumes[-1]
            if avg_vol_20 > 0:
                rvol = vol_today / avg_vol_20
                v_formatted = format_large_number(vol_today)
                if rvol >= 2.0:
                    vol_str = f"`{v_formatted}` ({rvol:.1f}x Avg 🔥 Unusual Surge)"
                elif rvol >= 1.3:
                    vol_str = f"`{v_formatted}` ({rvol:.1f}x Avg ⚡ Strong Volume)"
                elif rvol < 0.6:
                    vol_str = f"`{v_formatted}` ({rvol:.1f}x Avg 💤 Low Volume)"
                else:
                    vol_str = f"`{v_formatted}` ({rvol:.1f}x Avg 📊 Normal)"

        # 3. 14-Day RSI
        rsi_str = "N/A"
        rsi = calculate_rsi_from_closes(closes, 14)
        if rsi is not None:
            if rsi >= 75:
                rsi_str = f"`{rsi:.1f}` (⚠️ Extreme Overbought)"
            elif rsi >= 70:
                rsi_str = f"`{rsi:.1f}` (⚠️ Overbought Zone)"
            elif rsi <= 25:
                rsi_str = f"`{rsi:.1f}` (🟢 Extreme Oversold)"
            elif rsi <= 30:
                rsi_str = f"`{rsi:.1f}` (🟢 Oversold Zone)"
            elif rsi >= 50:
                rsi_str = f"`{rsi:.1f}` (Neutral / Bullish 📈)"
            else:
                rsi_str = f"`{rsi:.1f}` (Neutral / Bearish 📉)"

        # 4. 52-Week Range in Dollars & High Proximity
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

        # 5. 50D & 200D SMA Trend Health
        trend_str = "N/A"
        if len(closes) >= 200:
            sma_50 = sum(closes[-50:]) / 50
            sma_200 = sum(closes[-200:]) / 200
            if current_price >= sma_50 and current_price >= sma_200:
                trend_str = "Above 50D & 200D SMA (🟢 Strong Uptrend)"
            elif current_price < sma_50 and current_price < sma_200:
                trend_str = "Below 50D & 200D SMA (🔴 Strong Downtrend)"
            elif current_price >= sma_200 and current_price < sma_50:
                trend_str = "Above 200D, Below 50D SMA (🟡 Pullback)"
            else:
                trend_str = "Above 50D, Below 200D SMA (🟡 Rebound)"

        return {
            "ticker": ticker_symbol,
            "price": current_price,
            "change_pct": change_pct,
            "volume_str": vol_str,
            "rsi_str": rsi_str,
            "range_str": range_str,
            "trend_str": trend_str
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
    embed.add_field(name="📊 Volume (20D)", value=data['volume_str'], inline=False)
    embed.add_field(name="📈 RSI (14D)", value=data['rsi_str'], inline=True)
    embed.add_field(name="🏔️ 52-Week Range", value=data['range_str'], inline=True)
    embed.add_field(name="📈 Trend Health", value=data['trend_str'], inline=False)
    embed.set_footer(text="Looney • On-Demand Market Terminal")
    return embed

@bot.event
async def on_ready():
    print(f"🤖 Looney is ONLINE and listening in Discord as: {bot.user}")

# -------------------------------------------------------------
# 4. INSTANT AUTO-TRIGGER (e.g. `!NVDA`, `!TSLA`, `$BTC-USD`)
# -------------------------------------------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()

    # If message starts with `!` or `$`
    if content.startswith("!") or content.startswith("$"):
        raw_cmd = content[1:].strip()
        first_word = raw_cmd.split()[0].lower() if raw_cmd else ""

        # If they used standard command `!price NVDA` or `!p TSLA`
        if first_word in ["price", "p", "four", "check"]:
            await bot.process_commands(message)
            return

        # If they just typed direct ticker `!NVDA`, `!TSLA`, `$BTC-USD`, `$SPY`
        potential_ticker = raw_cmd.split()[0].upper()
        if potential_ticker and len(potential_ticker) <= 12 and re.match(r'^[A-Z0-9=\-\.]+$', potential_ticker):
            async with message.channel.typing():
                data, err = get_on_demand_data(potential_ticker)
                if not err:
                    embed = create_market_embed(data)
                    await message.channel.send(embed=embed)
                    return

    await bot.process_commands(message)

# Standard Fallback Commands
@bot.command(name="price", aliases=["p", "four", "check"])
async def price_command(ctx, ticker: str):
    async with ctx.typing():
        data, err = get_on_demand_data(ticker)
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
