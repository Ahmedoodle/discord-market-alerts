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

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
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
    now_ny = datetime.now(NY_TZ)
    if now_ny.time() < dtime(9, 30):
        session_date = now_ny.date() - timedelta(days=1)
    else:
        session_date = now_ny.date()
    return session_date.strftime("%Y-%m-%d")

def get_crypto_session_id():
    return datetime.now(UTC_TZ).strftime("%Y-%m-%d")

def load_alert_state():
    """Loads state for price benchmarks and seen news URLs."""
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
                
                if saved.get("stock_session") == current_stock_session:
                    state["stock_tickers"] = saved.get("stock_tickers", {})
                if saved.get("crypto_session") == current_crypto_session:
                    state["crypto_tickers"] = saved.get("crypto_tickers", {})
                
                state["seen_news_links"] = saved.get("seen_news_links", [])
        except Exception as e:
            print(f"Error loading state file: {e}")

    return state

def save_alert_state(state):
    """Saves updated benchmarks and keeps only the latest 500 news links."""
    try:
        state["seen_news_links"] = state["seen_news_links"][-500:]
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"State saved ({len(state['seen_news_links'])} news articles remembered).")
    except Exception as e:
        print(f"Error saving state file: {e}")

def send_discord_price_alert(ticker, current_price, change_pct, step_change=None):
    """Sends a price movement embed to Discord."""
    if not DISCORD_WEBHOOK_URL:
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
            "footer": {"text": "24/7 Cloud Bot • Price Alert"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending price alert for {ticker}: {e}")

def send_discord_news_alert(article):
    """Sends a breaking news headline embed to Discord."""
    if not DISCORD_WEBHOOK_URL:
        return

    payload = {
        "username": "Market Watcher",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [{
            "title": f"📰 Breaking News: {article['ticker']}",
            "description": f"**[{article['title']}]({article['link']})**",
            "color": 3447003,  # Blue/Cyan
            "fields": [
                {"name": "Publisher", "value": article["publisher"], "inline": True},
                {"name": "Published (ET)", "value": article["time_str"], "inline": True}
            ],
            "footer": {"text": "24/7 Cloud Bot • Live News Feed"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending news alert: {e}")

# --- NEWS FETCHING FUNCTIONS WITH EXACT TIMESTAMPS ---
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

    # 1. SCAN PRICES
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

                if ticker_symbol in tracked_dict:
                    last_alert_price = tracked_dict[ticker_symbol]
                    step_change_pct = ((current_price - last_alert_price) / last_alert_price) * 100
                    
                    if abs(step_change_pct) >= 2.0:
                        price_alerts_to_send.append({
                            "ticker": ticker_symbol, "price": current_price,
                            "daily_change": daily_change_pct, "step_change": step_change_pct
                        })
                        tracked_dict[ticker_symbol] = current_price
                else:
                    if abs(daily_change_pct) >= 2.0:
                        price_alerts_to_send.append({
                            "ticker": ticker_symbol, "price": current_price,
                            "daily_change": daily_change_pct, "step_change": None
                        })
                        tracked_dict[ticker_symbol] = current_price
        except Exception as e:
            print(f"❌ Error checking price for {ticker_symbol}: {e}")
        time.sleep(0.15)

    # 2. SCAN BREAKING NEWS (With 45-Minute Freshness Cutoff)
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

        # Skip if we already alerted on this link before
        if link in seen_news_set:
            continue

        # Add to seen list so we never inspect it again
        seen_news_set.add(link)
        state["seen_news_links"].append(link)

        # STRICT FILTER: Only send alert if published within the last 45 minutes
        if pub_dt and pub_dt >= cutoff_time:
            new_articles.append(item)

    # 3. DISPATCH DISCORD ALERTS
    # Send Sorted Price Alerts
    price_alerts_to_send.sort(key=lambda x: x["daily_change"], reverse=True)
    if price_alerts_to_send:
        print(f"Sending {len(price_alerts_to_send)} price alert(s)...")
        for alert in price_alerts_to_send:
            send_discord_price_alert(
                ticker=alert["ticker"],
                current_price=alert["price"],
                change_pct=alert["daily_change"],
                step_change=alert["step_change"]
            )
            time.sleep(0.5)

    # Send News Alerts (up to 5 per run)
    if new_articles:
        print(f"Sending {len(new_articles[:5])} fresh headline alert(s) (<= 45 mins old)...")
        for article in new_articles[:5]:
            send_discord_news_alert(article)
            time.sleep(0.5)

    # 4. PERSIST STATE
    save_alert_state(state)
    print(f"\n=======================================================")
    print(f"Check Complete. Price Alerts: {len(price_alerts_to_send)} | Fresh News Sent: {len(new_articles[:5])} (Total New: {len(new_articles)})")

if __name__ == "__main__":
    check_market()
