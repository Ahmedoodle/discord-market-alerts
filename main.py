import os
import time
import json
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
import requests
import yfinance as yf

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
STATE_FILE = "alerts_state.json"
NY_TZ = ZoneInfo("America/New_York")

# Categorized Watchlists
CRYPTO_WATCHLIST = [
    "BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD", "LINK-USD"
]

# Stocks, ETFs, and Futures (checked Mon-Fri 9:30 AM - 4:00 PM EST)
STOCK_ETF_WATCHLIST = [
    "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "NQ=F", "ES=F", "YM=F", "RTY=F",
    "USO", "BNO", "GLD", "SLV", "IBIT", "ETHA", "MSTR", "IREN",
    "BLSH", "NVDA", "AMD", "MU", "SNDK", "INTC", "AVGO", "ASML",
    "CBRS", "SKHY", "IBM", "TSLA", "SPCX", "RKLB", "PLTR", "META",
    "NBIS", "ORCL", "RBLX"
]

def is_us_stock_market_open():
    """Returns True if current time is Mon-Fri between 9:30 AM and 4:00 PM Eastern Time."""
    now_ny = datetime.now(NY_TZ)
    
    # 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday
    if now_ny.weekday() > 4:
        return False
    
    market_open = dtime(9, 30)
    market_close = dtime(16, 0)
    return market_open <= now_ny.time() <= market_close

def load_alert_state():
    """Loads saved price benchmarks. Resets memory on a new date (NY Time)."""
    today_str = datetime.now(NY_TZ).strftime("%Y-%m-%d")
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") == today_str:
                    return data.get("tickers", {})
                else:
                    print(f"📅 New day detected ({today_str}). Resetting daily alert memory.")
        except Exception as e:
            print(f"Error loading state file: {e}")
    return {}

def save_alert_state(ticker_states):
    """Saves updated price benchmarks."""
    today_str = datetime.now(NY_TZ).strftime("%Y-%m-%d")
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"date": today_str, "tickers": ticker_states}, f, indent=2)
        print(f"State saved successfully ({len(ticker_states)} tickers tracked).")
    except Exception as e:
        print(f"Error saving state file: {e}")

def send_discord_alert(ticker, current_price, change_pct, step_change=None):
    """Sends a formatted embed alert to Discord."""
    if not DISCORD_WEBHOOK_URL:
        print(f"Skipping alert for {ticker}: DISCORD_WEBHOOK_URL not configured.")
        return

    title_text = f"🚨 Market Alert: {ticker}"
    desc_text = f"**{ticker}** moved **{change_pct:+.2f}%** today!"
    
    if step_change is not None:
        desc_text = f"**{ticker}** moved another **{step_change:+.2f}%** (Total 1D: **{change_pct:+.2f}%**)!"

    payload = {
        "username": "Market Watcher",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [{
            "title": title_text,
            "description": desc_text,
            "color": 15158332 if change_pct < 0 else 3066993,
            "fields": [
                {"name": "Current Price", "value": f"${current_price:.2f}", "inline": True},
                {"name": "1D Total Change", "value": f"{change_pct:+.2f}%", "inline": True}
            ],
            "footer": {"text": "24/7 Cloud Bot • Step Alert Triggered"}
        }]
    }
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"Error sending Discord webhook for {ticker}: {e}")

def check_market():
    stock_market_active = is_us_stock_market_open()
    now_ny = datetime.now(NY_TZ).strftime("%Y-%m-%d %I:%M %p %Z")
    
    print(f"Current Time (NY): {now_ny}")
    print(f"US Stock Market Status: {'🟢 OPEN' if stock_market_active else '🔴 CLOSED (Crypto Only)'}\n")

    # Build active watchlist for this run
    active_watchlist = list(CRYPTO_WATCHLIST)
    if stock_market_active:
        active_watchlist.extend(STOCK_ETF_WATCHLIST)

    ticker_states = load_alert_state()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    new_alerts_count = 0

    for ticker_symbol in active_watchlist:
        try:
            ticker = yf.Ticker(ticker_symbol, session=session)
            hist = ticker.history(period="5d")
            
            if 'Close' in hist.columns:
                hist = hist.dropna(subset=['Close'])

            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current_price = hist['Close'].iloc[-1]
                daily_change_pct = ((current_price - prev_close) / prev_close) * 100
                
                # Check if we already alerted on this ticker today
                if ticker_symbol in ticker_states:
                    last_alert_price = ticker_states[ticker_symbol]
                    step_change_pct = ((current_price - last_alert_price) / last_alert_price) * 100
                    
                    if abs(step_change_pct) >= 2.0:
                        print(f"🔥 {ticker_symbol:10s} | STEP TRIGGER | Price: ${current_price:10.2f} | Step: {step_change_pct:+6.2f}%")
                        send_discord_alert(ticker_symbol, current_price, daily_change_pct, step_change=step_change_pct)
                        ticker_states[ticker_symbol] = current_price
                        new_alerts_count += 1
                    else:
                        print(f"⏭️ {ticker_symbol:10s} | Price: ${current_price:10.2f} | Step: {step_change_pct:+6.2f}% (Below 2%)")

                else:
                    # Initial check against previous day close
                    if abs(daily_change_pct) >= 2.0:
                        print(f"🚨 {ticker_symbol:10s} | INITIAL TRIGGER | Price: ${current_price:10.2f} | Change: {daily_change_pct:+6.2f}%")
                        send_discord_alert(ticker_symbol, current_price, daily_change_pct)
                        ticker_states[ticker_symbol] = current_price
                        new_alerts_count += 1
                    else:
                        print(f"✅ {ticker_symbol:10s} | Price: ${current_price:10.2f} | Change: {daily_change_pct:+6.2f}%")
            else:
                print(f"⚠️ {ticker_symbol:10s} | SKIPPED: Insufficient historical data")
        
        except Exception as e:
            print(f"❌ {ticker_symbol:10s} | ERROR: {e}")
        
        time.sleep(0.3)

    # Persist benchmark state
    save_alert_state(ticker_states)
    print(f"\n=======================================================")
    print(f"Check Complete. Active Tickers Checked: {len(active_watchlist)} | Alerts Sent: {new_alerts_count}")

if __name__ == "__main__":
    check_market()
