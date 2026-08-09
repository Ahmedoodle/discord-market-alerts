import os
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
    
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def check_market():
    # Tickers you want to watch
    watch_list = ["NVDA", "AMD", "SPY"]
    
    for ticker_symbol in watch_list:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="2d")
        
        if len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2]
            current_price = hist['Close'].iloc[-1]
            change_pct = ((current_price - prev_close) / prev_close) * 100
            
            print(f"{ticker_symbol}: ${current_price:.2f} ({change_pct:+.2f}%)")
            
            # Triggers alert if stock moves by 2% or more (up or down)
            if abs(change_pct) >= 2.0:
                send_discord_alert(ticker_symbol, current_price, change_pct)

if __name__ == "__main__":
    check_market()
