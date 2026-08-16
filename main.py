import os
import time
import json
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
import requests
import yfinance as yf

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
STATE_FILE = "alerts_state.json"
NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

# Crypto runs 24/7/365
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
    if now_ny.weekday() > 4:
        return False
    return dtime(9, 30) <= now_ny.time() <= dtime(16, 0)

def get_stock_session_id():
    """Stocks reset daily at 9:30 AM EST (US Market Open)."""
    now_ny = datetime.now(NY_TZ)
    if now_ny.time() < dtime(9, 30):
        session_date = now_ny.date() - timedelta(days=1)
    else:
        session_date = now_ny.date()
    return session_date.strftime("%Y-%m-%d")

def get_crypto_session_id():
    """Crypto resets daily at 00:00 UTC (Global Crypto Daily Candle Open)."""
    return datetime.now(UTC_TZ).strftime("%Y-%m-%d")

def load_alert_state():
    """Loads state with separate reset sessions for stocks and crypto."""
    current_stock_session = get_stock_session_id()
    current_crypto_session = get_crypto_session_id()

    state = {
        "stock_session": current_stock_session,
        "crypto_session": current_crypto_session,
        "stock_tickers": {},
        "crypto_tickers": {}
    }

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                
                # Restore stock state if same session
                if saved.get("stock_session") == current_stock_session:
                    state["stock_tickers"] = saved.get("stock_tickers", {})
                else:
                    print(f"🔔 New Stock Session ({current_stock_session}). Resetting stock memory.")

                # Restore crypto state if same session
                if saved.get("crypto_session") == current_crypto_session:
                    state["crypto_tickers"] = saved.get("crypto_tickers", {})
                else:
                    print(f"🪙 New Crypto Session ({current_crypto_session}). Resetting crypto memory.")
        except Exception as e:
            print(f"Error loading state file: {e}")

    return state

def save_alert_state(state):
    """Saves updated benchmarks for both asset classes."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        total_tracked = len(state["stock_tickers"]) + len(state["crypto_tickers"])
        print(f"State saved successfully ({total_tracked} tickers tracked).")
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

    state = load_alert_state()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    alerts_to_send = []

    # Build active watchlist
    active_watchlist = []
    for c in CRYPTO_WATCHLIST:
        active_watchlist.append((c, "crypto"))
    
    if stock_market_active:
        for s in STOCK_ETF_WATCHLIST:
            active_watchlist.append((s, "stock"))

    for ticker_symbol, asset_type in active_watchlist:
        try:
            ticker = yf.Ticker(ticker_symbol, session=session)
            hist = ticker.history(period="5d")
            
            if 'Close' in hist.columns:
                hist = hist.dropna(subset=['Close'])

            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current_price = hist['Close'].iloc[-1]
                daily_change_pct = ((current_price - prev_close) / prev_close) * 100
                
                tracked_dict = state["crypto_tickers"] if asset_type == "crypto" else state["stock_tickers"]

                # CASE 1: Already alerted in current session -> Check step change
                if ticker_symbol in tracked_dict:
                    last_alert_price = tracked_dict[ticker_symbol]
                    step_change_pct = ((current_price - last_alert_price) / last_alert_price) * 100
                    
                    if abs(step_change_pct) >= 2.0:
                        print(f"🔥 {ticker_symbol:10s} | STEP TRIGGER | Price: ${current_price:10.2f} | Step: {step_change_pct:+6.2f}%")
                        alerts_to_send.append({
                            "ticker": ticker_symbol,
                            "price": current_price,
                            "daily_change": daily_change_pct,
                            "step_change": step_change_pct
                        })
                        tracked_dict[ticker_symbol] = current_price
                    else:
                        print(f"⏭️ {ticker_symbol:10s} | Price: ${current_price:10.2f} | Step: {step_change_pct:+6.2f}% (Below 2%)")

                # CASE 2: No alert yet for this session -> Check initial 2% threshold
                else:
                    if abs(daily_change_pct) >= 2.0:
                        print(f"🚨 {ticker_symbol:10s} | INITIAL TRIGGER | Price: ${current_price:10.2f} | Change: {daily_change_pct:+6.2f}%")
                        alerts_to_send.append({
                            "ticker": ticker_symbol,
                            "price": current_price,
                            "daily_change": daily_change_pct,
                            "step_change": None
                        })
                        tracked_dict[ticker_symbol] = current_price
                    else:
                        print(f"✅ {ticker_symbol:10s} | Price: ${current_price:10.2f} | Change: {daily_change_pct:+6.2f}%")
            else:
                print(f"⚠️ {ticker_symbol:10s} | SKIPPED: Insufficient historical data")
        
        except Exception as e:
            print(f"❌ {ticker_symbol:10s} | ERROR: {e}")
        
        time.sleep(0.2)

    # Sort alerts: Highest gainers (+%) to biggest losers (-%)
    alerts_to_send.sort(key=lambda x: x["daily_change"], reverse=True)

    # Send alerts to Discord in sorted order
    if alerts_to_send:
        print(f"\nSending {len(alerts_to_send)} alerts sorted from highest to lowest...")
        for alert in alerts_to_send:
            send_discord_alert(
                ticker=alert["ticker"],
                current_price=alert["price"],
                change_pct=alert["daily_change"],
                step_change=alert["step_change"]
            )
            time.sleep(0.5)

    # Persist the state
    save_alert_state(state)
    print(f"\n=======================================================")
    print(f"Check Complete. Active Tickers Checked: {len(active_watchlist)} | Alerts Sent: {len(alerts_to_send)}")

if __name__ == "__main__":
    check_market()
