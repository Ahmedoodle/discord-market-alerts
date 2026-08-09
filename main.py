import os
import time
import requests
import yfinance as yf

# Load the secret webhook URL stored in GitHub Secrets
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_alert(ticker, price, change_pct):
    """Sends a formatted embed alert to Discord."""
    payload = {
        "username": "Market Watcher",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [{
            "title": f"🚨 Market Alert: {ticker}",
            "description": f"**{ticker}** triggered an alert!",
            "color": 15158332 if change_pct < 0 else 3066993, # Red if down, Green if up
            "fields": [
                {"name": "Current Price", "value": f"${price:.2f}", "inline": True},
                {"name": "Daily Change", "value": f"{change_pct:+.2f}%", "inline": True}
            ],
            "footer": {"text": "24/7 Cloud Automated Bot"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"Error sending Discord webhook for {ticker}: {e}")

def check_market():
    # Watchlist with NVDA removed
    watch_list = [
        "BTC-USD", "ETH-USD", "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F",
        "XRP-USD", "SOL-USD", "LINK-USD", "NQ=F", "ES=F", "YM=F", "RTY=F",
        "USO", "BNO", "GLD", "SLV", "IBIT", "ETHA", "MSTR", "IREN",
        "BLSH", "AMD", "MU", "SNDK", "INTC", "AVGO", "ASML",
        "CBRS", "SKHY", "IBM", "TSLA", "SPCX", "RKLB", "PLTR", "META",
        "NBIS", "ORCL", "RBLX"
    ]
    
    print(f"Starting market check for {len(watch_list)} assets...\n")
    alerts_sent = 0
    
    # Custom User-Agent prevents Yahoo Finance from blocking GitHub cloud IPs
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    for ticker_symbol in watch_list:
        try:
            ticker = yf.Ticker(ticker_symbol, session=session)
            hist = ticker.history(period="5d")
            
            if 'Close' in hist.columns:
                hist = hist.dropna(subset=['Close'])

            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current_price = hist['Close'].iloc[-1]
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                print(f"✅ {ticker_symbol:10s} | Price: ${current_price:10.2f} | 1D Change: {change_pct:+6.2f}%")
                
                # Triggers alert if asset moves by 2.0% or more
                if abs(change_pct) >= 2.0:
                    send_discord_alert(ticker_symbol, current_price, change_pct)
                    alerts_sent += 1
            else:
                print(f"⚠️ {ticker_symbol:10s} | SKIPPED: Insufficient rows returned by Yahoo (rows: {len(hist)})")
        
        except Exception as e:
            print(f"❌ {ticker_symbol:10s} | ERROR: {e}")
        
        # Short pause to prevent rate limiting
        time.sleep(0.3)

    print(f"\n=======================================================")
    print(f"Check Complete. Total Discord Alerts Sent: {alerts_sent}")

if __name__ == "__main__":
    check_market()
