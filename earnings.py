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

# Market Cap Reference Lists (guarantees calendar population even if Yahoo calendar API is throttled)
MAJOR_MARKET_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "LLY", "AVGO",
    "JPM", "V", "UNH", "MA", "COST", "HD", "PG", "NFLX", "CRM", "AMD",
    "RY.TO", "TD.TO", "SHOP.TO", "CNR.TO", "CP.TO", "ENB.TO", "BNS.TO", "BMO.TO",
    "PLTR", "ARM", "PANW", "CRWD", "SNOW", "COIN", "MSTR", "UBER", "ABNB", "DASH",
    "RKLB", "SOFI", "SMCI", "IREN", "MARA", "CLSK", "HUT", "ASTS", "IONQ"
]

http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
})

def format_large_number(num):
    if num is None or pd.isna(num):
        return "N/A"
    try:
        num = float(num)
        if num >= 1e12:
            return f"${num / 1e12:.2f}T"
        elif num >= 1e9:
            return f"${num / 1e9:.2f}B"
        elif num >= 1e6:
            return f"${num / 1e6:.1f}M"
        return f"${num:,.0f}"
    except Exception:
        return "N/A"

def get_country_badge(ticker_symbol):
    return "🍁" if ".TO" in ticker_symbol or ".V" in ticker_symbol else "🇺🇸"

def fetch_ticker_earnings(sym):
    """Reliably extracts earnings date and past surprise using yfinance object methods."""
    try:
        t_obj = yf.Ticker(sym, session=http_session)
        today = datetime.now(NY_TZ).date()

        market_cap = 0
        short_name = sym
        try:
            fi = t_obj.fast_info
            market_cap = getattr(fi, "market_cap", 0) or 0
            short_name = getattr(fi, "name", None) or sym
        except Exception:
            pass

        nxt_d = None
        eps_est_str = "Pending"
        time_badge = "After Close 🌙"

        # 1. Try calendar
        try:
            cal = t_obj.calendar
            if cal is not None and not (isinstance(cal, pd.DataFrame) and cal.empty):
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if ed:
                        target = ed[0] if isinstance(ed, list) else ed
                        if isinstance(target, (datetime, date)):
                            nxt_d = target.date() if isinstance(target, datetime) else target
                    if "Earnings High" in cal or "Earnings Average" in cal:
                        avg_val = cal.get("Earnings Average")
                        if avg_val is not None:
                            eps_est_str = f"${float(avg_val):.2f}"
                elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
                    ed = cal.loc["Earnings Date"].iloc[0]
                    if isinstance(ed, (datetime, date)):
                        nxt_d = ed.date() if isinstance(ed, datetime) else ed
        except Exception:
            pass

        # 2. Try earnings_dates
        prev_quarter_str = "N/A"
        try:
            ed_df = t_obj.get_earnings_dates(limit=8)
            if ed_df is not None and not ed_df.empty:
                # Find upcoming date if not found yet
                if nxt_d is None:
                    future_mask = ed_df['Reported EPS'].isna() if 'Reported EPS' in ed_df.columns else pd.Series([True]*len(ed_df), index=ed_df.index)
                    future_df = ed_df[future_mask]
                    if not future_df.empty:
                        nxt_idx = future_df.index[0]
                        nxt_dt = nxt_idx.tz_convert(NY_TZ) if hasattr(nxt_idx, "tz_convert") and nxt_idx.tz else (nxt_idx.to_pydatetime() if hasattr(nxt_idx, "to_pydatetime") else nxt_idx)
                        nxt_d = nxt_dt.date() if isinstance(nxt_dt, datetime) else nxt_dt
                        if "EPS Estimate" in future_df.columns:
                            eps_v = future_df["EPS Estimate"].iloc[0]
                            if pd.notna(eps_v):
                                eps_est_str = f"${float(eps_v):.2f}"

                # Find previous quarter
                past_df = ed_df[ed_df['Reported EPS'].notna()]
                if not past_df.empty:
                    p_dt = past_df.index[0]
                    p_eps = past_df['Reported EPS'].iloc[0]
                    p_surp = past_df['Surprise(%)'].iloc[0] if 'Surprise(%)' in past_df.columns else None
                    p_dt_str = p_dt.strftime("%b %Y") if hasattr(p_dt, "strftime") else "Prev Q"
                    surp_str = ""
                    if pd.notna(p_surp):
                        raw_s = float(p_surp)
                        surp_val = raw_s * 100 if abs(raw_s) <= 1.0 else raw_s
                        tag = "🎯" if surp_val >= 0 else "⚠️"
                        surp_str = f" • Beat by `{surp_val:+.1f}% {tag}`"
                    prev_quarter_str = f"`{p_dt_str}` (EPS: `${float(p_eps):.2f}`{surp_str})"
        except Exception:
            pass

        if nxt_d and nxt_d >= today:
            days_away = (nxt_d - today).days
            return {
                "ticker": sym,
                "name": short_name,
                "badge": get_country_badge(sym),
                "date": nxt_d,
                "days_away": days_away,
                "date_str": nxt_d.strftime("%b %d, %Y"),
                "time_badge": time_badge,
                "status": "Official / Confirmed 🟢",
                "market_cap": market_cap,
                "consensus_est": f"EPS: `{eps_est_str}`",
                "actual_reported": "Pending ⏳",
                "prev_quarter": prev_quarter_str
            }
    except Exception as e:
        logging.warning(f"Error fetching earnings for {sym}: {e}")
    return None

def fetch_yesterday_scorecard(symbols):
    """Pulls recently reported earnings for the given symbol list."""
    today = datetime.now(NY_TZ).date()
    scorecard_items = []
    
    for sym in symbols:
        try:
            t_obj = yf.Ticker(sym, session=http_session)
            ed_df = t_obj.get_earnings_dates(limit=4)
            if ed_df is None or ed_df.empty:
                continue

            past_df = ed_df[ed_df['Reported EPS'].notna()]
            if past_df.empty:
                continue

            last_dt = past_df.index[0]
            last_date = last_dt.date() if isinstance(last_dt, datetime) else last_dt

            # Check if reported within last 1 to 4 days
            if 0 < (today - last_date).days <= 4:
                actual_eps = past_df['Reported EPS'].iloc[0]
                est_eps = past_df['EPS Estimate'].iloc[0] if 'EPS Estimate' in past_df.columns else None
                surp = past_df['Surprise(%)'].iloc[0] if 'Surprise(%)' in past_df.columns else None

                move_str = "N/A"
                try:
                    hist = t_obj.history(period="5d")
                    if len(hist) >= 2:
                        p0 = hist['Close'].iloc[-2]
                        p1 = hist['Close'].iloc[-1]
                        chg = ((p1 - p0) / p0) * 100
                        move_str = f"`{chg:+.2f}%` {'🚀' if chg >= 0 else '🔻'}"
                except Exception:
                    pass

                surp_str = ""
                if pd.notna(surp):
                    raw_s = float(surp)
                    surp_val = raw_s * 100 if abs(raw_s) <= 1.0 else raw_s
                    tag = "🎯" if surp_val >= 0 else "⚠️"
                    surp_str = f" (**Beat by `{surp_val:+.1f}%` {tag}**)" if surp_val >= 0 else f" (**Missed by `{surp_val:+.1f}%` {tag}**)"

                eps_line = f"Actual: `${float(actual_eps):.2f}`"
                if pd.notna(est_eps):
                    eps_line += f" | Estimate: `${float(est_eps):.2f}`{surp_str}"

                name = sym
                try:
                    name = t_obj.fast_info.name or sym
                except Exception:
                    pass

                scorecard_items.append({
                    "ticker": sym,
                    "name": name,
                    "badge": get_country_badge(sym),
                    "reported_date": last_date.strftime("%b %d, %Y"),
                    "time_badge": "Reported",
                    "eps_line": eps_line,
                    "move_str": move_str
                })
        except Exception as e:
            logging.debug(f"Scorecard check skipped for {sym}: {e}")
            continue

    return scorecard_items

def format_earnings_entry(idx, item):
    return (
        f"**{idx}. {item['ticker']} — {item['name']}** {item['badge']}\n"
        f"• **Date & Time:** `{item['date_str']} (In {item['days_away']} Days)` • **{item['time_badge']}**\n"
        f"• **Status:** `{item['status']}`\n"
        f"• **Consensus Estimate:** {item['consensus_est']}\n"
        f"• **Actual Reported:** `{item['actual_reported']}`\n"
        f"• **Previous Quarter:** {item['prev_quarter']}\n"
    )

def dispatch_discord_earnings_embed(title, description, entries_text, color=3447003):
    if not DISCORD_EARNINGS_WEBHOOK_URL:
        logging.error("No Discord Webhook URL configured.")
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
        logging.info(f"Successfully posted: {title}")
        time.sleep(0.5)
    except Exception as e:
        logging.error(f"Error sending earnings embed ({title}): {e}")

def run_earnings_daily():
    now_ny = datetime.now(NY_TZ)
    today_str = now_ny.strftime("%A, %B %d, %Y")
    logging.info(f"Starting Market-Wide Earnings Radar for {today_str}...")

    # Combine Watchlist and Market tickers for scanning
    all_scan_tickers = list(dict.fromkeys(WATCHLIST + MAJOR_MARKET_TICKERS))
    
    # 1. SCAN TICKERS IN PARALLEL
    logging.info(f"Scanning {len(all_scan_tickers)} tickers for upcoming earnings...")
    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_ticker_earnings, sym): sym for sym in all_scan_tickers}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                all_results.append(res)

    logging.info(f"Found {len(all_results)} upcoming earnings events.")

    # 2. SCORECARD (Recently Reported)
    logging.info("Checking for recently reported earnings...")
    scorecard_items = fetch_yesterday_scorecard(all_scan_tickers)

    # 3. SEGMENT WATCHLIST
    watchlist_set = set(WATCHLIST)
    watchlist_results = [r for r in all_results if r["ticker"] in watchlist_set and r["days_away"] <= 30]
    watchlist_results.sort(key=lambda x: x["date"])

    # 4. SEGMENT MEGA, MID, SMALL CAPS
    mega_us, mega_ca = [], []
    mid_us, mid_ca = [], []
    small_us, small_ca = [], []

    for item in all_results:
        m_cap = item["market_cap"]
        is_ca = "🍁" in item["badge"]
        days = item["days_away"]

        if m_cap >= 2e11 and days <= 30:
            (mega_ca if is_ca else mega_us).append(item)
        elif 2e9 <= m_cap < 2e11 and days <= 14:
            (mid_ca if is_ca else mid_us).append(item)
        elif m_cap < 2e9 and days <= 14:
            (small_ca if is_ca else small_us).append(item)

    mega_us.sort(key=lambda x: x["date"])
    mega_ca.sort(key=lambda x: x["date"])
    mid_us.sort(key=lambda x: x["date"])
    mid_ca.sort(key=lambda x: x["date"])
    small_us.sort(key=lambda x: x["date"])
    small_ca.sort(key=lambda x: x["date"])

    # 5. DISPATCH EMBEDS
    if scorecard_items:
        scorecard_txt = ""
        for i, sc in enumerate(scorecard_items[:10], 1):
            scorecard_txt += (
                f"**{i}. {sc['ticker']} — {sc['name']}** {sc['badge']}\n"
                f"• **Reported Date:** `{sc['reported_date']}`\n"
                f"• **EPS Result:** {sc['eps_line']}\n"
                f"• **Market Reaction:** Stock Move: {sc['move_str']}\n\n"
            )
        dispatch_discord_earnings_embed(
            title="📢 Recent Earnings Scorecard [ACTUALS & BEATS/MISSES]",
            description="*Official results and stock price reactions from recent business days.*",
            entries_text=scorecard_txt,
            color=15844367
        )

    if watchlist_results:
        wl_txt = "\n".join([format_earnings_entry(i, item) for i, item in enumerate(watchlist_results[:10], 1)])
        dispatch_discord_earnings_embed(
            title="🗓️ Watchlist Earnings Calendar [NEXT 30 DAYS]",
            description=f"*Sorted by nearest report date across your watchlist as of {today_str}.*",
            entries_text=wl_txt,
            color=3066993
        )
    else:
        logging.info("No upcoming watchlist earnings found in the next 30 days.")

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

    mid_combined = mid_us + mid_ca
    if mid_combined:
        mid_txt = ""
        if mid_us:
            mid_txt += "**🇺🇸 UNITED STATES MID-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_us[:6], 1)]) + "\n\n"
        if mid_ca:
            mid_txt += "**🇨🇦 CANADIAN MID-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_ca[:6], 1)])
        dispatch_discord_earnings_embed(
            title="📈 Growth & Mid-Cap Earnings Calendar [NEXT 14 DAYS]",
            description="*High-momentum corporate reports in the next two weeks.*",
            entries_text=mid_txt,
            color=3447003
        )

    logging.info("Earnings Intelligence run completed.")

if __name__ == "__main__":
    run_earnings_daily()
