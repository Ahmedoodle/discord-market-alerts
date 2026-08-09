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
    watch_list = [
        "BTC-USD", "ETH-USD", "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F",
        "XRP-USD", "SOL-USD", "LINK-USD", "NQ=F", "ES=F", "YM=F", "RTY=F",
        "USO", "BNO", "GLD", "SLV", "IBIT", "ETHA", "MSTR", "IREN",
        "BLSH", "NVDA", "AMD", "MU", "SNDK", "INTC", "AVGO", "ASML",
        "CBRS", "SKHY", "IBM", "TSLA", "SPCX", "RKLB", "PLTR", "META",
        "NBIS", "ORCL", "RBLX"
    ]
    
    print(f"Fetching bulk market data for {len(watch_list)} assets...")
    
    try:
        # Bulk fetch all tickers at once to bypass rate limits
        data = yf.download(watch_list, period="2d", group_by="ticker", progress=False)
    except Exception as e:
        print(f"Error fetching bulk data: {e}")
        return

    for ticker_symbol in watch_list:
        try:
            # Extract ticker dataframe from bulk result
            if ticker_symbol in data.columns.levels[0]:
                df = data[ticker_symbol].dropna()
                
                if len(df) >= 2:
                    prev_close = df['Close'].iloc[-2]
                    current_price = df['Close'].iloc[-1]
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                    
                    print(f"{ticker_symbol}: ${current_price:.2f} ({change_pct:+.2f}%)")
                    
                    # Triggers alert if asset moves by 2% or more (up or down)
                    if abs(change_pct) >= 2.0:
                        send_discord_alert(ticker_symbol, current_price, change_pct)
                else:
                    print(f"{ticker_symbol}: Not enough historical data.")
        except Exception as e:
            print(f"Error processing {ticker_symbol}: {e}")

if __name__ == "__main__":
    check_market()
