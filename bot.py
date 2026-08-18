import os
import yfinance as yf
import pandas as pd
import discord
from discord.ext import commands

# -------------------------------------------------------------
# PASTE YOUR DISCORD BOT TOKEN HERE (Or set as environment variable)
# -------------------------------------------------------------
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "MTUzOTQxNjQ5Nzc3NTA1ODk3Ng.GGBhH6.1j0tk2kbPvL9GCWO9N8KxDK87DOCg3_tNlzrsk")

# Setup Discord Bot with message intents
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

def get_on_demand_data(ticker_symbol):
    """Pulls live price, 20D RVOL, 14D RSI, 52W Range, and 50/200 SMAs on demand."""
    ticker_symbol = ticker_symbol.upper().strip()
    try:
        t = yf.Ticker(ticker_symbol)
        
        # 1. Live Price & Previous Close
        fi = t.fast_info
        current_price = fi.last_price
        prev_close = fi.previous_close

        if current_price is None or prev_close is None:
            hist_2d = t.history(period="2d")
            if len(hist_2d) >= 2:
                prev_close = float(hist_2d['Close'].iloc[-2])
                current_price = float(hist_2d['Close'].iloc[-1])
            elif len(hist_2d) == 1:
                current_price = float(hist_2d['Close'].iloc[-1])
                prev_close = current_price

        if current_price is None or prev_close is None or prev_close == 0:
            return None, f"Could not find valid price data for `{ticker_symbol}`."

        change_pct = ((current_price - prev_close) / prev_close) * 100

        # 2. 1-Year History for Indicators
        hist = t.history(period="1y")
        if hist.empty or 'Close' not in hist or len(hist['Close']) < 15:
            return None, f"Insufficient historical data to compute indicators for `{ticker_symbol}`."

        closes = hist['Close'].dropna()
        volumes = hist['Volume'].dropna()

        # 3. 20-Day RVOL
        vol_str = "N/A"
        if len(volumes) >= 20:
            avg_vol_20 = volumes.iloc[-21:-1].mean()
            vol_today = volumes.iloc[-1]
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

        # 4. 14-Day RSI (Wilder's Formula)
        delta = closes.diff()
        gains = delta.clip(lower=0)
        losses = -1 * delta.clip(upper=0)
        avg_gain = gains.ewm(com=13, adjust=False).mean().iloc[-1]
        avg_loss = losses.ewm(com=13, adjust=False).mean().iloc[-1]
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

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

        # 5. 52-Week Range & Proximity
        range_str = "N/A"
        high_52w = hist['High'].max()
        low_52w = hist['Low'].min()
        if high_52w and low_52w and high_52w > low_52w:
            pos_pct = ((current_price - low_52w) / (high_52w - low_52w)) * 100
            dist_high = ((high_52w - current_price) / high_52w) * 100
            if dist_high <= 2.0:
                range_str = f"`{pos_pct:.1f}%` (🔥 {dist_high:.1f}% from 52W High!)"
            elif dist_high <= 5.0:
                range_str = f"`{pos_pct:.1f}%` (⚡ {dist_high:.1f}% from 52W High)"
            else:
                range_str = f"`{pos_pct:.1f}%` ({dist_high:.1f}% below 52W High)"

        # 6. 50D & 200D SMA Trend Health
        trend_str = "N/A"
        if len(closes) >= 200:
            sma_50 = closes.iloc[-50:].mean()
            sma_200 = closes.iloc[-200:].mean()
            if current_price >= sma_50 and current_price >= sma_200:
                trend_str = "Above 50D & 200D SMA (🟢 Strong Uptrend)"
            elif current_price < sma_50 and current_price < sma_200:
                trend_str = "Below 50D & 200D SMA (🔴 Strong Downtrend)"
            elif current_price >= sma_200 and current_price < sma_50:
                trend_str = "Above 200D, Below 50D SMA (🟡 Pullback in Uptrend)"
            else:
                trend_str = "Above 50D, Below 200D SMA (🟡 Rebound in Downtrend)"

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

@bot.event
async def on_ready():
    print(f"🤖 Looney is ONLINE and listening in Discord as: {bot.user}")

# Command 1: Trigger via `!price <ticker>` or `!p <ticker>`
@bot.command(name="price", aliases=["p", "four", "check"])
async def price_command(ctx, ticker: str):
    async with ctx.typing():
        data, err = get_on_demand_data(ticker)
        if err:
            await ctx.send(f"❌ {err}")
            return

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

        await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
