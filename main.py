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
    
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"Error sending Discord webhook for {ticker}: {e}")

def check_market():
    watch_list = [
        "BTC-USD", "ETH-USD", "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F",
        "XRP-USD", "SOL-USD", "LINK-USD", "NQ=F", "ES=F", "YM=F", "RTY=F",
        "USO", "BNO", "GLD", "SLV", "IBIT", "ETHA", "MSTR", "IREN",
        "BLSH", "NVDA", "AMD", "MU", "SNDK", "INTC", "AVGO", "ASML",
        "CBRS", "SKHY", "IBM", "TSLA", "SPCX", "RKLB", "PLTR", "META",
        "NBIS", "ORCL", "RBLX"
    ]
    
    print(f"Fetching market data for {len(watch_list)} assets...")
    
    # 5d period ensures enough historical trading days for both stocks and 24/7 crypto
    data = yf.download(watch_list, period="5d", progress=False)
    
    alerts_sent = 0
    print("\n=================== MARKET SUMMARY ===================")
    
    for ticker in watch_list:
        try:
            # Safely extract 'Close' price series for multi-index columns
            series = None
            if ('Close', ticker) in data.columns:
                series = data[('Close', ticker)].dropna()
            elif 'Close' in data and ticker in data['Close'].columns:
                series = data['Close'][ticker].dropna()

            if series is not None and len(series) >= 2:
                prev_close = series.iloc[-2]
                current_price = series.iloc[-1]
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                # Print exact calculations to GitHub Logs
                print(f"{ticker:10s} | Price: ${current_price:10.2f} | Change: {change_pct:+6.2f}%")
                
                # Triggers alert if asset moves by 2.0% or more (up or down)
                if abs(change_pct) >= 2.0:
                    send_discord_alert(ticker, current_price, change_pct)
                    alerts_sent += 1
            else:
                print(f"{ticker:10s} | Insufficient data")
        except Exception as e:
            print(f"{ticker:10s} | Error processing: {e}")
            
    print(f"=======================================================")
    print(f"Check Complete. Total Discord Alerts Sent: {alerts_sent}\n")

if __name__ == "__main__":
    check_market()
