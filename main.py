import os
import time
import json
import concurrent.futures
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, time as dtime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
import requests
import yfinance as yf

# Environment Variables (Securely pulled from GitHub Secrets)
DISCORD_NEWS_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_PRICE_WEBHOOK_URL = os.getenv("DISCORD_PRICE_WEBHOOK_URL")

STATE_FILE = "alerts_state.json"
NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

# Maximum allowed article age for Discord alerts (in minutes)
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
    """Loads state for price benchmarks, history trails, and remembered news URLs."""
    current_stock_session = get_stock_session_id()
    current_crypto_session = get_crypto_session_id()

    state = {
        "stock_session": current_stock_session,
        "crypto_session": current_crypto_session,
        "stock_tickers": {},
        "crypto_tickers": {},
        "seen_news_links": []
    }

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved = json.load(f)
                
                # Restore stock state if same session
                if saved.get("stock_session") == current_stock_session:
                    raw_stocks = saved.get("stock_tickers", {})
                    for k, v in raw_stocks.items():
                        if isinstance(v, (int, float)):
                            state["stock_tickers"][k] = {"last_price": v, "history": []}
                        else:
                            state["stock_tickers"][k] = v
                else:
                    print(f"🔔 New Stock Session ({current_stock_session}). Resetting stock memory.")

                # Restore crypto state if same session
                if saved.get("crypto_session") == current_crypto_session:
                    raw_crypto = saved.get("crypto_tickers", {})
                    for k, v in raw_crypto.items():
                        if isinstance(v, (int, float)):
                            state["crypto_tickers"][k] = {"last_price": v, "history": []}
                        else:
                            state["crypto_tickers"][k] = v
                else:
                    print(f"🪙 New Crypto Session ({current_crypto_session}). Resetting crypto memory.")
                
                # Remember all past news articles permanently
                state["seen_news_links"] = saved.get("seen_news_links", [])
        except Exception as e:
            print(f"Error loading state file: {e}")

    return state

def save_alert_state(state):
    """Saves updated benchmarks and remembers ALL news links permanently."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        total_prices = len(state["stock_tickers"]) + len(state["crypto_tickers"])
        print(f"State saved ({total_prices} active price benchmarks, {len(state['seen_news_links'])} total news links remembered).")
    except Exception as e:
        print(f"Error saving state file: {e}")

def send_discord_price_alert(ticker, current_price, change_pct, step_change=None, history_trail=None):
    """Sends a formatted price movement embed with trigger timeline to the PRICE channel."""
    if not DISCORD_PRICE_WEBHOOK_URL:
        print(f"Skipping price alert for {ticker}: DISCORD_PRICE_WEBHOOK_URL not configured.")
        return

    title_text = f"🚨 Market Alert: {ticker}"
    desc_text = f"**{ticker}** moved **{change_pct:+.2f}%** today!"
    if step_change is not None:
        desc_text = f"**{ticker}** moved **{step_change:+.2f}%** since last alert! (Total 1D: **{change_pct:+.2f}%**)"

    fields = [
        {"name": "Current Price", "value": f"${current_price:.2f}", "inline": True},
        {"name": "1D Total Change", "value": f"{change_pct:+.2f}%", "inline": True}
    ]

    # Add Trigger History Timeline if previous alerts occurred today
    if history_trail and len(history_trail) > 0:
        trail_str = " ➔ ".join(history_trail)
        fields.append({
            "name": "🕒 Today's Trigger Path",
            "value": f"`{trail_str}` ➔ **{change_pct:+.2f}%**",
            "inline": False
        })

    payload = {
        "username": "Price Watcher",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [{
            "title": title_text,
            "description": desc_text,
            "color": 15158332 if change_pct < 0 else 3066993,
            "fields": fields,
            "footer": {"text": "24/7 Cloud Bot • Price Action Channel"}
        }]
    }
    try:
        res = requests.post(DISCORD_PRICE_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"Error sending price alert for {ticker}: {e}")

def send_discord_news_alert(article):
    """Sends a formatted breaking news embed to the NEWS channel."""
    if not DISCORD_NEWS_WEBHOOK_URL:
        print(f"Skipping news alert for {article['ticker']}: DISCORD_WEBHOOK_URL not configured.")
        return

    payload = {
        "username": "News Watcher",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [{
            "title": f"📰 Breaking News: {article['ticker']}",
            "description": f"**[{article['title']}]({article['link']})**",
            "color": 3447003,  # Blue/Cyan
            "fields": [
                {"name": "Publisher", "value": article["publisher"], "inline": True},
                {"name": "Published (ET)", "value": article["time_str"], "inline": True}
            ],
            "footer": {"text": "24/7 Cloud Bot • Breaking News Channel"}
        }]
    }
    try:
        res = requests.post(DISCORD_NEWS_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"Error sending news alert: {e}")

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

def check_market():
    stock_market_active = is_us_stock_market_open()
    now_ny = datetime.now(NY_TZ)
    now_ny_str = now_ny.strftime("%Y-%m-%d %I:%M %p %Z")
    
    print(f"Current Time (NY): {now_ny_str}")
    print(f"US Stock Market Status: {'🟢 OPEN' if stock_market_active else '🔴 CLOSED (Crypto Only)'}\n")

    state = load_alert_state()
    seen_news_set = set(state.get("seen_news_links", []))
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    # ==========================================
    # 1. SCAN PRICES
    # ==========================================
    price_alerts_to_send = []
    active_price_watchlist = [(c, "crypto") for c in CRYPTO_WATCHLIST]
    if stock_market_active:
        active_price_watchlist.extend([(s, "stock") for s in STOCK_ETF_WATCHLIST])

    for ticker_symbol, asset_type in active_price_watchlist:
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

                # Case 1: Already alerted today -> check 2.0% step change
                if ticker_symbol in tracked_dict:
                    item_data = tracked_dict[ticker_symbol]
                    last_alert_price = item_data["last_price"]
                    history_trail = item_data.get("history", [])
                    
                    step_change_pct = ((current_price - last_alert_price) / last_alert_price) * 100
                    
                    if abs(step_change_pct) >= 2.0:
                        print(f"🔥 {ticker_symbol:10s} | STEP TRIGGER | Price: ${current_price:10.2f} | Step: {step_change_pct:+6.2f}%")
                        price_alerts_to_send.append({
                            "ticker": ticker_symbol, 
                            "price": current_price,
                            "daily_change": daily_change_pct, 
                            "step_change": step_change_pct,
                            "history_trail": list(history_trail)
                        })
                        # Update state with new price and append current % to history
                        history_trail.append(f"{daily_change_pct:+.2f}%")
                        tracked_dict[ticker_symbol] = {
                            "last_price": current_price,
                            "history": history_trail
                        }
                    else:
                        print(f"⏭️ {ticker_symbol:10s} | Price: ${current_price:10.2f} | Step: {step_change_pct:+6.2f}% (Below 2%)")

                # Case 2: Initial alert today -> check 2.0% daily threshold
                else:
                    if abs(daily_change_pct) >= 2.0:
                        print(f"🚨 {ticker_symbol:10s} | INITIAL TRIGGER | Price: ${current_price:10.2f} | Change: {daily_change_pct:+6.2f}%")
                        price_alerts_to_send.append({
                            "ticker": ticker_symbol, 
                            "price": current_price,
                            "daily_change": daily_change_pct, 
                            "step_change": None,
                            "history_trail": []
                        })
                        tracked_dict[ticker_symbol] = {
                            "last_price": current_price,
                            "history": [f"{daily_change_pct:+.2f}%"]
                        }
                    else:
                        print(f"✅ {ticker_symbol:10s} | Price: ${current_price:10.2f} | Change: {daily_change_pct:+6.2f}%")
            else:
                print(f"⚠️ {ticker_symbol:10s} | SKIPPED: Insufficient historical data")
        except Exception as e:
            print(f"❌ Error checking price for {ticker_symbol}: {e}")
        time.sleep(0.15)

    # ==========================================
    # 2. SCAN BREAKING NEWS (45-Min Cutoff)
    # ==========================================
    print("\nScanning breaking news across all tickers...")
    cutoff_time = now_ny - timedelta(minutes=MAX_NEWS_AGE_MINUTES)
    raw_news = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures_search = [executor.submit(fetch_ticker_news_search, sym, session) for sym in ALL_TICKERS]
        futures_rss = [executor.submit(fetch_ticker_news_rss, sym, session) for sym in ALL_TICKERS]
        
        for f in concurrent.futures.as_completed(futures_search + futures_rss):
            raw_news.extend(f.result())

    new_articles = []
    for item in raw_news:
        link = item["link"]
        pub_dt = item.get("pub_dt")

        # Skip if already saved in memory
        if link in seen_news_set:
            continue

        # Add to permanent memory so it is NEVER checked again
        seen_news_set.add(link)
        state["seen_news_links"].append(link)

        # STRICT FILTER: Only alert if published within the last 45 minutes
        if pub_dt and pub_dt >= cutoff_time:
            new_articles.append(item)

    # ==========================================
    # 3. DISPATCH DISCORD ALERTS
    # ==========================================
    # Send Sorted Price Alerts to the Price Channel
    price_alerts_to_send.sort(key=lambda x: x["daily_change"], reverse=True)
    if price_alerts_to_send:
        print(f"\nSending {len(price_alerts_to_send)} price alert(s) to PRICE CHANNEL...")
        for alert in price_alerts_to_send:
            send_discord_price_alert(
                ticker=alert["ticker"],
                current_price=alert["price"],
                change_pct=alert["daily_change"],
                step_change=alert["step_change"],
                history_trail=alert["history_trail"]
            )
            time.sleep(0.5)

    # Send ALL Fresh Breaking News Alerts to the News Channel
    if new_articles:
        print(f"\nSending ALL {len(new_articles)} fresh headline alert(s) to NEWS CHANNEL...")
        for article in new_articles:
            send_discord_news_alert(article)
            time.sleep(0.5)

    # ==========================================
    # 4. PERSIST STATE
    # ==========================================
    save_alert_state(state)
    print(f"\n=======================================================")
    print(f"Check Complete. Price Alerts: {len(price_alerts_to_send)} | Fresh News Sent: {len(new_articles)}")

if __name__ == "__main__":
    check_market()
