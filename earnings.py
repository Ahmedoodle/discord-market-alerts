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

# Complete TSX 60 & Canadian Mega/Mid-Cap Coverage (Ensures zero missed Canadian reports)
TSX_UNIVERSE = [
    # Big Banks & Financials
    "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "NA.TO", "MFC.TO", "SLF.TO", "POW.TO", "IFC.TO", "GWO.TO",
    # Energy & Pipelines
    "ENB.TO", "CNQ.TO", "SU.TO", "TRP.TO", "CVE.TO", "IMO.TO", "TOU.TO", "ARX.TO", "PPL.TO", "KEY.TO",
    # Tech & Communications
    "SHOP.TO", "CSU.TO", "TRI.TO", "OTEX.TO", "GIB-A.TO", "BCE.TO", "T.TO", "RCI-B.TO", "QBR-B.TO",
    # Industrials & Rails
    "CNR.TO", "CP.TO", "WCN.TO", "TFII.TO", "CAE.TO", "TIH.TO", "STN.TO", "ATS.TO",
    # Materials & Mining
    "ABX.TO", "AEM.TO", "FNV.TO", "WPM.TO", "NTR.TO", "TECK-B.TO", "FM.TO", "IVN.TO", "LUN.TO", "K.TO",
    # Consumer & Retail
    "ATD.TO", "L.TO", "DOL.TO", "MG.TO", "WN.TO", "QSR.TO", "MRU.TO", "EMP-A.TO", "CTC-A.TO",
    # Utilities & Real Estate
    "FTS.TO", "EMA.TO", "H.TO", "BAM.TO", "BN.TO", "CAR-UN.TO", "GRT-UN.TO", "REI-UN.TO"
]

nasdaq_session = requests.Session()
nasdaq_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/"
})

def clean_currency(val):
    """Ensures consistent single dollar sign formatting like $4.92."""
    if val is None or str(val).strip() in ["", "N/A", "None"]:
        return "N/A"
    s = str(val).replace("$", "").strip()
    try:
        f = float(s)
        return f"${f:.2f}"
    except Exception:
        return f"${s}"

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
# US MARKET CALENDAR & SCORECARD (NASDAQ API)
# ====================================================================
def fetch_nasdaq_calendar_day(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date_str}"
    items = []
    try:
        res = nasdaq_session.get(url, timeout=10)
        if res.status_code == 200:
            rows = res.json().get("data", {}).get("rows", []) or []
            for r in rows:
                sym = r.get("symbol", "").strip()
                if not sym or "^" in sym or "/" in sym or "." in sym:
                    continue
                
                mcap = parse_market_cap_str(r.get("marketCap", "0"))
                # Filter to only keep Mid-Cap ($2B+) and Mega-Cap ($200B+)
                if mcap < 2e9:
                    continue

                time_code = r.get("time", "time-not-supplied").lower()
                time_badge = "Before Open 🌅" if "pre" in time_code or "bmo" in time_code else "After Close 🌙"
                eps_forecast = clean_currency(r.get("epsForecast"))

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
                    "actual_reported": "Pending ⏳"
                })
    except Exception as e:
        logging.warning(f"Nasdaq calendar fetch error for {date_str}: {e}")
    return items

def fetch_us_yesterday_actuals(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date_str}"
    scorecard = []
    try:
        res = nasdaq_session.get(url, timeout=10)
        if res.status_code == 200:
            rows = res.json().get("data", {}).get("rows", []) or []
            for r in rows:
                sym = r.get("symbol", "").strip()
                eps_actual_raw = r.get("eps")
                if not sym or eps_actual_raw is None or str(eps_actual_raw).strip() in ["", "N/A"]:
                    continue
                
                mcap = parse_market_cap_str(r.get("marketCap", "0"))
                if mcap < 2e9:
                    continue

                eps_forecast_raw = r.get("epsForecast")
                act_str = clean_currency(eps_actual_raw)
                est_str = clean_currency(eps_forecast_raw)
                
                surp_str = ""
                try:
                    act_f = float(str(eps_actual_raw).replace("$", ""))
                    est_f = float(str(eps_forecast_raw).replace("$", ""))
                    diff = act_f - est_f
                    tag = "🎯" if diff >= 0 else "⚠️"
                    surp_str = f" (**{'Beat' if diff >= 0 else 'Missed'} by `${abs(diff):.2f}` {tag}**)"
                except Exception:
                    pass

                scorecard.append({
                    "ticker": sym,
                    "name": r.get("name", sym),
                    "badge": "🇺🇸",
                    "reported_date": target_date.strftime("%b %d, %Y"),
                    "market_cap": mcap,
                    "eps_line": f"Actual: `{act_str}` | Estimate: `{est_str}`{surp_str}"
                })
    except Exception as e:
        logging.warning(f"Error fetching US yesterday actuals: {e}")
    return scorecard

# ====================================================================
# CANADIAN (TSX) CALENDAR & SCORECARD ENGINE
# ====================================================================
def scan_single_tsx_ticker(sym, check_dates):
    """Fetches both upcoming dates and recently reported results for a TSX stock."""
    upcoming_item = None
    scorecard_item = None
    try:
        t_obj = yf.Ticker(sym)
        today = datetime.now(NY_TZ).date()
        m_cap = getattr(t_obj.fast_info, "market_cap", 0) or 0
        name = getattr(t_obj.fast_info, "name", None) or sym

        # 1. Check Upcoming Calendar
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
                    eps_est = clean_currency(avg_val)
            elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"].iloc[0]
                nxt_d = ed.date() if isinstance(ed, datetime) else ed

        if nxt_d and nxt_d >= today:
            days_away = (nxt_d - today).days
            if days_away <= 30:
                upcoming_item = {
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
                    "actual_reported": "Pending ⏳"
                }

        # 2. Check Yesterday's Scorecard (Recent Reports)
        ed_df = t_obj.get_earnings_dates(limit=4)
        if ed_df is not None and not ed_df.empty:
            past_df = ed_df[ed_df['Reported EPS'].notna()]
            if not past_df.empty:
                last_dt = past_df.index[0]
                last_date = last_dt.date() if isinstance(last_dt, datetime) else last_dt
                if last_date in check_dates:
                    actual_eps = past_df['Reported EPS'].iloc[0]
                    est_eps = past_df['EPS Estimate'].iloc[0] if 'EPS Estimate' in past_df.columns else None
                    surp = past_df['Surprise(%)'].iloc[0] if 'Surprise(%)' in past_df.columns else None

                    surp_str = ""
                    if pd.notna(surp):
                        raw_s = float(surp)
                        surp_val = raw_s * 100 if abs(raw_s) <= 1.0 else raw_s
                        tag = "🎯" if surp_val >= 0 else "⚠️"
                        surp_str = f" (**Beat by `{surp_val:+.1f}%` {tag}**)" if surp_val >= 0 else f" (**Missed by `{surp_val:+.1f}%` {tag}**)"

                    act_str = clean_currency(actual_eps)
                    est_str = clean_currency(est_eps)
                    eps_line = f"Actual: `{act_str}`" + (f" | Estimate: `{est_str}`{surp_str}" if est_eps is not None else "")

                    scorecard_item = {
                        "ticker": sym,
                        "name": name,
                        "badge": "🍁",
                        "reported_date": last_date.strftime("%b %d, %Y"),
                        "market_cap": m_cap,
                        "eps_line": eps_line
                    }
    except Exception:
        pass
    return upcoming_item, scorecard_item

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
    logging.info(f"Starting Earnings Intelligence Run for {today_str}...")

    prev_dates = [today - timedelta(days=i) for i in (range(1, 4) if today.weekday() == 0 else range(1, 2))]

    # 1. FETCH US SCORECARD
    logging.info("Pulling US reported earnings scorecard...")
    scorecard_items = []
    for d in prev_dates:
        scorecard_items.extend(fetch_us_yesterday_actuals(d))

    # 2. FETCH US UPCOMING CALENDAR (Next 30 Days)
    logging.info("Pulling 30-day US calendar...")
    upcoming_us_items = []
    for i in range(1, 31):
        target_d = today + timedelta(days=i)
        upcoming_us_items.extend(fetch_nasdaq_calendar_day(target_d))

    # 3. SCAN TSX UNIVERSE (Both Scorecard + Upcoming)
    logging.info("Scanning full Canadian TSX Universe...")
    upcoming_ca_items = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(scan_single_tsx_ticker, sym, prev_dates) for sym in TSX_UNIVERSE]
        for f in concurrent.futures.as_completed(futures):
            up, sc = f.result()
            if up:
                upcoming_ca_items.append(up)
            if sc:
                scorecard_items.append(sc)

    # Sort scorecard by market cap (highest importance first)
    scorecard_items.sort(key=lambda x: x["market_cap"], reverse=True)

    # 4. SEGMENT WATCHLIST
    all_upcoming = upcoming_us_items + upcoming_ca_items
    watchlist_set = set(WATCHLIST)
    watchlist_results = [item for item in all_upcoming if item["ticker"] in watchlist_set and item["days_away"] <= 30]
    watchlist_results.sort(key=lambda x: x["date"])

    # 5. SEGMENT MEGA AND MID CAPS ONLY
    mega_us, mega_ca = [], []
    mid_us, mid_ca = [], []

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

    # Sort each tier
    mega_us.sort(key=lambda x: (x["date"], -x["market_cap"]))
    mega_ca.sort(key=lambda x: (x["date"], -x["market_cap"]))
    mid_us.sort(key=lambda x: (x["date"], -x["market_cap"]))
    mid_ca.sort(key=lambda x: (x["date"], -x["market_cap"]))

    # =================================================================
    # DISPATCH 4 CARDS TO DISCORD
    # =================================================================
    # CARD 1: Unified Scorecard (US + TSX)
    if scorecard_items:
        scorecard_txt = ""
        for i, sc in enumerate(scorecard_items[:12], 1):
            scorecard_txt += (
                f"**{i}. {sc['ticker']} — {sc['name']}** {sc['badge']}\n"
                f"• **Reported Date:** `{sc['reported_date']}`\n"
                f"• **EPS Result:** {sc['eps_line']}\n\n"
            )
        dispatch_discord_earnings_embed(
            title="📢 Yesterday's Reported Earnings Scorecard [ACTUALS & SURPRISES]",
            description="*Official results reported in previous session across US and Canadian (TSX) markets.*",
            entries_text=scorecard_txt,
            color=15844367  # Gold
        )

    # CARD 2: Watchlist
    if watchlist_results:
        wl_txt = "\n".join([format_earnings_entry(i, item) for i, item in enumerate(watchlist_results[:10], 1)])
        dispatch_discord_earnings_embed(
            title="🗓️ Watchlist Earnings Calendar [NEXT 30 DAYS]",
            description=f"*Sorted by nearest report date across your watchlist as of {today_str}.*",
            entries_text=wl_txt,
            color=3066993  # Green
        )

    # CARD 3: Mega-Caps
    mega_combined = mega_us + mega_ca
    if mega_combined:
        mega_txt = ""
        if mega_us:
            mega_txt += "**🇺🇸 UNITED STATES MEGA-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_us[:8], 1)]) + "\n\n"
        if mega_ca:
            mega_txt += "**🇨🇦 CANADIAN MEGA-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mega_ca[:8], 1)])
        dispatch_discord_earnings_embed(
            title="👑 Mega-Cap Earnings Calendar [NEXT 30 DAYS — ≥ $200B]",
            description="*Major market-moving corporate reports over the next month.*",
            entries_text=mega_txt,
            color=10181046  # Purple
        )

    # CARD 4: Mid-Caps
    mid_combined = mid_us + mid_ca
    if mid_combined:
        mid_txt = ""
        if mid_us:
            mid_txt += "**🇺🇸 UNITED STATES MID-CAPS:**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_us[:8], 1)]) + "\n\n"
        if mid_ca:
            mid_txt += "**🇨🇦 CANADIAN MID-CAPS (TSX 🍁):**\n" + "\n".join([format_earnings_entry(i, item) for i, item in enumerate(mid_ca[:8], 1)])
        dispatch_discord_earnings_embed(
            title="📈 Mid-Cap Earnings Calendar [NEXT 14 DAYS — $2B to $200B]",
            description="*Institutional and momentum leaders reporting in the next two weeks.*",
            entries_text=mid_txt,
            color=3447003  # Blue
        )

    logging.info("Earnings Intelligence flow completed successfully.")

if __name__ == "__main__":
    run_earnings_daily()
