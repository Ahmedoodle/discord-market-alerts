import os
import time
import json
import logging
import concurrent.futures
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import requests
import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Webhook & Branding
DISCORD_EARNINGS_WEBHOOK_URL = os.getenv(
    "DISCORD_EARNINGS_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1539761350920642660/cDXOzG5Unsic7mcUrYS6KJK8evjolwQP0LSqs5ydvEFvnoXT-6djPpGj5VHM9czqRfrI"
)
BOT_NAME = "Looney"
BOT_AVATAR_URL = "https://cdn.discordapp.com/attachments/1536082016184045750/1539077205437714442/IMG_6630.jpg?ex=6a8500d8&is=6a83af58&hm=f46d7b936827c9651de6bafe607af3e23c40009ee9799431f622886c85c78013&"

NY_TZ = ZoneInfo("America/New_York")

# Your Curated Watchlist
WATCHLIST = [
    "NVDA", "AMD", "MU", "INTC", "AVGO", "ASML", "IBM", "TSLA", 
    "RKLB", "PLTR", "META", "ORCL", "RBLX", "MSTR", "IREN", "SHOP.TO"
]

# Core Canadian (TSX) Universe to scan daily
TSX_UNIVERSE = [
    "RY.TO", "TD.TO", "SHOP.TO", "CNR.TO", "CP.TO", "ENB.TO", "BNS.TO", "BMO.TO",
    "TRI.TO", "ATD.TO", "CSU.TO", "MFC.TO", "SU.TO", "BCE.TO", "TRP.TO", "ABX.TO",
    "WCN.TO", "QSR.TO", "POW.TO", "NTR.TO", "IMO.TO", "CVE.TO", "GIB-A.TO", "FM.TO",
    "HUT.TO", "BITF.TO", "LSPD.TO", "NVEI.TO", "TOY.TO", "BLX.TO", "CTS.TO"
]

nasdaq_session = requests.Session()
nasdaq_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/"
})

def get_country_badge(ticker_symbol):
    return "🍁" if ".TO" in ticker_symbol or ".V" in ticker_symbol else "🇺🇸"

def parse_market_cap_str(cap_str):
    if not cap_str or cap_str == "N/A":
        return 0
    try:
        clean = cap_str.replace("$", "").replace(",", "").strip()
        return float(clean)
    except Exception:
        return 0

# ====================================================================
# 1. LIVE MASTER CALENDAR API (NASDAQ + TSX)
# ====================================================================
def fetch_nasdaq_calendar_day(target_date):
    """Fetches every stock scheduled to report on target_date from Nasdaq official feed."""
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date_str}"
    items = []
    try:
        res = nasdaq_session.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            rows = data.get("data", {}).get("rows", []) or []
            for r in rows:
                sym = r.get("symbol", "").strip()
                if not sym or "^" in sym or "/" in sym or "." in sym:
                    continue  # skip preferreds and units
                
                mcap = parse_market_cap_str(r.get("marketCap", "0"))
                time_code = r.get("time", "time-not-supplied").lower()
                time_badge = "Before Open 🌅" if "pre" in time_code or "bmo" in time_code else "After Close 🌙"
                
                eps_forecast = r.get("epsForecast", "Pending")
                if eps_forecast and eps_forecast != "N/A":
                    eps_forecast = f"${eps_forecast}" if not eps_forecast.startswith("$") else eps_forecast

                items.append({
                    "ticker": sym,
                    "name": r.get("name", sym),
                    "badge": "🇺🇸",
                    "date": target_date,
                    "days_away": (target_date - datetime.now(NY_TZ).date()).days,
                    "date_str": target_date.strftime("%b %d, %Y"),
                    "time_badge": time_badge,
                    "status": "Official / Confirmed 🟢",
                    "market_cap": mcap,
                    "consensus_est": f"EPS: `{eps_forecast}`",
                    "actual_reported": "Pending ⏳",
                    "prev_quarter": "N/A"
                })
    except Exception as e:
        logging.warning(f"Nasdaq calendar fetch error for {date_str}: {e}")
    return items

def fetch_tsx_ticker_earnings(sym):
    """Pulls earnings info for Canadian TSX tickers."""
    try:
        t_obj = yf.Ticker(sym)
        today = datetime.now(NY_TZ).date()
        cal = t_obj.calendar
        nxt_d = None
        eps_est = "Pending"
        
        if cal is not None and not (isinstance(cal, pd.DataFrame) and cal.empty):
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    target = ed[0] if isinstance(ed, list) else ed
                    nxt_d = target.date() if isinstance(target, datetime) else target
                avg_val = cal.get("Earnings Average")
                if avg_val is not None:
                    eps_est = f"${float(avg_val):.2f}"
            elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"].iloc[0]
                nxt_d = ed.date() if isinstance(ed, datetime) else ed

        if nxt_d and nxt_d >= today:
            days_away = (nxt_d - today).days
            m_cap = getattr(t_obj.fast_info, "market_cap", 0) or 0
            name = getattr(t_obj.fast_info, "name", None) or sym
            return {
                "ticker": sym,
                "name": name,
                "badge": "🍁",
                "date": nxt_d,
                "days_away": days_away,
                "date_str": nxt_d.strftime("%b %d, %Y"),
                "time_badge": "After Close 🌙",
                "status": "Official / Confirmed 🟢",
                "market_cap": m_cap,
                "consensus_est": f"EPS: `{eps_est}`",
                "actual_reported": "Pending ⏳",
                "prev_quarter": "N/A"
            }
    except Exception:
        pass
    return None

def fetch_yesterday_actuals(target_date):
    """Pulls actual reported earnings results and price reactions from previous session."""
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date_str}"
    scorecard = []
    try:
        res = nasdaq_session.get(url, timeout=10)
        if res.status_code == 200:
            rows = res.json().get("data", {}).get("rows", []) or []
            for r in rows:
                sym = r.get("symbol", "").strip()
                eps_actual = r.get("eps")
                if not sym or eps_actual is None or eps_actual == "" or eps_actual == "N/A":
                    continue
                
                mcap = parse_market_cap_str(r.get("marketCap", "0"))
                eps_forecast = r.get("epsForecast", "N/A")
                
                # Check surprise
                surp_str = ""
                try:
                    act_f = float(eps_actual.replace("$", ""))
                    est_f = float(eps_forecast.replace("$", ""))
                    diff = act_f - est_f
                    tag = "🎯" if diff >= 0 else "⚠️"
                    surp_str = f" (**{'Beat' if diff >= 0 else 'Missed'} by `${abs(diff):.2f}` {tag}**)"
                except Exception:
                    pass

                scorecard.append({
                    "ticker": sym,
                    "name": r.get("name", sym),
                    "badge": get_country_badge(sym),
                    "reported_date": target_date.strftime("%b %d, %Y"),
                    "market_cap": mcap,
                    "eps_line": f"Actual: `${eps_actual}` | Estimate: `${eps_forecast}`{surp_str}",
                    "move_str": "Processed 📊"
                })
    except Exception as e:
        logging.warning(f"Error fetching yesterday actuals: {e}")
    
    # Sort by market cap so the biggest companies appear first
    scorecard.sort(key=lambda x: x["market_cap"], reverse=True)
    return scorecard

def format_earnings_entry(idx, item):
    return (
        f"**{idx}. {item['ticker']} — {item['name']}** {item['badge']}\n"
        f"• **Date & Time:** `{item['date_str']} (In {item['days_away']} Days)` • **{item['time_badge']}**\n"
        f"• **Status:** `{item['status']}`\n"
        f"• **Consensus Estimate:** {item['consensus_est']}\n"
        f"• **Actual Reported:** `{item['actual_reported']}`\n"
    )

def dispatch_discord_earnings_embed(title, description, entries_text, color=3447003):
    if not DISCORD_EARNINGS_WEBHOOK_URL:
        return

    payload = {
        "username": BOT_NAME,
        "avatar_url": BOT_AVATAR_URL,
        "embeds": [{
            "title": title,
            "description": f"{description}\n\n{entries_text}"[:4000],
            "color": color,
            "footer": {"text": "Looney • Daily 6:00 AM Earnings Intelligence"}
        }]
    }
    try:
        res = requests.post(DISCORD_EARNINGS_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        time.sleep(0.5)
    except Exception as e:
        logging.error(f"Error sending embed: {e}")

# ====================================================================
# MAIN RUNNER
# ====================================================================
def run_earnings_daily():
    now_ny = datetime.now(NY_TZ)
    today = now_ny.date()
    today_str = now_ny.strftime("%A, %B %d, %Y")
    logging.info(f"Starting Live Master Earnings Radar for {today_str}...")

    # 1. YESTERDAY'S SCORECARD
    prev_dates = [today - timedelta(days=i) for i in (range(1, 4) if today.weekday() == 0 else range(1, 2))]
    scorecard_items = []
    for d in prev_dates:
        scorecard_items.extend(fetch_yesterday_actuals(d))

    # 2. SCAN 30 DAYS MASTER CALENDAR (US via Nasdaq API)
    logging.info("Pulling 30-day master calendar across US exchanges...")
    upcoming_us_items = []
    for i in range(1, 31):
        target_d = today + timedelta(days=i)
        upcoming_us_items.extend(fetch_nasdaq_calendar_day(target_d))

    # 3. SCAN TSX UNIVERSE (Canada)
    logging.info("Scanning TSX Canadian universe...")
    upcoming_ca_items = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(fetch_tsx_ticker_earnings, TSX_UNIVERSE)
        for r in results:
            if r and r["days_away"] <= 30:
                upcoming_ca_items.append(r)

    all_upcoming = upcoming_us_items + upcoming_ca_items

    # 4. SEGMENT WATCHLIST
    watchlist_set = set(WATCHLIST)
    watchlist_results = [item for item in all_upcoming if item["ticker"] in watchlist_set and item["days_away"] <= 30]
    watchlist_results.sort(key=lambda x: x["date"])

    # 5. SEGMENT BY CAP
    mega_us, mega_ca = [], []
    mid_us, mid_ca = [], []
    small_us, small_ca = [], []

    for item in all_upcoming:
        m_cap = item["market_cap"]
        is_ca = item["badge"] == "🍁"
        days = item["days_away"]

        # Mega-Cap: >= $200B (Next 30 Days)
        if m_cap >= 2e11 and days <= 30:
            (mega_ca if is_ca else mega_us).append(item)
        # Mid-Cap: $2B to $200B (Next 14 Days)
        elif 2e9 <= m_cap < 2e11 and days <= 14:
            (mid_ca if is_ca else mid_us).append(item)
        # Small-Cap: < $2B (Next 14 Days) — filters out microscopic <$20M shells
        elif 2e7 <= m_cap < 2e9 and days <= 14:
            (small_ca if is_ca else small_us).append(item)

    # Sort each tier
    mega_us.sort(key=lambda x: (x["date"], -x["market_cap"]))
    mega_ca.sort(key=lambda x: (x["date"], -x["market_cap"]))
    mid_us.sort(key=lambda x: (x["date"], -x["market_cap"]))
    mid_ca.sort(key=lambda x: (x["date"], -x["market_cap"]))
    small_us.sort(key=lambda x: (x["date"], -x["market_cap"]))
    small_ca.sort(key=lambda x: (x["date"], -x["market_cap"]))

    # =================================================================
    # DISPATCH TO DISCORD
    # =================================================================
    # CARD 1: Yesterday's Scorecard
    if scorecard_items:
        scorecard_txt = ""
        for i, sc in enumerate(scorecard_items[:10], 1):
            scorecard_txt += (
                f"**{i}. {sc['ticker']} — {sc['name']}** {sc['badge']}\n"
                f"• **Reported Date:** `{sc['reported_date']}`\n"
                f"• **EPS Result:** {sc['eps_line']}\n\n"
            )
        dispatch_discord_earnings_embed(
            title="📢 Yesterday's Reported Earnings Scorecard [ACTUALS & SURPRISES]",
            description="*Official results reported in the previous business session across North America.*",
            entries_text=scorecard_txt,
            color=15844367
        )

    # CARD 2: Watchlist
    if watchlist_results:
        wl_txt = "\n".join([format_earnings_entry(i, item) for i, item in enumerate(watchlist_results[:10], 1)])
        dispatch_discord_earnings_embed(
            title="🗓️ Watchlist Earnings Calendar [NEXT 30 DAYS]",
            description=f"*Sorted by nearest report date across your watchlist as of {today_str}.*",
            entries_text=wl_txt,
            color=3066993
        )

    # CARD 3: Mega-Caps
    mega_combined = mega_us + mega_ca
    if mega_combined:
        mega_txt = ""
        if mega_us:
            mega_txt += "**🇺🇸 UNITED STATES MEGA-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_us[:6], 1)]) + "\n\n"
        if mega_ca:
            mega_txt += "**🇨🇦 CANADIAN MEGA-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_ca[:6], 1)])
        dispatch_discord_earnings_embed(
            title="👑 Mega-Cap Earnings Calendar [NEXT 30 DAYS — ≥ $200B]",
            description="*Major market-moving corporate reports over the next month.*",
            entries_text=mega_txt,
            color=10181046
        )

    # CARD 4: Mid-Caps
    mid_combined = mid_us + mid_ca
    if mid_combined:
        mid_txt = ""
        if mid_us:
            mid_txt += "**🇺🇸 UNITED STATES MID-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_us[:6], 1)]) + "\n\n"
        if mid_ca:
            mid_txt += "**🇨🇦 CANADIAN MID-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_ca[:6], 1)])
        dispatch_discord_earnings_embed(
            title="📈 Mid-Cap Earnings Calendar [NEXT 14 DAYS — $2B to $200B]",
            description="*High-growth and institutional leaders reporting in the next two weeks.*",
            entries_text=mid_txt,
            color=3447003
        )

    # CARD 5: Small-Caps
    small_combined = small_us + small_ca
    if small_combined:
        small_txt = ""
        if small_us:
            small_txt += "**🇺🇸 UNITED STATES SMALL-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(small_us[:6], 1)]) + "\n\n"
        if small_ca:
            small_txt += "**🇨🇦 CANADIAN SMALL-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(small_ca[:6], 1)])
        dispatch_discord_earnings_embed(
            title="🌱 Small-Cap Earnings Calendar [NEXT 14 DAYS — High Volatility]",
            description="*Active small-cap runners reporting in the next two weeks.*",
            entries_text=small_txt,
            color=15105570
        )

    logging.info("Daily earnings flow completed successfully.")

if __name__ == "__main__":
    run_earnings_daily()
